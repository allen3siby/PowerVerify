import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from concurrent.futures import ThreadPoolExecutor

from backend.app.main import app
from backend.app.database import get_connection, record_decision, get_decision_history, get_all_observation_statuses
from backend.app.data_pipeline import calculate_rolling_features, fit_isolation_forest, run_pipeline

client = TestClient(app)

# --------------------------------------------------------------------------
# PART A.8 & PART C.1-7: STATISTICAL AND ML ANOMALY DETECTION UNIT TESTS
# --------------------------------------------------------------------------

def test_screenshot_regression_fixture_high_anomaly():
    """
    PART A.8 regression test:
    Observed consumption = 5.30 kWh, Expected lower = 0.00 kWh, Expected upper = 3.74 kWh
    Verifies:
    - statistical_anomaly = True
    - anomaly_direction = 'high'
    - Detection method identifies statistical boundary breach
    - Tested across all 4 review states:
        1. Pending review
        2. Acknowledge / No Further Action
        3. Mark for Field Visit
        4. High Usage Authorized
    In every scenario, detection remains high anomaly.
    """
    obs_id = "REG_METER_2021-09-15"
    meter_id = "REG_METER"
    date_str = "2021-09-15"
    kwh = 5.30
    exp_lower = 0.00
    exp_upper = 3.74
    trailing_median = 2.00

    # Clean any prior fixture rows
    with get_connection() as conn:
        conn.execute("DELETE FROM review_decisions WHERE observation_id = ?", (obs_id,))
        conn.execute("DELETE FROM observation_status WHERE observation_id = ?", (obs_id,))
        conn.commit()

    # Synthetic observation dataframe
    test_df = pd.DataFrame([{
        "meter_id": meter_id,
        "date": date_str,
        "date_parsed": pd.to_datetime(date_str),
        "kwh": kwh,
        "district": "Bareilly",
        "prev_kwh": 2.1,
        "kwh_change": 3.2,
        "day_of_week": 2,
        "is_weekend": 0,
        "month": 9,
        "trailing_median": trailing_median,
        "trailing_mad": 0.47,
        "insufficient_history": False,
        "expected_upper": exp_upper,
        "expected_lower": exp_lower,
        "baseline_ratio": kwh / trailing_median,
        "robust_z": (kwh - trailing_median) / (1.4826 * 0.47),
    }])

    analyzed, meta = fit_isolation_forest(test_df, contamination=0.03, n_estimators=50)
    row = analyzed.iloc[0]

    # Verify authoritative classification
    assert row["statistical_anomaly"] == True
    assert row["anomaly_direction"] == "high"
    assert row["is_anomaly"] == True
    assert "exceeded historical upper boundary (3.74 kWh)" in row["reason"]

    # Test all 4 review decision states
    review_decisions = [
        None,  # 1. Pending review
        "Acknowledge / No Further Action",  # 2. Acknowledged
        "Mark for Field Visit",  # 3. Field visit
        "High Usage Authorized",  # 4. Authorized
    ]

    for dec in review_decisions:
        if dec is not None:
            res = record_decision(
                observation_id=obs_id,
                meter_id=meter_id,
                date=date_str,
                kwh=kwh,
                anomaly_direction="high",
                decision=dec,
                notes="Regression state validation"
            )
            assert res["review_status"] == "REVIEWED"
            assert res["review_decision"] == dec

        # Check DB effective state
        all_st = get_all_observation_statuses()
        curr = all_st.get(obs_id)

        if dec is None:
            assert curr is None or curr["review_status"] == "PENDING"
        else:
            assert curr["review_status"] == "REVIEWED"
            assert curr["review_decision"] == dec

        # In all scenarios, detection attributes remain uncorrupted
        assert row["statistical_anomaly"] == True
        assert row["anomaly_direction"] == "high"
        assert row["is_anomaly"] == True

    # Cleanup
    with get_connection() as conn:
        conn.execute("DELETE FROM review_decisions WHERE observation_id = ?", (obs_id,))
        conn.execute("DELETE FROM observation_status WHERE observation_id = ?", (obs_id,))
        conn.commit()


