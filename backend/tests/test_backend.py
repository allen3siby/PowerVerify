import os
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import init_db, record_decision, get_all_decisions, get_connection
from backend.app.data_pipeline import (
    load_and_validate_raw_data,
    calculate_rolling_features,
    fit_isolation_forest,
    run_pipeline,
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()

def test_load_and_validate_raw_ceew_data():
    df, summary = load_and_validate_raw_data()
    assert len(df) == 44610
    assert summary["total_meters"] == 84
    assert "Bareilly" in summary["districts"]
    assert "Mathura" in summary["districts"]
    assert summary["measurement_unit"] == "kWh (electricity consumption)"
    assert summary["quarantined_readings"] == 0
    assert summary["duplicate_readings"] == 0
    assert summary["start_date"] == "2019-05-01"
    assert summary["end_date"] == "2021-10-31"

def test_rolling_features_and_historical_mad_thresholds():
    df, _ = load_and_validate_raw_data()
    # Test on a single meter to verify calculations
    br02 = df[df["meter_id"] == "BR02"].copy()
    featured = calculate_rolling_features(br02)

    assert "trailing_median" in featured.columns
    assert "trailing_mad" in featured.columns
    assert "expected_upper" in featured.columns
    assert "expected_lower" in featured.columns
    assert "robust_z" in featured.columns
    assert "insufficient_history" in featured.columns

    # Check chronological ordering
    assert featured["date_parsed"].is_monotonic_increasing

    # Check expected bounds logic: upper >= lower >= 0
    assert (featured["expected_upper"] >= featured["expected_lower"]).all()
    assert (featured["expected_lower"] >= 0).all()

    # First few days have insufficient history
    assert featured["insufficient_history"].iloc[0] == True

def test_isolation_forest_model_execution():
    df, _ = load_and_validate_raw_data()
    sample_df = df[df["meter_id"].isin(["BR02", "MH01"])].copy()
    featured = calculate_rolling_features(sample_df)
    analyzed, meta = fit_isolation_forest(featured, contamination=0.04, n_estimators=50)

    assert meta["model_name"] == "Isolation Forest (scikit-learn)"
    assert meta["contamination"] == 0.04
    assert meta["total_anomalies"] > 0
    assert "anomaly_direction" in analyzed.columns
    assert "reason" in analyzed.columns

    # High anomaly reason check
    high_anoms = analyzed[analyzed["anomaly_direction"] == "high"]
    if not high_anoms.empty:
        assert "exceeded historical upper boundary" in high_anoms.iloc[0]["reason"]

def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "PowerVerify"

def test_dataset_summary_endpoint():
    res = client.get("/api/dataset/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_meters"] == 84
    assert data["valid_readings"] == 44610
    assert data["measurement_unit"] == "kWh (electricity consumption)"

def test_dashboard_stats_endpoint():
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["total_meters"] == 84
    assert data["total_readings"] == 44610
    assert data["flagged_anomalies"] > 0
    assert data["flagged_meters"] > 0
    assert data["pending_reviews"] >= 0

def test_dashboard_chart_endpoints():
    # Overview aggregate chart
    res = client.get("/api/dashboard/chart?time_range=30d")
    assert res.status_code == 200
    data = res.json()
    assert len(data["points"]) > 0
    assert "kwh" in data["points"][0]

    # Specific meter chart
    res_meter = client.get("/api/dashboard/chart?time_range=all&meter_id=BR02")
    assert res_meter.status_code == 200
    data_meter = res_meter.json()
    assert len(data_meter["points"]) > 0
    assert data_meter["points"][0]["meter_id"] == "BR02"

def test_meters_list_and_history():
    res = client.get("/api/meters")
    assert res.status_code == 200
    meters = res.json()
    assert len(meters) == 84
    meter_ids = [m["meter_id"] for m in meters]
    assert "BR02" in meter_ids
    assert "MH01" in meter_ids

    # History endpoint
    res_hist = client.get("/api/meters/BR02/history")
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert hist["meter_id"] == "BR02"
    assert len(hist["points"]) > 0

    # 404 for invalid meter
    res_404 = client.get("/api/meters/NONEXISTENT_999/history")
    assert res_404.status_code == 404

def test_review_workflow_and_persistence():
    # Find an actual flagged anomaly observation ID
    q_res = client.get("/api/review-queue?page=1&page_size=5")
    assert q_res.status_code == 200
    items = q_res.json()["items"]
    assert len(items) > 0
    test_obs = items[0]
    obs_id = test_obs["observation_id"]

    # Action 1: Mark for Field Visit
    rev1 = client.post("/api/reviews", json={
        "observation_id": obs_id,
        "decision": "Mark for Field Visit",
        "notes": "Verified sudden 4x spike. Dispatching technician."
    })
    assert rev1.status_code == 200
    assert rev1.json()["new_status"] == "Mark for Field Visit"

    # Verify status changed in review queue
    q_check = client.get(f"/api/review-queue?search={obs_id}")
    assert q_check.status_code == 200
    assert q_check.json()["items"][0]["review_status"] == "Mark for Field Visit"

    # Action 2: High Usage Authorized
    rev2 = client.post("/api/reviews", json={
        "observation_id": obs_id,
        "decision": "High Usage Authorized",
        "notes": "Customer confirmed wedding celebration equipment."
    })
    assert rev2.status_code == 200
    assert rev2.json()["previous_status"] == "Mark for Field Visit"
    assert rev2.json()["new_status"] == "High Usage Authorized"

    # Action 3: Acknowledge / No Further Action
    rev3 = client.post("/api/reviews", json={
        "observation_id": obs_id,
        "decision": "Acknowledge / No Further Action",
        "notes": "Case closed."
    })
    assert rev3.status_code == 200
    assert rev3.json()["new_status"] == "Acknowledge / No Further Action"

    # Check audit history
    hist_res = client.get(f"/api/reviews/{obs_id}/history")
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) >= 3

    # Restore seed state for test observation to maintain 5 seed reviews
    with get_connection() as conn:
        conn.execute("UPDATE observation_status SET current_status = ? WHERE observation_id = ?", ('Mark for Field Visit', obs_id))
        conn.commit()

