export interface DatasetSummary {
  dataset_name: string;
  source_institution: string;
  sampling_interval: string;
  measurement_unit: string;
  raw_files: string[];
  total_raw_rows: number;
  valid_readings: number;
  quarantined_readings: number;
  duplicate_readings: number;
  total_meters: number;
  meters_list: string[];
  districts: string[];
  start_date: string;
  end_date: string;
  mean_kwh: number;
  median_kwh: number;
  min_kwh: number;
  max_kwh: number;
}

export interface DashboardStats {
  total_meters: number;
  total_readings: number;
  flagged_anomalies: number;
  flagged_meters: number;
  pending_reviews: number;
  resolved_reviews: number;
  high_anomalies: number;
  low_anomalies: number;
  pattern_anomalies: number;
  start_date: string;
  end_date: string;
  model_name: string;
  contamination: number;
}

export interface ChartDataPoint {
  date: string;
  meter_id?: string | null;
  kwh: number;
  observed_consumption?: number;
  trailing_median?: number | null;
  expected_lower?: number | null;
  expected_upper?: number | null;
  is_anomaly: boolean;
  statistical_anomaly?: boolean;
  isolation_forest_anomaly?: boolean;
  anomaly_direction: 'high' | 'low' | 'pattern' | 'normal';
  anomaly_severity: number;
  anomaly_score?: number;
  detection_method?: string;
  reason: string;
  anomaly_reasons?: string;
  review_decision?: string;
  review_status: string;
  case_status?: string | null;
}

export interface DashboardChartResponse {
  points: ChartDataPoint[];
  total_points: number;
  sample_rate: number;
  start_date: string;
  end_date: string;
}

export interface MeterListItem {
  meter_id: string;
  district: string;
  total_days: number;
  mean_kwh: number;
  max_kwh: number;
  anomaly_count: number;
  high_anomaly_count: number;
  low_anomaly_count: number;
  pending_review_count: number;
}

export interface MeterHistoryResponse {
  meter_id: string;
  district: string;
  total_readings: number;
  mean_kwh: number;
  median_kwh: number;
  anomaly_count: number;
  points: ChartDataPoint[];
}

export interface ReviewQueueItem {
  observation_id: string;
  meter_id: string;
  district: string;
  date: string;
  kwh: number;
  observed_consumption?: number;
  trailing_median: number;
  expected_lower: number;
  expected_upper: number;
  is_anomaly?: boolean;
  statistical_anomaly?: boolean;
  isolation_forest_anomaly?: boolean;
  anomaly_direction: 'high' | 'low' | 'pattern' | 'normal';
  anomaly_severity: number;
  anomaly_score?: number;
  detection_method?: string;
  reason: string;
  anomaly_reasons?: string;
  review_decision?: string;
  review_status: string;
  case_status?: string | null;
  updated_at?: string;
}

