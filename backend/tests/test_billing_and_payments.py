import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import (
    init_db,
    seed_billing_and_payments_if_empty,
    get_synthetic_bill_by_id,
    get_synthetic_payments,
    get_case_by_id,
)
from backend.app.billing_engine import (
    verify_synthetic_bill,
    reconcile_bill_payments,
)

client = TestClient(app)

OFFICER_HEADERS = {"X-User-Role": "VERIFICATION_OFFICER", "X-User-Id": "officer.sharma"}
ADMIN_HEADERS = {"X-User-Role": "ADMIN", "X-User-Id": "admin.root"}

@pytest.fixture(autouse=True)
def setup_seed_data():
    """Ensure database has demonstration seed data prior to test execution."""
    init_db()
    seed_billing_and_payments_if_empty(force=True)

# ==============================================================================
# PHASE 2: BILLING VERIFICATION TESTS (1 to 14)
# ==============================================================================

def test_billing_01_configured_tariff_retrieval():
    """Billing Test 1: Configured tariff retrieval (tariffs list and flat rate rule)."""
    response = client.get("/api/tariffs")
    assert response.status_code == 200
    tariffs = response.json()
    assert len(tariffs) >= 1
    flat_rule = next((t for t in tariffs if t["tariff_id"] == "TAR-DEMO-FLAT"), None)
    assert flat_rule is not None
    assert flat_rule["rate_per_kwh_paise"] == 650
    assert flat_rule["fixed_charge_paise"] == 11000
    assert flat_rule["currency"] == "INR"
    assert flat_rule["is_active"] == 1

