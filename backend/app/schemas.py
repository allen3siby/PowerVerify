from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any

class DatasetSummaryResponse(BaseModel):
    dataset_name: str
    source_institution: str
    sampling_interval: str
    measurement_unit: str
    raw_files: List[str]
    total_raw_rows: int
    valid_readings: int
    quarantined_readings: int
    duplicate_readings: int
    total_meters: int
    meters_list: List[str]
    districts: List[str]
    start_date: str
    end_date: str
    mean_kwh: float
    median_kwh: float
    min_kwh: float
    max_kwh: float

class DashboardStatsResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    total_meters: int
    total_readings: int
    flagged_anomalies: int
    flagged_meters: int
    pending_reviews: int
    resolved_reviews: int
    high_anomalies: int
    low_anomalies: int
    pattern_anomalies: int
    start_date: str
    end_date: str
    model_name: str
    contamination: float
    statistical_anomalies: Optional[int] = 0
    isolation_forest_anomalies: Optional[int] = 0
    open_field_visits: Optional[int] = 0
    resolved_cases: Optional[int] = 0
    active_run_id: Optional[str] = None

class ChartDataPoint(BaseModel):
    date: str
    meter_id: Optional[str] = None
    kwh: float
    observed_consumption: Optional[float] = None
    trailing_median: Optional[float] = None
    expected_lower: Optional[float] = None
    expected_upper: Optional[float] = None
    is_anomaly: bool = False
    statistical_anomaly: bool = False
    isolation_forest_anomaly: bool = False
    anomaly_direction: str = "normal"  # 'high', 'low', 'pattern', 'normal'
    anomaly_severity: float = 0.0
    anomaly_score: Optional[float] = None
    detection_method: str = "NORMAL"
    reason: str = ""
    anomaly_reasons: Optional[str] = None
    review_decision: Optional[str] = "PENDING"
    review_status: str = "PENDING"
    case_status: Optional[str] = None

class DashboardChartResponse(BaseModel):
    points: List[ChartDataPoint]
    total_points: int
    sample_rate: int
    start_date: str
    end_date: str

class MeterListItem(BaseModel):
    meter_id: str
    district: str
    total_days: int
    mean_kwh: float
    max_kwh: float
    anomaly_count: int
    high_anomaly_count: int
    low_anomaly_count: int
    pending_review_count: int

class MeterHistoryResponse(BaseModel):
    meter_id: str
    district: str
    total_readings: int
    mean_kwh: float
    median_kwh: float
    anomaly_count: int
    points: List[ChartDataPoint]

class ReviewDecisionRequest(BaseModel):
    observation_id: str
    decision: str  # 'Acknowledge / No Further Action', 'Mark for Field Visit', 'High Usage Authorized'
    notes: Optional[str] = ""

class ReviewDecisionResponse(BaseModel):
    success: bool
    observation_id: str
    meter_id: str
    date: str
    previous_status: str
    new_status: str
    notes: str
    timestamp: str

class ReviewQueueItem(BaseModel):
    observation_id: str
    meter_id: str
    district: str
    date: str
    kwh: float
    observed_consumption: Optional[float] = None
    trailing_median: float
    expected_lower: float
    expected_upper: float
    is_anomaly: bool = True
    statistical_anomaly: bool = False
    isolation_forest_anomaly: bool = False
    anomaly_direction: str
    anomaly_severity: float
    anomaly_score: Optional[float] = None
    detection_method: str = "STATISTICAL_MAD"
    reason: str
    anomaly_reasons: Optional[str] = None
    review_decision: str = "PENDING"
    review_status: str
    case_status: Optional[str] = None
    updated_at: Optional[str] = None

class ReviewQueueResponse(BaseModel):
    items: List[ReviewQueueItem]
    total: int
    page: int
    page_size: int
    total_pages: int

class SettingsReanalyzeRequest(BaseModel):
    contamination: float = Field(default=0.03, ge=0.01, le=0.08)
    n_estimators: int = Field(default=150, ge=50, le=500)
    random_state: int = Field(default=42)

class ActiveConfigSchema(BaseModel):
    contamination: float
    n_estimators: int
    random_state: int
    active_run_id: Optional[str] = None
    updated_at: Optional[str] = None

class ModelRunSummarySchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    run_id: str
    model_name: str
    contamination: float
    n_estimators: int
    random_state: int
    status: str
    records_analyzed: int
    anomalies_flagged: int
    high_anomalies: int
    low_anomalies: int
    pattern_anomalies: int
    statistical_anomalies: int
    dataset_fingerprint: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    is_active: int
    error_message: Optional[str] = None
    created_at: str

