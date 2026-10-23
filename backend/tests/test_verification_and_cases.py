import pytest
import pandas as pd
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import (
    get_db,
    init_db,
    get_account_by_id,
    create_case,
    update_case_status,
    assign_case,
    record_case_decision,
    get_case_audit_trail,
)
from backend.app.verification_engine import (
    run_account_verification,
    check_account_data_completeness,
    check_meter_account_association,
    check_meter_reading_integrity,
    check_consumption_anomalies,
    check_billed_units_vs_metered,
    check_bill_amount_validation,
    check_payment_reconciliation,
)

client = TestClient(app)

def test_verification_engine_valid_account():
    """Verify that a standard CEEW account evaluates successfully across all 7 checks."""
    with get_db() as conn:
        acc = conn.execute("SELECT * FROM accounts WHERE meter_id = 'BR02'").fetchone()
        assert acc is not None, "Seed account for BR02 should exist"

    result = run_account_verification(acc["account_id"], scope="FULL_RECONCILIATION")
    assert result["verification_id"].startswith("VERIF-")
    assert result["account_id"] == acc["account_id"]
    assert result["total_checks"] == 7
    assert len(result["checks"]) == 7

    codes = [c["check_code"] for c in result["checks"]]
    assert "CHK_DATA_COMPLETENESS" in codes
    assert "CHK_METER_ASSOC" in codes
    assert "CHK_READING_INTEGRITY" in codes
    assert "CHK_ANOMALY_FINDINGS" in codes
    assert "CHK_BILLED_VS_METERED" in codes
    assert "CHK_BILL_AMOUNT_MATH" in codes
    assert "CHK_PAYMENT_RECONCILIATION" in codes


def test_missing_account_fields_flagged():
    """Missing critical account fields must be flagged, not passed."""
    sparse_account = {
        "account_id": "ACC_TEST_SPARSE",
        "consumer_id": "CON_TEST_SPARSE",
        "meter_id": "",
        "consumer_name": "",
        "district": "",
        "address": "",
        "tariff_category": "",
        "sanctioned_load_kw": 0.0,
        "connection_status": "ACTIVE",
    }
    chk = check_account_data_completeness(sparse_account)
    assert chk["status"] == "FLAGGED"
    assert "Missing mandatory attributes" in chk["findings"]


def test_missing_billing_and_payment_data_not_assessed():
    """Checks for billing and payment without available source data MUST return NOT_ASSESSED, never PASS."""
    dummy_acc = {
        "account_id": "ACC_CEEW_SAMPLE",
        "consumer_id": "CON_CEEW_SAMPLE",
        "meter_id": "BR02",
        "billing_account_id": None,
        "bill_id": None,
        "payment_transaction_id": None,
    }
    
    chk_billed = check_billed_units_vs_metered(dummy_acc, pd.DataFrame())
    assert chk_billed["status"] == "NOT_ASSESSED"
    assert "NOT ASSESSED" in chk_billed["findings"]
    assert "CEEW research dataset" in chk_billed["findings"]

    chk_bill_amount = check_bill_amount_validation(dummy_acc)
    assert chk_bill_amount["status"] == "NOT_ASSESSED"
    assert "NOT ASSESSED" in chk_bill_amount["findings"]

    chk_payment = check_payment_reconciliation(dummy_acc)
    assert chk_payment["status"] == "NOT_ASSESSED"
    assert "NOT ASSESSED" in chk_payment["findings"]


def test_reading_integrity_sequences():
    """Verify chronological sequence and valid non-negative readings."""
    dummy_acc = {
        "account_id": "ACC_INTEG",
        "consumer_id": "CON_INTEG",
        "meter_id": "MTR_INTEG",
    }
    
    # Test invalid reading with negative kWh
    df_invalid = pd.DataFrame([
        {"kwh": -4.2, "date_str": "2020-01-01", "date_parsed": pd.Timestamp("2020-01-01")},
        {"kwh": 8.0, "date_str": "2020-01-02", "date_parsed": pd.Timestamp("2020-01-02")},
    ])
    chk_invalid = check_meter_reading_integrity(dummy_acc, df_invalid)
    assert chk_invalid["status"] == "FLAGGED"
    assert "negative" in chk_invalid["findings"].lower()

    # Test valid reading sequence
    df_valid = pd.DataFrame([
        {"kwh": 5.2, "date_str": "2020-01-01", "date_parsed": pd.Timestamp("2020-01-01")},
        {"kwh": 6.8, "date_str": "2020-01-02", "date_parsed": pd.Timestamp("2020-01-02")},
    ])
    chk_valid = check_meter_reading_integrity(dummy_acc, df_valid)
    assert chk_valid["status"] == "PASS"


