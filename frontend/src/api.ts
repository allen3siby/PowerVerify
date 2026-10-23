import type {
  DatasetSummary,
  DashboardStats,
  DashboardChartResponse,
  MeterListItem,
  MeterHistoryResponse,
  ReviewQueueResponse,
  DecisionRecord,
  AccountItem,
  VerificationRun,
  CaseItem,
  CaseListResponse,
  CaseDetail,
  CaseAuditEvent,
  CaseNote,
  TariffRule,
  SyntheticBill,
  SyntheticBillListResponse,
  SyntheticPayment,
  BillingVerificationResult,
  PaymentReconciliationResult,
  BillingSummary,
  ModelConfigDetailResponse,
  ModelRerunResponse,
  ModelRunSummary,
  ModelComparison,
} from './types';

const CLOUDFLARE_PROD_URL = 'https://cubic-weight-tractor-kathy.trycloudflare.com/api';

export const getApiBase = (): string => {
  const envUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (envUrl && envUrl.trim().length > 0) {
    return envUrl.trim().replace(/\/+$/, '');
  }
  return import.meta.env.PROD ? CLOUDFLARE_PROD_URL : 'http://localhost:8000/api';
};

const API_BASE = getApiBase();

// Current session identity for RBAC
let activeUserRole: string = 'VERIFICATION_OFFICER';
let activeUserId: string = 'officer.sharma';

export const authState = {
  getRole: () => activeUserRole,
  getUserId: () => activeUserId,
  setUser: (role: string, userId: string) => {
    activeUserRole = role;
    activeUserId = userId;
  },
};

const getHeaders = (extra: Record<string, string> = {}) => ({
  'Content-Type': 'application/json',
  'X-User-Role': activeUserRole,
  'X-User-Id': activeUserId,
  ...extra,
});

async function handleResponse<T>(res: Response, fallbackErrMsg: string): Promise<T> {
  const contentType = res.headers.get('content-type') || '';
  if (!res.ok) {
    if (contentType.includes('application/json')) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || fallbackErrMsg);
    }
    throw new Error(`${fallbackErrMsg} (HTTP ${res.status})`);
  }
  if (!contentType.includes('application/json')) {
    throw new Error('API server returned non-JSON response. Ensure backend server is reachable.');
  }
  return res.json();
}

