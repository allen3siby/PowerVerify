import sqlite3
import os
import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "powerverify_lite.db")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

get_db = get_connection

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Existing Observation status tracking per observation
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS observation_status (
        observation_id TEXT PRIMARY KEY,
        meter_id TEXT NOT NULL,
        date TEXT NOT NULL,
        kwh REAL NOT NULL,
        anomaly_direction TEXT NOT NULL,
        current_status TEXT NOT NULL DEFAULT 'Pending Review',
        updated_at TEXT NOT NULL
    );
    """)

    # 2. Existing Review decisions audit log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS review_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        observation_id TEXT NOT NULL,
        meter_id TEXT NOT NULL,
        date TEXT NOT NULL,
        decision TEXT NOT NULL,
        notes TEXT,
        previous_status TEXT NOT NULL,
        new_status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (observation_id) REFERENCES observation_status (observation_id)
    );
    """)

    # 3. Model run metadata tracking
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS model_runs (
        run_id TEXT PRIMARY KEY,
        model_name TEXT NOT NULL,
        contamination REAL NOT NULL,
        n_estimators INTEGER NOT NULL,
        random_state INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'COMPLETED',
        records_analyzed INTEGER NOT NULL DEFAULT 0,
        anomalies_flagged INTEGER NOT NULL DEFAULT 0,
        high_anomalies INTEGER NOT NULL DEFAULT 0,
        low_anomalies INTEGER NOT NULL DEFAULT 0,
        pattern_anomalies INTEGER NOT NULL DEFAULT 0,
        statistical_anomalies INTEGER NOT NULL DEFAULT 0,
        features_used TEXT,
        dataset_fingerprint TEXT,
        flagged_observation_ids TEXT,
        started_at TEXT,
        completed_at TEXT,
        is_active INTEGER NOT NULL DEFAULT 0,
        error_message TEXT,
        created_at TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS active_model_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        contamination REAL NOT NULL DEFAULT 0.03,
        n_estimators INTEGER NOT NULL DEFAULT 150,
        random_state INTEGER NOT NULL DEFAULT 42,
        active_run_id TEXT,
        updated_at TEXT NOT NULL
    );
    """)

    # 4. Consumer Accounts registry
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        account_id TEXT PRIMARY KEY,
        consumer_id TEXT NOT NULL,
        meter_id TEXT NOT NULL UNIQUE,
        consumer_name TEXT NOT NULL,
        district TEXT NOT NULL,
        address TEXT NOT NULL,
        tariff_category TEXT NOT NULL,
        sanctioned_load_kw REAL NOT NULL,
        connection_status TEXT NOT NULL DEFAULT 'ACTIVE',
        connection_date TEXT NOT NULL,
        billing_account_id TEXT,
        bill_id TEXT,
        payment_transaction_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 5. Verification Runs (Account Verification Engine History)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS verification_runs (
        verification_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        consumer_id TEXT NOT NULL,
        meter_id TEXT NOT NULL,
        evaluated_at TEXT NOT NULL,
        scope TEXT NOT NULL,
        overall_status TEXT NOT NULL,
        ruleset_version TEXT NOT NULL,
        model_version TEXT NOT NULL,
        total_checks INTEGER NOT NULL,
        passed_checks INTEGER NOT NULL,
        flagged_checks INTEGER NOT NULL,
        not_assessed_checks INTEGER NOT NULL,
        error_checks INTEGER NOT NULL,
        summary_findings TEXT NOT NULL,
        raw_evidence_refs TEXT,
        FOREIGN KEY (account_id) REFERENCES accounts (account_id)
    );
    """)

    # 6. Verification Individual Check Results
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS verification_check_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        verification_id TEXT NOT NULL,
        check_code TEXT NOT NULL,
        check_name TEXT NOT NULL,
        status TEXT NOT NULL,
        severity TEXT NOT NULL,
        findings TEXT NOT NULL,
        evidence_detail TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (verification_id) REFERENCES verification_runs (verification_id) ON DELETE CASCADE
    );
    """)

    # 7. Verification Cases (Case Management)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cases (
        case_id TEXT PRIMARY KEY,
        verification_id TEXT,
        source_finding_id TEXT NOT NULL UNIQUE,
        account_id TEXT NOT NULL,
        consumer_id TEXT NOT NULL,
        meter_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        finding_category TEXT NOT NULL,
        severity TEXT NOT NULL,
        priority TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        assigned_officer TEXT NOT NULL DEFAULT 'Unassigned',
        decision TEXT NOT NULL DEFAULT 'PENDING',
        decision_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        resolved_at TEXT,
        closed_at TEXT
    );
    """)

    # 8. Case Notes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS case_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT NOT NULL,
        author_id TEXT NOT NULL,
        author_role TEXT NOT NULL,
        note_text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (case_id) REFERENCES cases (case_id) ON DELETE CASCADE
    );
    """)

    # 9. Case Audit Events (Persistent, Append-Only Audit Trail)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS case_audit_events (
        event_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        actor_role TEXT NOT NULL,
        action TEXT NOT NULL,
        previous_value TEXT,
        new_value TEXT,
        reason TEXT NOT NULL,
        metadata_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (case_id) REFERENCES cases (case_id) ON DELETE CASCADE
    );
    """)

    # 10. Tariff Rules
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tariff_rules (
        tariff_id TEXT PRIMARY KEY,
        tariff_name TEXT NOT NULL,
        effective_from TEXT NOT NULL,
        effective_to TEXT,
        rate_per_kwh_paise INTEGER NOT NULL,
        fixed_charge_paise INTEGER NOT NULL,
        currency TEXT NOT NULL DEFAULT 'INR',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 11. Synthetic Bills (Exact integer paise for monetary arithmetic)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS synthetic_bills (
        bill_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        meter_id TEXT NOT NULL,
        bill_date TEXT NOT NULL,
        period_start TEXT NOT NULL,
        period_end TEXT NOT NULL,
        consumed_units_kwh REAL NOT NULL,
        bill_amount_paise INTEGER NOT NULL,
        scenario_label TEXT NOT NULL,
        provenance TEXT NOT NULL DEFAULT 'SYNTHETIC_DEMO',
        is_synthetic INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts (account_id)
    );
    """)

    # 12. Synthetic Payments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS synthetic_payments (
        transaction_id TEXT PRIMARY KEY,
        bill_id TEXT,
        account_id TEXT NOT NULL,
        payment_date TEXT NOT NULL,
        amount_paise INTEGER NOT NULL,
        receipt_id TEXT,
        transaction_status TEXT NOT NULL,
        scenario_label TEXT NOT NULL,
        provenance TEXT NOT NULL DEFAULT 'SYNTHETIC_DEMO',
        is_synthetic INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (bill_id) REFERENCES synthetic_bills (bill_id),
        FOREIGN KEY (account_id) REFERENCES accounts (account_id)
    );
    """)

    # 13. Billing Verification Results
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS billing_verification_results (
        billing_check_id TEXT PRIMARY KEY,
        bill_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        billing_period TEXT NOT NULL,
        metered_units REAL,
        billed_units REAL NOT NULL,
        unit_difference REAL,
        configured_tariff_snapshot_json TEXT NOT NULL,
        expected_bill_amount_paise INTEGER,
        billed_amount_paise INTEGER NOT NULL,
        amount_difference_paise INTEGER,
        coverage_status TEXT NOT NULL,
        units_check_status TEXT NOT NULL,
        amount_check_status TEXT NOT NULL,
        overall_result TEXT NOT NULL,
        reason TEXT NOT NULL,
        linked_case_id TEXT,
        provenance TEXT NOT NULL DEFAULT 'SYNTHETIC_DEMO',
        evaluated_at TEXT NOT NULL,
        FOREIGN KEY (bill_id) REFERENCES synthetic_bills (bill_id),
        FOREIGN KEY (account_id) REFERENCES accounts (account_id)
    );
    """)

    # 14. Payment Reconciliation Results
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payment_reconciliation_results (
        reconciliation_id TEXT PRIMARY KEY,
        bill_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        bill_amount_paise INTEGER NOT NULL,
        confirmed_paid_paise INTEGER NOT NULL,
        outstanding_paise INTEGER NOT NULL,
        overpayment_paise INTEGER NOT NULL,
        matched_transactions_json TEXT NOT NULL,
        unmatched_transactions_json TEXT NOT NULL,
        duplicate_candidates_json TEXT NOT NULL,
        pending_transactions_json TEXT NOT NULL,
        reversed_transactions_json TEXT NOT NULL,
        reconciliation_status TEXT NOT NULL,
        reasons_json TEXT NOT NULL,
        linked_case_id TEXT,
        provenance TEXT NOT NULL DEFAULT 'SYNTHETIC_DEMO',
        evaluated_at TEXT NOT NULL,
        FOREIGN KEY (bill_id) REFERENCES synthetic_bills (bill_id),
        FOREIGN KEY (account_id) REFERENCES accounts (account_id)
    );
    """)

    # 15. Persistent Billing Findings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS billing_findings (
        finding_id TEXT PRIMARY KEY,
        bill_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        meter_id TEXT,
        finding_category TEXT NOT NULL DEFAULT 'BILLING_DISCREPANCY',
        reason TEXT NOT NULL,
        first_detected_at TEXT NOT NULL,
        latest_observed_at TEXT NOT NULL,
        latest_verification_run_id TEXT,
        review_status TEXT NOT NULL DEFAULT 'PENDING',
        review_decision TEXT DEFAULT 'PENDING',
        decision_reason TEXT,
        decision_by TEXT,
        decision_at TEXT,
        linked_case_id TEXT,
        occurrence_count INTEGER NOT NULL DEFAULT 1,
        is_recurring INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (bill_id) REFERENCES synthetic_bills (bill_id),
        FOREIGN KEY (account_id) REFERENCES accounts (account_id),
        FOREIGN KEY (linked_case_id) REFERENCES cases (case_id)
    );
    """)

    # Performance and query indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_meter ON cases(meter_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_account ON cases(account_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_finding ON cases(source_finding_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_case ON case_audit_events(case_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_verif_account ON verification_runs(account_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_verif_checks ON verification_check_results(verification_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_account ON synthetic_bills(account_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_meter ON synthetic_bills(meter_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_scenario ON synthetic_bills(scenario_label);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_bill ON synthetic_payments(bill_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_account ON synthetic_payments(account_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON synthetic_payments(transaction_status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_billing_verif_bill ON billing_verification_results(bill_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recon_bill ON payment_reconciliation_results(bill_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_billing_findings_bill ON billing_findings(bill_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_billing_findings_case ON billing_findings(linked_case_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_billing_findings_status ON billing_findings(review_status);")

    conn.commit()
    conn.close()

    # Seed initial accounts and demonstration billing/payment scenarios
    seed_accounts_if_empty()
    seed_billing_and_payments_if_empty()
    migrate_billing_findings_if_needed()
    migrate_model_runs_if_needed()
    migrate_verification_runs_if_needed()


def seed_accounts_if_empty():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM accounts")
    row = cursor.fetchone()
    if row and row["cnt"] > 0:
        conn.close()
        return

    now_str = datetime.utcnow().isoformat() + "Z"
    # Seed 84 standard CEEW meters: BR01-BR49, MH01-MH49
    # (Matches real CEEW smart meter study roster)
    seed_accounts = []
    for i in range(1, 50):
        m_id = f"BR{i:02d}"
        seed_accounts.append((
            f"ACCT-{m_id}",
            f"CONS-{m_id}",
            m_id,
            f"Consumer {m_id} (Bareilly)",
            "Bareilly",
            f"House {100+i}, Sector {((i % 7) + 1):02d}, Bareilly, UP",
            "Commercial (LMV-2)" if i % 5 == 0 else "Domestic (LMV-1)",
            5.0 if i % 5 == 0 else 3.0,
            "ACTIVE",
            "2019-05-01",
            None,
            None,
            None,
            now_str,
            now_str,
        ))

    for i in range(1, 50):
        m_id = f"MH{i:02d}"
        seed_accounts.append((
            f"ACCT-{m_id}",
            f"CONS-{m_id}",
            m_id,
            f"Consumer {m_id} (Mathura)",
            "Mathura",
            f"Plot {200+i}, Krishna Nagar, Mathura, UP",
            "Commercial (LMV-2)" if i % 5 == 0 else "Domestic (LMV-1)",
            5.0 if i % 5 == 0 else 3.0,
            "ACTIVE",
            "2019-05-01",
            None,
            None,
            None,
            now_str,
            now_str,
        ))

    cursor.executemany("""
    INSERT OR IGNORE INTO accounts (
        account_id, consumer_id, meter_id, consumer_name, district, address,
        tariff_category, sanctioned_load_kw, connection_status, connection_date,
        billing_account_id, bill_id, payment_transaction_id, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, seed_accounts)

    conn.commit()
    conn.close()