class ModelComparisonSchema(BaseModel):
    current_run_id: str
    previous_run_id: str
    current_contamination: float
    previous_contamination: float
    current_anomalies_count: int
    previous_anomalies_count: int
    newly_detected_count: int
    no_longer_detected_count: int
    continuing_count: int
    sample_newly_detected: List[str] = []
    sample_no_longer_detected: List[str] = []

class ModelRerunRequest(BaseModel):
    contamination: float = Field(default=0.03, ge=0.01, le=0.08)
    n_estimators: int = Field(default=150, ge=50, le=300)
    random_state: int = Field(default=42)

class ModelConfigDetailResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    saved_configuration: ActiveConfigSchema
    active_configuration: ActiveConfigSchema
    current_run: Optional[ModelRunSummarySchema] = None
    previous_run: Optional[ModelRunSummarySchema] = None
    is_running: bool = False
    model_metadata: Optional[Dict[str, Any]] = None

class ModelRerunResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    success: bool
    message: str
    run: ModelRunSummarySchema
    comparison: Optional[ModelComparisonSchema] = None
    model_metadata: Dict[str, Any]

# ==========================================
# Consumer Account Verification & Case Schemas
# ==========================================

class AccountSchema(BaseModel):
    account_id: str
    consumer_id: str
    meter_id: str
    consumer_name: str
    district: str
    address: str
    tariff_category: str
    sanctioned_load_kw: float
    connection_status: str
    connection_date: str
    billing_account_id: Optional[str] = None
    bill_id: Optional[str] = None
    payment_transaction_id: Optional[str] = None
    created_at: str
    updated_at: str

class VerificationCheckResultSchema(BaseModel):
    id: Optional[int] = None
    verification_id: Optional[str] = None
    check_code: str
    check_name: str
    status: str  # 'PASS', 'FLAGGED', 'NOT_ASSESSED', 'ERROR'
    severity: str  # 'INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    findings: str
    evidence_detail: Dict[str, Any] = {}

class VerificationRunResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    verification_id: str
    account_id: str
    consumer_id: str
    meter_id: str
    evaluated_at: str
    scope: str
    overall_status: str  # 'NO_ISSUES_DETECTED', 'FLAGGED_FOR_REVIEW', 'UNABLE_TO_VERIFY'
    ruleset_version: str
    model_version: str
    total_checks: int
    passed_checks: int
    flagged_checks: int
    not_assessed_checks: int
    error_checks: int
    summary_findings: str
    raw_evidence_refs: List[str] = []
    checks: List[VerificationCheckResultSchema] = []
    created_cases: Optional[List[Dict[str, Any]]] = []

class VerificationRunRequest(BaseModel):
    account_id: str
    scope: Optional[str] = "FULL_HISTORICAL_AUDIT"
    time_window_days: Optional[int] = None
    auto_create_cases: Optional[bool] = True

class CaseSchema(BaseModel):
    case_id: str
    verification_id: Optional[str] = None
    source_finding_id: str
    account_id: str
    consumer_id: str
    meter_id: str
    title: str
    description: str
    finding_category: str
    severity: str
    priority: str
    status: str
    assigned_officer: str
    decision: str
    decision_reason: Optional[str] = None
    created_at: str
    updated_at: str
    resolved_at: Optional[str] = None
    closed_at: Optional[str] = None

class CaseListResponse(BaseModel):
    items: List[CaseSchema]
    total: int
    page: int
    page_size: int
    total_pages: int

class CaseAuditEventSchema(BaseModel):
    event_id: str
    case_id: str
    actor_id: str
    actor_role: str
    action: str
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: str
    metadata: Dict[str, Any] = {}
    created_at: str

class CaseNoteSchema(BaseModel):
    id: int
    case_id: str
    author_id: str
    author_role: str
    note_text: str
    created_at: str

class CaseDetailResponse(BaseModel):
    case: CaseSchema
    account: Optional[AccountSchema] = None
    notes: List[CaseNoteSchema] = []
    audit_events: List[CaseAuditEventSchema] = []
    recent_meter_history: Optional[List[ChartDataPoint]] = None

class CaseStatusUpdateRequest(BaseModel):
    status: str
    reason: str = Field(..., min_length=2)

class CaseAssignmentRequest(BaseModel):
    assigned_officer: str = Field(..., min_length=2)
    reason: str = Field(..., min_length=2)

class CaseDecisionRequest(BaseModel):
    decision: str
    decision_reason: str = Field(..., min_length=2)
    notes: Optional[str] = ""

class CaseNoteRequest(BaseModel):
    note_text: str = Field(..., min_length=1)

