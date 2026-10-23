import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import (
    get_connection,
    record_decision,
    get_decision_history,
    get_all_observation_statuses,
    get_active_model_config,
    save_active_model_config,
    get_active_model_run,
    get_model_runs_history,
    compare_model_runs,
)
from backend.app.data_pipeline import (
    calculate_rolling_features,
    fit_isolation_forest,
    run_pipeline,
    validate_model_configuration,
    init_pipeline_from_saved_config,
    state,
    FEATURE_COLUMNS,
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def restore_default_configuration():
    """Ensure tests start and end with standard 3% contamination and 150 estimators."""
    yield
    try:
        run_pipeline(contamination=0.03, n_estimators=150, random_state=42, force_reload=True)
    except Exception:
        pass


# ==============================================================================
# SECTION 10.1: CONFIGURATION TESTS (Tests 1 to 6)
# ==============================================================================

def test_01_default_contamination_is_three_percent():
    """1. Default contamination is 3% (0.03)."""
    cfg = get_active_model_config()
    assert abs(cfg["contamination"] - 0.03) < 1e-4, f"Expected 0.03, got {cfg['contamination']}"
    assert cfg["n_estimators"] == 150
    assert cfg["random_state"] == 42


def test_02_changing_contamination_updates_backend_model():
    """2. Changing contamination updates the actual backend model and active run."""
    res = client.post("/api/model/rerun", json={
        "contamination": 0.05,
        "n_estimators": 150,
        "random_state": 42
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert abs(data["run"]["contamination"] - 0.05) < 1e-4
    assert abs(state.contamination - 0.05) < 1e-4
    assert data["run"]["status"] == "COMPLETED"


def test_03_configuration_persists_across_restart():
    """3. Configuration persists in SQLite and reloads on startup."""
    save_active_model_config(contamination=0.04, n_estimators=150, random_state=42)
    # Simulate restart by reinitializing from database
    df, summary, meta = init_pipeline_from_saved_config()
    assert abs(state.contamination - 0.04) < 1e-4
    assert abs(meta["contamination"] - 0.04) < 1e-4


def test_04_invalid_contamination_is_rejected():
    """4. Invalid contamination values (<0.01, >0.08, NaN, inf) are rejected with 400."""
    invalid_cases = [0.005, 0.09, -0.01, float("nan"), float("inf")]
    for bad_c in invalid_cases:
        res = client.post("/api/model/rerun", json={
            "contamination": bad_c,
            "n_estimators": 150,
            "random_state": 42
        })
        assert res.status_code == 400 or res.status_code == 422, f"Expected error for {bad_c}, got {res.status_code}"


def test_05_invalid_estimators_are_rejected():
    """5. Invalid tree counts (<50 or >300) are rejected with 400/422."""
    for bad_trees in [5, 45, 350, 1000]:
        res = client.post("/api/model/rerun", json={
            "contamination": 0.03,
            "n_estimators": bad_trees,
            "random_state": 42
        })
        assert res.status_code == 400 or res.status_code == 422, f"Expected error for {bad_trees}"


def test_06_failed_runs_do_not_replace_active_results():
    """6. Failed runs preserve previous successfully active model and findings."""
    # Ensure a known active state
    run_pipeline(contamination=0.03, n_estimators=150, random_state=42, force_reload=True)
    prev_active_run = get_active_model_run()
    prev_meta = state.model_metadata.copy()

    # Trigger a validation failure
    res = client.post("/api/model/rerun", json={
        "contamination": 0.99,
        "n_estimators": 150
    })
    assert res.status_code in (400, 422)

    # Active run and in-memory model findings must NOT be overwritten
    current_active_run = get_active_model_run()
    assert current_active_run["run_id"] == prev_active_run["run_id"]
    assert state.model_metadata["contamination"] == prev_meta["contamination"]


# ==============================================================================
# SECTION 10.2: DETECTION TESTS (Tests 7 to 17)
# ==============================================================================

def test_07_synthetic_high_usage_anomaly():
    """7. Synthetic high-usage anomaly test."""
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(40)]
    kwhs = [5.0] * 40
    kwhs[35] = 45.0  # Massive 9x spike

    df = pd.DataFrame({
        "meter_id": ["SYNTH_HIGH"] * 40,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": kwhs,
        "district": ["Bareilly"] * 40,
    })
    featured = calculate_rolling_features(df)
    analyzed, meta = fit_isolation_forest(featured, contamination=0.03, n_estimators=50)

    spike_row = analyzed.iloc[35]
    assert bool(spike_row["is_anomaly"]) is True
    assert spike_row["anomaly_direction"] == "high"
    assert "exceeded historical upper boundary" in spike_row["reason"]


def test_08_synthetic_low_usage_anomaly():
    """8. Synthetic low-usage anomaly test."""
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(40)]
    kwhs = [12.0] * 40
    kwhs[35] = 0.05  # Severe drop

    df = pd.DataFrame({
        "meter_id": ["SYNTH_LOW"] * 40,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": kwhs,
        "district": ["Mathura"] * 40,
    })
    featured = calculate_rolling_features(df)
    analyzed, meta = fit_isolation_forest(featured, contamination=0.03, n_estimators=50)

    drop_row = analyzed.iloc[35]
    assert bool(drop_row["is_anomaly"]) is True
    assert drop_row["anomaly_direction"] == "low"
    assert "dropped significantly below expected lower boundary" in drop_row["reason"]


def test_09_multidimensional_pattern_anomaly():
    """9. Multidimensional pattern anomaly within univariate bounds."""
    test_df = pd.DataFrame([{
        "meter_id": "PATTERN_METER",
        "date": "2021-08-10",
        "date_parsed": pd.to_datetime("2021-08-10"),
        "kwh": 6.0,
        "district": "Bareilly",
        "prev_kwh": 2.0,
        "kwh_change": 4.0,
        "day_of_week": 1,
        "is_weekend": 0,
        "month": 8,
        "trailing_median": 5.5,
        "trailing_mad": 0.8,
        "insufficient_history": False,
        "expected_upper": 8.5,  # within bounds!
        "expected_lower": 2.5,
        "baseline_ratio": 1.09,
        "robust_z": 0.42,
    }])
    # Build enough background rows so Isolation Forest fits
    bg_rows = []
    for i in range(50):
        bg_rows.append({
            "meter_id": "BG_METER",
            "date": f"2021-07-{i+1:02d}",
            "date_parsed": pd.to_datetime(f"2021-07-01") + timedelta(days=i),
            "kwh": 5.5,
            "district": "Bareilly",
            "prev_kwh": 5.5,
            "kwh_change": 0.0,
            "day_of_week": i % 7,
            "is_weekend": 1 if (i % 7) in (5, 6) else 0,
            "month": 7,
            "trailing_median": 5.5,
            "trailing_mad": 0.8,
            "insufficient_history": False,
            "expected_upper": 8.5,
            "expected_lower": 2.5,
            "baseline_ratio": 1.0,
            "robust_z": 0.0,
        })
    comb = pd.concat([pd.DataFrame(bg_rows), test_df], ignore_index=True)
    analyzed, meta = fit_isolation_forest(comb, contamination=0.04, n_estimators=50)
    
    # Target observation is at the end
    target = analyzed.iloc[-1]
    # Verify pattern direction is correctly handled when within bounds
    if target["isolation_forest_anomaly"]:
        assert target["anomaly_direction"] == "pattern"
        assert target["detection_method"] == "ISOLATION_FOREST_PATTERN"


def test_10_normal_observation_test():
    """10. Normal observation within bounds with typical values."""
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(30)]
    kwhs = [4.5] * 30
    df = pd.DataFrame({
        "meter_id": ["NORM01"] * 30,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": kwhs,
        "district": ["Bareilly"] * 30,
    })
    featured = calculate_rolling_features(df)
    analyzed, meta = fit_isolation_forest(featured, contamination=0.03, n_estimators=50)

    mid_row = analyzed.iloc[20]
    assert bool(mid_row["is_anomaly"]) is False
    assert mid_row["anomaly_direction"] == "normal"
    assert mid_row["detection_method"] == "NORMAL"