def test_known_synthetic_high_and_low_anomalies():
    """ML anomaly check must flag verified meters with anomaly observations."""
    dummy_acc = {
        "account_id": "ACC_ANOM",
        "consumer_id": "CON_ANOM",
        "meter_id": "MTR_ANOM",
    }
    df_with_anomalies = pd.DataFrame([
        {
            "is_anomaly": True,
            "anomaly_direction": "high",
            "anomaly_severity": 0.25,
            "date": "2020-06-15",
            "date_str": "2020-06-15",
            "observation_id": "OBS_TEST_HIGH",
            "kwh": 48.5,
            "trailing_median": 12.0,
            "expected_upper": 22.0,
            "expected_lower": 5.0,
            "reason": "Sudden 4x spike beyond upper bound",
        }
    ])
    chk, refs = check_consumption_anomalies(dummy_acc, df_with_anomalies)
    assert chk["status"] == "FLAGGED"
    assert chk["severity"] in ("MEDIUM", "HIGH", "CRITICAL")
    assert len(refs) == 1
    assert refs[0] == "OBS_TEST_HIGH"


def test_no_unsupported_inference_of_fraud():
    """Verification engine must evaluate to FLAGGED_FOR_REVIEW and NOT claim fraud."""
    with get_db() as conn:
        acc = conn.execute("SELECT * FROM accounts LIMIT 1").fetchone()

    res = run_account_verification(acc["account_id"], scope="FULL_RECONCILIATION")
    assert res["overall_status"] in ("NO_ISSUES_DETECTED", "FLAGGED_FOR_REVIEW", "UNABLE_TO_VERIFY")
    assert "FRAUD" not in res["overall_status"]
    assert "FRAUD_CONFIRMED" not in res["overall_status"]


def test_case_creation_and_deduplication():
    """Deterministic deduplication prevents duplicate cases for the same source finding."""
    with get_db() as conn:
        acc = conn.execute("SELECT * FROM accounts WHERE meter_id = 'BR02'").fetchone()

    source_finding = "ANOMALY-TEST-DEDUP-001"
    
    # First creation
    case1, created1 = create_case(
        source_finding_id=source_finding,
        account_id=acc["account_id"],
        consumer_id=acc["consumer_id"],
        meter_id=acc["meter_id"],
        title="Deduplication Test Case",
        description="Testing composite key deduplication",
        finding_category="TEST_CATEGORY",
        severity="HIGH",
        priority="HIGH",
        actor_id="test_suite",
        actor_role="ADMIN",
    )

    # Second creation with identical source_finding_id
    case2, created2 = create_case(
        source_finding_id=source_finding,
        account_id=acc["account_id"],
        consumer_id=acc["consumer_id"],
        meter_id=acc["meter_id"],
        title="Deduplication Duplicate Attempt",
        description="Should return existing case ID",
        finding_category="TEST_CATEGORY",
        severity="HIGH",
        priority="HIGH",
        actor_id="test_suite",
        actor_role="ADMIN",
    )

    assert case1["case_id"] == case2["case_id"], "Deduplication must return existing case ID"
    assert created2 is False, "Second call must return existing case without duplicating"


def test_case_state_transitions_and_validation():
    """State machine rules must enforce valid workflow transitions."""
    with get_db() as conn:
        acc = conn.execute("SELECT * FROM accounts LIMIT 1").fetchone()

    import uuid
    uid = str(uuid.uuid4())[:8]
    case, _ = create_case(
        source_finding_id=f"TRANSITION-TEST-{acc['account_id']}-{uid}",
        account_id=acc["account_id"],
        consumer_id=acc["consumer_id"],
        meter_id=acc["meter_id"],
        title="Workflow Transition Test",
        description="Testing state transitions",
        finding_category="WORKFLOW_TEST",
        severity="MEDIUM",
        priority="MEDIUM",
        actor_id="test_suite",
        actor_role="ADMIN",
    )
    cid = case["case_id"]

    # Valid transition: OPEN -> ASSIGNED
    c_assigned = update_case_status(cid, "ASSIGNED", reason="Assigned to inspector", actor_id="officer_1", actor_role="VERIFICATION_OFFICER")
    assert c_assigned["status"] == "ASSIGNED"

    # Valid transition: ASSIGNED -> UNDER_REVIEW
    c_review = update_case_status(cid, "UNDER_REVIEW", reason="Beginning review", actor_id="officer_1", actor_role="VERIFICATION_OFFICER")
    assert c_review["status"] == "UNDER_REVIEW"

    # Valid transition: UNDER_REVIEW -> RESOLVED
    c_resolved = update_case_status(cid, "RESOLVED", reason="Investigation finalized", actor_id="officer_1", actor_role="VERIFICATION_OFFICER")
    assert c_resolved["status"] == "RESOLVED"

    # Valid transition: RESOLVED -> CLOSED
    c_closed = update_case_status(cid, "CLOSED", reason="Case archived", actor_id="admin_1", actor_role="ADMIN")
    assert c_closed["status"] == "CLOSED"

    # Invalid transition: CLOSED -> UNDER_REVIEW (Must go to OPEN first)
    with pytest.raises(ValueError, match="Invalid status transition"):
        update_case_status(cid, "UNDER_REVIEW", reason="Illegal skip to under review", actor_id="admin_1", actor_role="ADMIN")


