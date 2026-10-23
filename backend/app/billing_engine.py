import uuid
import json
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np

from .data_pipeline import run_pipeline
from .database import (
    get_account_by_id,
    get_all_tariffs,
    get_active_tariff,
    get_synthetic_bill_by_id,
    get_synthetic_bills,
    get_synthetic_payments,
    save_billing_verification_result,
    get_billing_verification_history,
    save_payment_reconciliation_result,
    get_payment_reconciliation_history,
    create_case,
    record_case_decision,
    get_case_by_id,
    reconcile_billing_finding_on_run,
)

# Business Tolerances
UNIT_TOLERANCE_KWH = 1.0         # Allow up to 1 kWh measurement/rounding difference
AMOUNT_TOLERANCE_PAISE = 100     # Allow up to 100 paise (₹1.00) currency rounding difference
COVERAGE_THRESHOLD = 0.80        # Minimum 80% daily readings required for complete verification

def calculate_metered_consumption(
    meter_id: str,
    period_start: str,
    period_end: str,
    df_analyzed: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Calculates exact aggregate consumption from smart meter daily intervals
    and determines period coverage completeness.
    """
    if df_analyzed is None:
        df_analyzed, _, _ = run_pipeline()

    start_d = pd.to_datetime(period_start, errors="coerce")
    end_d = pd.to_datetime(period_end, errors="coerce")

    if pd.isna(start_d) or pd.isna(end_d) or start_d > end_d:
        return {
            "metered_units": 0.0,
            "days_observed": 0,
            "expected_days": 0,
            "coverage_ratio": 0.0,
            "coverage_status": "INVALID_PERIOD",
            "notes": f"Invalid date period range: {period_start} to {period_end}",
        }

    expected_days = (end_d - start_d).days + 1

    # Filter dataframe for meter and period
    meter_df = df_analyzed[
        (df_analyzed["meter_id"] == meter_id) &
        (df_analyzed["date"] >= period_start) &
        (df_analyzed["date"] <= period_end)
    ].copy()

    days_observed = int(meter_df["date"].nunique()) if not meter_df.empty else 0
    coverage_ratio = days_observed / max(expected_days, 1)

    if days_observed == 0:
        return {
            "metered_units": None,
            "days_observed": 0,
            "expected_days": expected_days,
            "coverage_ratio": 0.0,
            "coverage_status": "NONE",
            "notes": f"No smart meter intervals recorded between {period_start} and {period_end}.",
        }

    sum_kwh = float(meter_df["kwh"].sum())

    if coverage_ratio < COVERAGE_THRESHOLD:
        status = "INSUFFICIENT"
        notes = f"Partial interval coverage ({days_observed}/{expected_days} days, {coverage_ratio*100:.1f}%). Below {COVERAGE_THRESHOLD*100:.0f}% threshold."
    else:
        status = "COMPLETE"
        notes = f"Complete interval coverage ({days_observed}/{expected_days} days, {coverage_ratio*100:.1f}%)."

    return {
        "metered_units": round(sum_kwh, 2),
        "days_observed": days_observed,
        "expected_days": expected_days,
        "coverage_ratio": round(coverage_ratio, 3),
        "coverage_status": status,
        "notes": notes,
    }


def verify_synthetic_bill(
    bill_id: str,
    actor_id: str = "system",
    actor_role: str = "VERIFICATION_OFFICER",
    auto_create_case: bool = True,
    is_recurrence: bool = False,
) -> Dict[str, Any]:
    """
    Executes modular 4-step billing verification for a synthetic bill:
    1. Resolve account, meter, and applicable tariff.
    2. Aggregate metered interval consumption and assess coverage completeness.
    3. Compare metered vs billed units.
    4. Validate expected bill total using exact integer-paise tariff math.
    """
    bill = get_synthetic_bill_by_id(bill_id)
    if not bill:
        raise ValueError(f"Synthetic bill '{bill_id}' not found.")

    account = get_account_by_id(bill["account_id"])
    if not account:
        raise ValueError(f"Consumer account '{bill['account_id']}' not found.")

    now_str = datetime.utcnow().isoformat() + "Z"
    check_id = f"BCHK-{datetime.utcnow().strftime('%Y%m')}-{str(uuid.uuid4())[:8].upper()}"

    # Step 1: Resolve Applicable Tariff
    tariff = get_active_tariff(as_of_date=bill["period_start"])
    if not tariff:
        # Fallback to any active tariff
        tariffs = get_all_tariffs()
        tariff = tariffs[0] if tariffs else None

    tariff_snapshot = {
        "tariff_id": tariff["tariff_id"] if tariff else "NONE",
        "tariff_name": tariff["tariff_name"] if tariff else "No Tariff Available",
        "rate_per_kwh_paise": tariff["rate_per_kwh_paise"] if tariff else 0,
        "fixed_charge_paise": tariff["fixed_charge_paise"] if tariff else 0,
        "currency": tariff["currency"] if tariff else "INR",
    }

    # Step 2: Check for Duplicate Bills in the database for the same account & period
    all_account_bills, _ = get_synthetic_bills(account_id=bill["account_id"], page_size=100)
    overlapping_bills = [
        b for b in all_account_bills
        if b["bill_id"] != bill_id and (
            (b["period_start"] <= bill["period_end"] and b["period_end"] >= bill["period_start"])
        )
    ]
    is_duplicate = len(overlapping_bills) > 0

    # Step 3: Calculate metered consumption
    meter_analysis = calculate_metered_consumption(
        meter_id=bill["meter_id"],
        period_start=bill["period_start"],
        period_end=bill["period_end"],
    )

    metered_units = meter_analysis["metered_units"]
    billed_units = bill["consumed_units_kwh"]
    coverage_status = meter_analysis["coverage_status"]

    # Step 4: Evaluate Units Check
    if coverage_status in ["NONE", "INVALID_PERIOD"]:
        units_check_status = "NOT_ASSESSED"
        unit_difference = None
    elif coverage_status == "INSUFFICIENT":
        units_check_status = "FLAGGED"
        unit_difference = round(billed_units - (metered_units or 0.0), 2)
    else:
        unit_difference = round(billed_units - metered_units, 2)
        if abs(unit_difference) <= UNIT_TOLERANCE_KWH:
            units_check_status = "PASS"
        else:
            units_check_status = "FLAGGED"

    # Step 5: Evaluate Bill Amount Math
    if not tariff:
        amount_check_status = "NOT_ASSESSED"
        expected_bill_amount_paise = None
        amount_difference_paise = None
        reason = "TARIFF_UNAVAILABLE"
    else:
        # Energy charge = round(units * rate_paise)
        # Expected bill = energy_charge + fixed_charge
        calc_units = metered_units if metered_units is not None else billed_units
        energy_charge_paise = round(calc_units * tariff["rate_per_kwh_paise"])
        expected_bill_amount_paise = energy_charge_paise + tariff["fixed_charge_paise"]
        amount_difference_paise = bill["bill_amount_paise"] - expected_bill_amount_paise

        # Also verify if the bill amount is at least mathematically consistent with the billed units on the bill
        billed_math_paise = round(billed_units * tariff["rate_per_kwh_paise"]) + tariff["fixed_charge_paise"]
        internal_math_mismatch = abs(bill["bill_amount_paise"] - billed_math_paise) > AMOUNT_TOLERANCE_PAISE

        if internal_math_mismatch or abs(amount_difference_paise) > AMOUNT_TOLERANCE_PAISE:
            amount_check_status = "FLAGGED"
        else:
            amount_check_status = "PASS"

    # Step 6: Determine Overall Result & Specific Reason
    if is_duplicate:
        overall_result = "FLAGGED"
        reason = "DUPLICATE_BILL"
    elif coverage_status == "NONE":
        overall_result = "NOT_ASSESSED"
        reason = "NO_METER_DATA_AVAILABLE"
    elif coverage_status == "INSUFFICIENT":
        overall_result = "FLAGGED"
        reason = "INSUFFICIENT_METER_COVERAGE"
    elif units_check_status == "FLAGGED":
        overall_result = "FLAGGED"
        reason = "UNIT_MISMATCH"
    elif amount_check_status == "FLAGGED":
        overall_result = "FLAGGED"
        reason = "BILL_AMOUNT_MISMATCH"
    elif units_check_status == "PASS" and amount_check_status == "PASS":
        overall_result = "PASS"
        reason = "VERIFIED_MATCH"
    else:
        overall_result = "NOT_ASSESSED"
        reason = "DATA_INCOMPLETE"

    # Step 7: Case Creation & Finding Reconciliation for Discrepancies
    linked_case_id = None
    finding_dict = None
    case_dict = None
    if overall_result == "FLAGGED" and auto_create_case:
        finding_dict, case_dict, is_new = reconcile_billing_finding_on_run(
            bill_id=bill_id,
            account_id=account["account_id"],
            meter_id=bill["meter_id"],
            reason=reason,
            run_id=check_id,
            actor_id=actor_id,
            actor_role=actor_role,
            is_recurrence=is_recurrence,
        )
        linked_case_id = case_dict["case_id"] if case_dict else (finding_dict.get("linked_case_id") if finding_dict else None)

    record = {
        "billing_check_id": check_id,
        "bill_id": bill_id,
        "account_id": bill["account_id"],
        "billing_period": f"{bill['period_start']} to {bill['period_end']}",
        "metered_units": metered_units,
        "billed_units": billed_units,
        "unit_difference": unit_difference,
        "configured_tariff_snapshot_json": json.dumps(tariff_snapshot),
        "expected_bill_amount_paise": expected_bill_amount_paise,
        "billed_amount_paise": bill["bill_amount_paise"],
        "amount_difference_paise": amount_difference_paise,
        "coverage_status": coverage_status,
        "units_check_status": units_check_status,
        "amount_check_status": amount_check_status,
        "overall_result": overall_result,
        "reason": reason,
        "linked_case_id": linked_case_id,
        "provenance": "SYNTHETIC_DEMO",
        "evaluated_at": now_str,
    }

    save_billing_verification_result(record)
    record["tariff_snapshot"] = tariff_snapshot
    record["coverage_details"] = meter_analysis
    if case_dict:
        record["case_status"] = case_dict.get("status")
        record["review_decision"] = case_dict.get("decision")
        record["decision_reason"] = case_dict.get("decision_reason")
        record["resolved_at"] = case_dict.get("resolved_at")
    elif linked_case_id:
        c = get_case_by_id(linked_case_id)
        if c:
            record["case_status"] = c.get("status")
            record["review_decision"] = c.get("decision")
            record["decision_reason"] = c.get("decision_reason")
            record["resolved_at"] = c.get("resolved_at")

    if finding_dict:
        record["review_status"] = finding_dict.get("review_status")
        record["is_recurring"] = bool(finding_dict.get("is_recurring", 0))

    return record



def reconcile_bill_payments(
    bill_id: str,
    actor_id: str = "system",
    actor_role: str = "VERIFICATION_OFFICER",
    auto_create_case: bool = True,
) -> Dict[str, Any]:
    """
    Executes payment reconciliation for a bill:
    1. Collects all matching payment transactions by exact bill_id.
    2. Identifies unmatched payments for the account.
    3. Detects duplicate payment candidates (identical receipts/transaction amounts).
    4. Segregates SETTLED, PENDING, FAILED, and REVERSED transactions.
    5. Computes exact confirmed_paid, outstanding, and overpayment in integer paise.
    6. Determines formal reconciliation status and creates actionable case if review required.
    """
    bill = get_synthetic_bill_by_id(bill_id)
    if not bill:
        raise ValueError(f"Synthetic bill '{bill_id}' not found.")

    account = get_account_by_id(bill["account_id"])
    if not account:
        raise ValueError(f"Account '{bill['account_id']}' not found.")

    now_str = datetime.utcnow().isoformat() + "Z"
    recon_id = f"RECON-{datetime.utcnow().strftime('%Y%m')}-{str(uuid.uuid4())[:8].upper()}"

    # 1. Fetch related transactions
    related_txns = get_synthetic_payments(bill_id=bill_id)

    # 2. Fetch unmatched transactions for this account
    unmatched_account_txns = get_synthetic_payments(account_id=bill["account_id"], unmatched_only=True)

    matched = []
    duplicate_candidates = []
    pending = []
    reversed_txns = []
    failed = []

    # Check for duplicate candidates (same receipt_id or identical date + amount)
    receipt_seen: Dict[str, str] = {}
    eligible_settled_txns = []

    for tx in related_txns:
        st = tx["transaction_status"]
        r_id = tx.get("receipt_id")

        if st == "PENDING":
            pending.append(tx)
        elif st == "FAILED":
            failed.append(tx)
        elif st == "REVERSED":
            reversed_txns.append(tx)
        elif st == "SETTLED":
            # Check duplicate receipt
            if r_id and r_id in receipt_seen:
                duplicate_candidates.append({
                    "primary_txn": receipt_seen[r_id],
                    "duplicate_txn": tx["transaction_id"],
                    "receipt_id": r_id,
                    "amount_paise": tx["amount_paise"],
                })
            else:
                if r_id:
                    receipt_seen[r_id] = tx["transaction_id"]
                eligible_settled_txns.append(tx)
            matched.append(tx)

    # 3. Sum confirmed payments (only unique eligible settled transactions)
    confirmed_paid_paise = sum(tx["amount_paise"] for tx in eligible_settled_txns)
    bill_amount_paise = bill["bill_amount_paise"]

    outstanding_paise = max(0, bill_amount_paise - confirmed_paid_paise)
    overpayment_paise = max(0, confirmed_paid_paise - bill_amount_paise)

    # 4. Status Precedence
    reasons = []
    if len(duplicate_candidates) > 0:
        reconciliation_status = "REQUIRES_REVIEW"
        reasons.append("DUPLICATE_PAYMENT_CANDIDATE")
    elif len(reversed_txns) > 0:
        reconciliation_status = "REQUIRES_REVIEW"
        reasons.append("PAYMENT_REVERSED")
    elif confirmed_paid_paise == 0:
        reconciliation_status = "UNPAID"
        reasons.append("ZERO_PAYMENTS_RECORDED")
    elif outstanding_paise > 0:
        reconciliation_status = "PARTIALLY_PAID"
        reasons.append(f"PARTIAL_PAYMENT_OUTSTANDING_{outstanding_paise}")
    elif overpayment_paise > 0:
        reconciliation_status = "OVERPAID"
        reasons.append(f"OVERPAYMENT_CREDIT_{overpayment_paise}")
    else:
        reconciliation_status = "SETTLED"
        reasons.append("EXACT_SETTLEMENT_VERIFIED")

    # 5. Case creation for anomalies / review requirements
    linked_case_id = None
    if reconciliation_status == "REQUIRES_REVIEW" and auto_create_case:
        finding_id = f"RECON_REVIEW_{bill_id}"
        desc = (
            f"[SYNTHETIC DEMO EVALUATION] Payment reconciliation for bill {bill_id} flagged for review. "
            f"Duplicate payment candidate detected: {len(duplicate_candidates)} instance(s). "
            f"Bill Amount: ₹{bill_amount_paise/100:.2f}, Confirmed Paid: ₹{confirmed_paid_paise/100:.2f}."
        )
        case, _ = create_case(
            source_finding_id=finding_id,
            account_id=account["account_id"],
            consumer_id=account["consumer_id"],
            meter_id=bill["meter_id"],
            title=f"Payment Reconciliation Review: {bill_id}",
            description=desc,
            finding_category="PAYMENT_RECONCILIATION",
            severity="HIGH",
            priority="HIGH",
            actor_id=actor_id,
            actor_role=actor_role,
        )
        linked_case_id = case["case_id"]

    record = {
        "reconciliation_id": recon_id,
        "bill_id": bill_id,
        "account_id": bill["account_id"],
        "bill_amount_paise": bill_amount_paise,
        "confirmed_paid_paise": confirmed_paid_paise,
        "outstanding_paise": outstanding_paise,
        "overpayment_paise": overpayment_paise,
        "matched_transactions_json": json.dumps(matched),
        "unmatched_transactions_json": json.dumps(unmatched_account_txns),
        "duplicate_candidates_json": json.dumps(duplicate_candidates),
        "pending_transactions_json": json.dumps(pending),
        "reversed_transactions_json": json.dumps(reversed_txns),
        "reconciliation_status": reconciliation_status,
        "reasons_json": json.dumps(reasons),
        "linked_case_id": linked_case_id,
        "provenance": "SYNTHETIC_DEMO",
        "evaluated_at": now_str,
    }

    save_payment_reconciliation_result(record)

    record["matched_transactions"] = matched
    record["unmatched_transactions"] = unmatched_account_txns
    record["duplicate_candidates"] = duplicate_candidates
    record["pending_transactions"] = pending
    record["reversed_transactions"] = reversed_txns
    record["reasons"] = reasons
    return record