# ==========================================================
# PHASE 2 & 3: TARIFFS, BILLING & PAYMENT SCHEMAS
# ==========================================================

class TariffRuleSchema(BaseModel):
    tariff_id: str
    tariff_name: str
    effective_from: str
    effective_to: Optional[str] = None
    rate_per_kwh_paise: int
    fixed_charge_paise: int
    currency: str = "INR"
    is_active: int = 1
    created_at: str
    updated_at: str

class TariffRuleUpdateRequest(BaseModel):
    tariff_name: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    rate_per_kwh_paise: Optional[int] = Field(None, ge=0)
    fixed_charge_paise: Optional[int] = Field(None, ge=0)
    currency: Optional[str] = "INR"
    is_active: Optional[int] = 1

class SyntheticBillSchema(BaseModel):
    bill_id: str
    account_id: str
    meter_id: str
    bill_date: str
    period_start: str
    period_end: str
    consumed_units_kwh: float
    bill_amount_paise: int
    scenario_label: str
    provenance: str = "SYNTHETIC_DEMO"
    is_synthetic: int = 1
    notes: Optional[str] = None
    created_at: str
    updated_at: str
    latest_verification_status: Optional[str] = None
    latest_verification_reason: Optional[str] = None
    latest_reconciliation_status: Optional[str] = None
    review_status: Optional[str] = None
    review_decision: Optional[str] = None
    decision_reason: Optional[str] = None
    linked_case_id: Optional[str] = None
    case_status: Optional[str] = None
    resolved_at: Optional[str] = None
    is_recurring: Optional[bool] = False
    evaluated_at: Optional[str] = None

class SyntheticBillListResponse(BaseModel):
    items: List[SyntheticBillSchema]
    total: int
    page: int
    page_size: int
    total_pages: int

class SyntheticPaymentSchema(BaseModel):
    transaction_id: str
    bill_id: Optional[str] = None
    account_id: str
    payment_date: str
    amount_paise: int
    receipt_id: Optional[str] = None
    transaction_status: str
    scenario_label: str
    provenance: str = "SYNTHETIC_DEMO"
    is_synthetic: int = 1
    notes: Optional[str] = None
    created_at: str

class BillingVerificationResultSchema(BaseModel):
    billing_check_id: str
    bill_id: str
    account_id: str
    billing_period: str
    metered_units: Optional[float] = None
    billed_units: float
    unit_difference: Optional[float] = None
    configured_tariff_snapshot_json: str
    expected_bill_amount_paise: Optional[int] = None
    billed_amount_paise: int
    amount_difference_paise: Optional[int] = None
    coverage_status: str
    units_check_status: str
    amount_check_status: str
    overall_result: str
    reason: str
    linked_case_id: Optional[str] = None
    provenance: str = "SYNTHETIC_DEMO"
    evaluated_at: str
    tariff_snapshot: Optional[Dict[str, Any]] = None
    coverage_details: Optional[Dict[str, Any]] = None
    case_status: Optional[str] = None
    review_status: Optional[str] = None
    review_decision: Optional[str] = None
    decision_reason: Optional[str] = None
    resolved_at: Optional[str] = None
    is_recurring: Optional[bool] = False

class PaymentReconciliationResultSchema(BaseModel):
    reconciliation_id: str
    bill_id: str
    account_id: str
    bill_amount_paise: int
    confirmed_paid_paise: int
    outstanding_paise: int
    overpayment_paise: int
    matched_transactions: Optional[List[Dict[str, Any]]] = None
    unmatched_transactions: Optional[List[Dict[str, Any]]] = None
    duplicate_candidates: Optional[List[Dict[str, Any]]] = None
    pending_transactions: Optional[List[Dict[str, Any]]] = None
    reversed_transactions: Optional[List[Dict[str, Any]]] = None
    reconciliation_status: str
    reasons: Optional[List[str]] = None
    linked_case_id: Optional[str] = None
    provenance: str = "SYNTHETIC_DEMO"
    evaluated_at: str

class BillingSummaryResponse(BaseModel):
    total_bills: int
    total_bill_amount_inr: float
    total_transactions: int
    total_payment_amount_inr: float
    unmatched_payments_count: int
    bills_verified_passed: int
    billing_discrepancies_flagged: int
    billing_discrepancies_pending: Optional[int] = 0
    billing_discrepancies_resolved: Optional[int] = 0
    open_investigations: Optional[int] = 0
    resolved_investigations: Optional[int] = 0
    bills_settled: int
    bills_partially_paid: int
    bills_unpaid: int
    bills_requiring_review: int
    is_synthetic_demonstration: bool = True