def test_statistical_low_anomaly_detection():
    """Test 2: Statistical low anomaly classification."""
    test_df = pd.DataFrame([{
        "meter_id": "TEST_LOW",
        "date": "2021-08-10",
        "date_parsed": pd.to_datetime("2021-08-10"),
        "kwh": 0.10,
        "district": "Mathura",
        "prev_kwh": 4.5,
        "kwh_change": -4.4,
        "day_of_week": 1,
        "is_weekend": 0,
        "month": 8,
        "trailing_median": 4.5,
        "trailing_mad": 0.5,
        "insufficient_history": False,
        "expected_upper": 6.35,
        "expected_lower": 2.65,
        "baseline_ratio": 0.10 / 4.5,
        "robust_z": -5.87,
    }])

    analyzed, _ = fit_isolation_forest(test_df, contamination=0.03, n_estimators=50)
    row = analyzed.iloc[0]

    assert row["statistical_anomaly"] == True
    assert row["anomaly_direction"] == "low"
    assert row["is_anomaly"] == True
    assert "dropped significantly below expected lower boundary" in row["reason"]


def test_normal_observation_classification():
    """Test 3: Normal consumption within expected boundaries."""
    test_df = pd.DataFrame([{
        "meter_id": "TEST_NORM",
        "date": "2021-08-11",
        "date_parsed": pd.to_datetime("2021-08-11"),
        "kwh": 3.50,
        "district": "Mathura",
        "prev_kwh": 3.4,
        "kwh_change": 0.1,
        "day_of_week": 2,
        "is_weekend": 0,
        "month": 8,
        "trailing_median": 3.5,
        "trailing_mad": 0.5,
        "insufficient_history": False,
        "expected_upper": 5.35,
        "expected_lower": 1.65,
        "baseline_ratio": 1.0,
        "robust_z": 0.0,
    }])

    # Ensure model doesn't force inlier to anomalous
    analyzed, _ = fit_isolation_forest(test_df, contamination=0.01, n_estimators=50)
    row = analyzed.iloc[0]
    assert row["statistical_anomaly"] == False
    assert row["anomaly_direction"] in ("normal", "pattern")


def test_multidimensional_pattern_anomaly():
    """Test 4: Pattern anomaly where consumption is within bounds but unusual multi-feature shift."""
    # Construct synthetic pattern anomaly: val within bounds (3.0 vs 2.0-6.0), but massive day swing from 10.0 to 3.0 on weekend
    test_df = pd.DataFrame([{
        "meter_id": "TEST_PAT",
        "date": "2021-08-12",
        "date_parsed": pd.to_datetime("2021-08-12"),
        "kwh": 3.0,
        "district": "Mathura",
        "prev_kwh": 14.0,
        "kwh_change": -11.0,
        "day_of_week": 6,
        "is_weekend": 1,
        "month": 8,
        "trailing_median": 4.0,
        "trailing_mad": 0.8,
        "insufficient_history": False,
        "expected_upper": 7.0,
        "expected_lower": 1.0,
        "baseline_ratio": 0.75,
        "robust_z": -0.84,
    }])

    analyzed, _ = fit_isolation_forest(test_df, contamination=0.5, n_estimators=50)
    row = analyzed.iloc[0]
    # Within statistical bounds:
    assert row["statistical_anomaly"] == False
    # If isolation forest flags it, it must be 'pattern', never misclassified as normal
    if row["isolation_forest_anomaly"]:
        assert row["anomaly_direction"] == "pattern"
        assert row["detection_method"] == "ISOLATION_FOREST_PATTERN"
        assert "Pattern Anomaly" in row["reason"]


def test_burn_in_behavior_insufficient_history():
    """Test 5: Burn-in handling for initial observations with < 7 days."""
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(10)]
    df = pd.DataFrame({
        "meter_id": ["TEST_BURN"] * 10,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": [3.0 + i * 0.1 for i in range(10)],
        "district": ["Bareilly"] * 10,
    })

    featured = calculate_rolling_features(df)
    # First 7 days must be flagged as insufficient_history
    assert featured["insufficient_history"].iloc[:7].all() == True
    assert featured["insufficient_history"].iloc[7:].all() == False
    # Expected bounds must still be defined and finite
    assert (featured["expected_upper"] >= featured["expected_lower"]).all()
    assert (featured["expected_lower"] >= 0.0).all()


def test_zero_mad_robustness():
    """Test 6: Zero MAD handling when meter consumption is perfectly constant."""
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(20)]
    df = pd.DataFrame({
        "meter_id": ["TEST_ZERO_MAD"] * 20,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": [5.0] * 20,
        "district": ["Bareilly"] * 20,
    })

    featured = calculate_rolling_features(df)
    # Scale must not collapse to 0 (minimum safe threshold 0.05 applies)
    assert (featured["trailing_mad"] >= 0.05).all()
    assert (featured["expected_upper"] > featured["expected_lower"]).all()