def test_billing_02_configured_tariff_update():
    """Billing Test 2: Configured tariff updates (rate update in integer paise)."""
    response = client.put(
        "/api/tariffs/TAR-DEMO-FLAT",
        headers=ADMIN_HEADERS,
        json={"rate_per_kwh_paise": 700, "fixed_charge_paise": 12000, "tariff_name": "Updated Flat Tariff"}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["rate_per_kwh_paise"] == 700
    assert updated["fixed_charge_paise"] == 12000

    # Reset back to default for other tests
    client.put(
        "/api/tariffs/TAR-DEMO-FLAT",
        headers=ADMIN_HEADERS,
        json={"rate_per_kwh_paise": 650, "fixed_charge_paise": 11000, "tariff_name": "Standard Flat Tariff (Demo)"}
    )

def test_billing_03_perfect_match_verifies_to_pass():
    """Billing Test 3: Perfect match scenario verifies to PASS."""
    # BILL-BR02-201909 is a perfect match bill against real metered consumption (145.42 kWh, 105523 paise)
    response = client.post(
        "/api/billing/verify/BILL-BR02-201909",
        headers=OFFICER_HEADERS
    )
    assert response.status_code == 200
    result = response.json()
    assert result["overall_result"] == "PASS"
    assert result["units_check_status"] == "PASS"
    assert result["amount_check_status"] == "PASS"
    assert result["coverage_status"] == "COMPLETE"
    assert result["linked_case_id"] is None
    assert result["provenance"] == "SYNTHETIC_DEMO"

def test_billing_04_unit_mismatch_verifies_to_flagged():
    """Billing Test 4: Unit mismatch scenario verifies to FLAGGED and creates case."""
    # BILL-BR02-201910 billed 260 kWh while metered is ~117.67 kWh
    response = client.post(
        "/api/billing/verify/BILL-BR02-201910",
        headers=OFFICER_HEADERS
    )
    assert response.status_code == 200
    result = response.json()
    assert result["overall_result"] == "FLAGGED"
    assert result["units_check_status"] == "FLAGGED"
    assert result["unit_difference"] is not None
    assert abs(result["unit_difference"]) > 1.0
    assert result["linked_case_id"] is not None
    assert "CASE-" in result["linked_case_id"]

def test_billing_05_tariff_calc_error_verifies_to_flagged():
    """Billing Test 5: Tariff calculation error scenario verifies to FLAGGED."""
    # BILL-BR03-201911 billed 90 kWh at ₹1,450.00 while expected is ₹695.00
    response = client.post(
        "/api/billing/verify/BILL-BR03-201911",
        headers=OFFICER_HEADERS
    )
    assert response.status_code == 200
    result = response.json()
    assert result["overall_result"] == "FLAGGED"
    assert result["amount_check_status"] == "FLAGGED"
    assert result["amount_difference_paise"] is not None
    assert abs(result["amount_difference_paise"]) > 100
    assert result["linked_case_id"] is not None

def test_billing_06_missing_interval_telemetry_incomplete():
    """Billing Test 6: Missing interval telemetry (<80% coverage) triggers incomplete telemetry and FLAGGED."""
    # BILL-BR02-202005 only has 4 days of telemetry in CEEW dataset (12.9% coverage)
    response = client.post(
        "/api/billing/verify/BILL-BR02-202005",
        headers=OFFICER_HEADERS
    )
    assert response.status_code == 200
    result = response.json()
    assert result["overall_result"] == "FLAGGED"
    assert result["coverage_status"] == "INSUFFICIENT"
    cov = result["coverage_details"]
    assert cov["coverage_ratio"] < 0.80

def test_billing_07_incomplete_telemetry_case_reason():
    """Billing Test 7: Incomplete telemetry check creates case with reason detailing coverage ratio."""
    response = client.post(
        "/api/billing/verify/BILL-BR02-202005",
        headers=OFFICER_HEADERS
    )
    assert response.status_code == 200
    result = response.json()
    case_id = result["linked_case_id"]
    assert case_id is not None
    case = get_case_by_id(case_id)
    assert case is not None
    assert "coverage" in case["description"].lower()

def test_billing_08_zero_consumption_bill():
    """Billing Test 8: Zero-consumption bill verification (unoccupied premises, fixed charge only)."""
    response = client.post(
        "/api/billing/verify/BILL-BR06-201909-ZC",
        headers=OFFICER_HEADERS
    )
    assert response.status_code == 200
    result = response.json()
    assert result["billed_units"] == 0.0
    assert result["billed_amount_paise"] == 11000
    assert result["overall_result"] == "FLAGGED"  # Meter had actual usage, 0 billed is flagged discrepancy

def test_billing_09_extreme_high_bill():
    """Billing Test 9: Extreme high bill verification (large discrepancy, high priority case)."""
    response = client.post(
        "/api/billing/verify/BILL-BR07-201909-HB",
        headers=OFFICER_HEADERS
    )
    assert response.status_code == 200
    result = response.json()
    assert result["overall_result"] == "FLAGGED"
    assert result["linked_case_id"] is not None
    case = get_case_by_id(result["linked_case_id"])
    assert case["priority"] in ["MEDIUM", "HIGH", "URGENT"]

def test_billing_10_arrears_carried_over():
    """Billing Test 10: Arrears carried over scenario detects excess billed amount above tariff units."""
    response = client.post(
        "/api/billing/verify/BILL-BR08-201909-AR",
        headers=OFFICER_HEADERS
    )
    assert response.status_code == 200
    result = response.json()
    assert result["overall_result"] == "FLAGGED"
    assert result["amount_check_status"] == "FLAGGED"
    assert abs(result["amount_difference_paise"]) > 100

def test_billing_11_exact_integer_paise_arithmetic():
    """Billing Test 11: Exact integer-paise arithmetic verification (no floating point mismatch on fractional kWh)."""
    bill = get_synthetic_bill_by_id("BILL-BR02-201909")
    units = bill["consumed_units_kwh"]
    rate_paise = 650
    fixed_paise = 11000
    expected_paise = round(units * rate_paise) + fixed_paise
    assert isinstance(expected_paise, int)
    assert bill["bill_amount_paise"] == expected_paise

def test_billing_12_operational_ceew_verification_remains_not_assessed():
    """Billing Test 12: Real CEEW accounts evaluation remains NOT_ASSESSED under standard operational verification."""
    from backend.app.verification_engine import run_account_verification
    res = run_account_verification("ACCT-BR02", scope="FULL_HISTORICAL_AUDIT")
    for check_code in ["CHK_BILLED_VS_METERED", "CHK_BILL_AMOUNT_MATH", "CHK_PAYMENT_RECONCILIATION"]:
        chk = next((c for c in res["checks"] if c["check_code"] == check_code), None)
        assert chk is not None
        assert chk["status"] == "NOT_ASSESSED"

def test_billing_13_synthetic_sandbox_mode_provenance():
    """Billing Test 13: Synthetic sandbox mode explicitly flagged with provenance SYNTHETIC_DEMO."""
    response = client.get("/api/billing/bills/BILL-BR02-201909")
    assert response.status_code == 200
    bill = response.json()
    assert bill["provenance"] == "SYNTHETIC_DEMO"
    assert bill["is_synthetic"] == 1

def test_billing_14_verification_deduplication():
    """Billing Test 14: Deduplication prevents duplicate verification cases for same bill_id."""
    res1 = client.post("/api/billing/verify/BILL-BR02-201910", headers=OFFICER_HEADERS)
    res2 = client.post("/api/billing/verify/BILL-BR02-201910", headers=OFFICER_HEADERS)
    assert res1.status_code == 200
    assert res2.status_code == 200
    case_id_1 = res1.json()["linked_case_id"]
    case_id_2 = res2.json()["linked_case_id"]
    assert case_id_1 == case_id_2

# ==============================================================================
# PHASE 3: PAYMENT RECONCILIATION TESTS (1 to 14)
# ==============================================================================

def test_payment_01_full_payment_settled():
    """Payment Test 1: Full single payment on-time reconciles to SETTLED."""
    response = client.post("/api/payments/reconcile/BILL-BR02-201909", headers=OFFICER_HEADERS)
    assert response.status_code == 200
    rec = response.json()
    assert rec["reconciliation_status"] == "SETTLED"
    assert rec["outstanding_paise"] == 0
    assert rec["confirmed_paid_paise"] == rec["bill_amount_paise"]
    assert rec["linked_case_id"] is None

def test_payment_02_split_installments_settled():
    """Payment Test 2: Split / installment payments totaling exact bill reconcile to SETTLED."""
    response = client.post("/api/payments/reconcile/BILL-MH01-201909", headers=OFFICER_HEADERS)
    assert response.status_code == 200
    rec = response.json()
    assert rec["reconciliation_status"] == "SETTLED"
    assert len(rec["matched_transactions"]) == 2
    assert rec["outstanding_paise"] == 0

def test_payment_03_partial_payment():
    """Payment Test 3: Partial payment reconciles to PARTIALLY_PAID with correct outstanding balance in paise."""
    response = client.post("/api/payments/reconcile/BILL-BR03-201909", headers=OFFICER_HEADERS)
    assert response.status_code == 200
    rec = response.json()
    assert rec["reconciliation_status"] == "PARTIALLY_PAID"
    assert rec["confirmed_paid_paise"] == 50000
    assert rec["outstanding_paise"] == 70000
    assert rec["confirmed_paid_paise"] + rec["outstanding_paise"] == rec["bill_amount_paise"]

def test_payment_04_overpayment():
    """Payment Test 4: Overpayment reconciles to OVERPAID with correct credit balance in paise."""
    response = client.post("/api/payments/reconcile/BILL-MH02-201909", headers=OFFICER_HEADERS)
    assert response.status_code == 200
    rec = response.json()
    assert rec["reconciliation_status"] == "OVERPAID"
    assert rec["overpayment_paise"] == 37500
    assert rec["outstanding_paise"] == 0

def test_payment_05_unpaid_bill():
    """Payment Test 5: Unpaid bill reconciles to UNPAID with 100% outstanding balance."""
    response = client.post("/api/payments/reconcile/BILL-BR05-201911", headers=OFFICER_HEADERS)
    assert response.status_code == 200
    rec = response.json()
    assert rec["reconciliation_status"] == "UNPAID"
    assert rec["confirmed_paid_paise"] == 0
    assert rec["outstanding_paise"] == rec["bill_amount_paise"]

def test_payment_06_duplicate_candidate_detection():
    """Payment Test 6: Duplicate payment candidate detection triggers REQUIRES_REVIEW and auto-creates case."""
    response = client.post("/api/payments/reconcile/BILL-MH03-201910", headers=OFFICER_HEADERS)
    assert response.status_code == 200
    rec = response.json()
    assert rec["reconciliation_status"] == "REQUIRES_REVIEW"
    assert len(rec["duplicate_candidates"]) > 0
    assert rec["linked_case_id"] is not None
    assert "CASE-" in rec["linked_case_id"]

def test_payment_07_reversed_transaction_requires_review():
    """Payment Test 7: Reversed / chargeback transaction triggers REQUIRES_REVIEW."""
    response = client.post("/api/payments/reconcile/BILL-MH04-201911", headers=OFFICER_HEADERS)
    assert response.status_code == 200
    rec = response.json()
    assert rec["reconciliation_status"] == "REQUIRES_REVIEW"
    assert len(rec["reversed_transactions"]) > 0
    assert rec["linked_case_id"] is not None

def test_payment_08_failed_transaction_excluded():
    """Payment Test 8: Failed transaction excluded from confirmed paid calculation."""
    txs = get_synthetic_payments(bill_id="BILL-MH05-201910")
    rec = reconcile_bill_payments("BILL-MH05-201910")
    for tx in rec["reversed_transactions"]:
        assert tx["transaction_status"] in ["REVERSED", "FAILED"]
    assert rec["confirmed_paid_paise"] == 0

def test_payment_09_pending_transaction_excluded():
    """Payment Test 9: Pending transaction excluded from confirmed paid calculation."""
    rec = reconcile_bill_payments("BILL-BR08-201910")
    assert len(rec["pending_transactions"]) >= 1
    assert rec["confirmed_paid_paise"] == 0

def test_payment_10_unmatched_payment_transactions():
    """Payment Test 10: Unmatched payment transactions listed in summary endpoint."""
    response = client.get("/api/billing/summary")
    assert response.status_code == 200
    summary = response.json()
    assert summary["unmatched_payments_count"] >= 1
    all_txs = client.get("/api/payments/transactions").json()
    orphan_txs = [t for t in all_txs if t["bill_id"] is None]
    assert len(orphan_txs) >= 1

def test_payment_11_status_precedence_requires_review():
    """Payment Test 11: Status precedence: REQUIRES_REVIEW takes priority over partial or settled."""
    rec = reconcile_bill_payments("BILL-MH03-201910")
    assert rec["reconciliation_status"] == "REQUIRES_REVIEW"

def test_payment_12_reconciling_creates_audit_case_deduplicated():
    """Payment Test 12: Reconciling creates audit case for discrepancies, deduplicated by source_finding_id."""
    r1 = client.post("/api/payments/reconcile/BILL-MH03-201910", headers=OFFICER_HEADERS)
    r2 = client.post("/api/payments/reconcile/BILL-MH03-201910", headers=OFFICER_HEADERS)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["linked_case_id"] == r2.json()["linked_case_id"]

def test_payment_13_exact_integer_paise_reconciliation_balance():
    """Payment Test 13: Exact integer paise reconciliation balances."""
    for bill_id in ["BILL-BR02-201909", "BILL-BR03-201909", "BILL-MH01-201909", "BILL-MH02-201909"]:
        rec = reconcile_bill_payments(bill_id)
        if rec["reconciliation_status"] == "SETTLED":
            assert rec["confirmed_paid_paise"] == rec["bill_amount_paise"]
            assert rec["outstanding_paise"] == 0
        elif rec["reconciliation_status"] == "PARTIALLY_PAID":
            assert rec["confirmed_paid_paise"] + rec["outstanding_paise"] == rec["bill_amount_paise"]
        elif rec["reconciliation_status"] == "OVERPAID":
            assert rec["confirmed_paid_paise"] == rec["bill_amount_paise"] + rec["overpayment_paise"]

def test_payment_14_provenance_tag_on_all_outputs():
    """Payment Test 14: Provenance tag SYNTHETIC_DEMO present on all reconciliation outputs."""
    response = client.post("/api/payments/reconcile/BILL-BR02-201909", headers=OFFICER_HEADERS)
    assert response.status_code == 200
    assert response.json()["provenance"] == "SYNTHETIC_DEMO"

# ==============================================================================
# INTEGRATED SCENARIOS A TO J TESTS
# ==============================================================================

def test_scenario_a_standard_settled():
    """Scenario A: Standard on-time full payment (BR02)."""
    v = client.post("/api/billing/verify/BILL-BR02-201909", headers=OFFICER_HEADERS).json()
    r = client.post("/api/payments/reconcile/BILL-BR02-201909", headers=OFFICER_HEADERS).json()
    assert v["overall_result"] == "PASS"
    assert r["reconciliation_status"] == "SETTLED"

def test_scenario_b_unit_mismatch():
    """Scenario B: Unit mismatch flagged (BR02 2019-10)."""
    v = client.post("/api/billing/verify/BILL-BR02-201910", headers=OFFICER_HEADERS).json()
    assert v["overall_result"] == "FLAGGED"
    assert v["units_check_status"] == "FLAGGED"

def test_scenario_c_tariff_calc_error():
    """Scenario C: Tariff calculation error flagged (BR03 2019-11)."""
    v = client.post("/api/billing/verify/BILL-BR03-201911", headers=OFFICER_HEADERS).json()
    assert v["overall_result"] == "FLAGGED"
    assert v["amount_check_status"] == "FLAGGED"

def test_scenario_d_missing_telemetry():
    """Scenario D: Incomplete telemetry flagged (BR02 2020-05)."""
    v = client.post("/api/billing/verify/BILL-BR02-202005", headers=OFFICER_HEADERS).json()
    assert v["overall_result"] == "FLAGGED"
    assert v["coverage_status"] == "INSUFFICIENT"

def test_scenario_e_zero_consumption():
    """Scenario E: Zero consumption unoccupied premises (BR06 2019-09)."""
    v = client.post("/api/billing/verify/BILL-BR06-201909-ZC", headers=OFFICER_HEADERS).json()
    assert v["billed_units"] == 0.0
    assert v["overall_result"] in ["PASS", "FLAGGED"]

def test_scenario_f_extreme_high_bill():
    """Scenario F: Extreme high bill flagged (BR07 2019-09)."""
    v = client.post("/api/billing/verify/BILL-BR07-201909-HB", headers=OFFICER_HEADERS).json()
    assert v["overall_result"] == "FLAGGED"

def test_scenario_g_arrears():
    """Scenario G: Arrears carried over (BR08 2019-09)."""
    v = client.post("/api/billing/verify/BILL-BR08-201909-AR", headers=OFFICER_HEADERS).json()
    assert v["overall_result"] == "FLAGGED"

def test_scenario_h_partial_payment():
    """Scenario H: Partial payment with outstanding balance (BR03 2019-09)."""
    r = client.post("/api/payments/reconcile/BILL-BR03-201909", headers=OFFICER_HEADERS).json()
    assert r["reconciliation_status"] == "PARTIALLY_PAID"
    assert r["outstanding_paise"] > 0

def test_scenario_i_split_payment():
    """Scenario I: Two split installment payments (MH01 2019-09)."""
    r = client.post("/api/payments/reconcile/BILL-MH01-201909", headers=OFFICER_HEADERS).json()
    assert r["reconciliation_status"] == "SETTLED"
    assert len(r["matched_transactions"]) == 2

def test_scenario_j_duplicate_receipt_and_reversal():
    """Scenario J: Duplicate receipt detection & reversal (MH03 & MH04)."""
    r_dup = client.post("/api/payments/reconcile/BILL-MH03-201910", headers=OFFICER_HEADERS).json()
    r_rev = client.post("/api/payments/reconcile/BILL-MH04-201911", headers=OFFICER_HEADERS).json()
    assert r_dup["reconciliation_status"] == "REQUIRES_REVIEW"
    assert r_rev["reconciliation_status"] == "REQUIRES_REVIEW"