export interface ReviewQueueResponse {
  items: ReviewQueueItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DecisionRecord {
  id: number;
  observation_id: string;
  meter_id: string;
  date: string;
  decision: string;
  notes: string;
  previous_status: string;
  new_status: string;
  created_at: string;
}

export interface AccountItem {
  account_id: string;
  consumer_id: string;
  meter_id: string;
  consumer_name: string;
  district: string;
  address: string;
  tariff_category: string;
  sanctioned_load_kw: number;
  connection_status: string;
  connection_date: string;
  billing_account_id?: string | null;
  bill_id?: string | null;
  payment_transaction_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface VerificationCheckResult {
  id?: number;
  verification_id?: string;
  check_code: string;
  check_name: string;
  status: 'PASS' | 'FLAGGED' | 'NOT_ASSESSED' | 'ERROR';
  severity: 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  findings: string;
  evidence_detail: any;
}

export interface VerificationRun {
  verification_id: string;
  account_id: string;
  consumer_id: string;
  meter_id: string;
  evaluated_at: string;
  scope: string;
  overall_status: 'NO_ISSUES_DETECTED' | 'FLAGGED_FOR_REVIEW' | 'UNABLE_TO_VERIFY';
  ruleset_version: string;
  model_version: string;
  total_checks: number;
  passed_checks: number;
  flagged_checks: number;
  not_assessed_checks: number;
  error_checks: number;
  summary_findings: string;
  raw_evidence_refs: string[];
  checks: VerificationCheckResult[];
  created_cases?: any[];
}

export interface CaseItem {
  case_id: string;
  verification_id?: string | null;
  source_finding_id: string;
  account_id: string;
  consumer_id: string;
  meter_id: string;
  title: string;
  description: string;
  finding_category: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT';
  status: 'OPEN' | 'ASSIGNED' | 'UNDER_REVIEW' | 'PENDING_INFO' | 'ESCALATED' | 'RESOLVED' | 'CLOSED';
  assigned_officer: string;
  decision: string;
  decision_reason?: string | null;
  created_at: string;
  updated_at: string;
  resolved_at?: string | null;
  closed_at?: string | null;
}

export interface CaseListResponse {
  items: CaseItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CaseAuditEvent {
  event_id: string;
  case_id: string;
  actor_id: string;
  actor_role: string;
  action: string;
  previous_value?: string | null;
  new_value?: string | null;
  reason: string;
  metadata: any;
  created_at: string;
}

export interface CaseNote {
  id: number;
  case_id: string;
  author_id: string;
  author_role: string;
  note_text: string;
  created_at: string;
}

export interface CaseDetail {
  case: CaseItem;
  account?: AccountItem | null;
  notes: CaseNote[];
  audit_events: CaseAuditEvent[];
  recent_meter_history?: ChartDataPoint[] | null;
}

export type CaseStatus = 'OPEN' | 'ASSIGNED' | 'UNDER_REVIEW' | 'PENDING_INFO' | 'ESCALATED' | 'RESOLVED' | 'CLOSED';
export type CasePriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT' | 'CRITICAL';
export type UserRole = 'ADMIN' | 'VERIFICATION_OFFICER' | 'AUDITOR';

// ==========================================
// Phase 2 & 3: Billing & Payment Types
// ==========================================

export interface TariffRule {
  tariff_id: string;
  tariff_name: string;
  effective_from: string;
  effective_to?: string | null;
  rate_per_kwh_paise: number;
  fixed_charge_paise: number;
  currency: string;
  is_active: number;
  created_at: string;
  updated_at: string;
}

export interface SyntheticBill {
  bill_id: string;
  account_id: string;
  meter_id: string;
  bill_date: string;
  period_start: string;
  period_end: string;
  consumed_units_kwh: number;
  bill_amount_paise: number;
  scenario_label: string;
  provenance: string;
  is_synthetic: number;
  notes?: string | null;
  created_at: string;
  updated_at: string;
  latest_verification_status?: string | null;
  latest_reconciliation_status?: string | null;
  latest_verification_reason?: string | null;
  evaluated_at?: string | null;
  review_status?: string | null;
  review_decision?: string | null;
  decision_reason?: string | null;
  linked_case_id?: string | null;
  case_status?: string | null;
  case_priority?: string | null;
  resolved_at?: string | null;
  is_recurring?: boolean | number;
}

export interface SyntheticBillListResponse {
  items: SyntheticBill[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SyntheticPayment {
  transaction_id: string;
  bill_id?: string | null;
  account_id: string;
  payment_date: string;
  amount_paise: number;
  receipt_id?: string | null;
  transaction_status: string;
  scenario_label: string;
  provenance: string;
  is_synthetic: number;
  notes?: string | null;
  created_at: string;
}

export interface BillingVerificationResult {
  billing_check_id: string;
  bill_id: string;
  account_id: string;
  billing_period: string;
  metered_units?: number | null;
  billed_units: number;
  unit_difference?: number | null;
  configured_tariff_snapshot_json: string;
  expected_bill_amount_paise?: number | null;
  billed_amount_paise: number;
  amount_difference_paise?: number | null;
  coverage_status: string;
  units_check_status: string;
  amount_check_status: string;
  overall_result: string;
  reason: string;
  linked_case_id?: string | null;
  provenance: string;
  evaluated_at: string;
  finding_id?: string | null;
  review_status?: string | null;
  review_decision?: string | null;
  decision_reason?: string | null;
  case_status?: string | null;
  resolved_at?: string | null;
  is_recurring?: boolean | number;
  occurrence_count?: number;
  tariff_snapshot?: {
    tariff_id: string;
    tariff_name: string;
    rate_per_kwh_paise: number;
    fixed_charge_paise: number;
    currency: string;
  };
  coverage_details?: {
    metered_units?: number | null;
    days_observed: number;
    expected_days: number;
    coverage_ratio: number;
    coverage_status: string;
    notes: string;
  };
}

export interface PaymentReconciliationResult {
  reconciliation_id: string;
  bill_id: string;
  account_id: string;
  bill_amount_paise: number;
  confirmed_paid_paise: number;
  outstanding_paise: number;
  overpayment_paise: number;
  matched_transactions: SyntheticPayment[];
  unmatched_transactions: SyntheticPayment[];
  duplicate_candidates: any[];
  pending_transactions: SyntheticPayment[];
  reversed_transactions: SyntheticPayment[];
  reconciliation_status: string;
  reasons: string[];
  linked_case_id?: string | null;
  provenance: string;
  evaluated_at: string;
}

export interface BillingSummary {
  total_bills: number;
  total_bill_amount_inr: number;
  total_transactions: number;
  total_payment_amount_inr: number;
  unmatched_payments_count: number;
  bills_verified_passed: number;
  billing_discrepancies_flagged: number;
  billing_discrepancies_pending?: number;
  billing_discrepancies_resolved?: number;
  open_investigations?: number;
  resolved_investigations?: number;
  bills_settled: number;
  bills_partially_paid: number;
  bills_unpaid: number;
  bills_requiring_review: number;
  is_synthetic_demonstration: boolean;
}

export interface ActiveConfig {
  contamination: number;
  n_estimators: number;
  random_state: number;
  active_run_id?: string | null;
  updated_at?: string | null;
}

export interface ModelRunSummary {
  run_id: string;
  model_name: string;
  contamination: number;
  n_estimators: number;
  random_state: number;
  status: string;
  records_analyzed: number;
  anomalies_flagged: number;
  high_anomalies: number;
  low_anomalies: number;
  pattern_anomalies: number;
  statistical_anomalies: number;
  dataset_fingerprint?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  is_active: number;
  error_message?: string | null;
  created_at: string;
}

export interface ModelComparison {
  current_run_id: string;
  previous_run_id: string;
  current_contamination: number;
  previous_contamination: number;
  current_anomalies_count: number;
  previous_anomalies_count: number;
  newly_detected_count: number;
  no_longer_detected_count: number;
  continuing_count: number;
  sample_newly_detected?: string[];
  sample_no_longer_detected?: string[];
}

export interface ModelConfigDetailResponse {
  saved_configuration: ActiveConfig;
  active_configuration: ActiveConfig;
  current_run?: ModelRunSummary | null;
  previous_run?: ModelRunSummary | null;
  is_running: boolean;
  model_metadata?: Record<string, any> | null;
}

export interface ModelRerunResponse {
  success: boolean;
  message: string;
  run: ModelRunSummary;
  comparison?: ModelComparison | null;
  model_metadata: Record<string, any>;
}