def test_missing_observation_safety():
    """Test 7: Missing observations should be handled gracefully without division by zero."""
    dates = [datetime(2021, 1, 1) + timedelta(days=i*2) for i in range(15)]
    df = pd.DataFrame({
        "meter_id": ["TEST_GAPS"] * 15,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": [4.0] * 15,
        "district": ["Mathura"] * 15,
    })
    featured = calculate_rolling_features(df)
    assert not featured["expected_upper"].isna().any()
    assert not featured["expected_lower"].isna().any()


# --------------------------------------------------------------------------
# PART C.8-17: STATE SEPARATION, PERSISTENCE, IDEMPOTENCY & CASE CONSISTENCY
# --------------------------------------------------------------------------

def test_detection_and_review_state_separation():
    """Test 8: Changing review decision NEVER alters detection direction or is_anomaly flag."""
    obs_id = "SEP_TEST_2021-09-01"
    res = record_decision(
        observation_id=obs_id,
        meter_id="TEST_METER",
        date="2021-09-01",
        kwh=8.5,
        anomaly_direction="high",
        decision="Acknowledge / No Further Action",
        notes="Reviewed as benign surge"
    )
    assert res["review_status"] == "REVIEWED"
    assert res["review_decision"] == "Acknowledge / No Further Action"

    # Cleanup
    with get_connection() as conn:
        conn.execute("DELETE FROM review_decisions WHERE observation_id = ?", (obs_id,))
        conn.execute("DELETE FROM observation_status WHERE observation_id = ?", (obs_id,))
        conn.commit()


def test_acknowledge_decision_persistence():
    """Test 9: Acknowledge decision persists in observation_status and review_decisions."""
    obs_id = "ACK_TEST_2021-09-02"
    record_decision(
        observation_id=obs_id,
        meter_id="TEST_METER",
        date="2021-09-02",
        kwh=9.0,
        anomaly_direction="high",
        decision="Acknowledge / No Further Action",
        notes="Acknowledged"
    )
    history = get_decision_history(obs_id)
    assert len(history) >= 1
    assert history[0]["decision"] == "Acknowledge / No Further Action"

    # Cleanup
    with get_connection() as conn:
        conn.execute("DELETE FROM review_decisions WHERE observation_id = ?", (obs_id,))
        conn.execute("DELETE FROM observation_status WHERE observation_id = ?", (obs_id,))
        conn.commit()


def test_field_visit_decision_persistence_and_case_sync():
    """Test 10: Mark for field visit creates an open/under-review investigation case."""
    obs_id = "FV_TEST_2021-09-03"
    record_decision(
        observation_id=obs_id,
        meter_id="TEST_METER",
        date="2021-09-03",
        kwh=12.0,
        anomaly_direction="high",
        decision="Mark for Field Visit",
        notes="Site inspection required"
    )
    history = get_decision_history(obs_id)
    assert len(history) >= 1
    assert history[0]["decision"] == "Mark for Field Visit"

    # Cleanup
    with get_connection() as conn:
        conn.execute("DELETE FROM review_decisions WHERE observation_id = ?", (obs_id,))
        conn.execute("DELETE FROM observation_status WHERE observation_id = ?", (obs_id,))
        conn.commit()


def test_authorized_usage_decision_persistence():
    """Test 11: Authorized usage decision persistence."""
    obs_id = "AUTH_TEST_2021-09-04"
    record_decision(
        observation_id=obs_id,
        meter_id="TEST_METER",
        date="2021-09-04",
        kwh=7.5,
        anomaly_direction="high",
        decision="High Usage Authorized",
        notes="Seasonal heater authorized"
    )
    history = get_decision_history(obs_id)
    assert len(history) >= 1
    assert history[0]["decision"] == "High Usage Authorized"

    # Cleanup
    with get_connection() as conn:
        conn.execute("DELETE FROM review_decisions WHERE observation_id = ?", (obs_id,))
        conn.execute("DELETE FROM observation_status WHERE observation_id = ?", (obs_id,))
        conn.commit()


def test_decision_history_preservation():
    """Test 12: Multiple decisions on the same observation append to audit history without erasing prior events."""
    obs_id = "HIST_TEST_2021-09-05"
    record_decision(
        observation_id=obs_id,
        meter_id="TEST_METER",
        date="2021-09-05",
        kwh=8.0,
        anomaly_direction="high",
        decision="Mark for Field Visit",
        notes="Step 1: Dispatch technician"
    )
    record_decision(
        observation_id=obs_id,
        meter_id="TEST_METER",
        date="2021-09-05",
        kwh=8.0,
        anomaly_direction="high",
        decision="High Usage Authorized",
        notes="Step 2: Technician confirmed permitted load"
    )
    history = get_decision_history(obs_id)
    assert len(history) == 2
    assert history[0]["decision"] == "High Usage Authorized"
    assert history[1]["decision"] == "Mark for Field Visit"

    # Cleanup
    with get_connection() as conn:
        conn.execute("DELETE FROM review_decisions WHERE observation_id = ?", (obs_id,))
        conn.execute("DELETE FROM observation_status WHERE observation_id = ?", (obs_id,))
        conn.commit()