def test_settings_reanalyze():
    try:
        res = client.post("/api/settings/reanalyze", json={
            "contamination": 0.02,
            "n_estimators": 100
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] == True
        assert data["model_metadata"]["contamination"] == 0.02
    finally:
        client.post("/api/settings/reanalyze", json={
            "contamination": 0.03,
            "n_estimators": 150
        })

def test_csv_and_report_exports():
    res_flagged = client.get("/api/export/csv?flagged_only=true")
    assert res_flagged.status_code == 200
    assert "observation_id,meter_id" in res_flagged.text

    res_decisions = client.get("/api/export/reviews/csv")
    assert res_decisions.status_code == 200
    assert "decision" in res_decisions.text

    res_report = client.get("/api/export/report")
    assert res_report.status_code == 200
    assert "PowerVerify" in res_report.text
    assert "Council on Energy, Environment and Water" in res_report.text

def test_synthetic_high_and_low_anomalies():
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta

    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(50)]
    kwhs = [10.0] * 50
    # Day 40: High spike (6x baseline)
    kwhs[40] = 60.0
    # Day 45: Extreme low drop
    kwhs[45] = 0.1

    test_df = pd.DataFrame({
        "meter_id": ["TEST01"] * 50,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": kwhs,
        "district": ["Bareilly"] * 50,
    })

    featured = calculate_rolling_features(test_df)
    analyzed, meta = fit_isolation_forest(featured, contamination=0.04, n_estimators=50)

    # 1. Synthetic High Anomaly
    high_row = analyzed.iloc[40]
    assert high_row["is_anomaly"] == True
    assert high_row["anomaly_direction"] == "high"
    assert "exceeded historical upper boundary" in high_row["reason"] or "Isolation Forest high anomaly" in high_row["reason"]

    # 2. Synthetic Low Anomaly
    low_row = analyzed.iloc[45]
    assert low_row["is_anomaly"] == True
    assert low_row["anomaly_direction"] == "low"
    assert "dropped significantly below expected lower boundary" in low_row["reason"] or "Isolation Forest low anomaly" in low_row["reason"]

    # 3. Normal Observation
    normal_row = analyzed.iloc[25]
    assert normal_row["is_anomaly"] == False
    assert normal_row["anomaly_direction"] == "normal"
    assert "is within expected historical bounds" in normal_row["reason"]

def test_empty_anomaly_period():
    import pandas as pd
    from datetime import datetime, timedelta

    # 20 consecutive identical normal days with no variance
    dates = [datetime(2021, 6, 1) + timedelta(days=i) for i in range(25)]
    normal_df = pd.DataFrame({
        "meter_id": ["TEST_FLAT"] * 25,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": [12.0] * 25,
        "district": ["Mathura"] * 25,
    })
    featured = calculate_rolling_features(normal_df)
    analyzed, _ = fit_isolation_forest(featured, contamination=0.01, n_estimators=50)

    # In a perfectly flat series without deviations, middle observations are not outliers
    mid_period = analyzed.iloc[10:20]
    assert (mid_period["is_anomaly"] == False).all()
    assert (mid_period["anomaly_direction"] == "normal").all()

def test_meter_and_date_filtering():
    res_30d = client.get("/api/dashboard/chart?time_range=30d&meter_id=BR02")
    assert res_30d.status_code == 200
    data_30d = res_30d.json()
    assert len(data_30d["points"]) <= 31
    for pt in data_30d["points"]:
        assert pt["meter_id"] == "BR02"

    res_all = client.get("/api/dashboard/chart?time_range=all&meter_id=BR02")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert len(data_all["points"]) > len(data_30d["points"])

def test_consistency_between_plotted_markers_and_anomaly_records():
    # Verify aggregate overview chart markers
    res_sys = client.get("/api/dashboard/chart?time_range=all")
    assert res_sys.status_code == 200
    sys_points = res_sys.json()["points"]

    for pt in sys_points:
        assert isinstance(pt["kwh"], (int, float))
        assert pt["expected_upper"] >= pt["expected_lower"] >= 0
        if pt["is_anomaly"]:
            assert pt["anomaly_direction"] in ["high", "low"]
            assert len(pt["reason"]) > 0

    # Verify meter-level chart markers
    res_meter = client.get("/api/dashboard/chart?time_range=all&meter_id=BR02")
    assert res_meter.status_code == 200
    meter_points = res_meter.json()["points"]

    for pt in meter_points:
        assert pt["meter_id"] == "BR02"
        assert isinstance(pt["kwh"], (int, float))
        assert pt["expected_upper"] >= pt["expected_lower"] >= 0
        if pt["is_anomaly"]:
            assert pt["anomaly_direction"] in ["high", "low"]
            assert len(pt["reason"]) > 0
            assert pt["review_status"] in [
                "Pending Review",
                "Mark for Field Visit",
                "High Usage Authorized",
                "Acknowledge / No Further Action",
            ]

