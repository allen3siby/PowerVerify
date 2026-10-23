import React, { useState, useEffect } from 'react';
import {
  FileText,
  CreditCard,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  HelpCircle,
  RefreshCw,
  Sliders,
  DollarSign,
  ExternalLink,
  ShieldAlert,
  Info,
  Zap,
} from 'lucide-react';
import { api } from '../api';
import type {
  SyntheticBill,
  SyntheticPayment,
  BillingVerificationResult,
  PaymentReconciliationResult,
  BillingSummary,
  TariffRule,
} from '../types';
import { CaseWorkspaceModal } from '../components/CaseWorkspaceModal';

interface BillingPaymentsProps {
  onSelectMeter?: (meterId: string) => void;
  onNavigateToCase?: (caseId: string) => void;
}

export const BillingPayments: React.FC<BillingPaymentsProps> = ({
  onSelectMeter,
  onNavigateToCase: _onNavigateToCase,
}) => {
  const [subTab, setSubTab] = useState<'billing' | 'payments' | 'summary' | 'tariffs'>('billing');
  const [_loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Summary State
  const [summary, setSummary] = useState<BillingSummary | null>(null);

  // Tariffs State
  const [tariffs, setTariffs] = useState<TariffRule[]>([]);
  const [editingTariff, setEditingTariff] = useState<TariffRule | null>(null);
  const [ratePaiseInput, setRatePaiseInput] = useState<number>(650);
  const [fixedPaiseInput, setFixedPaiseInput] = useState<number>(11000);
  const [savingTariff, setSavingTariff] = useState<boolean>(false);

  // Bills State
  const [bills, setBills] = useState<SyntheticBill[]>([]);
  const [selectedBillId, setSelectedBillId] = useState<string>('');
  const [scenarioFilter, setScenarioFilter] = useState<string>('ALL');
  const [verifyingBill, setVerifyingBill] = useState<boolean>(false);
  const [verificationResult, setVerificationResult] = useState<BillingVerificationResult | null>(null);
  const [_verificationHistory, setVerificationHistory] = useState<BillingVerificationResult[]>([]);

  // Payments State
  const [transactions, setTransactions] = useState<SyntheticPayment[]>([]);
  const [selectedReconcileBillId, setSelectedReconcileBillId] = useState<string>('');
  const [reconcilingPayment, setReconcilingPayment] = useState<boolean>(false);
  const [reconciliationResult, setReconciliationResult] = useState<PaymentReconciliationResult | null>(null);
  const [_reconciliationHistory, setReconciliationHistory] = useState<PaymentReconciliationResult[]>([]);

  // Case Modal State
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [isCaseModalOpen, setIsCaseModalOpen] = useState<boolean>(false);

  // Formatters
  const formatInr = (paise?: number | null) => {
    if (paise === undefined || paise === null) return '—';
    return (paise / 100).toLocaleString('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 2,
    });
  };

  const formatPaise = (paise?: number | null) => {
    if (paise === undefined || paise === null) return '—';
    return `${paise.toLocaleString('en-IN')} paise`;
  };

  // Load Initial Data
  const loadInitialData = async (preserveBillId?: string) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const [sumRes, tariffRes, billsRes, paymentsRes] = await Promise.all([
        api.getBillingSummary(),
        api.getTariffs(),
        api.getSyntheticBills({ limit: 100 }),
        api.getSyntheticPayments({ limit: 100 }),
      ]);
      setSummary(sumRes);
      setTariffs(tariffRes);
      setBills(billsRes.items);
      setTransactions(paymentsRes.items);

      const targetBillId = preserveBillId || selectedBillId || (billsRes.items.length > 0 ? billsRes.items[0].bill_id : '');
      if (targetBillId && billsRes.items.some((b) => b.bill_id === targetBillId)) {
        setSelectedBillId(targetBillId);
        try {
          const hist = await api.getBillingVerificationHistory(targetBillId);
          setVerificationHistory(hist);
          if (hist.length > 0) {
            setVerificationResult(hist[0]);
          } else {
            setVerificationResult(null);
          }
        } catch (e) {
          console.error('Failed to load verification history', e);
        }
      } else if (billsRes.items.length > 0) {
        setSelectedBillId(billsRes.items[0].bill_id);
      }

      if (!selectedReconcileBillId && billsRes.items.length > 0) {
        setSelectedReconcileBillId(billsRes.items[0].bill_id);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to initialize Billing & Payment sandbox');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  // When selected bill changes in Billing tab, fetch its history
  useEffect(() => {
    if (!selectedBillId) return;
    const fetchHistory = async () => {
      try {
        const hist = await api.getBillingVerificationHistory(selectedBillId);
        setVerificationHistory(hist);
        if (hist.length > 0) {
          setVerificationResult(hist[0]);
        } else {
          setVerificationResult(null);
        }
      } catch (e) {
        console.error('Failed to load verification history', e);
      }
    };
    fetchHistory();
  }, [selectedBillId]);

  // When selected bill changes in Payments tab, fetch its reconciliation history
  useEffect(() => {
    if (!selectedReconcileBillId) return;
    const fetchHistory = async () => {
      try {
        const hist = await api.getPaymentReconciliationHistory(selectedReconcileBillId);
        setReconciliationHistory(hist);
        if (hist.length > 0) {
          setReconciliationResult(hist[0]);
        } else {
          setReconciliationResult(null);
        }
      } catch (e) {
        console.error('Failed to load reconciliation history', e);
      }
    };
    fetchHistory();
  }, [selectedReconcileBillId]);

  // Run Billing Verification for selected bill
  const handleVerifyBill = async (billId: string) => {
    setVerifyingBill(true);
    try {
      const res = await api.verifySyntheticBill(billId);
      setVerificationResult(res);
      // Refresh history, summary, and bills list
      const [hist, sum, billsRes] = await Promise.all([
        api.getBillingVerificationHistory(billId),
        api.getBillingSummary(),
        api.getSyntheticBills({ limit: 100 }),
      ]);
      setVerificationHistory(hist);
      setSummary(sum);
      setBills(billsRes.items);
    } catch (err: any) {
      alert(`Verification failed: ${err.message}`);
    } finally {
      setVerifyingBill(false);
    }
  };

  // Run Payment Reconciliation for selected bill
  const handleReconcileBill = async (billId: string) => {
    setReconcilingPayment(true);
    try {
      const res = await api.reconcileBillPayments(billId);
      setReconciliationResult(res);
      // Refresh history & summary
      const [hist, sum] = await Promise.all([
        api.getPaymentReconciliationHistory(billId),
        api.getBillingSummary(),
      ]);
      setReconciliationHistory(hist);
      setSummary(sum);
    } catch (err: any) {
      alert(`Reconciliation failed: ${err.message}`);
    } finally {
      setReconcilingPayment(false);
    }
  };

  // Re-seed demonstration dataset
  const handleReSeed = async () => {
    if (!confirm('Re-seed synthetic billing and payments sandbox dataset? Existing test results will reset.')) {
      return;
    }
    setLoading(true);
    try {
      await api.seedBillingDataset();
      await loadInitialData();
      alert('Demonstration dataset re-seeded successfully.');
    } catch (err: any) {
      alert(`Failed to re-seed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Update Tariff Rule
  const handleSaveTariff = async () => {
    if (!editingTariff) return;
    setSavingTariff(true);
    try {
      const updated = await api.updateTariff(editingTariff.tariff_id, {
        rate_per_kwh_paise: Number(ratePaiseInput),
        fixed_charge_paise: Number(fixedPaiseInput),
        tariff_name: editingTariff.tariff_name,
      });
      setTariffs((prev) => prev.map((t) => (t.tariff_id === updated.tariff_id ? updated : t)));
      setEditingTariff(null);
      alert('Tariff rule updated. Future verifications will use these new rates.');
    } catch (err: any) {
      alert(`Failed to update tariff: ${err.message}`);
    } finally {
      setSavingTariff(false);
    }
  };

  // Filtered bills
  const filteredBills = bills.filter((b) => {
    if (scenarioFilter === 'ALL') return true;
    return b.scenario_label === scenarioFilter;
  });

  const selectedBill = bills.find((b) => b.bill_id === selectedBillId);
  const selectedReconcileBill = bills.find((b) => b.bill_id === selectedReconcileBillId);

  // Status Badge Helper
  const renderStatusBadge = (status?: string | null) => {
    if (!status) return <span className="badge badge-slate">UNVERIFIED</span>;
    switch (status) {
      case 'PASS':
      case 'SETTLED':
        return (
          <span className="badge badge-green" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <CheckCircle2 size={13} /> {status}
          </span>
        );
      case 'FLAGGED':
      case 'REQUIRES_REVIEW':
        return (
          <span className="badge badge-red" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <AlertCircle size={13} /> {status}
          </span>
        );
      case 'PARTIALLY_PAID':
        return (
          <span className="badge badge-amber" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <AlertTriangle size={13} /> {status}
          </span>
        );
      case 'OVERPAID':
        return (
          <span className="badge" style={{ background: '#f5f3ff', color: '#6d28d9', borderColor: '#ddd6fe', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <DollarSign size={13} /> {status}
          </span>
        );
      case 'UNPAID':
        return (
          <span className="badge badge-amber" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <AlertCircle size={13} /> {status}
          </span>
        );
      case 'NOT_ASSESSED':
      default:
        return (
          <span className="badge badge-slate" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <HelpCircle size={13} /> {status}
          </span>
        );
    }
  };

  return (
    <div className="page-container" style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* Synthetic Demo Provenance Banner */}
      <div
        style={{
          background: 'linear-gradient(90deg, #eff6ff 0%, #f0fdf4 100%)',
          border: '1px solid #bfdbfe',
          borderRadius: 'var(--radius-md)',
          padding: '16px 20px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '14px',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div
          style={{
            background: 'var(--primary-blue)',
            color: '#fff',
            borderRadius: '6px',
            padding: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginTop: '2px',
          }}
        >
          <Zap size={20} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
            <strong style={{ color: 'var(--primary-blue)', fontSize: '0.95rem' }}>
              DEMONSTRATION & SANDBOX ENVIRONMENT: BILLING & PAYMENT RECONCILIATION
            </strong>
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 600,
                textTransform: 'uppercase',
                background: '#dbeafe',
                color: '#1e40af',
                padding: '2px 8px',
                borderRadius: '12px',
                border: '1px solid #93c5fd',
              }}
            >
              PROVENANCE: SYNTHETIC_DEMO
            </span>
          </div>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.45 }}>
            Operational CEEW smart-meter records contain raw hourly and daily kW/kWh interval telemetry and do not include real commercial DISCOM utility bills or bank transactions.
            To verify tariff calculation rules and payment reconciliation logic safely, this sandbox uses <strong>exact integer-paise arithmetic</strong> (no floating point rounding error) with deterministic synthetic bills and bank receipts mapped against real CEEW interval telemetry.
          </p>
        </div>
        <button
          className="btn btn-secondary"
          onClick={handleReSeed}
          title="Reset demonstration sandbox data to factory seeds"
          style={{ fontSize: '0.78rem', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <RefreshCw size={14} /> Re-Seed Sandbox
        </button>
      </div>

      {/* Sub-navigation Tabs */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid var(--border-color)',
          marginBottom: '24px',
        }}
      >
        <div style={{ display: 'flex', gap: '4px' }}>
          <button
            className={`btn ${subTab === 'billing' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ borderRadius: '6px 6px 0 0', borderBottom: 'none' }}
            onClick={() => setSubTab('billing')}
          >
            <FileText size={16} /> Billing Verification
          </button>
          <button
            className={`btn ${subTab === 'payments' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ borderRadius: '6px 6px 0 0', borderBottom: 'none' }}
            onClick={() => setSubTab('payments')}
          >
            <CreditCard size={16} /> Payment Reconciliation
          </button>
          <button
            className={`btn ${subTab === 'summary' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ borderRadius: '6px 6px 0 0', borderBottom: 'none' }}
            onClick={() => setSubTab('summary')}
          >
            <DollarSign size={16} /> Demonstration Summary & KPIs
          </button>
          <button
            className={`btn ${subTab === 'tariffs' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ borderRadius: '6px 6px 0 0', borderBottom: 'none' }}
            onClick={() => setSubTab('tariffs')}
          >
            <Sliders size={16} /> Configured Tariffs
          </button>
        </div>

        <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
          {summary && (
            <span>
              Bills: <strong>{summary.total_bills}</strong> • Billed Total:{' '}
              <strong>₹{summary.total_bill_amount_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong>
            </span>
          )}
        </div>
      </div>

      {/* Error Message */}
      {errorMsg && (
        <div
          style={{
            background: 'var(--badge-red-bg)',
            color: 'var(--badge-red-text)',
            border: '1px solid var(--badge-red-border)',
            borderRadius: 'var(--radius-md)',
            padding: '12px 16px',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <AlertCircle size={18} /> {errorMsg}
        </div>
      )}

      {/* SUB-TAB 1: BILLING VERIFICATION */}
      {subTab === 'billing' && (
        <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: '24px' }}>
          {/* Left Column: Bills Selector & Filter */}
          <div className="card" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>Demonstration Bills</h3>
              <span className="badge badge-slate">{filteredBills.length} Bills</span>
            </div>

            {/* Scenario Filter */}
            <div style={{ marginBottom: '14px' }}>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                FILTER BY SCENARIO
              </label>
              <select
                className="input-select"
                value={scenarioFilter}
                onChange={(e) => setScenarioFilter(e.target.value)}
                style={{ width: '100%', fontSize: '0.8rem', padding: '6px 10px' }}
              >
                <option value="ALL">All Scenarios ({bills.length})</option>
                <option value="PERFECT_MATCH">Perfect Match (Valid)</option>
                <option value="UNIT_MISMATCH">Unit Mismatch (Discrepancy)</option>
                <option value="TARIFF_CALC_ERROR">Tariff Calc Error (Discrepancy)</option>
                <option value="MISSING_TELEMETRY">Missing Telemetry (&lt;80%)</option>
                <option value="ZERO_CONSUMPTION">Zero Consumption (Unoccupied)</option>
                <option value="EXTREME_HIGH_BILL">Extreme High Bill</option>
                <option value="ARREARS_CARRIED_OVER">Arrears Carried Over</option>
                <option value="ROUNDING_DISCREPANCY">Rounding Discrepancy</option>
              </select>
            </div>

            {/* Bills List */}
            <div style={{ maxHeight: '600px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {filteredBills.map((b) => {
                const isSelected = b.bill_id === selectedBillId;
                return (
                  <div
                    key={b.bill_id}
                    onClick={() => setSelectedBillId(b.bill_id)}
                    style={{
                      padding: '12px',
                      borderRadius: 'var(--radius-sm)',
                      border: isSelected ? '2px solid var(--primary-blue)' : '1px solid var(--border-color)',
                      background: isSelected ? 'var(--primary-light)' : '#ffffff',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{b.bill_id}</span>
                      <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {formatInr(b.bill_amount_paise)}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                      Acc: <strong>{b.account_id}</strong> • Meter: {b.meter_id}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.72rem', marginTop: '6px' }}>
                      <span style={{ color: 'var(--text-muted)' }}>{b.period_start} to {b.period_end}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                        {b.latest_verification_status === 'FLAGGED' ? (
                          <span className="badge badge-red" style={{ fontSize: '0.65rem', padding: '1px 5px' }}>FLAGGED</span>
                        ) : b.latest_verification_status === 'PASS' ? (
                          <span className="badge badge-green" style={{ fontSize: '0.65rem', padding: '1px 5px' }}>PASS</span>
                        ) : (
                          <span className="badge badge-slate" style={{ fontSize: '0.65rem', padding: '1px 5px' }}>UNVERIFIED</span>
                        )}
                        {b.case_status && (
                          <span
                            className={`badge ${b.case_status === 'RESOLVED' || b.case_status === 'CLOSED' ? 'badge-green' : 'badge-amber'}`}
                            style={{ fontSize: '0.65rem', padding: '1px 5px' }}
                          >
                            Case: {b.case_status}
                          </span>
                        )}
                        {Boolean(b.is_recurring) && (
                          <span className="badge badge-amber" style={{ fontSize: '0.65rem', padding: '1px 4px' }} title="Recurring discrepancy detected">
                            🔁
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Bill Details & Verification Sandbox */}
          <div>
            {selectedBill ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {/* Bill Header Card */}
                <div className="card" style={{ padding: '20px' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '16px' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>Bill {selectedBill.bill_id}</h2>
                        <span className="badge badge-slate" style={{ fontSize: '0.75rem' }}>
                          Scenario: {selectedBill.scenario_label}
                        </span>
                        <span className="badge badge-slate" style={{ fontSize: '0.72rem', background: '#e0f2fe', color: '#0369a1' }}>
                          SYNTHETIC_DEMO
                        </span>
                      </div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        Account: <strong>{selectedBill.account_id}</strong> • Meter ID:{' '}
                        <button
                          className="btn-link"
                          onClick={() => onSelectMeter && onSelectMeter(selectedBill.meter_id)}
                          style={{ fontWeight: 600, color: 'var(--primary-blue)', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
                        >
                          {selectedBill.meter_id} <ExternalLink size={12} style={{ display: 'inline' }} />
                        </button>
                      </div>
                    </div>

                    <button
                      className="btn btn-primary"
                      onClick={() => handleVerifyBill(selectedBill.bill_id)}
                      disabled={verifyingBill}
                      style={{ padding: '8px 18px', display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                      <RefreshCw size={15} className={verifyingBill ? 'spin' : ''} />
                      {verifyingBill ? 'Verifying...' : 'Run Billing Verification'}
                    </button>
                  </div>

                  {/* Bill Metrics Grid */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(4, 1fr)',
                      gap: '14px',
                      background: 'var(--bg-main)',
                      padding: '14px',
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        Billing Period
                      </div>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                        {selectedBill.period_start} → {selectedBill.period_end}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        Billed Units
                      </div>
                      <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--primary-blue)' }}>
                        {selectedBill.consumed_units_kwh.toFixed(2)} <span style={{ fontSize: '0.75rem', fontWeight: 400 }}>kWh</span>
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        Billed Amount
                      </div>
                      <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {formatInr(selectedBill.bill_amount_paise)}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        Exact: {formatPaise(selectedBill.bill_amount_paise)}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        Latest Verification
                      </div>
                      <div style={{ marginTop: '2px' }}>
                        {renderStatusBadge(verificationResult?.overall_result)}
                      </div>
                    </div>
                  </div>

                  {selectedBill.notes && (
                    <div style={{ marginTop: '12px', fontSize: '0.78rem', color: 'var(--text-secondary)', background: '#fff', padding: '8px 12px', borderRadius: '4px', border: '1px dashed var(--border-color)' }}>
                      <strong>Synthetic Scenario Context:</strong> {selectedBill.notes}
                    </div>
                  )}

                  {/* Finding & Investigation Governance Lifecycle Panel */}
                  {(selectedBill.linked_case_id || verificationResult?.linked_case_id) && (
                    <div
                      style={{
                        marginTop: '16px',
                        padding: '16px',
                        background: '#f8fafc',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <ShieldAlert size={16} color="var(--primary-blue)" />
                          <span style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                            Discrepancy Investigation & Finding Lifecycle
                          </span>
                          {Boolean(verificationResult?.is_recurring || selectedBill.is_recurring) && (
                            <span className="badge badge-amber" style={{ fontSize: '0.72rem' }}>
                              🔁 Recurring Observation
                            </span>
                          )}
                        </div>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setSelectedCaseId(verificationResult?.linked_case_id || selectedBill.linked_case_id!);
                            setIsCaseModalOpen(true);
                          }}
                          style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '6px' }}
                        >
                          <ExternalLink size={13} /> Open Case Workspace ({verificationResult?.case_status || selectedBill.case_status || 'OPEN'})
                        </button>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', fontSize: '0.8rem' }}>
                        <div>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Finding ID</span>
                          <div style={{ fontWeight: 600, fontFamily: 'JetBrains Mono, monospace', fontSize: '0.8rem' }}>
                            {verificationResult?.finding_id || `BILL_DISCREPANCY_${selectedBill.bill_id}`}
                          </div>
                        </div>
                        <div>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Review Status</span>
                          <div>
                            <span className={`badge ${(verificationResult?.review_status || selectedBill.review_status) === 'REVIEWED' ? 'badge-green' : 'badge-amber'}`}>
                              {(verificationResult?.review_status || selectedBill.review_status || 'PENDING')}
                            </span>
                          </div>
                        </div>
                        <div>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Investigation Status</span>
                          <div>
                            <span className={`badge ${(verificationResult?.case_status || selectedBill.case_status) === 'RESOLVED' ? 'badge-green' : 'badge-amber'}`}>
                              Case: {(verificationResult?.case_status || selectedBill.case_status || 'OPEN')}
                            </span>
                          </div>
                        </div>
                        <div>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Adjudicated Decision</span>
                          <div style={{ fontWeight: 600, color: (verificationResult?.review_decision || selectedBill.review_decision) ? 'var(--primary-blue)' : 'var(--text-muted)' }}>
                            {(verificationResult?.review_decision || selectedBill.review_decision) ? (verificationResult?.review_decision || selectedBill.review_decision) : 'Pending Review'}
                          </div>
                        </div>
                      </div>

                      {/* Documented Justification */}
                      {(verificationResult?.decision_reason || selectedBill.decision_reason) && (
                        <div style={{ marginTop: '10px', padding: '10px 12px', background: '#eff6ff', borderRadius: 'var(--radius-sm)', border: '1px solid #bfdbfe', fontSize: '0.8rem', color: '#1e3a8a' }}>
                          <strong>Recorded Decision Justification:</strong> &ldquo;{verificationResult?.decision_reason || selectedBill.decision_reason}&rdquo;
                          {(verificationResult?.resolved_at || selectedBill.resolved_at) && (
                            <span style={{ marginLeft: '8px', color: '#3b82f6', fontSize: '0.75rem' }}>
                              (Resolved: {(verificationResult?.resolved_at || selectedBill.resolved_at)?.substring(0, 16).replace('T', ' ')})
                            </span>
                          )}
                        </div>
                      )}

                      {/* Regulatory Distinction Notice for FLAGGED verification + RESOLVED case */}
                      {verificationResult?.overall_result === 'FLAGGED' && (verificationResult?.case_status === 'RESOLVED' || selectedBill.case_status === 'RESOLVED') && (
                        <div
                          style={{
                            marginTop: '10px',
                            padding: '10px 12px',
                            background: '#fffbeb',
                            borderRadius: 'var(--radius-sm)',
                            border: '1px solid #fde68a',
                            fontSize: '0.78rem',
                            color: '#92400e',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                          }}
                        >
                          <Info size={16} color="#d97706" style={{ flexShrink: 0 }} />
                          <div>
                            <strong>Regulatory Audit Transparency:</strong> Telemetry verification mathematically remains <strong>FLAGGED</strong> ({verificationResult.coverage_details ? `${(verificationResult.coverage_details.coverage_ratio * 100).toFixed(1)}%` : '73.3%'} coverage &lt; 80% threshold). The linked investigation case is formally <strong>RESOLVED</strong>. Administrative resolution records the authorized adjudication without falsifying the historical telemetry fact.
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Verification Evaluation Card */}
                {verificationResult ? (
                  <div className="card" style={{ padding: '20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <h3 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>4-Step Audit Verification Breakdown</h3>
                        {renderStatusBadge(verificationResult.overall_result)}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        Evaluated: {new Date(verificationResult.evaluated_at).toLocaleString()}
                      </div>
                    </div>

                    {/* Step Cards Grid */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '20px' }}>
                      {/* Check 1: Telemetry Completeness */}
                      <div
                        style={{
                          border: '1px solid var(--border-color)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '14px',
                          background: verificationResult.coverage_status === 'COMPLETE' ? '#f0fdf4' : '#fffbeb',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                          <span style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>
                            1. Interval Telemetry Coverage
                          </span>
                          <span
                            className={`badge ${
                              verificationResult.coverage_status === 'COMPLETE' ? 'badge-green' : 'badge-amber'
                            }`}
                          >
                            {verificationResult.coverage_status}
                          </span>
                        </div>
                        <div style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '4px' }}>
                          {verificationResult.coverage_details
                            ? `${(verificationResult.coverage_details.coverage_ratio * 100).toFixed(1)}%`
                            : '—'}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                          Observed:{' '}
                          <strong>
                            {verificationResult.coverage_details?.days_observed ?? '—'} /{' '}
                            {verificationResult.coverage_details?.expected_days ?? '—'} days
                          </strong>
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                          Requirement: ≥ 80% coverage
                        </div>
                      </div>

                      {/* Check 2: Metered vs Billed Units */}
                      <div
                        style={{
                          border: '1px solid var(--border-color)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '14px',
                          background: verificationResult.units_check_status === 'MATCH' ? '#f0fdf4' : '#fef2f2',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                          <span style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>
                            2. Unit Consumption Match
                          </span>
                          <span
                            className={`badge ${
                              verificationResult.units_check_status === 'MATCH' ? 'badge-green' : 'badge-red'
                            }`}
                          >
                            {verificationResult.units_check_status}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.85rem', marginBottom: '2px' }}>
                          Metered: <strong>{verificationResult.metered_units !== null ? `${verificationResult.metered_units?.toFixed(2)} kWh` : 'N/A'}</strong>
                        </div>
                        <div style={{ fontSize: '0.85rem', marginBottom: '4px' }}>
                          Billed: <strong>{verificationResult.billed_units.toFixed(2)} kWh</strong>
                        </div>
                        <div style={{ fontSize: '0.75rem', color: (verificationResult.unit_difference !== null && verificationResult.unit_difference !== undefined && Math.abs(verificationResult.unit_difference) > 0.05) ? 'var(--badge-red-text)' : 'var(--badge-green-text)', fontWeight: 600 }}>
                          Difference: {(verificationResult.unit_difference !== null && verificationResult.unit_difference !== undefined) ? `${verificationResult.unit_difference > 0 ? '+' : ''}${verificationResult.unit_difference.toFixed(2)} kWh` : '—'}
                        </div>
                      </div>

                      {/* Check 3: Tariff Math Calculation */}
                      <div
                        style={{
                          border: '1px solid var(--border-color)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '14px',
                          background: verificationResult.amount_check_status === 'MATCH' ? '#f0fdf4' : '#fef2f2',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                          <span style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>
                            3. Tariff Calculation Math
                          </span>
                          <span
                            className={`badge ${
                              verificationResult.amount_check_status === 'MATCH' ? 'badge-green' : 'badge-red'
                            }`}
                          >
                            {verificationResult.amount_check_status}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.85rem', marginBottom: '2px' }}>
                          Expected: <strong>{formatInr(verificationResult.expected_bill_amount_paise)}</strong>
                        </div>
                        <div style={{ fontSize: '0.85rem', marginBottom: '4px' }}>
                          Billed: <strong>{formatInr(verificationResult.billed_amount_paise)}</strong>
                        </div>
                        <div style={{ fontSize: '0.75rem', color: verificationResult.amount_difference_paise && Math.abs(verificationResult.amount_difference_paise) > 100 ? 'var(--badge-red-text)' : 'var(--badge-green-text)', fontWeight: 600 }}>
                          Diff: {verificationResult.amount_difference_paise !== null ? formatInr(verificationResult.amount_difference_paise) : '—'} ({formatPaise(verificationResult.amount_difference_paise)})
                        </div>
                      </div>
                    </div>

                    {/* Tariff Snapshot Formula Breakdown */}
                    {verificationResult.tariff_snapshot && (
                      <div
                        style={{
                          background: 'var(--bg-main)',
                          padding: '12px 16px',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.8rem',
                          marginBottom: '16px',
                          border: '1px solid var(--border-color)',
                        }}
                      >
                        <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>Configured Tariff Formula: </span>
                        <code>
                          Expected Paise = round({verificationResult.billed_units.toFixed(2)} kWh × {verificationResult.tariff_snapshot.rate_per_kwh_paise} paise) + {verificationResult.tariff_snapshot.fixed_charge_paise} paise = {verificationResult.expected_bill_amount_paise} paise (₹{(Number(verificationResult.expected_bill_amount_paise || 0) / 100).toFixed(2)})
                        </code>
                      </div>
                    )}

                    {/* Result Reason Banner & Linked Case Navigation */}
                    <div
                      style={{
                        padding: '14px 18px',
                        borderRadius: 'var(--radius-sm)',
                        background: verificationResult.overall_result === 'PASS' ? 'var(--badge-green-bg)' : 'var(--badge-red-bg)',
                        border: `1px solid ${verificationResult.overall_result === 'PASS' ? 'var(--badge-green-border)' : 'var(--badge-red-border)'}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '0.88rem', color: verificationResult.overall_result === 'PASS' ? 'var(--badge-green-text)' : 'var(--badge-red-text)', marginBottom: '2px' }}>
                          Verification Audit Conclusion: {verificationResult.overall_result}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          {verificationResult.reason}
                        </div>
                      </div>

                      {verificationResult.linked_case_id && (
                        <button
                          className="btn"
                          onClick={() => {
                            setSelectedCaseId(verificationResult.linked_case_id!);
                            setIsCaseModalOpen(true);
                          }}
                          style={{
                            fontSize: '0.8rem',
                            padding: '6px 14px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            background: (verificationResult.case_status === 'RESOLVED' || selectedBill?.case_status === 'RESOLVED') ? '#15803d' : '#b91c1c',
                            color: '#ffffff',
                            border: 'none',
                            borderRadius: 'var(--radius-sm)',
                            cursor: 'pointer',
                          }}
                        >
                          <ShieldAlert size={14} /> {(verificationResult.case_status === 'RESOLVED' || selectedBill?.case_status === 'RESOLVED') ? `Case Workspace (RESOLVED)` : `Investigate Case ${verificationResult.linked_case_id}`}
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="card" style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    <Info size={32} style={{ margin: '0 auto 12px', display: 'block', color: 'var(--primary-blue)' }} />
                    <p style={{ margin: 0, fontSize: '0.9rem' }}>
                      Click <strong>"Run Billing Verification"</strong> above to compute metered telemetry sum, tariff rule math, and unit difference.
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                Select a demonstration bill from the left to inspect and verify.
              </div>
            )}
          </div>
        </div>
      )}

      {/* SUB-TAB 2: PAYMENT RECONCILIATION */}
      {subTab === 'payments' && (
        <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: '24px' }}>
          {/* Left Column: Bills for Reconciliation */}
          <div className="card" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>Bills to Reconcile</h3>
              <span className="badge badge-slate">{bills.length} Bills</span>
            </div>

            <div style={{ maxHeight: '600px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {bills.map((b) => {
                const isSelected = b.bill_id === selectedReconcileBillId;
                // Count transactions linked to this bill
                const txCount = transactions.filter((t) => t.bill_id === b.bill_id).length;
                return (
                  <div
                    key={b.bill_id}
                    onClick={() => setSelectedReconcileBillId(b.bill_id)}
                    style={{
                      padding: '12px',
                      borderRadius: 'var(--radius-sm)',
                      border: isSelected ? '2px solid var(--primary-blue)' : '1px solid var(--border-color)',
                      background: isSelected ? 'var(--primary-light)' : '#ffffff',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{b.bill_id}</span>
                      <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {formatInr(b.bill_amount_paise)}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                      Account: <strong>{b.account_id}</strong>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.72rem' }}>
                      <span style={{ color: 'var(--text-muted)' }}>{txCount} linked payments</span>
                      <span style={{ background: '#f1f5f9', padding: '1px 6px', borderRadius: '4px', fontWeight: 500 }}>
                        {b.scenario_label}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Reconciliation Sandbox View */}
          <div>
            {selectedReconcileBill ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {/* Reconciliation Header Card */}
                <div className="card" style={{ padding: '20px' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '16px' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>
                          Reconcile Bill {selectedReconcileBill.bill_id}
                        </h2>
                        {renderStatusBadge(reconciliationResult?.reconciliation_status)}
                      </div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        Account: <strong>{selectedReconcileBill.account_id}</strong> • Bill Amount:{' '}
                        <strong>{formatInr(selectedReconcileBill.bill_amount_paise)}</strong> ({formatPaise(selectedReconcileBill.bill_amount_paise)})
                      </div>
                    </div>

                    <button
                      className="btn btn-primary"
                      onClick={() => handleReconcileBill(selectedReconcileBill.bill_id)}
                      disabled={reconcilingPayment}
                      style={{ padding: '8px 18px', display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                      <RefreshCw size={15} className={reconcilingPayment ? 'spin' : ''} />
                      {reconcilingPayment ? 'Reconciling...' : 'Run Payment Reconciliation'}
                    </button>
                  </div>

                  {/* Financial Balance Summary Grid */}
                  {reconciliationResult && (
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(4, 1fr)',
                        gap: '14px',
                        background: 'var(--bg-main)',
                        padding: '14px',
                        borderRadius: 'var(--radius-sm)',
                        marginBottom: '16px',
                      }}
                    >
                      <div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                          Total Billed
                        </div>
                        <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                          {formatInr(reconciliationResult.bill_amount_paise)}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                          {formatPaise(reconciliationResult.bill_amount_paise)}
                        </div>
                      </div>

                      <div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                          Confirmed Paid
                        </div>
                        <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--badge-green-text)' }}>
                          {formatInr(reconciliationResult.confirmed_paid_paise)}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                          {formatPaise(reconciliationResult.confirmed_paid_paise)}
                        </div>
                      </div>

                      <div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                          Outstanding Balance
                        </div>
                        <div style={{ fontSize: '1.1rem', fontWeight: 700, color: reconciliationResult.outstanding_paise > 0 ? 'var(--badge-red-text)' : 'var(--text-secondary)' }}>
                          {formatInr(reconciliationResult.outstanding_paise)}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                          {formatPaise(reconciliationResult.outstanding_paise)}
                        </div>
                      </div>

                      <div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                          Overpayment
                        </div>
                        <div style={{ fontSize: '1.1rem', fontWeight: 700, color: reconciliationResult.overpayment_paise > 0 ? '#6d28d9' : 'var(--text-secondary)' }}>
                          {formatInr(reconciliationResult.overpayment_paise)}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                          {formatPaise(reconciliationResult.overpayment_paise)}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Audit Findings / Reasons */}
                  {reconciliationResult && reconciliationResult.reasons.length > 0 && (
                    <div style={{ marginBottom: '14px' }}>
                      <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
                        RECONCILIATION AUDIT FINDINGS:
                      </div>
                      <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                        {reconciliationResult.reasons.map((r, i) => (
                          <li key={i} style={{ marginBottom: '2px' }}>
                            {r}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Linked Case Button */}
                  {reconciliationResult?.linked_case_id && (
                    <div
                      style={{
                        padding: '12px 16px',
                        borderRadius: 'var(--radius-sm)',
                        background: 'var(--badge-red-bg)',
                        border: '1px solid var(--badge-red-border)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--badge-red-text)', fontSize: '0.85rem', fontWeight: 600 }}>
                        <ShieldAlert size={16} /> Discrepancy Case Auto-Created: {reconciliationResult.linked_case_id}
                      </div>
                      <button
                        className="btn btn-primary"
                        onClick={() => {
                          setSelectedCaseId(reconciliationResult.linked_case_id!);
                          setIsCaseModalOpen(true);
                        }}
                        style={{ fontSize: '0.78rem', padding: '5px 12px', background: '#b91c1c', borderColor: '#991b1b' }}
                      >
                        Open Case Investigation
                      </button>
                    </div>
                  )}
                </div>

                {/* Transactions Breakdown Tables */}
                {reconciliationResult && (
                  <div className="card" style={{ padding: '20px' }}>
                    <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '14px' }}>
                      Associated Bank & Cash Payment Records
                    </h3>

                    {/* Matched Settled Transactions */}
                    <div style={{ marginBottom: '20px' }}>
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                        Matched Settled Transactions ({reconciliationResult.matched_transactions.length})
                      </div>
                      {reconciliationResult.matched_transactions.length > 0 ? (
                        <table className="table" style={{ width: '100%', fontSize: '0.8rem' }}>
                          <thead>
                            <tr style={{ background: 'var(--bg-main)', textAlign: 'left' }}>
                              <th style={{ padding: '8px 12px' }}>Tx ID</th>
                              <th style={{ padding: '8px 12px' }}>Date</th>
                              <th style={{ padding: '8px 12px' }}>Receipt ID</th>
                              <th style={{ padding: '8px 12px' }}>Status</th>
                              <th style={{ padding: '8px 12px', textAlign: 'right' }}>Amount (Paise / INR)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {reconciliationResult.matched_transactions.map((tx) => (
                              <tr key={tx.transaction_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                                <td style={{ padding: '8px 12px', fontWeight: 600 }}>{tx.transaction_id}</td>
                                <td style={{ padding: '8px 12px' }}>{tx.payment_date}</td>
                                <td style={{ padding: '8px 12px' }}>{tx.receipt_id || '—'}</td>
                                <td style={{ padding: '8px 12px' }}>
                                  <span className="badge badge-green">{tx.transaction_status}</span>
                                </td>
                                <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600 }}>
                                  {formatInr(tx.amount_paise)} ({formatPaise(tx.amount_paise)})
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                          No settled transactions matched to this bill.
                        </div>
                      )}
                    </div>

                    {/* Duplicate Candidate Warnings */}
                    {reconciliationResult.duplicate_candidates.length > 0 && (
                      <div style={{ marginBottom: '20px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--radius-sm)', padding: '12px 14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#b91c1c', fontWeight: 600, fontSize: '0.82rem', marginBottom: '8px' }}>
                          <AlertTriangle size={15} /> Potential Duplicate Transactions Flagged ({reconciliationResult.duplicate_candidates.length})
                        </div>
                        <table className="table" style={{ width: '100%', fontSize: '0.78rem' }}>
                          <thead>
                            <tr style={{ textAlign: 'left', color: '#991b1b' }}>
                              <th>Tx ID</th>
                              <th>Receipt ID</th>
                              <th>Amount</th>
                              <th>Status</th>
                              <th>Duplicate Reason</th>
                            </tr>
                          </thead>
                          <tbody>
                            {reconciliationResult.duplicate_candidates.map((dup, i) => (
                              <tr key={i} style={{ borderBottom: '1px solid #fee2e2' }}>
                                <td style={{ padding: '4px 0', fontWeight: 600 }}>{dup.transaction_id}</td>
                                <td>{dup.receipt_id}</td>
                                <td>{formatInr(dup.amount_paise)}</td>
                                <td><span className="badge badge-red">{dup.transaction_status}</span></td>
                                <td style={{ color: '#b91c1c' }}>{dup.reason || 'Duplicate receipt number or duplicate settlement'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Pending or Reversed / Failed Payments */}
                    {(reconciliationResult.pending_transactions.length > 0 || reconciliationResult.reversed_transactions.length > 0) && (
                      <div style={{ marginTop: '14px' }}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                          Pending / Reversed / Failed Transactions
                        </div>
                        <table className="table" style={{ width: '100%', fontSize: '0.8rem' }}>
                          <thead>
                            <tr style={{ background: 'var(--bg-main)', textAlign: 'left' }}>
                              <th style={{ padding: '8px 12px' }}>Tx ID</th>
                              <th style={{ padding: '8px 12px' }}>Date</th>
                              <th style={{ padding: '8px 12px' }}>Status</th>
                              <th style={{ padding: '8px 12px', textAlign: 'right' }}>Amount</th>
                            </tr>
                          </thead>
                          <tbody>
                            {[...reconciliationResult.pending_transactions, ...reconciliationResult.reversed_transactions].map((tx) => (
                              <tr key={tx.transaction_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                                <td style={{ padding: '8px 12px' }}>{tx.transaction_id}</td>
                                <td style={{ padding: '8px 12px' }}>{tx.payment_date}</td>
                                <td style={{ padding: '8px 12px' }}>
                                  <span className={`badge ${tx.transaction_status === 'PENDING' ? 'badge-amber' : 'badge-red'}`}>
                                    {tx.transaction_status}
                                  </span>
                                </td>
                                <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                                  {formatInr(tx.amount_paise)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                Select a demonstration bill from the left to reconcile bank payments.
              </div>
            )}
          </div>
        </div>
      )}

      {/* SUB-TAB 3: DEMONSTRATION SUMMARY & KPIS */}
      {subTab === 'summary' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {summary && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
              <div className="card" style={{ padding: '18px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                  Total Demonstration Billed
                </div>
                <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--primary-blue)' }}>
                  ₹{summary.total_bill_amount_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Across {summary.total_bills} synthetic bills
                </div>
              </div>

              <div className="card" style={{ padding: '18px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                  Total Collected Payments
                </div>
                <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--badge-green-text)' }}>
                  ₹{summary.total_payment_amount_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Across {summary.total_transactions} bank transactions
                </div>
              </div>

              <div className="card" style={{ padding: '18px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                  Billing Discrepancies Flagged
                </div>
                <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--badge-red-text)' }}>
                  {summary.billing_discrepancies_flagged}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Unit diffs, tariff errors, & missing telemetry
                </div>
              </div>

              <div className="card" style={{ padding: '18px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                  Unmatched Payments
                </div>
                <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--badge-amber-text)' }}>
                  {summary.unmatched_payments_count}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Orphan receipts without matching bill
                </div>
              </div>
            </div>
          )}

          {/* Discrepancy & Case Investigation Governance Breakdown */}
          {summary && (
            <div className="card" style={{ padding: '20px' }}>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 600, marginBottom: '14px' }}>
                Discrepancy Findings & Case Investigation Governance
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px' }}>
                <div style={{ padding: '14px', borderRadius: 'var(--radius-sm)', background: '#fef2f2', border: '1px solid #fecaca' }}>
                  <div style={{ fontSize: '0.75rem', color: '#991b1b', fontWeight: 600 }}>PENDING FINDINGS</div>
                  <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#991b1b' }}>{summary.billing_discrepancies_pending ?? 0}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Awaiting review decision</div>
                </div>

                <div style={{ padding: '14px', borderRadius: 'var(--radius-sm)', background: 'var(--badge-green-bg)', border: '1px solid var(--badge-green-border)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--badge-green-text)', fontWeight: 600 }}>RESOLVED FINDINGS</div>
                  <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--badge-green-text)' }}>{summary.billing_discrepancies_resolved ?? 0}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Adjudicated with justification</div>
                </div>

                <div style={{ padding: '14px', borderRadius: 'var(--radius-sm)', background: 'var(--badge-amber-bg)', border: '1px solid var(--badge-amber-border)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--badge-amber-text)', fontWeight: 600 }}>OPEN INVESTIGATIONS</div>
                  <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--badge-amber-text)' }}>{summary.open_investigations ?? 0}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Active officer workflow cases</div>
                </div>

                <div style={{ padding: '14px', borderRadius: 'var(--radius-sm)', background: '#f0fdf4', border: '1px solid #bbf7d0' }}>
                  <div style={{ fontSize: '0.75rem', color: '#166534', fontWeight: 600 }}>RESOLVED INVESTIGATIONS</div>
                  <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#166534' }}>{summary.resolved_investigations ?? 0}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Closed / resolved cases</div>
                </div>
              </div>
            </div>
          )}

          {/* Settlement Status Breakdown */}
          {summary && (
            <div className="card" style={{ padding: '20px' }}>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 600, marginBottom: '14px' }}>
                Demonstration Reconciliation Status Distribution
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px' }}>
                <div style={{ padding: '14px', borderRadius: 'var(--radius-sm)', background: 'var(--badge-green-bg)', border: '1px solid var(--badge-green-border)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--badge-green-text)', fontWeight: 600 }}>SETTLED BILLS</div>
                  <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--badge-green-text)' }}>{summary.bills_settled}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Full payment confirmed</div>
                </div>

                <div style={{ padding: '14px', borderRadius: 'var(--radius-sm)', background: 'var(--badge-amber-bg)', border: '1px solid var(--badge-amber-border)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--badge-amber-text)', fontWeight: 600 }}>PARTIALLY PAID</div>
                  <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--badge-amber-text)' }}>{summary.bills_partially_paid}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Partial payment confirmed</div>
                </div>

                <div style={{ padding: '14px', borderRadius: 'var(--radius-sm)', background: '#fff7ed', border: '1px solid #ffedd5' }}>
                  <div style={{ fontSize: '0.75rem', color: '#c2410c', fontWeight: 600 }}>UNPAID BILLS</div>
                  <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#c2410c' }}>{summary.bills_unpaid}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Zero payment received</div>
                </div>

                <div style={{ padding: '14px', borderRadius: 'var(--radius-sm)', background: 'var(--badge-red-bg)', border: '1px solid var(--badge-red-border)' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--badge-red-text)', fontWeight: 600 }}>REQUIRES REVIEW</div>
                  <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--badge-red-text)' }}>{summary.bills_requiring_review}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Duplicate or reversed receipts</div>
                </div>
              </div>
            </div>
          )}

          {/* Unmatched Transactions List */}
          <div className="card" style={{ padding: '20px' }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, marginBottom: '14px' }}>
              All Synthetic Bank & Cash Transactions ({transactions.length})
            </h3>
            <table className="table" style={{ width: '100%', fontSize: '0.8rem' }}>
              <thead>
                <tr style={{ background: 'var(--bg-main)', textAlign: 'left' }}>
                  <th style={{ padding: '8px 12px' }}>Tx ID</th>
                  <th style={{ padding: '8px 12px' }}>Account</th>
                  <th style={{ padding: '8px 12px' }}>Bill ID</th>
                  <th style={{ padding: '8px 12px' }}>Date</th>
                  <th style={{ padding: '8px 12px' }}>Receipt ID</th>
                  <th style={{ padding: '8px 12px' }}>Status</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right' }}>Amount</th>
                  <th style={{ padding: '8px 12px' }}>Scenario</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((tx) => (
                  <tr key={tx.transaction_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '8px 12px', fontWeight: 600 }}>{tx.transaction_id}</td>
                    <td style={{ padding: '8px 12px' }}>{tx.account_id}</td>
                    <td style={{ padding: '8px 12px' }}>{tx.bill_id || <span style={{ color: 'var(--badge-amber-text)' }}>UNMATCHED</span>}</td>
                    <td style={{ padding: '8px 12px' }}>{tx.payment_date}</td>
                    <td style={{ padding: '8px 12px' }}>{tx.receipt_id || '—'}</td>
                    <td style={{ padding: '8px 12px' }}>
                      <span className={`badge ${tx.transaction_status === 'SETTLED' ? 'badge-green' : tx.transaction_status === 'PENDING' ? 'badge-amber' : 'badge-red'}`}>
                        {tx.transaction_status}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600 }}>
                      {formatInr(tx.amount_paise)}
                    </td>
                    <td style={{ padding: '8px 12px', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {tx.scenario_label}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* SUB-TAB 4: CONFIGURED TARIFFS */}
      {subTab === 'tariffs' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Active Tariff Schedules</h3>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Tariff rules use exact integer-paise representation to avoid fractional rounding discrepancies.
                </div>
              </div>
            </div>

            <table className="table" style={{ width: '100%', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ background: 'var(--bg-main)', textAlign: 'left' }}>
                  <th style={{ padding: '10px 14px' }}>Tariff ID</th>
                  <th style={{ padding: '10px 14px' }}>Name</th>
                  <th style={{ padding: '10px 14px' }}>Effective From</th>
                  <th style={{ padding: '10px 14px' }}>Energy Rate (Paise & INR)</th>
                  <th style={{ padding: '10px 14px' }}>Fixed Monthly Charge</th>
                  <th style={{ padding: '10px 14px' }}>Status</th>
                  <th style={{ padding: '10px 14px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {tariffs.map((t) => (
                  <tr key={t.tariff_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 600 }}>{t.tariff_id}</td>
                    <td style={{ padding: '10px 14px' }}>{t.tariff_name}</td>
                    <td style={{ padding: '10px 14px' }}>{t.effective_from}</td>
                    <td style={{ padding: '10px 14px', fontWeight: 600 }}>
                      {t.rate_per_kwh_paise} paise/kWh <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(₹{(t.rate_per_kwh_paise / 100).toFixed(2)}/kWh)</span>
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      {formatInr(t.fixed_charge_paise)} <span style={{ color: 'var(--text-muted)' }}>({t.fixed_charge_paise} paise)</span>
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <span className="badge badge-green">ACTIVE</span>
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                      <button
                        className="btn btn-secondary"
                        onClick={() => {
                          setEditingTariff(t);
                          setRatePaiseInput(t.rate_per_kwh_paise);
                          setFixedPaiseInput(t.fixed_charge_paise);
                        }}
                        style={{ fontSize: '0.78rem', padding: '4px 10px' }}
                      >
                        Edit Tariff
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Edit Tariff Modal / Inline Form */}
          {editingTariff && (
            <div className="card" style={{ padding: '20px', background: '#f8fafc', border: '2px solid var(--primary-blue)' }}>
              <h4 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '14px', color: 'var(--primary-blue)' }}>
                Configure Tariff: {editingTariff.tariff_name} ({editingTariff.tariff_id})
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                <div>
                  <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    Rate per kWh (in exact integer paise)
                  </label>
                  <input
                    type="number"
                    className="input-text"
                    value={ratePaiseInput}
                    onChange={(e) => setRatePaiseInput(Number(e.target.value))}
                    style={{ width: '100%', padding: '8px 12px' }}
                  />
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Equivalent in INR: ₹{(ratePaiseInput / 100).toFixed(2)} per kWh
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>
                    Fixed Monthly Charge (in exact integer paise)
                  </label>
                  <input
                    type="number"
                    className="input-text"
                    value={fixedPaiseInput}
                    onChange={(e) => setFixedPaiseInput(Number(e.target.value))}
                    style={{ width: '100%', padding: '8px 12px' }}
                  />
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Equivalent in INR: ₹{(fixedPaiseInput / 100).toFixed(2)} per month
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => setEditingTariff(null)}
                  style={{ padding: '6px 14px' }}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleSaveTariff}
                  disabled={savingTariff}
                  style={{ padding: '6px 18px' }}
                >
                  {savingTariff ? 'Saving...' : 'Save Tariff Settings'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Case Workspace Investigation Modal */}
      {isCaseModalOpen && (
        <CaseWorkspaceModal
          caseId={selectedCaseId}
          isOpen={isCaseModalOpen}
          onClose={() => setIsCaseModalOpen(false)}
          onCaseUpdated={() => {
            loadInitialData(selectedBillId);
          }}
        />
      )}
    </div>
  );
};