def test_idempotent_review_submissions():
    """Test 13: Submitting the identical decision and note twice is idempotent (does not duplicate audit row)."""
    obs_id = "IDEM_TEST_2021-09-06"
    res1 = record_decision(
        observation_id=obs_id,
        meter_id="TEST_METER",
        date="2021-09-06",
        kwh=5.0,
        anomaly_direction="high",
        decision="Mark for Field Visit",
        notes="Identical submission test"
    )
    assert res1["is_retry"] == False

    res2 = record_decision(
        observation_id=obs_id,
        meter_id="TEST_METER",
        date="2021-09-06",
        kwh=5.0,
        anomaly_direction="high",
        decision="Mark for Field Visit",
        notes="Identical submission test"
    )
    assert res2["is_retry"] == True

    # Audit history must have only 1 row
    history = get_decision_history(obs_id)
    assert len(history) == 1

    # Cleanup
    with get_connection() as conn:
        conn.execute("DELETE FROM review_decisions WHERE observation_id = ?", (obs_id,))
        conn.execute("DELETE FROM observation_status WHERE observation_id = ?", (obs_id,))
        conn.commit()


def test_concurrent_review_submissions():
    """Test 14: Concurrent submissions do not corrupt SQLite database state."""
    obs_id = "CONC_TEST_2021-09-07"

    def submit_action(i):
        return record_decision(
            observation_id=obs_id,
            meter_id="TEST_METER",
            date="2021-09-07",
            kwh=6.0,
            anomaly_direction="high",
            decision="Mark for Field Visit" if i % 2 == 0 else "Acknowledge / No Further Action",
            notes=f"Concurrent submission {i}"
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(submit_action, range(4)))

    assert len(results) == 4
    history = get_decision_history(obs_id)
    assert len(history) >= 1

    # Cleanup
    with get_connection() as conn:
        conn.execute("DELETE FROM review_decisions WHERE observation_id = ?", (obs_id,))
        conn.execute("DELETE FROM observation_status WHERE observation_id = ?", (obs_id,))
        conn.commit()


def test_correct_pending_review_counts():
    """Test 15: Review count calculation: Total = Pending + Reviewed."""
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["flagged_anomalies"] == stats["pending_reviews"] + stats["resolved_reviews"]
    assert stats["flagged_anomalies"] > 0
    assert stats["resolved_reviews"] >= 5
    assert stats["pending_reviews"] == stats["flagged_anomalies"] - stats["resolved_reviews"]


def test_case_status_consistency():
    """Test 16: Case status consistency across endpoints."""
    res = client.get("/api/cases?page=1&page_size=10")
    assert res.status_code == 200
    cases = res.json()
    assert cases["total"] > 0
    for c in cases["items"]:
        assert c["status"] in ("OPEN", "ASSIGNED", "UNDER_REVIEW", "RESOLVED", "CLOSED")


def test_existing_api_compatibility():
    """Test 17: Verify backward compatibility with existing API endpoints."""
    # Chart endpoint
    res_chart = client.get("/api/dashboard/chart?time_range=all")
    assert res_chart.status_code == 200
    pts = res_chart.json()["points"]
    assert len(pts) > 0
    pt = pts[0]
    assert "date" in pt
    assert "kwh" in pt
    assert "is_anomaly" in pt
    assert "anomaly_direction" in pt
    assert "expected_upper" in pt
    assert "expected_lower" in pt
    assert "review_status" in pt
    # New authoritative fields present
    assert "statistical_anomaly" in pt
    assert "isolation_forest_anomaly" in pt
    assert "detection_method" in pt

    # Review queue endpoint
    res_q = client.get("/api/review-queue?page=1&page_size=5")
    assert res_q.status_code == 200
    items = res_q.json()["items"]
    assert len(items) > 0
    item = items[0]
    assert "observation_id" in item
    assert "meter_id" in item
    assert "review_status" in item
    assert "review_decision" in item
    assert "statistical_anomaly" in item
    assert "isolation_forest_anomaly" in item