export const api = {
  // Existing Dashboard & Telemetry
  async getDatasetSummary(): Promise<DatasetSummary> {
    const res = await fetch(`${API_BASE}/dataset/summary`);
    return handleResponse<DatasetSummary>(res, 'Failed to load dataset summary');
  },

  async getDashboardStats(): Promise<DashboardStats> {
    const res = await fetch(`${API_BASE}/dashboard/stats`);
    return handleResponse<DashboardStats>(res, 'Failed to load dashboard stats');
  },

  async getDashboardChart(timeRange: string = 'all', meterId?: string): Promise<DashboardChartResponse> {
    const params = new URLSearchParams({ time_range: timeRange });
    if (meterId) params.append('meter_id', meterId);
    const res = await fetch(`${API_BASE}/dashboard/chart?${params.toString()}`);
    return handleResponse<DashboardChartResponse>(res, 'Failed to load chart data');
  },

  async getMeters(): Promise<MeterListItem[]> {
    const res = await fetch(`${API_BASE}/meters`);
    return handleResponse<MeterListItem[]>(res, 'Failed to load meters');
  },

  async getMeterHistory(meterId: string, timeRange: string = 'all'): Promise<MeterHistoryResponse> {
    const res = await fetch(`${API_BASE}/meters/${meterId}/history?time_range=${timeRange}`);
    if (!res.ok) throw new Error(`Failed to load history for meter ${meterId}`);
    return res.json();
  },

  async getReviewQueue(params: {
    meterId?: string;
    direction?: string;
    status?: string;
    search?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ReviewQueueResponse> {
    const q = new URLSearchParams();
    if (params.meterId) q.append('meter_id', params.meterId);
    if (params.direction && params.direction !== 'all') q.append('direction', params.direction);
    if (params.status && params.status !== 'all') q.append('status', params.status);
    if (params.search) q.append('search', params.search);
    if (params.page) q.append('page', params.page.toString());
    if (params.pageSize) q.append('page_size', params.pageSize.toString());

    const res = await fetch(`${API_BASE}/review-queue?${q.toString()}`);
    if (!res.ok) throw new Error('Failed to load review queue');
    return res.json();
  },

  async submitReview(observationId: string, decision: string, notes?: string) {
    const res = await fetch(`${API_BASE}/reviews`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        observation_id: observationId,
        decision,
        notes: notes || '',
      }),
    });
    if (!res.ok) throw new Error('Failed to submit review decision');
    return res.json();
  },

  async getReviewHistory(observationId: string): Promise<DecisionRecord[]> {
    const res = await fetch(`${API_BASE}/reviews/${observationId}/history`);
    if (!res.ok) throw new Error('Failed to load review history');
    return res.json();
  },

  async getModelConfig(): Promise<ModelConfigDetailResponse> {
    const res = await fetch(`${API_BASE}/model/config`);
    if (!res.ok) throw new Error('Failed to load model configuration');
    return res.json();
  },

  async rerunIsolationForest(contamination: number, nEstimators: number = 150, randomState: number = 42): Promise<ModelRerunResponse> {
    const res = await fetch(`${API_BASE}/model/rerun`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        contamination,
        n_estimators: nEstimators,
        random_state: randomState,
      }),
    });
    return handleResponse<ModelRerunResponse>(res, 'Failed to rerun Isolation Forest');
  },

  async getModelRuns(limit: number = 20): Promise<ModelRunSummary[]> {
    const res = await fetch(`${API_BASE}/model/runs?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to load model runs');
    return res.json();
  },

  async compareModelRuns(currentRunId?: string, previousRunId?: string): Promise<ModelComparison> {
    const params = new URLSearchParams();
    if (currentRunId) params.append('current_run_id', currentRunId);
    if (previousRunId) params.append('previous_run_id', previousRunId);
    const res = await fetch(`${API_BASE}/model/compare?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to compare model runs');
    return res.json();
  },

  async reanalyzeSettings(contamination: number, nEstimators: number = 150) {
    return this.rerunIsolationForest(contamination, nEstimators);
  },

  getExportCsvUrl(flaggedOnly: boolean = true): string {
    return `${API_BASE}/export/csv?flagged_only=${flaggedOnly}`;
  },

  getExportReviewsCsvUrl(): string {
    return `${API_BASE}/export/reviews/csv`;
  },

  getExportReportUrl(): string {
    return `${API_BASE}/export/report`;
  },

  // ==========================================
  // Consumer Account APIs
  // ==========================================
  async getAccounts(search?: string, district?: string): Promise<AccountItem[]> {
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    if (district && district !== 'all') params.append('district', district);
    const res = await fetch(`${API_BASE}/accounts?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch accounts list');
    return res.json();
  },

  async getAccountDetail(accountId: string): Promise<AccountItem> {
    const res = await fetch(`${API_BASE}/accounts/${accountId}`);
    if (!res.ok) throw new Error(`Account ${accountId} not found`);
    return res.json();
  },

  // ==========================================
  // Account Verification Engine APIs
  // ==========================================
  async runVerification(
    accountId: string,
    scope: string = 'FULL_HISTORICAL_AUDIT',
    timeWindowDays?: number,
    autoCreateCases: boolean = true
  ): Promise<VerificationRun> {
    const res = await fetch(`${API_BASE}/verification/run`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        account_id: accountId,
        scope,
        time_window_days: timeWindowDays,
        auto_create_cases: autoCreateCases,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to run verification engine');
    }
    return res.json();
  },

  async getVerificationDetails(verificationId: string): Promise<VerificationRun> {
    const res = await fetch(`${API_BASE}/verification/${verificationId}`);
    if (!res.ok) throw new Error('Failed to fetch verification details');
    return res.json();
  },

  async getAccountVerificationHistory(accountId: string): Promise<VerificationRun[]> {
    const res = await fetch(`${API_BASE}/accounts/${accountId}/verification-history`);
    if (!res.ok) throw new Error('Failed to fetch verification history');
    return res.json();
  },

  // ==========================================
  // Case Management APIs
  // ==========================================
  async getCases(params: {
    status?: string;
    priority?: string;
    category?: string;
    assignee?: string;
    meterId?: string;
    search?: string;
    page?: number;
    pageSize?: number;
  }): Promise<CaseListResponse> {
    const q = new URLSearchParams();
    if (params.status && params.status !== 'all') q.append('status', params.status);
    if (params.priority && params.priority !== 'all') q.append('priority', params.priority);
    if (params.category && params.category !== 'all') q.append('category', params.category);
    if (params.assignee && params.assignee !== 'all') q.append('assignee', params.assignee);
    if (params.meterId) q.append('meter_id', params.meterId);
    if (params.search) q.append('search', params.search);
    if (params.page) q.append('page', params.page.toString());
    if (params.pageSize) q.append('page_size', params.pageSize.toString());

    const res = await fetch(`${API_BASE}/cases?${q.toString()}`);
    if (!res.ok) throw new Error('Failed to load cases');
    return res.json();
  },

  async getCaseDetail(caseId: string): Promise<CaseDetail> {
    const res = await fetch(`${API_BASE}/cases/${caseId}`);
    if (!res.ok) throw new Error(`Case ${caseId} not found`);
    return res.json();
  },

  async updateCaseStatus(caseId: string, status: string, reason: string): Promise<CaseItem> {
    const res = await fetch(`${API_BASE}/cases/${caseId}/status`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ status, reason }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update case status');
    }
    return res.json();
  },

  async assignCase(caseId: string, assignedOfficer: string, reason: string): Promise<CaseItem> {
    const res = await fetch(`${API_BASE}/cases/${caseId}/assign`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ assigned_officer: assignedOfficer, reason }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to assign case officer');
    }
    return res.json();
  },

  async submitCaseDecision(
    caseId: string,
    decision: string,
    decisionReason: string,
    notes?: string
  ): Promise<CaseItem> {
    const res = await fetch(`${API_BASE}/cases/${caseId}/decision`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ decision, decision_reason: decisionReason, notes: notes || '' }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to submit review decision');
    }
    return res.json();
  },

  async addCaseNote(caseId: string, noteText: string): Promise<CaseNote> {
    const res = await fetch(`${API_BASE}/cases/${caseId}/notes`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ note_text: noteText }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to add note');
    }
    return res.json();
  },

  async getCaseAuditTrail(caseId: string): Promise<CaseAuditEvent[]> {
    const res = await fetch(`${API_BASE}/cases/${caseId}/audit-trail`);
    if (!res.ok) throw new Error('Failed to load audit trail');
    return res.json();
  },

  // ==========================================
  // Phase 2 & 3: Billing & Payment Sandbox API
  // ==========================================

  async getTariffs(): Promise<TariffRule[]> {
    const res = await fetch(`${API_BASE}/tariffs`);
    if (!res.ok) throw new Error('Failed to load tariffs');
    return res.json();
  },

  async updateTariff(
    tariffId: string,
    payload: { rate_per_kwh_paise?: number; fixed_charge_paise?: number; tariff_name?: string }
  ): Promise<TariffRule> {
    const res = await fetch(`${API_BASE}/tariffs/${tariffId}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update tariff');
    }
    return res.json();
  },

  async getBillingSummary(): Promise<BillingSummary> {
    const res = await fetch(`${API_BASE}/billing/summary`);
    if (!res.ok) throw new Error('Failed to load billing summary');
    return res.json();
  },

  async seedBillingDataset(): Promise<{ message: string; seeded: boolean; counts: any }> {
    const res = await fetch(`${API_BASE}/billing/seed`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to seed billing demonstration dataset');
    return res.json();
  },

  async getSyntheticBills(params?: {
    account_id?: string;
    scenario_label?: string;
    limit?: number;
    offset?: number;
  }): Promise<SyntheticBillListResponse> {
    const q = new URLSearchParams();
    if (params?.account_id) q.append('account_id', params.account_id);
    if (params?.scenario_label && params.scenario_label !== 'ALL') q.append('scenario_label', params.scenario_label);
    if (params?.limit) q.append('limit', params.limit.toString());
    if (params?.offset) q.append('offset', params.offset.toString());
    const res = await fetch(`${API_BASE}/billing/bills?${q.toString()}`);
    if (!res.ok) throw new Error('Failed to load synthetic bills');
    return res.json();
  },

  async getSyntheticBill(billId: string): Promise<SyntheticBill> {
    const res = await fetch(`${API_BASE}/billing/bills/${billId}`);
    if (!res.ok) throw new Error(`Failed to load bill ${billId}`);
    return res.json();
  },

  async verifySyntheticBill(billId: string): Promise<BillingVerificationResult> {
    const res = await fetch(`${API_BASE}/billing/verify/${billId}`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to verify bill ${billId}`);
    }
    return res.json();
  },

  async getBillingVerificationHistory(billId: string): Promise<BillingVerificationResult[]> {
    const res = await fetch(`${API_BASE}/billing/verification-history/${billId}`);
    if (!res.ok) throw new Error(`Failed to load verification history for bill ${billId}`);
    return res.json();
  },

  async getSyntheticPayments(params?: {
    bill_id?: string;
    account_id?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ items: SyntheticPayment[]; total: number }> {
    const q = new URLSearchParams();
    if (params?.bill_id) q.append('bill_id', params.bill_id);
    if (params?.account_id) q.append('account_id', params.account_id);
    if (params?.status && params.status !== 'ALL') q.append('status', params.status);
    if (params?.limit) q.append('limit', params.limit.toString());
    if (params?.offset) q.append('offset', params.offset.toString());
    const res = await fetch(`${API_BASE}/payments/transactions?${q.toString()}`);
    if (!res.ok) throw new Error('Failed to load transactions');
    return res.json();
  },

  async reconcileBillPayments(billId: string): Promise<PaymentReconciliationResult> {
    const res = await fetch(`${API_BASE}/payments/reconcile/${billId}`, {
      method: 'POST',
      headers: getHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to reconcile payments for bill ${billId}`);
    }
    return res.json();
  },

  async getPaymentReconciliationHistory(billId: string): Promise<PaymentReconciliationResult[]> {
    const res = await fetch(`${API_BASE}/payments/reconciliation-history/${billId}`);
    if (!res.ok) throw new Error(`Failed to load reconciliation history for bill ${billId}`);
    return res.json();
  },

  async getBillingPaymentDiscrepancies(): Promise<{
    billing_discrepancies: BillingVerificationResult[];
    payment_discrepancies: PaymentReconciliationResult[];
    counts: any;
  }> {
    const res = await fetch(`${API_BASE}/billing-payments/discrepancies`);
    if (!res.ok) throw new Error('Failed to load billing/payment discrepancies');
    return res.json();
  },
};