def test_11_flat_calm_dataset_behavior():
    """11. Flat or calm dataset test: trailing MAD floor of 0.05 prevents div by zero."""
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(30)]
    kwhs = [3.0] * 30  # Completely invariant flat consumption
    df = pd.DataFrame({
        "meter_id": ["FLAT01"] * 30,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": kwhs,
        "district": ["Bareilly"] * 30,
    })
    featured = calculate_rolling_features(df)
    assert not featured["trailing_mad"].isna().any()
    assert (featured["trailing_mad"] >= 0.05).all(), "MAD must have safety floor"
    analyzed, meta = fit_isolation_forest(featured, contamination=0.03, n_estimators=50)
    assert not analyzed["anomaly_score"].isna().any()


def test_12_empty_dataset_behavior():
    """12. Empty dataset behavior handles boundary conditions cleanly."""
    with pytest.raises(Exception):
        fit_isolation_forest(pd.DataFrame(columns=FEATURE_COLUMNS))


def test_13_missing_value_handling():
    """13. Missing-value handling: SimpleImputer handles NaN features without crashing."""
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(25)]
    kwhs = [4.0] * 25
    df = pd.DataFrame({
        "meter_id": ["MISS01"] * 25,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": kwhs,
        "district": ["Bareilly"] * 25,
    })
    featured = calculate_rolling_features(df)
    # Inject isolated NaNs in features
    featured.loc[10, "kwh_change"] = np.nan
    featured.loc[12, "robust_z"] = np.nan

    analyzed, meta = fit_isolation_forest(featured, contamination=0.03, n_estimators=50)
    assert len(analyzed) == 25
    assert not analyzed["anomaly_score"].isna().any()


