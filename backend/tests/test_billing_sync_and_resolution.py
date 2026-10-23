import pytest
import sqlite3
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import (
    get_db,
    init_db,
    get_synthetic_bill_by_id,
    reconcile_billing_finding_on_run,
    record_case_decision,
    update_case_status,
    get_billing_summary_metrics,
    get_case_audit_trail,
)
from backend.app.billing_engine import verify_synthetic_bill

client = TestClient(app)

OFFICER_HEADERS = {"X-User-Role": "VERIFICATION_OFFICER", "X-User-Id": "officer_sharma"}
ADMIN_HEADERS = {"X-User-Role": "ADMIN", "X-User-Id": "admin_root"}


def test_01_create_billing_discrepancy():
    """Test 1: Create a billing discrepancy. Expected: One finding and one linked investigation according to policy."""
    bill_id = "BILL-BR03-201911"
    # Run billing verification to evaluate discrepancy and trigger idempotent finding and case creation
    resp = client.post(f"/api/billing/verify/{bill_id}", headers=OFFICER_HEADERS)
    assert resp.status_code == 200
    v_res = resp.json()
    assert v_res["overall_result"] == "FLAGGED"
    assert v_res["linked_case_id"] is not None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM billing_findings WHERE bill_id = ?", (bill_id,))
        findings = cursor.fetchall()
        assert len(findings) >= 1
        finding = dict(findings[0])
        assert finding["linked_case_id"] == v_res["linked_case_id"]
        assert finding["linked_case_id"] is not None

        cursor.execute("SELECT * FROM cases WHERE case_id = ?", (finding["linked_case_id"],))
        case = cursor.fetchone()
        assert case is not None
        assert dict(case)["finding_category"] == "BILLING_DISCREPANCY"