def test_assignment_and_decision_recording():
    """Test assigning officer and submitting a review decision with audit trail."""
    with get_db() as conn:
        acc = conn.execute("SELECT * FROM accounts LIMIT 1").fetchone()

    case, _ = create_case(
        source_finding_id=f"DECISION-TEST-{acc['account_id']}",
        account_id=acc["account_id"],
        consumer_id=acc["consumer_id"],
        meter_id=acc["meter_id"],
        title="Decision Recording Test",
        description="Testing authorized decision submission",
        finding_category="DECISION_TEST",
        severity="HIGH",
        priority="HIGH",
        actor_id="test_suite",
        actor_role="ADMIN",
    )
    cid = case["case_id"]

    # Assign officer
    c_assigned = assign_case(cid, "officer_patel", reason="Specialist assignment", actor_id="admin_1", actor_role="ADMIN")
    assert c_assigned["assigned_officer"] == "officer_patel"

    # Record decision
    c_decided = record_case_decision(
        cid,
        decision="Discrepancy Confirmed",
        decision_reason="Phase imbalance observed on physical check",
        actor_id="officer_patel",
        actor_role="VERIFICATION_OFFICER",
    )
    assert c_decided["decision"] == "Discrepancy Confirmed"
    assert c_decided["status"] == "RESOLVED"
    assert c_decided["resolved_at"] is not None

    # Check audit trail
    audit_events = get_case_audit_trail(cid)
    actions = [evt["action"] for evt in audit_events]
    assert "CASE_CREATED" in actions
    assert "CASE_ASSIGNED" in actions
    assert "DECISION_RECORDED" in actions


def test_rbac_security_auditor_restriction():
    """AUDITOR role must be restricted to read-only access (HTTP 403 on mutate endpoints)."""
    # Create test case
    with get_db() as conn:
        acc = conn.execute("SELECT * FROM accounts LIMIT 1").fetchone()
    case, _ = create_case(
        source_finding_id=f"RBAC-TEST-{acc['account_id']}",
        account_id=acc["account_id"],
        consumer_id=acc["consumer_id"],
        meter_id=acc["meter_id"],
        title="RBAC Auditor Test",
        description="Testing RBAC",
        finding_category="RBAC",
        severity="LOW",
        priority="LOW",
        actor_id="admin",
        actor_role="ADMIN",
    )
    cid = case["case_id"]

    # Auditor headers
    auditor_headers = {
        "X-User-Role": "AUDITOR",
        "X-User-Id": "auditor_inspect",
    }

    # Auditor CAN read case detail
    r_get = client.get(f"/api/cases/{cid}", headers=auditor_headers)
    assert r_get.status_code == 200

    # Auditor CAN read audit trail
    r_audit = client.get(f"/api/cases/{cid}/audit-trail", headers=auditor_headers)
    assert r_audit.status_code == 200

    # Auditor CANNOT change status (HTTP 403)
    r_status = client.post(
        f"/api/cases/{cid}/status",
        headers=auditor_headers,
        json={"status": "UNDER_REVIEW", "reason": "Attempted auditor edit"},
    )
    assert r_status.status_code == 403

    # Auditor CANNOT record decision (HTTP 403)
    r_decision = client.post(
        f"/api/cases/{cid}/decision",
        headers=auditor_headers,
        json={"decision": "Discrepancy Confirmed", "decision_reason": "Auditor override attempt"},
    )
    assert r_decision.status_code == 403


def test_api_account_verification_flow():
    """End-to-end API test for running verification and inspecting case."""
    # List accounts
    r_accs = client.get("/api/accounts")
    assert r_accs.status_code == 200
    accs = r_accs.json()
    assert len(accs) > 0
    test_acc = accs[0]

    # Run verification via API
    r_run = client.post(
        "/api/verification/run",
        json={"account_id": test_acc["account_id"], "scope": "FULL_RECONCILIATION"},
        headers={"X-User-Role": "VERIFICATION_OFFICER", "X-User-Id": "officer_sharma"},
    )
    assert r_run.status_code == 200
    run_data = r_run.json()
    assert run_data["total_checks"] == 7
    assert run_data["account_id"] == test_acc["account_id"]

    # Get verification history via API
    r_hist = client.get(f"/api/accounts/{test_acc['account_id']}/verification-history")
    assert r_hist.status_code == 200
    assert len(r_hist.json()) >= 1


def test_preservation_of_existing_review_decisions():
    """Ensure existing review decisions in review_decisions table are preserved and accounted for."""
    with get_db() as conn:
        decisions = conn.execute("SELECT COUNT(*) as cnt FROM review_decisions").fetchone()["cnt"]
        assert decisions >= 5, "Existing 5 decisions must be preserved in database"

    # Verify pending count calculation matches total anomalies and resolved reviews
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["flagged_anomalies"] > 0
    assert stats["flagged_anomalies"] == stats["pending_reviews"] + stats["resolved_reviews"]
    assert stats["resolved_reviews"] >= 5, "Expected at least 5 preserved resolved reviews"
    assert stats["pending_reviews"] == stats["flagged_anomalies"] - stats["resolved_reviews"]