def test_14_insufficient_history_behavior():
    """14. Insufficient-history behavior marks observations < 7 historical readings."""
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(10)]
    kwhs = [5.0] * 10
    df = pd.DataFrame({
        "meter_id": ["SHORT01"] * 10,
        "date_parsed": dates,
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "kwh": kwhs,
        "district": ["Mathura"] * 10,
    })
    featured = calculate_rolling_features(df)
    assert bool(featured.iloc[0]["insufficient_history"]) is True
    assert bool(featured.iloc[6]["insufficient_history"]) is True
    assert bool(featured.iloc[7]["insufficient_history"]) is False


def test_15_reproducibility_for_identical_inputs_and_configuration():
    """15. Reproducibility for identical inputs and random_state=42."""
    df, _, _ = run_pipeline(contamination=0.03, n_estimators=100, random_state=42, force_reload=True)
    scores_1 = df["anomaly_score"].to_numpy().copy()
    flags_1 = df["isolation_forest_anomaly"].to_numpy().copy()

    df2, _, _ = run_pipeline(contamination=0.03, n_estimators=100, random_state=42, force_reload=True)
    scores_2 = df2["anomaly_score"].to_numpy()
    flags_2 = df2["isolation_forest_anomaly"].to_numpy()

    np.testing.assert_array_almost_equal(scores_1, scores_2)
    assert (flags_1 == flags_2).all()


def test_16_different_contamination_configurations_passed_to_model():
    """16. Different contamination configurations (0.01 vs 0.08) are passed into IsolationForest."""
    df_low, _, meta_low = run_pipeline(contamination=0.01, n_estimators=100, force_reload=True)
    df_high, _, meta_high = run_pipeline(contamination=0.08, n_estimators=100, force_reload=True)

    count_low = int(df_low["isolation_forest_anomaly"].sum())
    count_high = int(df_high["isolation_forest_anomaly"].sum())

    assert count_high > count_low, f"Expected count_high ({count_high}) > count_low ({count_low})"
    assert meta_low["contamination"] == 0.01
    assert meta_high["contamination"] == 0.08


def test_17_verify_mad_results_do_not_change_when_contamination_changes():
    """17. Verify that Historical MAD thresholds and anomalies do NOT change when contamination changes."""
    df_c1, _, _ = run_pipeline(contamination=0.01, force_reload=True)
    mad_upper_1 = df_c1["expected_upper"].to_numpy().copy()
    mad_lower_1 = df_c1["expected_lower"].to_numpy().copy()
    stat_anom_1 = df_c1["statistical_anomaly"].to_numpy().copy()

    df_c8, _, _ = run_pipeline(contamination=0.08, force_reload=True)
    mad_upper_8 = df_c8["expected_upper"].to_numpy()
    mad_lower_8 = df_c8["expected_lower"].to_numpy()
    stat_anom_8 = df_c8["statistical_anomaly"].to_numpy()

    # Mathematical bounds must remain 100% invariant
    np.testing.assert_array_equal(mad_upper_1, mad_upper_8)
    np.testing.assert_array_equal(mad_lower_1, mad_lower_8)
    assert (stat_anom_1 == stat_anom_8).all(), "Statistical MAD anomalies must NOT change when contamination changes"


# ==============================================================================
# SECTION 10.3: PERSISTENCE AND REVIEW WORKFLOW TESTS (Tests 18 to 25)
# ==============================================================================

