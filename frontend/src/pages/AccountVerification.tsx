import React, { useState, useEffect } from 'react';
import {
  Search,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Play,
  Clock,
  Zap,
  ExternalLink,
} from 'lucide-react';
import { api } from '../api';
import type {
  AccountItem,
  VerificationRun,
} from '../types';
import { CaseWorkspaceModal } from '../components/CaseWorkspaceModal';

interface AccountVerificationProps {
  onSelectMeter?: (meterId: string) => void;
}

export const AccountVerification: React.FC<AccountVerificationProps> = ({ onSelectMeter }) => {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<AccountItem | null>(null);
  const [loadingAccounts, setLoadingAccounts] = useState<boolean>(false);

  // Verification execution state
  const [selectedScope, setSelectedScope] = useState<string>('FULL_RECONCILIATION');
  const [runningVerification, setRunningVerification] = useState<boolean>(false);
  const [currentResult, setCurrentResult] = useState<VerificationRun | null>(null);
  const [historyRuns, setHistoryRuns] = useState<VerificationRun[]>([]);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);

  // Case Investigation Modal from verification finding
  const [openedCaseId, setOpenedCaseId] = useState<string | null>(null);
  const [caseModalOpen, setCaseModalOpen] = useState<boolean>(false);

  // Search accounts
  const loadAccounts = async (query = '') => {
    setLoadingAccounts(true);
    try {
      const data = await api.getAccounts(query);
      setAccounts(data);
      if (data.length > 0 && !selectedAccount) {
        selectAccount(data[0]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingAccounts(false);
    }
  };

  useEffect(() => {
    loadAccounts();
  }, []);

  const selectAccount = async (acc: AccountItem) => {
    setSelectedAccount(acc);
    setCurrentResult(null);
    setLoadingHistory(true);
    try {
      const history = await api.getAccountVerificationHistory(acc.account_id);
      setHistoryRuns(history);
      if (history.length > 0) {
        setCurrentResult(history[0]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadAccounts(searchQuery);
  };

  const handleRunVerification = async () => {
    if (!selectedAccount) return;
    setRunningVerification(true);
    try {
      const run = await api.runVerification(selectedAccount.account_id, selectedScope);
      setCurrentResult(run);
      // Refresh history
      const history = await api.getAccountVerificationHistory(selectedAccount.account_id);
      setHistoryRuns(history);
    } catch (err: any) {
      alert(`Verification run failed: ${err.message}`);
    } finally {
      setRunningVerification(false);
    }
  };

  const getOverallStatusBadge = (status: string) => {
    switch (status) {
      case 'NO_ISSUES_DETECTED':
        return <span className="badge badge-verified-clean"><CheckCircle2 size={13} /> NO ISSUES DETECTED</span>;
      case 'FLAGGED_FOR_REVIEW':
        return <span className="badge badge-verified-flagged"><AlertCircle size={13} /> FLAGGED FOR REVIEW</span>;
      case 'UNABLE_TO_VERIFY':
        return <span className="badge badge-verified-unable"><HelpCircle size={13} /> UNABLE TO VERIFY</span>;
      default:
        return <span className="badge">{status}</span>;
    }
  };

  const getCheckOutcomeBadge = (status: string) => {
    switch (status) {
      case 'PASS':
        return <span className="badge badge-pass"><CheckCircle2 size={12} /> PASS</span>;
      case 'FLAGGED':
        return <span className="badge badge-flagged"><AlertCircle size={12} /> FLAGGED</span>;
      case 'NOT_ASSESSED':
        return <span className="badge badge-not-assessed"><HelpCircle size={12} /> NOT ASSESSED</span>;
      case 'ERROR':
        return <span className="badge badge-error">ERROR</span>;
      default:
        return <span className="badge">{status}</span>;
    }
  };

  return (
    <div className="page-container">
      {/* Page Title & Scope Notice */}
      <div className="card" style={{ padding: '20px 24px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              Consumer Account Verification Engine
            </h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
              Multi-dimensional evidence evaluation across account metadata, meter bindings, reading sequence integrity, and ML anomaly findings.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '0.78rem', background: '#eff6ff', color: '#1e40af', padding: '6px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid #bfdbfe', fontWeight: 600 }}>
              Engine Ruleset: v2.1.0 (Isolation Forest + Historical MAD)
            </span>
          </div>
        </div>
      </div>

      {/* Main Grid: Account Selector (Left) vs Engine Workspace (Right) */}
      <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: '20px', alignItems: 'start' }}>
        {/* Left Column: Account Directory */}
        <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', maxHeight: '820px' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '10px' }}>
            Consumer Accounts ({accounts.length})
          </h3>

          <form onSubmit={handleSearchSubmit} style={{ marginBottom: '12px' }}>
            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-muted)' }} />
              <input
                type="text"
                placeholder="Search Consumer ID, meter..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: '100%',
                  padding: '7px 10px 7px 30px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.82rem',
                }}
              />
            </div>
          </form>

          {/* Account List */}
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {loadingAccounts ? (
              <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                Loading accounts...
              </div>
            ) : accounts.length === 0 ? (
              <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                No accounts match query
              </div>
            ) : (
              accounts.map((acc) => {
                const isSelected = selectedAccount?.account_id === acc.account_id;
                return (
                  <div
                    key={acc.account_id}
                    onClick={() => selectAccount(acc)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: 'var(--radius-sm)',
                      background: isSelected ? 'var(--primary-light)' : '#ffffff',
                      border: isSelected ? '1px solid #bfdbfe' : '1px solid var(--border-light)',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 700, fontSize: '0.88rem', color: isSelected ? 'var(--primary-blue)' : 'var(--text-primary)' }}>
                        {acc.consumer_id}
                      </span>
                      <span className="badge" style={{ fontSize: '0.72rem', background: '#f1f5f9', color: '#475569' }}>
                        {acc.meter_id}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                      {acc.consumer_name} • {acc.district || 'Bareilly'}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Verification Engine Workspace */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {selectedAccount ? (
            <>
              {/* Account Profile Header Card */}
              <div className="card" style={{ padding: '20px 24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {selectedAccount.consumer_name}
                      </h3>
                      <span className="badge badge-normal">{selectedAccount.tariff_category}</span>
                      <span className="badge" style={{ background: '#ecfdf5', color: '#047857' }}>{selectedAccount.connection_status}</span>
                    </div>
                    <div style={{ display: 'flex', gap: '16px', marginTop: '6px', fontSize: '0.82rem', color: 'var(--text-secondary)', flexWrap: 'wrap' }}>
                      <span><strong>Consumer ID:</strong> {selectedAccount.consumer_id}</span>
                      <span><strong>Meter ID:</strong> {selectedAccount.meter_id}</span>
                      <span><strong>District:</strong> {selectedAccount.district}</span>
                      <span><strong>Sanctioned Load:</strong> {selectedAccount.sanctioned_load_kw} kW</span>
                    </div>
                  </div>

                  {/* Run Verification Controls */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <select
                      value={selectedScope}
                      onChange={(e) => setSelectedScope(e.target.value)}
                      style={{ padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.85rem' }}
                    >
                      <option value="FULL_RECONCILIATION">Full Reconciliation</option>
                      <option value="TELEMETRY_ONLY">Telemetry Only</option>
                      <option value="BILLING_CHECK">Billing Check</option>
                      <option value="DATA_INTEGRITY">Data Integrity</option>
                    </select>

                    <button
                      onClick={handleRunVerification}
                      disabled={runningVerification}
                      className="btn btn-primary btn-sm"
                      style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px' }}
                    >
                      {runningVerification ? (
                        <>
                          <Clock size={15} className="spin" /> Evaluating...
                        </>
                      ) : (
                        <>
                          <Play size={15} /> Run Verification
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {/* Evaluation Outcome & Check Matrix */}
              {currentResult ? (
                <div className="card" style={{ padding: '20px 24px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', paddingBottom: '14px', borderBottom: '1px solid var(--border-color)' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Latest Run:</span>
                        <span style={{ fontSize: '0.82rem', fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
                          {currentResult.verification_id}
                        </span>
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          • {currentResult.evaluated_at.substring(0, 19).replace('T', ' ')}
                        </span>
                      </div>
                      <div style={{ marginTop: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>Overall Assessment:</span>
                        {getOverallStatusBadge(currentResult.overall_status)}
                      </div>
                    </div>

                    {/* Quick navigation to Meter Analysis */}
                    {onSelectMeter && selectedAccount.meter_id && (
                      <button
                        onClick={() => onSelectMeter(selectedAccount.meter_id)}
                        className="btn btn-secondary btn-sm"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                      >
                        <Zap size={14} /> Open in Meter Analysis
                      </button>
                    )}
                  </div>

                  {/* Modular Verification Check Results Table */}
                  <h4 style={{ fontSize: '0.92rem', fontWeight: 700, marginBottom: '12px' }}>
                    Modular Verification Checks ({currentResult.checks.length})
                  </h4>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {currentResult.checks.map((chk, i) => (
                      <div
                        key={chk.id || i}
                        style={{
                          border: '1px solid var(--border-light)',
                          background: chk.status === 'FLAGGED' ? '#fffbfa' : '#ffffff',
                          borderRadius: 'var(--radius-sm)',
                          padding: '12px 16px',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '0.75rem', fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-muted)', background: '#f1f5f9', padding: '2px 6px', borderRadius: '4px' }}>
                              {chk.check_code}
                            </span>
                            <span style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                              {chk.check_name}
                            </span>
                          </div>
                          {getCheckOutcomeBadge(chk.status)}
                        </div>

                        <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                          {chk.findings}
                        </div>

                        {chk.evidence_detail && Object.keys(chk.evidence_detail).length > 0 && (
                          <div style={{ marginTop: '6px', fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'JetBrains Mono, monospace' }}>
                            Detail: {JSON.stringify(chk.evidence_detail)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Findings & Case Association Card */}
                  {currentResult.overall_status === 'FLAGGED_FOR_REVIEW' && (
                    <div style={{ marginTop: '20px', padding: '16px', background: 'var(--badge-red-bg)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--badge-red-border)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
                        <div>
                          <strong style={{ fontSize: '0.9rem', color: 'var(--badge-red-text)' }}>
                            Actionable Verification Findings Detected
                          </strong>
                          <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                            A verification case has been created or matched in the Review Queue. Anomaly observations alone do not establish fraud.
                          </div>
                        </div>
                        <button
                          onClick={async () => {
                            // Find case for this consumer
                            try {
                              const caseList = await api.getCases({ search: selectedAccount.consumer_id, pageSize: 5 });
                              if (caseList.items.length > 0) {
                                setOpenedCaseId(caseList.items[0].case_id);
                                setCaseModalOpen(true);
                              } else {
                                alert('No active case found for this consumer');
                              }
                            } catch (e: any) {
                              alert(`Failed to load case: ${e.message}`);
                            }
                          }}
                          className="btn btn-secondary btn-sm"
                          style={{ background: '#ffffff' }}
                        >
                          <ExternalLink size={14} /> Open Investigation Case
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ) : loadingHistory ? (
                <div className="card" style={{ padding: '60px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <Clock size={28} className="spin" style={{ marginBottom: '8px' }} />
                  <div>Loading account evaluation history...</div>
                </div>
              ) : (
                <div className="card" style={{ padding: '60px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <ShieldCheck size={36} style={{ marginBottom: '8px', color: 'var(--primary-blue)' }} />
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                    No Verification Runs Recorded
                  </div>
                  <div style={{ fontSize: '0.85rem' }}>
                    Click &quot;Run Verification&quot; above to evaluate this consumer account against all 7 modular verification checks.
                  </div>
                </div>
              )}

              {/* Historical Verification Runs */}
              {historyRuns.length > 1 && (
                <div className="card" style={{ padding: '18px 22px' }}>
                  <h4 style={{ fontSize: '0.92rem', fontWeight: 700, marginBottom: '12px' }}>
                    Previous Verification Runs ({historyRuns.length})
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {historyRuns.map((r) => (
                      <div
                        key={r.verification_id}
                        onClick={() => setCurrentResult(r)}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '10px 14px',
                          background: currentResult?.verification_id === r.verification_id ? '#eff6ff' : '#f8fafc',
                          border: currentResult?.verification_id === r.verification_id ? '1px solid #bfdbfe' : '1px solid var(--border-light)',
                          borderRadius: 'var(--radius-sm)',
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <span style={{ fontSize: '0.8rem', fontFamily: 'JetBrains Mono, monospace' }}>
                            {r.verification_id}
                          </span>
                          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                            {r.evaluated_at.substring(0, 19).replace('T', ' ')}
                          </span>
                          <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                            Scope: {r.scope}
                          </span>
                        </div>
                        {getOverallStatusBadge(r.overall_status)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="card" style={{ padding: '60px', textAlign: 'center', color: 'var(--text-muted)' }}>
              Select an account from the left directory to inspect verification state.
            </div>
          )}
        </div>
      </div>

      {/* Case Workspace Modal */}
      <CaseWorkspaceModal
        caseId={openedCaseId}
        isOpen={caseModalOpen}
        onClose={() => setCaseModalOpen(false)}
        onCaseUpdated={() => {
          if (selectedAccount) selectAccount(selectedAccount);
        }}
      />
    </div>
  );
};