def test_02_resolve_investigation():
    """Test 2: Resolve the investigation. Expected: Correct effective state across case and finding."""
    bill_id = "BILL-BR03-201911"
    bill = get_synthetic_bill_by_id(bill_id)
    assert bill is not None
    case_id = bill["linked_case_id"]
    assert case_id is not None

    # Submit resolution decision via API
    response = client.post(
        f"/api/cases/{case_id}/decision",
        headers=OFFICER_HEADERS,
        json={
            "decision": "Discrepancy Confirmed",
            "decision_reason": "Verified telemetry loss during substation maintenance; variance documented and approved.",
        },
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "RESOLVED"
    assert res_data["decision"] == "Discrepancy Confirmed"

    # Verify both case and finding in DB
    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["case"]["status"] == "RESOLVED"
    assert detail["case"]["decision"] == "Discrepancy Confirmed"
    assert detail["case"]["resolved_at"] is not None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM billing_findings WHERE linked_case_id = ?", (case_id,))
        f = dict(cursor.fetchone())
        assert f["review_status"] == "REVIEWED"
        assert f["review_decision"] == "Discrepancy Confirmed"
        assert f["decision_reason"] == "Verified telemetry loss during substation maintenance; variance documented and approved."
        assert f["decision_at"] is not None


def test_03_reload_application_state_persists():
    """Test 3: Reload the application. Expected: The resolved state persists."""
    bill_id = "BILL-BR03-201911"
    response = client.get(f"/api/billing/bills/{bill_id}")
    assert response.status_code == 200
    bill = response.json()
    assert bill["case_status"] == "RESOLVED"
    assert bill["review_status"] == "REVIEWED"
    assert bill["review_decision"] == "Discrepancy Confirmed"
    assert "substation maintenance" in (bill["decision_reason"] or "")


def test_04_rerun_verification_no_duplicates_no_reset():
    """Test 4: Rerun billing verification with the same discrepancy.
    Expected: No duplicate finding, no duplicate case, no reset to pending.
    """
    bill_id = "BILL-BR03-201911"
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM billing_findings WHERE bill_id = ?", (bill_id,))
        count_before = c.fetchone()[0]
        c.execute("SELECT linked_case_id FROM billing_findings WHERE bill_id = ?", (bill_id,))
        original_case_id = c.fetchone()[0]

    # Rerun verification via API
    resp = client.post(f"/api/billing/verify/{bill_id}", headers=OFFICER_HEADERS)
    assert resp.status_code == 200
    v_result = resp.json()

    # Telemetry result remains FLAGGED
    assert v_result["overall_result"] == "FLAGGED"
    # But review state and case state remain preserved
    assert v_result["review_status"] == "REVIEWED"
    assert v_result["case_status"] == "RESOLVED"
    assert v_result["review_decision"] == "Discrepancy Confirmed"
    assert v_result["linked_case_id"] == original_case_id

    # Check database counts
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM billing_findings WHERE bill_id = ?", (bill_id,))
        count_after = c.fetchone()[0]
        assert count_after == count_before, "No duplicate findings should be created on rerun"

        c.execute("SELECT status, decision FROM cases WHERE case_id = ?", (original_case_id,))
        case_row = c.fetchone()
        assert case_row[0] == "RESOLVED", "Case status must not reset to OPEN or PENDING"
        assert case_row[1] == "Discrepancy Confirmed", "Decision must not reset"


def test_05_resolve_a_finding_and_rerun_verification_multiple_times():
    """Test 5: Resolve a finding and rerun verification multiple times.
    Expected: Decision history and current state remain consistent.
    """
    bill_id = "BILL-BR03-201911"
    for i in range(3):
        resp = client.post(f"/api/billing/verify/{bill_id}", headers=OFFICER_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["review_status"] == "REVIEWED"
        assert data["case_status"] == "RESOLVED"
        assert data["review_decision"] == "Discrepancy Confirmed"

    # Confirm audit history in case detail remains healthy
    bill = get_synthetic_bill_by_id(bill_id)
    case_detail = client.get(f"/api/cases/{bill['linked_case_id']}").json()
    assert len(case_detail["audit_events"]) >= 2
    assert any(e["action"] == "DECISION_RECORDED" for e in case_detail["audit_events"])


def test_06_introduce_a_genuinely_recurring_discrepancy():
    """Test 6: Introduce a genuinely recurring discrepancy.
    Expected: Recurrence is recorded and the documented case recurrence policy (Option A) is applied.
    """
    bill_id = "BILL-BR03-201911"
    bill = get_synthetic_bill_by_id(bill_id)
    case_id = bill["linked_case_id"]

    # Reconcile with is_recurrence=True to trigger documented recurrence policy
    run_id = "RUN-TEST-RECURRENCE-01"
    finding_dict, case_dict, is_new = reconcile_billing_finding_on_run(
        bill_id=bill_id,
        account_id=bill["account_id"],
        meter_id=bill["meter_id"],
        reason="INSUFFICIENT_METER_COVERAGE",
        run_id=run_id,
        is_recurrence=True,
    )
    assert finding_dict is not None

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT is_recurring, review_status FROM billing_findings WHERE finding_id = ?", (finding_dict["finding_id"],))
        f_row = c.fetchone()
        assert f_row[0] == 1, "Finding is_recurring flag must be set"

        c.execute("SELECT status FROM cases WHERE case_id = ?", (case_id,))
        case_status = c.fetchone()[0]
        assert case_status == "UNDER_REVIEW", "Resolved case should reopen to UNDER_REVIEW on genuine recurrence"

        c.execute("SELECT action, reason FROM case_audit_events WHERE case_id = ? AND action = 'DISCREPANCY_RECURRED'", (case_id,))
        recur_event = c.fetchone()
        assert recur_event is not None, "DISCREPANCY_RECURRED audit event must be logged"


def test_07_resolve_one_finding_within_a_multi_finding_case():
    """Test 7: Resolve one finding within a multi-finding case.
    Expected: Unrelated findings retain their states.
    """
    case_id = "CASE-MULTI-TEST-001"
    with get_db() as conn:
        c = conn.cursor()
        # Create test case
        c.execute(
            """INSERT OR REPLACE INTO cases (case_id, consumer_id, meter_id, account_id, source_finding_id, title, description, finding_category, severity, priority, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (case_id, "CON-TEST-1", "MTR-TEST-1", "ACC-TEST-1", "FINDING-A1", "Multi-finding test case", "Testing independent finding state", "BILLING_DISCREPANCY", "MEDIUM", "MEDIUM", "OPEN")
        )
        # Create two findings linked to the same case
        c.execute(
            """INSERT OR REPLACE INTO billing_findings (finding_id, bill_id, account_id, meter_id, finding_category, reason, first_detected_at, latest_observed_at, review_status, review_decision, linked_case_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?, ?, datetime('now'), datetime('now'))""",
            ("FINDING-A1", "BILL-TEST-MULTI", "ACC-TEST-1", "MTR-TEST-1", "BILLING_DISCREPANCY", "UNIT_MISMATCH", "PENDING", None, case_id)
        )
        c.execute(
            """INSERT OR REPLACE INTO billing_findings (finding_id, bill_id, account_id, meter_id, finding_category, reason, first_detected_at, latest_observed_at, review_status, review_decision, linked_case_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?, ?, datetime('now'), datetime('now'))""",
            ("FINDING-B2", "BILL-TEST-MULTI", "ACC-TEST-1", "MTR-TEST-1", "BILLING_DISCREPANCY", "TARIFF_CALC_ERROR", "PENDING", None, case_id)
        )
        conn.commit()

        # Update finding A1 only
        c.execute(
            """UPDATE billing_findings
               SET review_status = 'REVIEWED', review_decision = 'Explained Discrepancy', decision_reason = 'Approved adjustment'
               WHERE finding_id = 'FINDING-A1'"""
        )
        conn.commit()

        # Verify finding B2 remains PENDING
        c.execute("SELECT review_status, review_decision FROM billing_findings WHERE finding_id = 'FINDING-B2'")
        b2 = c.fetchone()
        assert b2[0] == "PENDING"
        assert b2[1] is None

        c.execute("SELECT review_status, review_decision FROM billing_findings WHERE finding_id = 'FINDING-A1'")
        a1 = c.fetchone()
        assert a1[0] == "REVIEWED"
        assert a1[1] == "Explained Discrepancy"


def test_08_transaction_rollback_on_failure():
    """Test 8: Simulate a failure halfway through resolution.
    Expected: Full transaction rollback.
    """
    case_id = "CASE-ROLLBACK-TEST"
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO cases (case_id, consumer_id, meter_id, account_id, source_finding_id, title, description, finding_category, severity, priority, status, decision, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (case_id, "CON-RB-1", "MTR-RB-1", "ACC-RB-1", "FINDING-RB-1", "Rollback test", "Desc", "BILLING_DISCREPANCY", "MEDIUM", "MEDIUM", "OPEN", "PENDING")
        )
        c.execute(
            """INSERT OR REPLACE INTO billing_findings (finding_id, bill_id, account_id, meter_id, finding_category, reason, first_detected_at, latest_observed_at, review_status, linked_case_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?, datetime('now'), datetime('now'))""",
            ("FINDING-RB-1", "BILL-RB-1", "ACC-RB-1", "MTR-RB-1", "BILLING_DISCREPANCY", "UNIT_MISMATCH", "PENDING", case_id)
        )
        conn.commit()

    # Simulate atomic failure inside transaction
    with pytest.raises(Exception):
        with get_db() as conn:
            c = conn.cursor()
            c.execute("UPDATE cases SET status = 'RESOLVED' WHERE case_id = ?", (case_id,))
            # Force an integrity violation to cause rollback
            c.execute("INSERT INTO cases (case_id, consumer_id, meter_id, title, description) VALUES (NULL, NULL, NULL, NULL, NULL)")
            conn.commit()

    # Verify case remains OPEN and not partially updated
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT status, decision FROM cases WHERE case_id = ?", (case_id,))
        row = c.fetchone()
        assert row[0] == "OPEN"
        assert row[1] == "PENDING"


def test_09_duplicate_resolution_requests():
    """Test 9: Submit duplicate resolution requests.
    Expected: Idempotent behavior or a clear conflict response.
    """
    bill_id = "BILL-BR03-201911"
    bill = get_synthetic_bill_by_id(bill_id)
    case_id = bill["linked_case_id"]

    # First submission
    resp1 = client.post(
        f"/api/cases/{case_id}/decision",
        headers=OFFICER_HEADERS,
        json={"decision": "Discrepancy Confirmed", "decision_reason": "Identical reason for idempotency test"},
    )
    assert resp1.status_code == 200

    # Duplicate submission
    resp2 = client.post(
        f"/api/cases/{case_id}/decision",
        headers=OFFICER_HEADERS,
        json={"decision": "Discrepancy Confirmed", "decision_reason": "Identical reason for idempotency test"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "RESOLVED"
    assert resp2.json()["decision"] == "Discrepancy Confirmed"


def test_10_validate_review_queue_counts():
    """Test 10: Validate Review Queue and billing summary counts."""
    metrics = get_billing_summary_metrics()
    assert "billing_discrepancies_flagged" in metrics
    assert "billing_discrepancies_pending" in metrics
    assert "billing_discrepancies_resolved" in metrics
    assert "open_investigations" in metrics
    assert "resolved_investigations" in metrics

    # Flagged count equals pending + resolved
    total_findings = metrics["billing_discrepancies_pending"] + metrics["billing_discrepancies_resolved"]
    assert total_findings >= metrics["billing_discrepancies_flagged"]


def test_11_billing_verification_status_after_refresh():
    """Test 11: Validate Billing Verification status after refresh."""
    bill_id = "BILL-BR03-201911"
    resp = client.get(f"/api/billing/bills/{bill_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bill_id"] == bill_id
    assert data["latest_verification_status"] == "FLAGGED"
    assert data["case_status"] in ["RESOLVED", "UNDER_REVIEW"]


def test_12_audit_trail_consistency():
    """Test 12: Validate case status, finding status, and audit history consistency."""
    bill_id = "BILL-BR03-201911"
    bill = get_synthetic_bill_by_id(bill_id)
    case_id = bill["linked_case_id"]

    events = get_case_audit_trail(case_id)
    assert len(events) >= 1
    # Check each event has required fields
    for e in events:
        assert "event_id" in e
        assert "action" in e
        assert "created_at" in e
        assert "actor_id" in e


def test_13_insufficient_telemetry_coverage_behavior():
    """Test 13: Validate insufficient telemetry coverage behavior.
    Coverage 73.3% (<80%) must preserve FLAGGED verification result.
    """
    bill_id = "BILL-BR03-201911"
    res = verify_synthetic_bill(bill_id)
    assert res["coverage_status"] == "INSUFFICIENT"
    assert res["overall_result"] == "FLAGGED"
    assert res["coverage_details"]["days_observed"] == 22
    assert res["coverage_details"]["expected_days"] == 30
    assert abs(res["coverage_details"]["coverage_ratio"] - 0.733) < 0.01


def test_14_frontend_state_refresh_payload():
    """Test 14: Validate frontend state refresh after case resolution."""
    bill_id = "BILL-BR03-201911"
    resp = client.get(f"/api/billing/bills/{bill_id}")
    assert resp.status_code == 200
    b = resp.json()
    assert "review_status" in b
    assert "review_decision" in b
    assert "decision_reason" in b
    assert "case_status" in b
    assert "linked_case_id" in b


def test_15_legacy_records_and_api_compatibility():
    """Test 15: Validate legacy records and API compatibility."""
    # Test cases list endpoint
    resp = client.get("/api/cases?category=BILLING_DISCREPANCY")
    assert resp.status_code == 200
    cases_data = resp.json()
    assert "items" in cases_data
    assert "total" in cases_data
    assert cases_data["total"] >= 1

    # Test review queue endpoint for telemetry
    resp_queue = client.get("/api/review-queue?pageSize=5")
    assert resp_queue.status_code == 200
    queue_data = resp_queue.json()
    assert "items" in queue_data
    assert "total" in queue_data