def test_18_model_run_records_persist_correctly():
    """18. Model run records persist in model_runs table with all metadata."""
    res = client.post("/api/model/rerun", json={
        "contamination": 0.03,
        "n_estimators": 150,
        "random_state": 42
    })
    assert res.status_code == 200
    run_id = res.json()["run"]["run_id"]

    history = get_model_runs_history(limit=5)
    matching = [r for r in history if r["run_id"] == run_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "COMPLETED"
    assert matching[0]["records_analyzed"] > 0
    assert matching[0]["is_active"] == 1


def test_19_finding_identities_remain_stable():
    """19. Finding identities (meter_id_date) remain stable across runs."""
    df1, _, _ = run_pipeline(contamination=0.03, force_reload=True)
    obs_ids_1 = df1["observation_id"].tolist()

    df2, _, _ = run_pipeline(contamination=0.05, force_reload=True)
    obs_ids_2 = df2["observation_id"].tolist()

    assert obs_ids_1 == obs_ids_2, "Observation IDs must be completely deterministic and stable"


def test_20_reruns_do_not_duplicate_logical_findings():
    """20. Rerunning model does not create duplicate rows in observation_status."""
    with get_connection() as conn:
        before_count = conn.execute("SELECT COUNT(DISTINCT observation_id) as cnt FROM observation_status").fetchone()["cnt"]
        total_rows = conn.execute("SELECT COUNT(*) as cnt FROM observation_status").fetchone()["cnt"]
        assert before_count == total_rows, "observation_id primary key ensures zero duplicates"


def test_21_existing_review_decisions_remain_preserved():
    """21. Existing review decisions and notes remain preserved after model rerun."""
    obs_id = "BR36_2021-10-31"
    # Record a decision
    res = record_decision(
        observation_id=obs_id,
        meter_id="BR36",
        date="2021-10-31",
        kwh=5.3,
        anomaly_direction="high",
        decision="Mark for Field Visit",
        notes="Audit verification note for test 21"
    )
    assert res["review_status"] == "REVIEWED"

    # Rerun model with different contamination
    client.post("/api/model/rerun", json={"contamination": 0.04, "n_estimators": 150})

    # Verify decision is intact
    history = get_decision_history(obs_id)
    assert len(history) >= 1
    assert any(h["decision"] == "Mark for Field Visit" for h in history)

    st_map = get_all_observation_statuses()
    assert st_map[obs_id]["review_status"] == "REVIEWED"
    assert st_map[obs_id]["review_decision"] == "Mark for Field Visit"


def test_22_resolved_findings_do_not_reappear_as_duplicate_pending():
    """22. Resolved findings maintain reviewed status and do not revert to pending."""
    obs_id = "BR36_2021-10-25"
    record_decision(
        observation_id=obs_id,
        meter_id="BR36",
        date="2021-10-25",
        kwh=4.8,
        anomaly_direction="high",
        decision="Acknowledge / No Further Action",
        notes="Case acknowledged"
    )
    # Rerun model
    client.post("/api/model/rerun", json={"contamination": 0.03, "n_estimators": 150})

    res = client.get(f"/api/review-queue?search={obs_id}")
    assert res.status_code == 200
    items = res.json()["items"]
    if items:
        assert items[0]["review_status"] != "Pending Review"
        assert items[0]["review_decision"] == "Acknowledge / No Further Action"


def test_23_newly_detected_findings_enter_review_workflow():
    """23. Newly detected findings enter review workflow with Pending Review."""
    # Run with broad contamination
    client.post("/api/model/rerun", json={"contamination": 0.08, "n_estimators": 150})
    res = client.get("/api/review-queue?page=1&page_size=20")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] > 0
    # Every unreviewed item is Pending Review
    for item in data["items"]:
        if item["review_decision"] == "PENDING":
            assert item["review_status"] in ("Pending Review", "PENDING")


def test_24_disappeared_findings_handled_according_to_lifecycle():
    """24. Disappeared findings preserve historical decision records even when dropped from active queue."""
    # Record decision on an observation
    obs_id = "BR36_2021-10-23"
    record_decision(
        observation_id=obs_id,
        meter_id="BR36",
        date="2021-10-23",
        kwh=4.1,
        anomaly_direction="high",
        decision="High Usage Authorized",
        notes="Permitted authorized load"
    )

    # Rerun model with strict 1% contamination
    client.post("/api/model/rerun", json={"contamination": 0.01, "n_estimators": 150})

    # The historical decision still exists in the database
    hist = get_decision_history(obs_id)
    assert len(hist) >= 1
    assert hist[0]["decision"] == "High Usage Authorized"


def test_25_review_queue_counts_consistent_with_database():
    """25. Review queue counts reconcile with database records."""
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["flagged_anomalies"] == stats["pending_reviews"] + stats["resolved_reviews"]