# -------------------------------------------------------------
# Existing Observation Status & Review Decisions Functions
# -------------------------------------------------------------

def record_decision(
    observation_id: str,
    meter_id: str,
    date: str,
    kwh: float,
    anomaly_direction: str,
    decision: str,
    notes: Optional[str] = None,
    actor_id: str = "officer_sharma",
    actor_role: str = "VERIFICATION_OFFICER"
) -> Dict[str, Any]:
    """
    Valid decisions:
    - 'Acknowledge / No Further Action'
    - 'Mark for Field Visit'
    - 'High Usage Authorized'
    """
    allowed_decisions = {
        "Acknowledge / No Further Action",
        "Mark for Field Visit",
        "High Usage Authorized",
    }
    if decision not in allowed_decisions:
        raise ValueError(f"Invalid review decision '{decision}'. Allowed: {list(allowed_decisions)}")

    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"

    # Get current status if exists
    cursor.execute("SELECT current_status FROM observation_status WHERE observation_id = ?", (observation_id,))
    row = cursor.fetchone()
    previous_status = row["current_status"] if row else "Pending Review"
    new_status = decision

    # Idempotency check: if the latest decision is identical to the incoming one, avoid duplicate audit row
    cursor.execute("""
    SELECT decision, notes FROM review_decisions 
    WHERE observation_id = ? 
    ORDER BY id DESC LIMIT 1
    """, (observation_id,))
    last_rec = cursor.fetchone()
    is_duplicate = False
    if last_rec and last_rec["decision"] == decision and (last_rec["notes"] or "") == (notes or ""):
        is_duplicate = True

    # Upsert current status in observation_status
    cursor.execute("""
    INSERT INTO observation_status (observation_id, meter_id, date, kwh, anomaly_direction, current_status, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(observation_id) DO UPDATE SET
        current_status = excluded.current_status,
        updated_at = excluded.updated_at;
    """, (observation_id, meter_id, date, kwh, anomaly_direction, new_status, now_str))

    # Append to decision log only if not an exact retry
    if not is_duplicate:
        cursor.execute("""
        INSERT INTO review_decisions (observation_id, meter_id, date, decision, notes, previous_status, new_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (observation_id, meter_id, date, decision, notes or "", previous_status, new_status, now_str))

    conn.commit()
    conn.close()

    # Automatically sync to linked case
    sync_observation_decision_to_case(observation_id, decision, notes or "", now_str)

    return {
        "observation_id": observation_id,
        "meter_id": meter_id,
        "date": date,
        "previous_status": previous_status,
        "new_status": new_status,
        "review_status": "REVIEWED",
        "review_decision": new_status,
        "notes": notes or "",
        "actor_id": actor_id,
        "actor_role": actor_role,
        "timestamp": now_str,
        "is_retry": is_duplicate
    }

def get_observation_status_map() -> Dict[str, str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT observation_id, current_status FROM observation_status")
    status_map = {row["observation_id"]: row["current_status"] for row in cursor.fetchall()}
    conn.close()
    return status_map

def get_all_observation_statuses() -> Dict[str, Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT observation_id, current_status, updated_at FROM observation_status")
    res = {}
    for row in cursor.fetchall():
        decision = row["current_status"]
        is_pending = decision in ("Pending Review", "PENDING", None)
        res[row["observation_id"]] = {
            "current_status": decision,
            "review_status": "PENDING" if is_pending else "REVIEWED",
            "review_decision": "PENDING" if is_pending else decision,
            "updated_at": row["updated_at"]
        }
    conn.close()
    return res

def get_anomaly_case_map() -> Dict[str, str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT source_finding_id, status FROM cases WHERE source_finding_id LIKE 'ANOM_%'")
    case_map = {}
    for row in cursor.fetchall():
        obs_id = row["source_finding_id"].replace("ANOM_", "", 1)
        case_map[obs_id] = row["status"]
    conn.close()
    return case_map

def get_decision_history(observation_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, observation_id, meter_id, date, decision, notes, previous_status, new_status, created_at
    FROM review_decisions
    WHERE observation_id = ?
    ORDER BY id DESC
    """, (observation_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_decisions() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, observation_id, meter_id, date, decision, notes, previous_status, new_status, created_at
    FROM review_decisions
    ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# -------------------------------------------------------------
# Account Repository Functions
# -------------------------------------------------------------

def get_accounts(search: Optional[str] = None, district: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM accounts WHERE 1=1"
    params = []

    if search:
        s = f"%{search.strip().lower()}%"
        query += " AND (LOWER(account_id) LIKE ? OR LOWER(consumer_id) LIKE ? OR LOWER(meter_id) LIKE ? OR LOWER(consumer_name) LIKE ?)"
        params.extend([s, s, s, s])

    if district and district != "all":
        query += " AND district = ?"
        params.append(district)

    query += " ORDER BY meter_id ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_account_by_id(account_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE account_id = ? OR consumer_id = ?", (account_id, account_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_account_by_meter_id(meter_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE meter_id = ?", (meter_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def save_account(account_data: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"
    
    cursor.execute("""
    INSERT INTO accounts (
        account_id, consumer_id, meter_id, consumer_name, district, address,
        tariff_category, sanctioned_load_kw, connection_status, connection_date,
        billing_account_id, bill_id, payment_transaction_id, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(account_id) DO UPDATE SET
        consumer_name = excluded.consumer_name,
        district = excluded.district,
        address = excluded.address,
        tariff_category = excluded.tariff_category,
        sanctioned_load_kw = excluded.sanctioned_load_kw,
        connection_status = excluded.connection_status,
        billing_account_id = excluded.billing_account_id,
        bill_id = excluded.bill_id,
        payment_transaction_id = excluded.payment_transaction_id,
        updated_at = excluded.updated_at
    """, (
        account_data["account_id"],
        account_data["consumer_id"],
        account_data["meter_id"],
        account_data["consumer_name"],
        account_data["district"],
        account_data["address"],
        account_data["tariff_category"],
        float(account_data["sanctioned_load_kw"]),
        account_data.get("connection_status", "ACTIVE"),
        account_data.get("connection_date", "2019-05-01"),
        account_data.get("billing_account_id"),
        account_data.get("bill_id"),
        account_data.get("payment_transaction_id"),
        now_str,
        now_str,
    ))
    conn.commit()
    conn.close()
    return get_account_by_id(account_data["account_id"])

# -------------------------------------------------------------
# Verification Engine Repository Functions
# -------------------------------------------------------------

def save_verification_run(
    verification_id: str,
    account_id: str,
    consumer_id: str,
    meter_id: str,
    scope: str,
    overall_status: str,
    ruleset_version: str,
    model_version: str,
    checks: List[Dict[str, Any]],
    summary_findings: str,
    raw_evidence_refs: Optional[List[str]] = None,
    active_model_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"

    total_checks = len(checks)
    executed_c = sum(1 for c in checks if c["status"] != "NOT_APPLICABLE")
    passed_c = sum(1 for c in checks if c["status"] == "PASS")
    flagged_c = sum(1 for c in checks if c["status"] == "FLAGGED")
    not_assessed_c = sum(1 for c in checks if c["status"] in ("NOT_ASSESSED", "INSUFFICIENT_EVIDENCE"))
    error_c = sum(1 for c in checks if c["status"] == "ERROR")
    excluded_c = sum(1 for c in checks if c["status"] == "NOT_APPLICABLE")
    attention_c = not_assessed_c + error_c

    # Insert verification run
    cursor.execute("""
    INSERT INTO verification_runs (
        verification_id, account_id, consumer_id, meter_id, evaluated_at, scope,
        overall_status, ruleset_version, model_version, total_checks, passed_checks,
        flagged_checks, not_assessed_checks, error_checks, summary_findings, raw_evidence_refs,
        checks_executed, checks_passed, checks_flagged, checks_requiring_attention,
        checks_excluded, active_model_run_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        verification_id,
        account_id,
        consumer_id,
        meter_id,
        now_str,
        scope,
        overall_status,
        ruleset_version,
        model_version,
        total_checks,
        passed_c,
        flagged_c,
        not_assessed_c,
        error_c,
        summary_findings,
        json.dumps(raw_evidence_refs or []),
        executed_c,
        passed_c,
        flagged_c,
        attention_c,
        excluded_c,
        active_model_run_id,
    ))

    # Insert individual check results
    check_rows = []
    for c in checks:
        check_rows.append((
            verification_id,
            c["check_code"],
            c["check_name"],
            c["status"],
            c.get("severity", "INFO"),
            c["findings"],
            json.dumps(c.get("evidence_detail", {})),
            now_str,
        ))

    cursor.executemany("""
    INSERT INTO verification_check_results (
        verification_id, check_code, check_name, status, severity, findings, evidence_detail, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, check_rows)

    conn.commit()
    conn.close()

    return get_verification_run_by_id(verification_id)

def get_verification_run_by_id(verification_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM verification_runs WHERE verification_id = ?", (verification_id,))
    v_row = cursor.fetchone()
    if not v_row:
        conn.close()
        return None

    v_dict = dict(v_row)
    v_dict["raw_evidence_refs"] = json.loads(v_dict["raw_evidence_refs"] or "[]")

    cursor.execute("""
    SELECT * FROM verification_check_results WHERE verification_id = ? ORDER BY id ASC
    """, (verification_id,))
    c_rows = cursor.fetchall()
    conn.close()

    v_dict["checks"] = []
    for r in c_rows:
        cd = dict(r)
        cd["evidence_detail"] = json.loads(cd["evidence_detail"] or "{}")
        v_dict["checks"].append(cd)

    # Reconcile dynamic header metrics
    v_dict["checks_executed"] = v_dict.get("checks_executed") if v_dict.get("checks_executed") is not None and v_dict.get("checks_executed") > 0 else sum(1 for c in v_dict["checks"] if c["status"] != "NOT_APPLICABLE")
    v_dict["checks_passed"] = v_dict.get("checks_passed") if v_dict.get("checks_passed") is not None else sum(1 for c in v_dict["checks"] if c["status"] == "PASS")
    v_dict["checks_flagged"] = v_dict.get("checks_flagged") if v_dict.get("checks_flagged") is not None else sum(1 for c in v_dict["checks"] if c["status"] == "FLAGGED")
    v_dict["checks_requiring_attention"] = v_dict.get("checks_requiring_attention") if v_dict.get("checks_requiring_attention") is not None else sum(1 for c in v_dict["checks"] if c["status"] in ("INSUFFICIENT_EVIDENCE", "ERROR", "NOT_ASSESSED"))
    v_dict["checks_excluded"] = v_dict.get("checks_excluded") if v_dict.get("checks_excluded") is not None else sum(1 for c in v_dict["checks"] if c["status"] == "NOT_APPLICABLE")
    v_dict["verification_mode"] = v_dict.get("scope")

    return v_dict

def get_verification_history_for_account(account_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM verification_runs
    WHERE account_id = ? OR consumer_id = ?
    ORDER BY evaluated_at DESC
    LIMIT ?
    """, (account_id, account_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# -------------------------------------------------------------
# Case Management & State Machine Repository Functions
# -------------------------------------------------------------

# Valid state transition graph
VALID_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    "OPEN": ["ASSIGNED", "UNDER_REVIEW", "CLOSED"],
    "ASSIGNED": ["UNDER_REVIEW", "PENDING_INFO", "ESCALATED", "OPEN", "CLOSED"],
    "UNDER_REVIEW": ["PENDING_INFO", "ESCALATED", "RESOLVED", "ASSIGNED", "CLOSED"],
    "PENDING_INFO": ["UNDER_REVIEW", "ASSIGNED", "ESCALATED", "CLOSED"],
    "ESCALATED": ["UNDER_REVIEW", "RESOLVED", "ASSIGNED", "CLOSED"],
    "RESOLVED": ["CLOSED", "UNDER_REVIEW"],  # UNDER_REVIEW for reopening
    "CLOSED": ["OPEN"],                       # Reopening closed case
}

VALID_REVIEW_DECISIONS: List[str] = [
    "PENDING",
    "Discrepancy Confirmed",
    "False Positive",
    "Insufficient Evidence",
    "Escalated",
    "Other / Unresolved",
    # Backward compatibility with existing observation decisions
    "Acknowledge / No Further Action",
    "Mark for Field Visit",
    "High Usage Authorized",
]

def create_case(
    source_finding_id: str,
    account_id: str,
    consumer_id: str,
    meter_id: str,
    title: str,
    description: str,
    finding_category: str,
    severity: str = "MEDIUM",
    priority: str = "MEDIUM",
    verification_id: Optional[str] = None,
    actor_id: str = "system",
    actor_role: str = "ADMIN",
) -> Tuple[Dict[str, Any], bool]:
    """
    Creates a new case with deterministic deduplication on source_finding_id.
    Returns (case_dict, is_new: bool).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if case with this source_finding_id already exists
    cursor.execute("SELECT * FROM cases WHERE source_finding_id = ?", (source_finding_id,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return dict(existing), False

    case_id = f"CASE-{datetime.utcnow().strftime('%Y%m')}-{str(uuid.uuid4())[:8].upper()}"
    now_str = datetime.utcnow().isoformat() + "Z"

    try:
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("""
        INSERT INTO cases (
            case_id, verification_id, source_finding_id, account_id, consumer_id,
            meter_id, title, description, finding_category, severity, priority,
            status, assigned_officer, decision, decision_reason, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 'Unassigned', 'PENDING', NULL, ?, ?)
        """, (
            case_id,
            verification_id,
            source_finding_id,
            account_id,
            consumer_id,
            meter_id,
            title,
            description,
            finding_category,
            severity,
            priority,
            now_str,
            now_str,
        ))

        # Record initial audit event
        event_id = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO case_audit_events (
            event_id, case_id, actor_id, actor_role, action, previous_value,
            new_value, reason, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, 'CASE_CREATED', NULL, 'OPEN', ?, ?, ?)
        """, (
            event_id,
            case_id,
            actor_id,
            actor_role,
            "Initial case creation from verification findings",
            json.dumps({"source_finding_id": source_finding_id, "category": finding_category, "severity": severity}),
            now_str,
        ))

        cursor.execute("COMMIT;")
    except Exception as e:
        cursor.execute("ROLLBACK;")
        conn.close()
        raise e

    cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    new_case = cursor.fetchone()
    conn.close()
    return dict(new_case), True

def get_cases(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    assignee: Optional[str] = None,
    meter_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM cases WHERE 1=1"
    params = []

    if status and status != "all":
        query += " AND status = ?"
        params.append(status)

    if priority and priority != "all":
        query += " AND priority = ?"
        params.append(priority)

    if category and category != "all":
        query += " AND finding_category = ?"
        params.append(category)

    if assignee and assignee != "all":
        query += " AND assigned_officer = ?"
        params.append(assignee)

    if meter_id:
        query += " AND meter_id = ?"
        params.append(meter_id)

    if search:
        s = f"%{search.strip().lower()}%"
        query += " AND (LOWER(case_id) LIKE ? OR LOWER(meter_id) LIKE ? OR LOWER(account_id) LIKE ? OR LOWER(title) LIKE ? OR LOWER(description) LIKE ?)"
        params.extend([s, s, s, s, s])

    # Count total
    count_query = query.replace("SELECT *", "SELECT COUNT(*) as total", 1)
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()["total"]

    # Paginate
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    offset = (page - 1) * page_size
    params.extend([page_size, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    total_pages = max(1, (total_count + page_size - 1) // page_size)
    return {
        "items": [dict(r) for r in rows],
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }

def get_case_by_id(case_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_case_status(
    case_id: str,
    new_status: str,
    reason: str,
    actor_id: str,
    actor_role: str,
) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"

    cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    case_row = cursor.fetchone()
    if not case_row:
        conn.close()
        raise ValueError(f"Case '{case_id}' not found.")

    curr_status = case_row["status"]
    if curr_status == new_status:
        conn.close()
        return dict(case_row)

    valid_targets = VALID_STATUS_TRANSITIONS.get(curr_status, [])
    if new_status not in valid_targets:
        conn.close()
        raise ValueError(
            f"Invalid status transition from '{curr_status}' to '{new_status}'. "
            f"Permitted transitions: {valid_targets}"
        )

    resolved_at = now_str if new_status == "RESOLVED" else case_row["resolved_at"]
    closed_at = now_str if new_status == "CLOSED" else (None if new_status == "OPEN" else case_row["closed_at"])

    # If transitioning to RESOLVED and decision was PENDING, auto-set default confirmed with given reason
    new_decision = case_row["decision"]
    new_decision_reason = case_row["decision_reason"]
    if new_status == "RESOLVED" and (not new_decision or new_decision == "PENDING"):
        new_decision = "Discrepancy Confirmed"
        new_decision_reason = reason

    try:
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("""
        UPDATE cases SET
            status = ?,
            decision = ?,
            decision_reason = ?,
            resolved_at = ?,
            closed_at = ?,
            updated_at = ?
        WHERE case_id = ?
        """, (new_status, new_decision, new_decision_reason, resolved_at, closed_at, now_str, case_id))

        # Synchronize linked billing finding if applicable
        finding_review_status = "REVIEWED" if new_status in ["RESOLVED", "CLOSED"] else ("PENDING" if new_status == "OPEN" else "UNDER_REVIEW")
        cursor.execute("""
        UPDATE billing_findings SET
            review_status = ?,
            review_decision = ?,
            decision_reason = ?,
            decision_by = ?,
            decision_at = CASE WHEN ? = 'REVIEWED' THEN COALESCE(decision_at, ?) ELSE decision_at END,
            updated_at = ?
        WHERE linked_case_id = ? OR finding_id = ?
        """, (
            finding_review_status, new_decision, new_decision_reason, actor_id,
            finding_review_status, now_str, now_str, case_id, case_row["source_finding_id"]
        ))

        action_type = "CASE_REOPENED" if (curr_status in ["RESOLVED", "CLOSED"] and new_status in ["OPEN", "UNDER_REVIEW"]) else "STATUS_CHANGED"
        event_id = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO case_audit_events (
            event_id, case_id, actor_id, actor_role, action, previous_value,
            new_value, reason, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id,
            case_id,
            actor_id,
            actor_role,
            action_type,
            curr_status,
            new_status,
            reason,
            json.dumps({"transition": f"{curr_status}->{new_status}"}),
            now_str,
        ))

        cursor.execute("COMMIT;")
    except Exception as e:
        cursor.execute("ROLLBACK;")
        conn.close()
        raise e

    cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    updated_case = cursor.fetchone()
    conn.close()
    return dict(updated_case)

def update_case_assignment(
    case_id: str,
    assigned_officer: str,
    reason: str,
    actor_id: str,
    actor_role: str,
) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"

    cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    case_row = cursor.fetchone()
    if not case_row:
        conn.close()
        raise ValueError(f"Case '{case_id}' not found.")

    prev_assignee = case_row["assigned_officer"]
    new_status = case_row["status"]
    if case_row["status"] == "OPEN" and assigned_officer != "Unassigned":
        new_status = "ASSIGNED"

    try:
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("""
        UPDATE cases SET
            assigned_officer = ?,
            status = ?,
            updated_at = ?
        WHERE case_id = ?
        """, (assigned_officer, new_status, now_str, case_id))

        event_id = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO case_audit_events (
            event_id, case_id, actor_id, actor_role, action, previous_value,
            new_value, reason, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, 'CASE_ASSIGNED', ?, ?, ?, ?, ?)
        """, (
            event_id,
            case_id,
            actor_id,
            actor_role,
            prev_assignee,
            assigned_officer,
            reason,
            json.dumps({"previous_assignee": prev_assignee, "new_assignee": assigned_officer}),
            now_str,
        ))

        cursor.execute("COMMIT;")
    except Exception as e:
        cursor.execute("ROLLBACK;")
        conn.close()
        raise e

    cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    updated_case = cursor.fetchone()
    conn.close()
    return dict(updated_case)

assign_case = update_case_assignment

def record_case_decision(
    case_id: str,
    decision: str,
    decision_reason: str,
    actor_id: str,
    actor_role: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    if decision not in VALID_REVIEW_DECISIONS:
        raise ValueError(f"Invalid review decision '{decision}'. Permitted: {VALID_REVIEW_DECISIONS}")
    if not decision_reason or not decision_reason.strip():
        raise ValueError("A valid decision justification (reason) is required.")

    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"

    cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    case_row = cursor.fetchone()
    if not case_row:
        conn.close()
        raise ValueError(f"Case '{case_id}' not found.")

    # Idempotent check: if already in resolved status with identical decision & reason, return cleanly without duplicate audit log
    if case_row["status"] == "RESOLVED" and case_row["decision"] == decision and case_row["decision_reason"] == decision_reason:
        conn.close()
        return dict(case_row)

    prev_decision = case_row["decision"]
    # Resolving case on confirmed or verified decision
    new_status = "RESOLVED" if decision not in ["PENDING", "Escalated"] else ("ESCALATED" if decision == "Escalated" else case_row["status"])

    try:
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("""
        UPDATE cases SET
            decision = ?,
            decision_reason = ?,
            status = ?,
            resolved_at = CASE WHEN ? = 'RESOLVED' THEN ? ELSE resolved_at END,
            updated_at = ?
        WHERE case_id = ?
        """, (decision, decision_reason, new_status, new_status, now_str, now_str, case_id))

        # Atomic synchronization with linked billing finding if this case has one
        finding_review_status = "REVIEWED" if new_status in ["RESOLVED", "CLOSED"] else ("PENDING" if new_status == "OPEN" else "UNDER_REVIEW")
        cursor.execute("""
        UPDATE billing_findings SET
            review_status = ?,
            review_decision = ?,
            decision_reason = ?,
            decision_by = ?,
            decision_at = ?,
            updated_at = ?
        WHERE linked_case_id = ? OR finding_id = ?
        """, (
            finding_review_status, decision, decision_reason, actor_id, now_str, now_str,
            case_id, case_row["source_finding_id"]
        ))

        if notes:
            cursor.execute("""
            INSERT INTO case_notes (case_id, author_id, author_role, note_text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """, (case_id, actor_id, actor_role, notes, now_str))

        event_id = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO case_audit_events (
            event_id, case_id, actor_id, actor_role, action, previous_value,
            new_value, reason, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, 'DECISION_RECORDED', ?, ?, ?, ?, ?)
        """, (
            event_id,
            case_id,
            actor_id,
            actor_role,
            prev_decision,
            decision,
            decision_reason,
            json.dumps({"decision": decision, "notes": notes or ""}),
            now_str,
        ))

        cursor.execute("COMMIT;")
    except Exception as e:
        cursor.execute("ROLLBACK;")
        conn.close()
        raise e

    cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    updated_case = cursor.fetchone()
    conn.close()
    return dict(updated_case)


def migrate_billing_findings_if_needed():
    """
    Backfills persistent billing findings from existing cases and verification runs.
    Ensures safe, idempotent migration without dropping or altering records.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM billing_findings")
    count = cursor.fetchone()["cnt"]
    if count > 0:
        conn.close()
        return

    now_str = datetime.utcnow().isoformat() + "Z"

    # 1. Backfill from existing cases with finding_category = 'BILLING_DISCREPANCY'
    cursor.execute("SELECT * FROM cases WHERE finding_category = 'BILLING_DISCREPANCY'")
    cases = cursor.fetchall()
    for c in cases:
        case_id = c["case_id"]
        source_id = c["source_finding_id"] or ""
        bill_id = source_id.replace("BILL_DISCREPANCY_", "") if "BILL_DISCREPANCY_" in source_id else ""
        account_id = c["account_id"]
        meter_id = c["meter_id"]
        status = c["status"]
        decision = c["decision"]
        reason_txt = c["decision_reason"]
        resolved_at = c["resolved_at"]
        officer = c["assigned_officer"]

        cursor.execute("""
        SELECT reason, billing_check_id, evaluated_at
        FROM billing_verification_results
        WHERE bill_id = ?
        ORDER BY evaluated_at DESC LIMIT 1
        """, (bill_id,))
        vr = cursor.fetchone()
        discrepancy_reason = vr["reason"] if (vr and vr["reason"]) else "INSUFFICIENT_METER_COVERAGE"
        run_id = vr["billing_check_id"] if vr else None
        latest_eval = vr["evaluated_at"] if vr else c["created_at"]

        cursor.execute("SELECT COUNT(*) as cnt FROM billing_verification_results WHERE bill_id = ?", (bill_id,))
        run_count = cursor.fetchone()["cnt"] or 1

        rev_status = "REVIEWED" if status in ("RESOLVED", "CLOSED") else "PENDING"
        finding_id = source_id if source_id else f"BILL_DISCREPANCY_{bill_id}"

        cursor.execute("""
        INSERT OR REPLACE INTO billing_findings (
            finding_id, bill_id, account_id, meter_id, finding_category,
            reason, first_detected_at, latest_observed_at, latest_verification_run_id,
            review_status, review_decision, decision_reason, decision_by, decision_at,
            linked_case_id, occurrence_count, is_recurring, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'BILLING_DISCREPANCY', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            finding_id, bill_id, account_id, meter_id,
            discrepancy_reason, c["created_at"], latest_eval, run_id,
            rev_status, decision, reason_txt, officer, resolved_at,
            case_id, max(1, run_count), c["created_at"], now_str
        ))

    conn.commit()
    conn.close()

def get_billing_findings(
    bill_id: Optional[str] = None,
    account_id: Optional[str] = None,
    review_status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    where_clauses = []
    params = []
    if bill_id:
        where_clauses.append("bill_id = ?")
        params.append(bill_id)
    if account_id:
        where_clauses.append("account_id = ?")
        params.append(account_id)
    if review_status and review_status != "all":
        where_clauses.append("review_status = ?")
        params.append(review_status)

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    cursor.execute(f"SELECT * FROM billing_findings {where_str} ORDER BY updated_at DESC", params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_billing_finding_by_id(finding_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM billing_findings WHERE finding_id = ?", (finding_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def reconcile_billing_finding_on_run(
    bill_id: str,
    account_id: str,
    meter_id: str,
    reason: str,
    run_id: str,
    actor_id: str = "system",
    actor_role: str = "SYSTEM",
    is_recurrence: bool = False,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], bool]:
    """
    Reconciles a billing discrepancy finding against a stable identity.
    Preserves existing review decision and case status on idempotent runs.
    Applies documented recurrence policy (Option A) if is_recurrence=True on a resolved case.
    Returns (finding_dict, case_dict, is_new: bool).
    """
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"

    canonical_finding_id = f"BILL_DISCREPANCY_{bill_id}"
    finding_id_with_reason = f"BILL_DISCREPANCY_{bill_id}_{reason}"

    # Search for existing finding by canonical ID, composite ID, or bill_id + reason
    cursor.execute("""
    SELECT * FROM billing_findings
    WHERE finding_id = ? OR finding_id = ? OR (bill_id = ? AND reason = ?)
    LIMIT 1
    """, (canonical_finding_id, finding_id_with_reason, bill_id, reason))
    existing_finding = cursor.fetchone()

    if existing_finding:
        f_dict = dict(existing_finding)
        linked_case_id = f_dict["linked_case_id"]
        case_dict = None

        if linked_case_id:
            cursor.execute("SELECT * FROM cases WHERE case_id = ?", (linked_case_id,))
            c_row = cursor.fetchone()
            if c_row:
                case_dict = dict(c_row)

        new_count = f_dict["occurrence_count"] + 1

        # Check for recurrence policy on a previously resolved/closed case
        case_is_resolved = case_dict and case_dict["status"] in ("RESOLVED", "CLOSED")
        should_reopen = is_recurrence and case_is_resolved

        try:
            cursor.execute("BEGIN TRANSACTION;")
            if should_reopen:
                # Recurrence policy: Reopen existing case to UNDER_REVIEW with audit log
                cursor.execute("""
                UPDATE billing_findings SET
                    occurrence_count = ?,
                    latest_observed_at = ?,
                    latest_verification_run_id = ?,
                    is_recurring = 1,
                    review_status = 'UNDER_REVIEW',
                    updated_at = ?
                WHERE finding_id = ?
                """, (new_count, now_str, run_id, now_str, f_dict["finding_id"]))

                cursor.execute("""
                UPDATE cases SET
                    status = 'UNDER_REVIEW',
                    updated_at = ?
                WHERE case_id = ?
                """, (now_str, linked_case_id))

                event_id = str(uuid.uuid4())
                cursor.execute("""
                INSERT INTO case_audit_events (
                    event_id, case_id, actor_id, actor_role, action, previous_value,
                    new_value, reason, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, 'DISCREPANCY_RECURRED', ?, 'UNDER_REVIEW', ?, ?, ?)
                """, (
                    event_id, linked_case_id, actor_id, actor_role,
                    case_dict["status"],
                    f"Discrepancy recurred on verification rerun: {reason}",
                    json.dumps({
                        "run_id": run_id,
                        "prior_decision": case_dict["decision"],
                        "prior_resolution": case_dict["resolved_at"],
                        "occurrence_count": new_count,
                    }),
                    now_str
                ))
            else:
                # Idempotent rerun: update observations, keep review decision & case status intact
                cursor.execute("""
                UPDATE billing_findings SET
                    occurrence_count = ?,
                    latest_observed_at = ?,
                    latest_verification_run_id = ?,
                    updated_at = ?
                WHERE finding_id = ?
                """, (new_count, now_str, run_id, now_str, f_dict["finding_id"]))

            cursor.execute("COMMIT;")
        except Exception as e:
            cursor.execute("ROLLBACK;")
            conn.close()
            raise e

        cursor.execute("SELECT * FROM billing_findings WHERE finding_id = ?", (f_dict["finding_id"],))
        updated_finding = dict(cursor.fetchone())

        if linked_case_id:
            cursor.execute("SELECT * FROM cases WHERE case_id = ?", (linked_case_id,))
            c_row = cursor.fetchone()
            case_dict = dict(c_row) if c_row else None

        conn.close()
        return updated_finding, case_dict, False

    # New finding
    finding_id = canonical_finding_id
    case_dict, is_case_new = create_case(
        source_finding_id=finding_id,
        account_id=account_id,
        consumer_id=f"CONS-{account_id.replace('ACCT-', '')}",
        meter_id=meter_id,
        title=f"Billing Discrepancy: {reason} on {bill_id}",
        description=f"Automated verification detected {reason} on bill {bill_id}.",
        finding_category="BILLING_DISCREPANCY",
        severity="MEDIUM",
        priority="MEDIUM",
        actor_id=actor_id,
        actor_role=actor_role,
    )
    linked_case_id = case_dict["case_id"]

    try:
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("""
        INSERT INTO billing_findings (
            finding_id, bill_id, account_id, meter_id, finding_category,
            reason, first_detected_at, latest_observed_at, latest_verification_run_id,
            review_status, review_decision, decision_reason, decision_by, decision_at,
            linked_case_id, occurrence_count, is_recurring, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'BILLING_DISCREPANCY', ?, ?, ?, ?, 'PENDING', 'PENDING', NULL, NULL, NULL, ?, 1, 0, ?, ?)
        """, (
            finding_id, bill_id, account_id, meter_id,
            reason, now_str, now_str, run_id, linked_case_id, now_str, now_str
        ))
        cursor.execute("COMMIT;")
    except Exception as e:
        cursor.execute("ROLLBACK;")
        conn.close()
        raise e

    cursor.execute("SELECT * FROM billing_findings WHERE finding_id = ?", (finding_id,))
    new_finding = dict(cursor.fetchone())
    conn.close()
    return new_finding, case_dict, True



def add_case_note(
    case_id: str,
    note_text: str,
    author_id: str,
    author_role: str,
) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"

    cursor.execute("SELECT case_id FROM cases WHERE case_id = ?", (case_id,))
    if not cursor.fetchone():
        conn.close()
        raise ValueError(f"Case '{case_id}' not found.")

    try:
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("""
        INSERT INTO case_notes (case_id, author_id, author_role, note_text, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (case_id, author_id, author_role, note_text, now_str))

        event_id = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO case_audit_events (
            event_id, case_id, actor_id, actor_role, action, previous_value,
            new_value, reason, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, 'NOTE_ADDED', NULL, NULL, 'Note added to case file', ?, ?)
        """, (
            event_id,
            case_id,
            author_id,
            author_role,
            json.dumps({"preview": note_text[:120]}),
            now_str,
        ))

        cursor.execute("COMMIT;")
    except Exception as e:
        cursor.execute("ROLLBACK;")
        conn.close()
        raise e

    cursor.execute("SELECT * FROM case_notes WHERE case_id = ? ORDER BY id DESC LIMIT 1", (case_id,))
    new_note = cursor.fetchone()
    conn.close()
    return dict(new_note)

def get_case_notes(case_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM case_notes WHERE case_id = ? ORDER BY id ASC", (case_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_case_audit_trail(case_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM case_audit_events
    WHERE case_id = ?
    ORDER BY created_at ASC
    """, (case_id,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d["metadata"] = json.loads(d["metadata_json"] or "{}")
        results.append(d)
    return results

def sync_observation_decision_to_case(
    observation_id: str,
    decision: str,
    notes: str,
    now_str: str,
):
    """
    Seamless bridge: If a review decision is recorded on an observation,
    update any linked case. For field visits, keep case in investigation/field workflow.
    """
    source_id = f"ANOM_{observation_id}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cases WHERE source_finding_id = ?", (source_id,))
    existing = cursor.fetchone()
    if existing:
        is_field_visit = (decision == "Mark for Field Visit")
        case_status = "UNDER_REVIEW" if is_field_visit else "RESOLVED"
        resolved_at = None if is_field_visit else now_str
        cursor.execute("""
        UPDATE cases SET
            decision = ?,
            decision_reason = ?,
            status = ?,
            resolved_at = ?,
            updated_at = ?
        WHERE case_id = ?
        """, (decision, notes or f"Decision recorded via Review Queue: {decision}", case_status, resolved_at, now_str, existing["case_id"]))
        conn.commit()
    conn.close()

# ==========================================================
# PHASE 2 & 3: TARIFFS, SYNTHETIC BILLS & PAYMENT FUNCTIONS
# ==========================================================

def get_all_tariffs() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tariff_rules ORDER BY effective_from DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_active_tariff(as_of_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    target_date = as_of_date or datetime.utcnow().strftime("%Y-%m-%d")
    cursor.execute("""
    SELECT * FROM tariff_rules
    WHERE is_active = 1
      AND effective_from <= ?
      AND (effective_to IS NULL OR effective_to >= ?)
    ORDER BY effective_from DESC
    LIMIT 1
    """, (target_date, target_date))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_or_update_tariff(
    tariff_id: str,
    tariff_name: Optional[str] = None,
    effective_from: Optional[str] = None,
    rate_per_kwh_paise: Optional[int] = None,
    fixed_charge_paise: Optional[int] = None,
    effective_to: Optional[str] = None,
    currency: Optional[str] = "INR",
    is_active: Optional[int] = 1,
) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"

    cursor.execute("SELECT * FROM tariff_rules WHERE tariff_id = ?", (tariff_id,))
    existing = cursor.fetchone()

    if existing:
        final_name = tariff_name if tariff_name is not None else existing["tariff_name"]
        final_from = effective_from if effective_from is not None else existing["effective_from"]
        final_to = effective_to if effective_to is not None else existing["effective_to"]
        final_rate = rate_per_kwh_paise if rate_per_kwh_paise is not None else existing["rate_per_kwh_paise"]
        final_fixed = fixed_charge_paise if fixed_charge_paise is not None else existing["fixed_charge_paise"]
        final_currency = currency if currency is not None else existing["currency"]
        final_active = is_active if is_active is not None else existing["is_active"]

        if final_rate < 0:
            conn.close()
            raise ValueError("rate_per_kwh_paise must be non-negative.")
        if final_fixed < 0:
            conn.close()
            raise ValueError("fixed_charge_paise must be non-negative.")
        if final_to and final_from > final_to:
            conn.close()
            raise ValueError("effective_from must be earlier than or equal to effective_to.")

        cursor.execute("""
        UPDATE tariff_rules SET
            tariff_name = ?,
            effective_from = ?,
            effective_to = ?,
            rate_per_kwh_paise = ?,
            fixed_charge_paise = ?,
            currency = ?,
            is_active = ?,
            updated_at = ?
        WHERE tariff_id = ?
        """, (
            final_name, final_from, final_to,
            final_rate, final_fixed, final_currency, final_active,
            now_str, tariff_id
        ))
    else:
        final_name = tariff_name or f"Tariff {tariff_id}"
        final_from = effective_from or "2019-01-01"
        final_rate = rate_per_kwh_paise if rate_per_kwh_paise is not None else 650
        final_fixed = fixed_charge_paise if fixed_charge_paise is not None else 11000
        final_currency = currency or "INR"
        final_active = is_active if is_active is not None else 1

        cursor.execute("""
        INSERT INTO tariff_rules (
            tariff_id, tariff_name, effective_from, effective_to,
            rate_per_kwh_paise, fixed_charge_paise, currency, is_active,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tariff_id, final_name, final_from, effective_to,
            final_rate, final_fixed, final_currency, final_active,
            now_str, now_str
        ))

    conn.commit()
    cursor.execute("SELECT * FROM tariff_rules WHERE tariff_id = ?", (tariff_id,))
    updated = cursor.fetchone()
    conn.close()
    return dict(updated)

def get_synthetic_bills(
    account_id: Optional[str] = None,
    meter_id: Optional[str] = None,
    scenario_label: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[Dict[str, Any]], int]:
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if account_id:
        where_clauses.append("account_id = ?")
        params.append(account_id)
    if meter_id:
        where_clauses.append("meter_id = ?")
        params.append(meter_id)
    if scenario_label and scenario_label != "all":
        where_clauses.append("scenario_label = ?")
        params.append(scenario_label)
    if search:
        s = f"%{search.strip()}%"
        where_clauses.append("(bill_id LIKE ? OR account_id LIKE ? OR meter_id LIKE ? OR scenario_label LIKE ?)")
        params.extend([s, s, s, s])

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    cursor.execute(f"SELECT COUNT(*) as total FROM synthetic_bills {where_str}", params)
    total = cursor.fetchone()["total"]

    offset = (page - 1) * page_size
    query = f"""
    SELECT b.*,
           (SELECT overall_result FROM billing_verification_results
            WHERE bill_id = b.bill_id ORDER BY evaluated_at DESC LIMIT 1) as latest_verification_status,
           (SELECT reason FROM billing_verification_results
            WHERE bill_id = b.bill_id ORDER BY evaluated_at DESC LIMIT 1) as latest_verification_reason,
           (SELECT evaluated_at FROM billing_verification_results
            WHERE bill_id = b.bill_id ORDER BY evaluated_at DESC LIMIT 1) as evaluated_at,
           (SELECT reconciliation_status FROM payment_reconciliation_results
            WHERE bill_id = b.bill_id ORDER BY evaluated_at DESC LIMIT 1) as latest_reconciliation_status,
           (SELECT review_status FROM billing_findings
            WHERE bill_id = b.bill_id ORDER BY updated_at DESC LIMIT 1) as review_status,
           (SELECT review_decision FROM billing_findings
            WHERE bill_id = b.bill_id ORDER BY updated_at DESC LIMIT 1) as review_decision,
           (SELECT decision_reason FROM billing_findings
            WHERE bill_id = b.bill_id ORDER BY updated_at DESC LIMIT 1) as decision_reason,
           (SELECT linked_case_id FROM billing_findings
            WHERE bill_id = b.bill_id ORDER BY updated_at DESC LIMIT 1) as linked_case_id,
           (SELECT c.status FROM cases c
            JOIN billing_findings bf ON bf.linked_case_id = c.case_id
            WHERE bf.bill_id = b.bill_id ORDER BY bf.updated_at DESC LIMIT 1) as case_status,
           (SELECT c.resolved_at FROM cases c
            JOIN billing_findings bf ON bf.linked_case_id = c.case_id
            WHERE bf.bill_id = b.bill_id ORDER BY bf.updated_at DESC LIMIT 1) as resolved_at,
           (SELECT is_recurring FROM billing_findings
            WHERE bill_id = b.bill_id ORDER BY updated_at DESC LIMIT 1) as is_recurring
    FROM synthetic_bills b
    {where_str}
    ORDER BY bill_date DESC
    LIMIT ? OFFSET ?
    """
    cursor.execute(query, params + [page_size, offset])
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows], total

def get_synthetic_bill_by_id(bill_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT b.*,
           (SELECT overall_result FROM billing_verification_results
            WHERE bill_id = b.bill_id ORDER BY evaluated_at DESC LIMIT 1) as latest_verification_status,
           (SELECT reason FROM billing_verification_results
            WHERE bill_id = b.bill_id ORDER BY evaluated_at DESC LIMIT 1) as latest_verification_reason,
           (SELECT evaluated_at FROM billing_verification_results
            WHERE bill_id = b.bill_id ORDER BY evaluated_at DESC LIMIT 1) as evaluated_at,
           (SELECT reconciliation_status FROM payment_reconciliation_results
            WHERE bill_id = b.bill_id ORDER BY evaluated_at DESC LIMIT 1) as latest_reconciliation_status,
           (SELECT review_status FROM billing_findings
            WHERE bill_id = b.bill_id ORDER BY updated_at DESC LIMIT 1) as review_status,
           (SELECT review_decision FROM billing_findings
            WHERE bill_id = b.bill_id ORDER BY updated_at DESC LIMIT 1) as review_decision,
           (SELECT decision_reason FROM billing_findings
            WHERE bill_id = b.bill_id ORDER BY updated_at DESC LIMIT 1) as decision_reason,
           (SELECT linked_case_id FROM billing_findings
            WHERE bill_id = b.bill_id ORDER BY updated_at DESC LIMIT 1) as linked_case_id,
           (SELECT c.status FROM cases c
            JOIN billing_findings bf ON bf.linked_case_id = c.case_id
            WHERE bf.bill_id = b.bill_id ORDER BY bf.updated_at DESC LIMIT 1) as case_status,
           (SELECT c.resolved_at FROM cases c
            JOIN billing_findings bf ON bf.linked_case_id = c.case_id
            WHERE bf.bill_id = b.bill_id ORDER BY bf.updated_at DESC LIMIT 1) as resolved_at,
           (SELECT is_recurring FROM billing_findings
            WHERE bill_id = b.bill_id ORDER BY updated_at DESC LIMIT 1) as is_recurring
    FROM synthetic_bills b
    WHERE bill_id = ?
    """, (bill_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_synthetic_payments(
    account_id: Optional[str] = None,
    bill_id: Optional[str] = None,
    transaction_status: Optional[str] = None,
    unmatched_only: bool = False,
) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if account_id:
        where_clauses.append("account_id = ?")
        params.append(account_id)
    if bill_id:
        where_clauses.append("bill_id = ?")
        params.append(bill_id)
    if transaction_status and transaction_status != "all":
        where_clauses.append("transaction_status = ?")
        params.append(transaction_status)
    if unmatched_only:
        where_clauses.append("bill_id IS NULL")

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    cursor.execute(f"SELECT * FROM synthetic_payments {where_str} ORDER BY payment_date DESC", params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_billing_verification_result(record: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO billing_verification_results (
        billing_check_id, bill_id, account_id, billing_period,
        metered_units, billed_units, unit_difference,
        configured_tariff_snapshot_json, expected_bill_amount_paise,
        billed_amount_paise, amount_difference_paise,
        coverage_status, units_check_status, amount_check_status,
        overall_result, reason, linked_case_id, provenance, evaluated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record["billing_check_id"],
        record["bill_id"],
        record["account_id"],
        record["billing_period"],
        record.get("metered_units"),
        record["billed_units"],
        record.get("unit_difference"),
        record["configured_tariff_snapshot_json"],
        record.get("expected_bill_amount_paise"),
        record["billed_amount_paise"],
        record.get("amount_difference_paise"),
        record["coverage_status"],
        record["units_check_status"],
        record["amount_check_status"],
        record["overall_result"],
        record["reason"],
        record.get("linked_case_id"),
        record.get("provenance", "SYNTHETIC_DEMO"),
        record["evaluated_at"],
    ))
    conn.commit()
    conn.close()
    return record

def get_billing_verification_history(bill_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT bvr.*,
           bf.review_status,
           bf.review_decision,
           bf.decision_reason,
           bf.decision_by,
           bf.decision_at,
           bf.is_recurring,
           c.status as case_status,
           c.resolved_at
    FROM billing_verification_results bvr
    LEFT JOIN billing_findings bf ON bf.bill_id = bvr.bill_id
    LEFT JOIN cases c ON c.case_id = COALESCE(bvr.linked_case_id, bf.linked_case_id)
    WHERE bvr.bill_id = ?
    ORDER BY bvr.evaluated_at DESC
    """, (bill_id,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d["tariff_snapshot"] = json.loads(d["configured_tariff_snapshot_json"] or "{}")
        results.append(d)
    return results

def save_payment_reconciliation_result(record: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO payment_reconciliation_results (
        reconciliation_id, bill_id, account_id,
        bill_amount_paise, confirmed_paid_paise, outstanding_paise, overpayment_paise,
        matched_transactions_json, unmatched_transactions_json, duplicate_candidates_json,
        pending_transactions_json, reversed_transactions_json,
        reconciliation_status, reasons_json, linked_case_id, provenance, evaluated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record["reconciliation_id"],
        record["bill_id"],
        record["account_id"],
        record["bill_amount_paise"],
        record["confirmed_paid_paise"],
        record["outstanding_paise"],
        record["overpayment_paise"],
        record["matched_transactions_json"],
        record["unmatched_transactions_json"],
        record["duplicate_candidates_json"],
        record["pending_transactions_json"],
        record["reversed_transactions_json"],
        record["reconciliation_status"],
        record["reasons_json"],
        record.get("linked_case_id"),
        record.get("provenance", "SYNTHETIC_DEMO"),
        record["evaluated_at"],
    ))
    conn.commit()
    conn.close()
    return record

def get_payment_reconciliation_history(bill_id: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM payment_reconciliation_results
    WHERE bill_id = ?
    ORDER BY evaluated_at DESC
    """, (bill_id,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d["matched_transactions"] = json.loads(d["matched_transactions_json"] or "[]")
        d["unmatched_transactions"] = json.loads(d["unmatched_transactions_json"] or "[]")
        d["duplicate_candidates"] = json.loads(d["duplicate_candidates_json"] or "[]")
        d["pending_transactions"] = json.loads(d["pending_transactions_json"] or "[]")
        d["reversed_transactions"] = json.loads(d["reversed_transactions_json"] or "[]")
        d["reasons"] = json.loads(d["reasons_json"] or "[]")
        results.append(d)
    return results

def get_billing_summary_metrics() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total_bills, SUM(bill_amount_paise) as total_paise FROM synthetic_bills")
    b_stat = cursor.fetchone()
    total_bills = b_stat["total_bills"] or 0
    total_bill_amount_paise = b_stat["total_paise"] or 0

    cursor.execute("SELECT COUNT(*) as total_txns, SUM(amount_paise) as total_tx_paise FROM synthetic_payments")
    p_stat = cursor.fetchone()
    total_txns = p_stat["total_txns"] or 0
    total_payment_paise = p_stat["total_tx_paise"] or 0

    cursor.execute("SELECT COUNT(*) as cnt FROM synthetic_payments WHERE bill_id IS NULL")
    unmatched_count = cursor.fetchone()["cnt"] or 0

    cursor.execute("SELECT COUNT(DISTINCT bill_id) as cnt FROM billing_verification_results WHERE overall_result = 'PASS'")
    bills_passed = cursor.fetchone()["cnt"] or 0

    cursor.execute("SELECT COUNT(DISTINCT bill_id) as cnt FROM billing_verification_results WHERE overall_result = 'FLAGGED'")
    billing_discrepancies = cursor.fetchone()["cnt"] or 0

    cursor.execute("SELECT COUNT(DISTINCT bill_id) as cnt FROM billing_findings WHERE review_status = 'PENDING'")
    pending_discrepancies = cursor.fetchone()["cnt"] or 0

    cursor.execute("SELECT COUNT(DISTINCT bill_id) as cnt FROM billing_findings WHERE review_status = 'REVIEWED'")
    resolved_discrepancies = cursor.fetchone()["cnt"] or 0

    cursor.execute("SELECT COUNT(*) as cnt FROM cases WHERE finding_category = 'BILLING_DISCREPANCY' AND status NOT IN ('RESOLVED', 'CLOSED')")
    open_investigations = cursor.fetchone()["cnt"] or 0

    cursor.execute("SELECT COUNT(*) as cnt FROM cases WHERE finding_category = 'BILLING_DISCREPANCY' AND status IN ('RESOLVED', 'CLOSED')")
    resolved_investigations = cursor.fetchone()["cnt"] or 0

    cursor.execute("SELECT COUNT(DISTINCT bill_id) as cnt FROM payment_reconciliation_results WHERE reconciliation_status = 'SETTLED'")
    settled_bills = cursor.fetchone()["cnt"] or 0

    cursor.execute("SELECT COUNT(DISTINCT bill_id) as cnt FROM payment_reconciliation_results WHERE reconciliation_status = 'PARTIALLY_PAID'")
    partial_bills = cursor.fetchone()["cnt"] or 0

    cursor.execute("SELECT COUNT(DISTINCT bill_id) as cnt FROM payment_reconciliation_results WHERE reconciliation_status = 'UNPAID'")
    unpaid_bills = cursor.fetchone()["cnt"] or 0

    cursor.execute("SELECT COUNT(DISTINCT bill_id) as cnt FROM payment_reconciliation_results WHERE reconciliation_status = 'REQUIRES_REVIEW'")
    review_bills = cursor.fetchone()["cnt"] or 0

    conn.close()
    return {
        "total_bills": total_bills,
        "total_bill_amount_inr": round(total_bill_amount_paise / 100.0, 2),
        "total_transactions": total_txns,
        "total_payment_amount_inr": round(total_payment_paise / 100.0, 2),
        "unmatched_payments_count": unmatched_count,
        "bills_verified_passed": bills_passed,
        "billing_discrepancies_flagged": billing_discrepancies,
        "billing_discrepancies_pending": pending_discrepancies,
        "billing_discrepancies_resolved": resolved_discrepancies,
        "open_investigations": open_investigations,
        "resolved_investigations": resolved_investigations,
        "bills_settled": settled_bills,
        "bills_partially_paid": partial_bills,
        "bills_unpaid": unpaid_bills,
        "bills_requiring_review": review_bills,
        "is_synthetic_demonstration": True,
    }

def seed_billing_and_payments_if_empty(force: bool = False):
    conn = get_connection()
    cursor = conn.cursor()

    if not force:
        cursor.execute("SELECT COUNT(*) as cnt FROM synthetic_bills")
        if cursor.fetchone()["cnt"] > 0:
            conn.close()
            return {"status": "skipped", "message": "Synthetic billing dataset already present."}

    now_str = datetime.utcnow().isoformat() + "Z"

    if force:
        cursor.execute("DELETE FROM payment_reconciliation_results;")
        cursor.execute("DELETE FROM billing_verification_results;")
        cursor.execute("DELETE FROM billing_findings;")
        cursor.execute("DELETE FROM synthetic_payments;")
        cursor.execute("DELETE FROM synthetic_bills;")
        cursor.execute("DELETE FROM tariff_rules;")


    # 1. Default Flat Tariff
    cursor.execute("""
    INSERT OR REPLACE INTO tariff_rules (
        tariff_id, tariff_name, effective_from, effective_to,
        rate_per_kwh_paise, fixed_charge_paise, currency, is_active,
        created_at, updated_at
    ) VALUES (
        'TAR-DEMO-FLAT',
        'UP Domestic LMV-1 Demonstration Flat Tariff',
        '2019-01-01',
        '2025-12-31',
        650,
        11000,
        'INR',
        1,
        ?,
        ?
    )
    """, (now_str, now_str))

    # 2. Deterministic Synthetic Bills (24 demonstration bills covering all required scenarios)
    bills_data = [
        # Correct bill: BR02 2019-09 exact metered sum = 145.42 kWh. Expected: 145.42*650 + 11000 = 105523 paise (₹1,055.23)
        ("BILL-BR02-201909", "ACCT-BR02", "BR02", "2019-10-05", "2019-09-01", "2019-09-30", 145.42, 105523, "CORRECT_BILL", "Correct bill matching metered telemetry and tariff rules"),
        # Billed units high: BR02 2019-10 (metered ~117.67 kWh, billed 260.00 kWh)
        ("BILL-BR02-201910", "ACCT-BR02", "BR02", "2019-11-05", "2019-10-01", "2019-10-31", 260.00, 180000, "BILLED_UNITS_HIGH", "Billed units (260 kWh) significantly exceed metered interval sum (~117.67 kWh)"),
        # Billed units low: BR02 2019-08 (metered ~172.55 kWh, billed 50.00 kWh)
        ("BILL-BR02-201908", "ACCT-BR02", "BR02", "2019-09-05", "2019-08-01", "2019-08-31", 50.00, 43500, "BILLED_UNITS_LOW", "Billed units (50 kWh) substantially understate metered interval sum (~172.55 kWh)"),
        # Incorrect amount math: BR03 2019-11 (billed 90 kWh; expected: 90*650+11000=69500 paise; bill says 145000 paise)
        ("BILL-BR03-201911", "ACCT-BR03", "BR03", "2019-12-05", "2019-11-01", "2019-11-30", 90.00, 145000, "INCORRECT_BILL_AMOUNT", "Billed amount (₹1,450.00) deviates from tariff calculation (₹695.00)"),
        # Insufficient meter coverage: BR02 2020-05 (only 4 days of telemetry in CEEW dataset)
        ("BILL-BR02-202005", "ACCT-BR02", "BR02", "2020-06-05", "2020-05-01", "2020-05-31", 180.00, 128000, "INSUFFICIENT_METER_COVERAGE", "Smart meter offline during majority of billing cycle; partial interval coverage (13%)"),
        # No meter coverage: BR04 2022-01 (outside CEEW dataset range)
        ("BILL-BR04-202201", "ACCT-BR04", "BR04", "2022-02-05", "2022-01-01", "2022-01-31", 150.00, 108500, "NO_METER_DATA_COVERAGE", "Zero smart meter telemetry available for evaluation period; cannot verify"),
        # Duplicate bills: BR05 2019-10 (Two concurrent bills issued for identical period)
        ("BILL-BR05-201910-A", "ACCT-BR05", "BR05", "2019-11-05", "2019-10-01", "2019-10-31", 120.00, 89000, "DUPLICATE_BILL", "Primary bill cycle issued for October 2019"),
        ("BILL-BR05-201910-B", "ACCT-BR05", "BR05", "2019-11-06", "2019-10-01", "2019-10-31", 120.00, 89000, "DUPLICATE_BILL", "Erroneous duplicate bill cycle generated for identical billing period"),
        # Partial payment scenario: BR03 2019-09 (Bill ₹1,200.00, partial payment ₹500.00)
        ("BILL-BR03-201909", "ACCT-BR03", "BR03", "2019-10-05", "2019-09-01", "2019-09-30", 160.00, 120000, "PARTIAL_PAYMENT", "Demonstration bill with subsequent partial customer instalment"),
        # Full payment scenario: BR04 2019-10 (Bill ₹955.00, full settled payment)
        ("BILL-BR04-201910", "ACCT-BR04", "BR04", "2019-11-05", "2019-10-01", "2019-10-31", 130.00, 95500, "FULL_PAYMENT_SETTLED", "Demonstration bill fully settled with verified receipt"),
        # Unpaid overdue bill: BR05 2019-11 (Bill ₹1,020.00, zero payments recorded)
        ("BILL-BR05-201911", "ACCT-BR05", "BR05", "2019-12-05", "2019-11-01", "2019-11-30", 140.00, 102000, "UNPAID_BILL", "Demonstration bill with outstanding unpaid balance"),
        # Multiple instalments: MH01 2019-09 (Bill ₹1,345.00, two payments ₹700 + ₹645)
        ("BILL-MH01-201909", "ACCT-MH01", "MH01", "2019-10-05", "2019-09-01", "2019-09-30", 190.00, 134500, "MULTIPLE_INSTALMENTS", "Demonstration bill settled across two separate payments"),
        # Overpayment: MH02 2019-09 (Bill ₹825.00, customer paid ₹1,200.00)
        ("BILL-MH02-201909", "ACCT-MH02", "MH02", "2019-10-05", "2019-09-01", "2019-09-30", 110.00, 82500, "OVERPAYMENT", "Demonstration bill with customer overpayment resulting in credit balance"),
        # Duplicate payment candidate: MH03 2019-10 (Bill ₹1,247.50, two identical txn receipts)
        ("BILL-MH03-201910", "ACCT-MH03", "MH03", "2019-11-05", "2019-10-01", "2019-10-31", 175.00, 124750, "DUPLICATE_PAYMENT_CANDIDATE", "Bill associated with duplicate transaction candidate requiring audit review"),
        # Payment reversed: MH04 2019-11 (Bill ₹1,410.00, payment reversed by bank)
        ("BILL-MH04-201911", "ACCT-MH04", "MH04", "2019-12-05", "2019-11-01", "2019-11-30", 200.00, 141000, "PAYMENT_REVERSED", "Bill payment transaction dishonoured and reversed"),
        # Failed transaction: MH05 2019-10 (Bill ₹1,085.00, payment failed at gateway)
        ("BILL-MH05-201910", "ACCT-MH05", "MH05", "2019-11-05", "2019-10-01", "2019-10-31", 150.00, 108500, "FAILED_TRANSACTION", "Payment gateway transaction failed; bill remains unpaid"),
        # Late payment: BR06 2019-08 (Bill date 2019-09-05, paid 2019-10-25)
        ("BILL-BR06-201908", "ACCT-BR06", "BR06", "2019-09-05", "2019-08-01", "2019-08-31", 140.00, 102000, "LATE_PAYMENT", "Settled 50 days after bill issue date"),
        # Pending transaction: BR08 2019-10 (Bill ₹1,117.50, payment still pending settlement)
        ("BILL-BR08-201910", "ACCT-BR08", "BR08", "2019-11-05", "2019-10-01", "2019-10-31", 155.00, 111750, "PENDING_TRANSACTION", "Customer payment initiated but pending bank settlement confirmation"),
        # Additional standard bills
        ("BILL-BR07-201909", "ACCT-BR07", "BR07", "2019-10-05", "2019-09-01", "2019-09-30", 135.00, 98750, "CORRECT_BILL", "Demonstration residential bill"),
        ("BILL-BR09-201911", "ACCT-BR09", "BR09", "2019-12-05", "2019-11-01", "2019-11-30", 165.00, 118250, "CORRECT_BILL", "Demonstration commercial bill"),
        ("BILL-MH06-201908", "ACCT-MH06", "MH06", "2019-09-05", "2019-08-01", "2019-08-31", 125.00, 92250, "CORRECT_BILL", "Demonstration residential bill"),
        ("BILL-MH07-201909", "ACCT-MH07", "MH07", "2019-10-05", "2019-09-01", "2019-09-30", 145.00, 105250, "PARTIAL_PAYMENT", "Demonstration partial payment"),
        ("BILL-MH08-201910", "ACCT-MH08", "MH08", "2019-11-05", "2019-10-01", "2019-10-31", 130.00, 95500, "UNPAID_BILL", "Demonstration unpaid bill"),
        ("BILL-MH10-201910", "ACCT-MH10", "MH10", "2019-11-05", "2019-10-01", "2019-10-31", 185.00, 131250, "FULL_PAYMENT_SETTLED", "Demonstration settled bill"),
        # Zero consumption (unoccupied premises, fixed charge only)
        ("BILL-BR06-201909-ZC", "ACCT-BR06", "BR06", "2019-10-05", "2019-09-01", "2019-09-30", 0.0, 11000, "ZERO_CONSUMPTION", "Unoccupied premises with 0 kWh consumption and fixed charges only"),
        # Extreme high bill (spike in billed units vs historical profile)
        ("BILL-BR07-201909-HB", "ACCT-BR07", "BR07", "2019-10-05", "2019-09-01", "2019-09-30", 950.0, 628500, "EXTREME_HIGH_BILL", "Abnormal spike in billed units vs historical profile"),
        # Arrears carried forward
        ("BILL-BR08-201909-AR", "ACCT-BR08", "BR08", "2019-10-05", "2019-09-01", "2019-09-30", 120.0, 149000, "ARREARS_CARRIED_OVER", "Bill includes prior overdue arrears carried forward"),
    ]

    cursor.executemany("""
    INSERT OR REPLACE INTO synthetic_bills (
        bill_id, account_id, meter_id, bill_date, period_start, period_end,
        consumed_units_kwh, bill_amount_paise, scenario_label, provenance, is_synthetic,
        notes, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNTHETIC_DEMO', 1, ?, ?, ?)
    """, [(b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], b[8], b[9], now_str, now_str) for b in bills_data])

    # 3. Deterministic Synthetic Payments
    payments_data = [
        # Full payment for BILL-BR02-201909 (105523 paise = ₹1,055.23)
        ("TXN-BR02-201909-01", "BILL-BR02-201909", "ACCT-BR02", "2019-10-12", 105523, "RCP-2019-001", "SETTLED", "FULL_PAYMENT", "Full bill payment cleared via UPI"),
        # Partial payment for BILL-BR03-201909 (₹500.00 against ₹1,200.00)
        ("TXN-BR03-201909-01", "BILL-BR03-201909", "ACCT-BR03", "2019-10-14", 50000, "RCP-2019-002", "SETTLED", "PARTIAL_PAYMENT", "Partial instalment received via netbanking"),
        # Full payment for BILL-BR04-201910 (₹955.00)
        ("TXN-BR04-201910-01", "BILL-BR04-201910", "ACCT-BR04", "2019-11-12", 95500, "RCP-2019-003", "SETTLED", "FULL_PAYMENT", "Full payment cleared via BBPS"),
        # Multiple instalments for BILL-MH01-201909 (₹700.00 + ₹645.00 against ₹1,345.00)
        ("TXN-MH01-201909-01", "BILL-MH01-201909", "ACCT-MH01", "2019-10-08", 70000, "RCP-2019-004A", "SETTLED", "MULTIPLE_INSTALMENT_1", "First instalment paid at counter"),
        ("TXN-MH01-201909-02", "BILL-MH01-201909", "ACCT-MH01", "2019-10-22", 64500, "RCP-2019-004B", "SETTLED", "MULTIPLE_INSTALMENT_2", "Second instalment paid online"),
        # Overpayment for BILL-MH02-201909 (₹1,200.00 against ₹825.00)
        ("TXN-MH02-201909-01", "BILL-MH02-201909", "ACCT-MH02", "2019-10-10", 120000, "RCP-2019-005", "SETTLED", "OVERPAYMENT", "Customer rounded up payment; ₹375.00 credit balance"),
        # Duplicate candidate for BILL-MH03-201910 (Two payments of ₹1,247.50 with same receipt)
        ("TXN-MH03-201910-01", "BILL-MH03-201910", "ACCT-MH03", "2019-11-10", 124750, "RCP-DUP-991", "SETTLED", "DUPLICATE_TXN_ORIGINAL", "Initial payment capture"),
        ("TXN-MH03-201910-02", "BILL-MH03-201910", "ACCT-MH03", "2019-11-10", 124750, "RCP-DUP-991", "SETTLED", "DUPLICATE_TXN_CANDIDATE", "Duplicate gateway notification with identical receipt"),
        # Reversed payment for BILL-MH04-201911 (₹1,410.00 REVERSED)
        ("TXN-MH04-201911-01", "BILL-MH04-201911", "ACCT-MH04", "2019-12-10", 141000, "RCP-2019-007", "REVERSED", "PAYMENT_REVERSED", "Payment returned/reversed due to insufficient funds"),
        # Failed payment for BILL-MH05-201910 (₹1,085.00 FAILED)
        ("TXN-MH05-201910-01", "BILL-MH05-201910", "ACCT-MH05", "2019-11-08", 108500, None, "FAILED", "FAILED_TRANSACTION", "Payment gateway timed out during processing"),
        # Late payment for BILL-BR06-201908 (₹1,020.00 paid 2019-10-25)
        ("TXN-BR06-201908-01", "BILL-BR06-201908", "ACCT-BR06", "2019-10-25", 102000, "RCP-2019-009", "SETTLED", "LATE_PAYMENT", "Payment completed after billing due date"),
        # Pending payment for BILL-BR08-201910 (₹1,117.50 PENDING)
        ("TXN-BR08-201910-01", "BILL-BR08-201910", "ACCT-BR08", "2019-11-10", 111750, None, "PENDING", "PENDING_TRANSACTION", "ACH clearing pending bank confirmation"),
        # Partial payment for BILL-MH07-201909
        ("TXN-MH07-201909-01", "BILL-MH07-201909", "ACCT-MH07", "2019-10-10", 50000, "RCP-2019-010", "SETTLED", "PARTIAL_PAYMENT", "Partial online payment"),
        # Full payment for BILL-MH10-201910
        ("TXN-MH10-201910-01", "BILL-MH10-201910", "ACCT-MH10", "2019-11-15", 131250, "RCP-2019-011", "SETTLED", "FULL_PAYMENT", "Full payment cleared via wallet"),
        # Unmatched payment (no bill_id reference): ACCT-BR02 ₹850.00
        ("TXN-UNMATCHED-01", None, "ACCT-BR02", "2019-10-18", 85000, "RCP-UNM-888", "SETTLED", "UNMATCHED_PAYMENT", "Unallocated direct bank deposit without bill reference"),
    ]

    cursor.executemany("""
    INSERT OR REPLACE INTO synthetic_payments (
        transaction_id, bill_id, account_id, payment_date, amount_paise,
        receipt_id, transaction_status, scenario_label, provenance, is_synthetic,
        notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'SYNTHETIC_DEMO', 1, ?, ?)
    """, [(p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], now_str) for p in payments_data])

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "bills_seeded": len(bills_data),
        "payments_seeded": len(payments_data),
        "tariffs_seeded": 1,
        "is_synthetic": True,
    }


# -------------------------------------------------------------
# Isolation Forest Configuration & Model Run History Functions
# -------------------------------------------------------------

def migrate_model_runs_if_needed():
    """
    Ensures model_runs table has all tracking and comparison columns,
    and active_model_config table exists with default configuration.
    Safe and idempotent.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Ensure active_model_config exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS active_model_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        contamination REAL NOT NULL DEFAULT 0.03,
        n_estimators INTEGER NOT NULL DEFAULT 150,
        random_state INTEGER NOT NULL DEFAULT 42,
        active_run_id TEXT,
        updated_at TEXT NOT NULL
    );
    """)

    # Seed default row if not present
    cursor.execute("SELECT COUNT(*) as cnt FROM active_model_config WHERE id = 1")
    if cursor.fetchone()["cnt"] == 0:
        now_str = datetime.utcnow().isoformat() + "Z"
        cursor.execute("""
        INSERT INTO active_model_config (id, contamination, n_estimators, random_state, active_run_id, updated_at)
        VALUES (1, 0.03, 150, 42, NULL, ?)
        """, (now_str,))

    # 2. Check existing columns of model_runs
    cursor.execute("PRAGMA table_info(model_runs)")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    needed_cols = [
        ("status", "TEXT NOT NULL DEFAULT 'COMPLETED'"),
        ("high_anomalies", "INTEGER NOT NULL DEFAULT 0"),
        ("low_anomalies", "INTEGER NOT NULL DEFAULT 0"),
        ("pattern_anomalies", "INTEGER NOT NULL DEFAULT 0"),
        ("statistical_anomalies", "INTEGER NOT NULL DEFAULT 0"),
        ("features_used", "TEXT"),
        ("dataset_fingerprint", "TEXT"),
        ("flagged_observation_ids", "TEXT"),
        ("started_at", "TEXT"),
        ("completed_at", "TEXT"),
        ("is_active", "INTEGER NOT NULL DEFAULT 0"),
        ("error_message", "TEXT"),
    ]
    for col_name, col_type in needed_cols:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE model_runs ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()

def migrate_verification_runs_if_needed():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(verification_runs)")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    needed_cols = [
        ("checks_executed", "INTEGER DEFAULT 0"),
        ("checks_passed", "INTEGER DEFAULT 0"),
        ("checks_flagged", "INTEGER DEFAULT 0"),
        ("checks_requiring_attention", "INTEGER DEFAULT 0"),
        ("checks_excluded", "INTEGER DEFAULT 0"),
        ("active_model_run_id", "TEXT"),
    ]
    for col_name, col_type in needed_cols:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE verification_runs ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()

def get_active_model_config() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT contamination, n_estimators, random_state, active_run_id, updated_at FROM active_model_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "contamination": float(row["contamination"]),
            "n_estimators": int(row["n_estimators"]),
            "random_state": int(row["random_state"]),
            "active_run_id": row["active_run_id"],
            "updated_at": row["updated_at"]
        }
    return {
        "contamination": 0.03,
        "n_estimators": 150,
        "random_state": 42,
        "active_run_id": None,
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }

def save_active_model_config(
    contamination: float,
    n_estimators: int = 150,
    random_state: int = 42,
    active_run_id: Optional[str] = None
):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"
    cursor.execute("""
    INSERT INTO active_model_config (id, contamination, n_estimators, random_state, active_run_id, updated_at)
    VALUES (1, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        contamination = excluded.contamination,
        n_estimators = excluded.n_estimators,
        random_state = excluded.random_state,
        active_run_id = COALESCE(excluded.active_run_id, active_model_config.active_run_id),
        updated_at = excluded.updated_at;
    """, (contamination, n_estimators, random_state, active_run_id, now_str))
    conn.commit()
    conn.close()

def record_model_run_start(
    run_id: str,
    contamination: float,
    n_estimators: int,
    random_state: int,
    model_name: str = "Isolation Forest (scikit-learn)",
    features_used: Optional[List[str]] = None,
    dataset_fingerprint: str = ""
) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"
    features_json = json.dumps(features_used or [])
    cursor.execute("""
    INSERT INTO model_runs (
        run_id, model_name, contamination, n_estimators, random_state,
        status, records_analyzed, anomalies_flagged, high_anomalies, low_anomalies,
        pattern_anomalies, statistical_anomalies, features_used, dataset_fingerprint,
        flagged_observation_ids, started_at, completed_at, is_active, error_message, created_at
    ) VALUES (?, ?, ?, ?, ?, 'RUNNING', 0, 0, 0, 0, 0, 0, ?, ?, '[]', ?, NULL, 0, NULL, ?)
    """, (run_id, model_name, contamination, n_estimators, random_state, features_json, dataset_fingerprint, now_str, now_str))
    conn.commit()
    conn.close()
    return run_id

def record_model_run_completed(
    run_id: str,
    records_analyzed: int,
    anomalies_flagged: int,
    high_anomalies: int,
    low_anomalies: int,
    pattern_anomalies: int,
    statistical_anomalies: int,
    features_used: List[str],
    flagged_ids: List[str],
    dataset_fingerprint: str = "",
    set_active: bool = True
):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"
    features_json = json.dumps(features_used)
    flagged_ids_json = json.dumps(flagged_ids)

    if set_active:
        cursor.execute("UPDATE model_runs SET is_active = 0 WHERE is_active = 1")

    cursor.execute("""
    UPDATE model_runs SET
        status = 'COMPLETED',
        records_analyzed = ?,
        anomalies_flagged = ?,
        high_anomalies = ?,
        low_anomalies = ?,
        pattern_anomalies = ?,
        statistical_anomalies = ?,
        features_used = ?,
        flagged_observation_ids = ?,
        dataset_fingerprint = ?,
        completed_at = ?,
        is_active = ?,
        error_message = NULL
    WHERE run_id = ?
    """, (
        records_analyzed, anomalies_flagged, high_anomalies, low_anomalies,
        pattern_anomalies, statistical_anomalies, features_json, flagged_ids_json,
        dataset_fingerprint, now_str, 1 if set_active else 0, run_id
    ))

    if set_active:
        cursor.execute("UPDATE active_model_config SET active_run_id = ?, updated_at = ? WHERE id = 1", (run_id, now_str))

    conn.commit()
    conn.close()

def record_model_run_failed(run_id: str, error_message: str):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat() + "Z"
    cursor.execute("""
    UPDATE model_runs SET
        status = 'FAILED',
        completed_at = ?,
        error_message = ?
    WHERE run_id = ?
    """, (now_str, error_message, run_id))
    conn.commit()
    conn.close()

def get_model_run_by_id(run_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM model_runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("features_used"):
        try:
            d["features_used"] = json.loads(d["features_used"])
        except Exception:
            d["features_used"] = []
    if d.get("flagged_observation_ids"):
        try:
            d["flagged_observation_ids"] = json.loads(d["flagged_observation_ids"])
        except Exception:
            d["flagged_observation_ids"] = []
    return d

def get_active_model_run() -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT run_id FROM model_runs WHERE is_active = 1 AND status = 'COMPLETED' ORDER BY rowid DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return get_model_run_by_id(row["run_id"])

def get_latest_successful_model_run(exclude_run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if exclude_run_id:
        cursor.execute("""
        SELECT run_id FROM model_runs 
        WHERE status = 'COMPLETED' AND run_id != ? 
        ORDER BY rowid DESC LIMIT 1
        """, (exclude_run_id,))
    else:
        cursor.execute("""
        SELECT run_id FROM model_runs 
        WHERE status = 'COMPLETED' 
        ORDER BY rowid DESC LIMIT 1
        """)
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return get_model_run_by_id(row["run_id"])

def get_model_runs_history(limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT run_id, model_name, contamination, n_estimators, random_state,
           status, records_analyzed, anomalies_flagged, high_anomalies, low_anomalies,
           pattern_anomalies, statistical_anomalies, dataset_fingerprint,
           started_at, completed_at, is_active, error_message, created_at
    FROM model_runs
    ORDER BY rowid DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def compare_model_runs(run_id_current: str, run_id_previous: str) -> Dict[str, Any]:
    run_curr = get_model_run_by_id(run_id_current)
    run_prev = get_model_run_by_id(run_id_previous)
    if not run_curr or not run_prev:
        raise ValueError("One or both model run records not found.")

    curr_ids = set(run_curr.get("flagged_observation_ids", []))
    prev_ids = set(run_prev.get("flagged_observation_ids", []))

    newly_detected = sorted(list(curr_ids - prev_ids))
    no_longer_detected = sorted(list(prev_ids - curr_ids))
    continuing = sorted(list(curr_ids & prev_ids))

    return {
        "current_run_id": run_id_current,
        "previous_run_id": run_id_previous,
        "current_contamination": run_curr["contamination"],
        "previous_contamination": run_prev["contamination"],
        "current_anomalies_count": len(curr_ids),
        "previous_anomalies_count": len(prev_ids),
        "newly_detected_count": len(newly_detected),
        "no_longer_detected_count": len(no_longer_detected),
        "continuing_count": len(continuing),
        "sample_newly_detected": newly_detected[:10],
        "sample_no_longer_detected": no_longer_detected[:10],
    }