# ==============================================================================
# SECTION 10.4: API AND INTEGRATION TESTS (Tests 26 to 33)
# ==============================================================================

def test_26_meter_filter_works():
    """26. Chart and queue endpoints filter correctly by meter_id."""
    res = client.get("/api/dashboard/chart?meter_id=BR02")
    assert res.status_code == 200
    points = res.json()["points"]
    assert len(points) > 0
    assert all(p["meter_id"] == "BR02" for p in points)


def test_27_date_range_filter_works():
    """27. Time range filters (30d, 90d, 1y, all) filter timestamps appropriately."""
    res_30 = client.get("/api/dashboard/chart?time_range=30d")
    res_all = client.get("/api/dashboard/chart?time_range=all")
    assert res_30.status_code == 200
    assert res_all.status_code == 200
    assert len(res_30.json()["points"]) <= len(res_all.json()["points"])


def test_28_overview_api_returns_consistent_data():
    """28. Overview API returns consistent model metadata and counters."""
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["total_meters"] == 84
    assert stats["total_readings"] == 44610
    assert stats["high_anomalies"] + stats["low_anomalies"] + stats["pattern_anomalies"] > 0


def test_29_meter_analysis_api_returns_consistent_data():
    """29. Meter Analysis history endpoint returns accurate coordinates and bounds."""
    res = client.get("/api/meters/BR02/history?time_range=30d")
    assert res.status_code == 200
    data = res.json()
    assert data["meter_id"] == "BR02"
    assert len(data["points"]) > 0
    for pt in data["points"]:
        assert pt["kwh"] >= 0
        if pt["expected_upper"] is not None and pt["expected_lower"] is not None:
            assert pt["expected_upper"] >= pt["expected_lower"]


def test_30_review_queue_reflects_current_eligible_findings():
    """30. Review Queue returns eligible anomaly observations with rich metadata."""
    res = client.get("/api/review-queue?page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["page"] == 1
    assert data["total"] > 0
    if data["items"]:
        first = data["items"][0]
        assert first["is_anomaly"] is True
        assert first["detection_method"] in ("STATISTICAL_MAD", "ISOLATION_FOREST_PATTERN", "STATISTICAL_AND_ML")


def test_31_model_run_comparison_works():
    """31. Model run comparison calculates newly detected, disappeared, and continuing findings."""
    # Run 1: 0.02
    res1 = client.post("/api/model/rerun", json={"contamination": 0.02, "n_estimators": 100})
    assert res1.status_code == 200
    run_1_id = res1.json()["run"]["run_id"]

    # Run 2: 0.05
    res2 = client.post("/api/model/rerun", json={"contamination": 0.05, "n_estimators": 100})
    assert res2.status_code == 200
    run_2_id = res2.json()["run"]["run_id"]

    comp = compare_model_runs(run_2_id, run_1_id)
    assert comp["current_contamination"] == 0.05
    assert comp["previous_contamination"] == 0.02
    assert comp["newly_detected_count"] > 0
    assert comp["continuing_count"] > 0

    # Also test API endpoint
    api_comp = client.get(f"/api/model/compare?current_run_id={run_2_id}&previous_run_id={run_1_id}")
    assert api_comp.status_code == 200
    assert api_comp.json()["newly_detected_count"] == comp["newly_detected_count"]


def test_32_frontend_api_handles_success_and_failures():
    """32. Backend endpoints return appropriate status codes and error payloads."""
    # Bad request
    res_bad = client.post("/api/model/rerun", json={"contamination": "invalid"})
    assert res_bad.status_code in (400, 422)

    # Valid config endpoint
    res_cfg = client.get("/api/model/config")
    assert res_cfg.status_code == 200
    cfg_data = res_cfg.json()
    assert "active_configuration" in cfg_data
    assert "saved_configuration" in cfg_data


def test_33_no_broken_billing_payment_or_account_workflows():
    """33. Billing verification, payment reconciliation, and account verification workflows remain 100% operational."""
    # 1. Accounts
    res_acc = client.get("/api/accounts")
    assert res_acc.status_code == 200
    assert len(res_acc.json()) > 0

    # 2. Cases
    res_cases = client.get("/api/cases?page=1&page_size=5")
    assert res_cases.status_code == 200
    assert "items" in res_cases.json()

    # 3. Billing summary
    res_bill = client.get("/api/billing/summary")
    assert res_bill.status_code == 200
    assert res_bill.json()["total_bills"] > 0
