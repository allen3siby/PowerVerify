import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  FileSpreadsheet,
  FileText,
  Search,
  ShieldCheck,
  Zap,
  Briefcase,
  Layers,
  User,
} from 'lucide-react';
import { api } from '../api';
import type { ReviewQueueItem, CaseItem, CasePriority, CaseStatus } from '../types';
import { ReviewModal } from '../components/ReviewModal';
import { CaseWorkspaceModal } from '../components/CaseWorkspaceModal';

interface ReviewQueueProps {
  onSelectMeter: (meterId: string) => void;
}

export const ReviewQueue: React.FC<ReviewQueueProps> = ({ onSelectMeter }) => {
  // Top-level mode: 'cases' (Phase 3 Case Management) or 'telemetry' (Existing Review Queue)
  const [viewMode, setViewMode] = useState<'cases' | 'telemetry'>('cases');

  // --- TELEMETRY STATE (Existing Review Queue) ---
  const [telemetryItems, setTelemetryItems] = useState<ReviewQueueItem[]>([]);
  const [telemetryTotal, setTelemetryTotal] = useState<number>(0);
  const [telemetryTotalPages, setTelemetryTotalPages] = useState<number>(1);
  const [telemetryPage, setTelemetryPage] = useState<number>(1);
  const [telemetryLoading, setTelemetryLoading] = useState<boolean>(true);
  const [telemetrySearch, setTelemetrySearch] = useState<string>('');
  const [directionFilter, setDirectionFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [activeTelemetryItem, setActiveTelemetryItem] = useState<ReviewQueueItem | null>(null);
  const [telemetryModalOpen, setTelemetryModalOpen] = useState<boolean>(false);

  // --- CASES STATE (Phase 3 Case Management) ---
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [casesTotal, setCasesTotal] = useState<number>(0);
  const [casesTotalPages, setCasesTotalPages] = useState<number>(1);
  const [casesPage, setCasesPage] = useState<number>(1);
  const [casesLoading, setCasesLoading] = useState<boolean>(true);
  const [caseSearch, setCaseSearch] = useState<string>('');
  const [caseStatusFilter, setCaseStatusFilter] = useState<string>('all');
  const [casePriorityFilter, setCasePriorityFilter] = useState<string>('all');
  const [caseCategoryFilter, setCaseCategoryFilter] = useState<string>('all');
  const [caseAssigneeFilter, setCaseAssigneeFilter] = useState<string>('all');

  // Active case for investigation workspace
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [caseWorkspaceOpen, setCaseWorkspaceOpen] = useState<boolean>(false);

  // Fetch Telemetry Queue
  const fetchTelemetryQueue = async () => {
    setTelemetryLoading(true);
    try {
      const res = await api.getReviewQueue({
        direction: directionFilter,
        status: statusFilter,
        search: telemetrySearch || undefined,
        page: telemetryPage,
        pageSize: 20,
      });
      setTelemetryItems(res.items);
      setTelemetryTotal(res.total);
      setTelemetryTotalPages(res.total_pages);
    } catch (err) {
      console.error(err);
    } finally {
      setTelemetryLoading(false);
    }
  };

  // Fetch Cases Queue
  const fetchCasesQueue = async () => {
    setCasesLoading(true);
    try {
      const res = await api.getCases({
        status: caseStatusFilter !== 'all' ? (caseStatusFilter as CaseStatus) : undefined,
        priority: casePriorityFilter !== 'all' ? (casePriorityFilter as CasePriority) : undefined,
        category: caseCategoryFilter !== 'all' ? caseCategoryFilter : undefined,
        assignee: caseAssigneeFilter !== 'all' ? caseAssigneeFilter : undefined,
        search: caseSearch || undefined,
        page: casesPage,
        pageSize: 20,
      });
      setCases(res.items);
      setCasesTotal(res.total);
      setCasesTotalPages(res.total_pages);
    } catch (err) {
      console.error(err);
    } finally {
      setCasesLoading(false);
    }
  };

  useEffect(() => {
    if (viewMode === 'telemetry') {
      fetchTelemetryQueue();
    } else {
      fetchCasesQueue();
    }
  }, [
    viewMode,
    telemetryPage,
    directionFilter,
    statusFilter,
    casesPage,
    caseStatusFilter,
    casePriorityFilter,
    caseCategoryFilter,
    caseAssigneeFilter,
  ]);

  const handleTelemetrySearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setTelemetryPage(1);
    fetchTelemetryQueue();
  };

  const handleCaseSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCasesPage(1);
    fetchCasesQueue();
  };

  const handleOpenCaseWorkspace = (caseId: string) => {
    setSelectedCaseId(caseId);
    setCaseWorkspaceOpen(true);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Pending Review':
        return <span className="badge badge-pending"><Clock size={12} /> Pending</span>;
      case 'Mark for Field Visit':
        return <span className="badge badge-field"><AlertTriangle size={12} /> Field Visit</span>;
      case 'High Usage Authorized':
        return <span className="badge badge-auth"><ShieldCheck size={12} /> Authorized</span>;
      case 'Acknowledge / No Further Action':
        return <span className="badge badge-ack"><CheckCircle size={12} /> Acknowledged</span>;
      default:
        return <span className="badge badge-pending">{status}</span>;
    }
  };

  const getCaseStatusBadge = (status: string) => {
    const s = status.toLowerCase().replace('_', '-');
    return <span className={`badge status-${s}`}>{status}</span>;
  };

  const getCasePriorityBadge = (p: CasePriority) => {
    const s = p.toLowerCase();
    return <span className={`badge priority-${s}`}>{p}</span>;
  };

  return (
    <div className="page-container">
      {/* Header and Mode Selector */}
      <div className="card" style={{ padding: '20px 24px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                Verification Case Management & Review
              </h2>
            </div>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
              Unified investigation workspace: manage formal verification cases, assignment workflows, and telemetry anomaly triage.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <a href={api.getExportCsvUrl(true)} className="btn btn-secondary btn-sm" title="Download flagged anomalies CSV">
              <FileSpreadsheet size={15} /> Export Flagged
            </a>
            <a href={api.getExportReviewsCsvUrl()} className="btn btn-secondary btn-sm" title="Download audit log of all review decisions">
              <CheckCircle size={15} /> Export Decisions CSV
            </a>
            <a href={api.getExportReportUrl()} target="_blank" rel="noreferrer" className="btn btn-primary btn-sm" title="Download formatted summary report">
              <FileText size={15} /> Download Report
            </a>
          </div>
        </div>

        {/* View Switcher Sub-tabs */}
        <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px', borderTop: '1px solid var(--border-light)', paddingTop: '14px' }}>
          <div className="sub-tabs-container">
            <button
              className={`sub-tab-btn ${viewMode === 'cases' ? 'active' : ''}`}
              onClick={() => { setViewMode('cases'); setCasesPage(1); }}
            >
              <Briefcase size={15} /> Investigation Cases ({casesTotal})
            </button>
            <button
              className={`sub-tab-btn ${viewMode === 'telemetry' ? 'active' : ''}`}
              onClick={() => { setViewMode('telemetry'); setTelemetryPage(1); }}
            >
              <Layers size={15} /> Flagged Telemetry Queue ({telemetryTotal})
            </button>
          </div>

          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Deterministic Deduplication Active • Preserves all prior audit decisions
          </span>
        </div>

        {/* Filters for CASES View */}
        {viewMode === 'cases' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginTop: '14px', paddingTop: '12px', borderTop: '1px solid var(--border-light)' }}>
            <form onSubmit={handleCaseSearchSubmit} style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: '220px' }}>
              <div style={{ position: 'relative', width: '100%' }}>
                <Search size={15} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-muted)' }} />
                <input
                  type="text"
                  placeholder="Search by Case ID, Consumer ID, or Title..."
                  value={caseSearch}
                  onChange={(e) => setCaseSearch(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '7px 10px 7px 32px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    fontSize: '0.85rem',
                  }}
                />
              </div>
              <button type="submit" className="btn btn-secondary btn-sm">Search</button>
            </form>

            {/* Status Filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Status:</span>
              <select
                value={caseStatusFilter}
                onChange={(e) => { setCaseStatusFilter(e.target.value); setCasesPage(1); }}
                style={{ padding: '6px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.82rem' }}
              >
                <option value="all">All Statuses</option>
                <option value="OPEN">OPEN</option>
                <option value="ASSIGNED">ASSIGNED</option>
                <option value="UNDER_REVIEW">UNDER_REVIEW</option>
                <option value="PENDING_INFO">PENDING_INFO</option>
                <option value="ESCALATED">ESCALATED</option>
                <option value="RESOLVED">RESOLVED</option>
                <option value="CLOSED">CLOSED</option>
              </select>
            </div>

            {/* Priority Filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Priority:</span>
              <select
                value={casePriorityFilter}
                onChange={(e) => { setCasePriorityFilter(e.target.value); setCasesPage(1); }}
                style={{ padding: '6px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.82rem' }}
              >
                <option value="all">All Priorities</option>
                <option value="CRITICAL">CRITICAL</option>
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
              </select>
            </div>

            {/* Category Filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Category:</span>
              <select
                value={caseCategoryFilter}
                onChange={(e) => { setCaseCategoryFilter(e.target.value); setCasesPage(1); }}
                style={{ padding: '6px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.82rem' }}
              >
                <option value="all">All Categories</option>
                <option value="BILLING_DISCREPANCY">Billing Discrepancy</option>
                <option value="PAYMENT_MISMATCH">Payment Mismatch</option>
                <option value="TELEMETRY_ANOMALY">Telemetry Anomaly</option>
                <option value="READING_INTEGRITY">Reading Integrity</option>
                <option value="METER_ASSOCIATION">Meter Association</option>
                <option value="DATA_INCOMPLETE">Data Incomplete</option>
              </select>
            </div>

            {/* Assignee Filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Assignee:</span>
              <select
                value={caseAssigneeFilter}
                onChange={(e) => { setCaseAssigneeFilter(e.target.value); setCasesPage(1); }}
                style={{ padding: '6px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.82rem' }}
              >
                <option value="all">All Assignees</option>
                <option value="officer_sharma">Officer Sharma</option>
                <option value="officer_patel">Officer Patel</option>
                <option value="officer_verma">Officer Verma</option>
              </select>
            </div>
          </div>
        )}

        {/* Filters for TELEMETRY View */}
        {viewMode === 'telemetry' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginTop: '14px', paddingTop: '12px', borderTop: '1px solid var(--border-light)' }}>
            <form onSubmit={handleTelemetrySearchSubmit} style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: '220px' }}>
              <div style={{ position: 'relative', width: '100%' }}>
                <Search size={15} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-muted)' }} />
                <input
                  type="text"
                  placeholder="Search by Meter ID, date, or keywords..."
                  value={telemetrySearch}
                  onChange={(e) => setTelemetrySearch(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '7px 10px 7px 32px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    fontSize: '0.85rem',
                  }}
                />
              </div>
              <button type="submit" className="btn btn-secondary btn-sm">Search</button>
            </form>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Direction:</span>
              <select
                value={directionFilter}
                onChange={(e) => { setDirectionFilter(e.target.value); setTelemetryPage(1); }}
                style={{ padding: '6px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.82rem' }}
              >
                <option value="all">All Directions</option>
                <option value="high">High Usage (Red)</option>
                <option value="low">Low Usage (Amber)</option>
                <option value="pattern">Pattern Volatility</option>
              </select>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Status:</span>
              <select
                value={statusFilter}
                onChange={(e) => { setStatusFilter(e.target.value); setTelemetryPage(1); }}
                style={{ padding: '6px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.82rem' }}
              >
                <option value="all">All Statuses</option>
                <option value="Pending Review">Pending Review</option>
                <option value="Mark for Field Visit">Mark for Field Visit</option>
                <option value="High Usage Authorized">High Usage Authorized</option>
                <option value="Acknowledge / No Further Action">Acknowledge / No Further Action</option>
              </select>
            </div>
          </div>
        )}
      </div>

      {/* CASES VIEW TABLE */}
      {viewMode === 'cases' && (
        <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
          <div className="table-wrapper">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Case ID</th>
                  <th>Consumer / Account</th>
                  <th>Title & Finding Summary</th>
                  <th>Category</th>
                  <th>Priority</th>
                  <th>Workflow Status</th>
                  <th>Assigned Officer</th>
                  <th>Updated</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {casesLoading ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                      Loading verification cases...
                    </td>
                  </tr>
                ) : cases.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                      No verification cases match the selected filters.
                    </td>
                  </tr>
                ) : (
                  cases.map((c) => (
                    <tr key={c.case_id}>
                      <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82rem', fontWeight: 600 }}>
                        {c.case_id}
                      </td>
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--primary-blue)' }}>
                          {c.consumer_id}
                        </div>
                      </td>
                      <td style={{ maxWidth: '300px' }}>
                        <div style={{ fontWeight: 600, fontSize: '0.88rem' }}>{c.title}</div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {c.description}
                        </div>
                      </td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                        {c.finding_category}
                      </td>
                      <td>
                        {getCasePriorityBadge(c.priority)}
                      </td>
                      <td>
                        {getCaseStatusBadge(c.status)}
                      </td>
                      <td>
                        <span style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <User size={13} color="var(--text-muted)" /> {c.assigned_officer || 'Unassigned'}
                        </span>
                      </td>
                      <td style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                        {c.updated_at.substring(0, 16).replace('T', ' ')}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          onClick={() => handleOpenCaseWorkspace(c.case_id)}
                          className="btn btn-secondary btn-sm"
                          style={{ fontWeight: 600 }}
                        >
                          <ShieldCheck size={14} color="var(--primary-blue)" /> Investigate
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Cases Pagination */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', background: '#ffffff', borderTop: '1px solid var(--border-light)' }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Showing <strong>{cases.length > 0 ? (casesPage - 1) * 20 + 1 : 0}</strong> to <strong>{Math.min(casesPage * 20, casesTotal)}</strong> of <strong>{casesTotal}</strong> verification cases
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                onClick={() => setCasesPage(p => Math.max(1, p - 1))}
                disabled={casesPage === 1 || casesLoading}
                className="btn btn-secondary btn-sm"
              >
                Previous
              </button>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, padding: '0 8px' }}>
                Page {casesPage} of {casesTotalPages}
              </span>
              <button
                onClick={() => setCasesPage(p => Math.min(casesTotalPages, p + 1))}
                disabled={casesPage === casesTotalPages || casesLoading}
                className="btn btn-secondary btn-sm"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TELEMETRY VIEW TABLE (Preserved Existing Table) */}
      {viewMode === 'telemetry' && (
        <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
          <div className="table-wrapper">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Meter ID</th>
                  <th>District</th>
                  <th>Date</th>
                  <th>Observed (kWh)</th>
                  <th>Expected Range</th>
                  <th>Direction</th>
                  <th>Analytical Explanation</th>
                  <th>Review Status</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {telemetryLoading ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                      Loading review queue observations...
                    </td>
                  </tr>
                ) : telemetryItems.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: 'center', padding: '36px', color: 'var(--text-muted)' }}>
                      No flagged observations match the current filter criteria.
                    </td>
                  </tr>
                ) : (
                  telemetryItems.map((item) => (
                    <tr key={item.observation_id}>
                      <td>
                        <button
                          onClick={() => onSelectMeter(item.meter_id)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: 'var(--primary-blue)',
                            fontWeight: 700,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                          title={`Inspect history for meter ${item.meter_id}`}
                        >
                          <Zap size={14} /> {item.meter_id}
                        </button>
                      </td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                        {item.district}
                      </td>
                      <td style={{ fontWeight: 500 }}>
                        {item.date}
                      </td>
                      <td>
                        <strong style={{ fontSize: '0.95rem' }}>{item.kwh.toFixed(2)}</strong> <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>kWh</span>
                      </td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                        {item.expected_lower.toFixed(2)} – {item.expected_upper.toFixed(2)}
                      </td>
                      <td>
                        <span className={`badge ${item.anomaly_direction === 'high' ? 'badge-high' : item.anomaly_direction === 'pattern' ? 'badge-pattern' : 'badge-low'}`}>
                          {item.anomaly_direction.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ maxWidth: '320px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                        {item.reason}
                      </td>
                      <td>
                        {getStatusBadge(item.review_status)}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          onClick={() => {
                            setActiveTelemetryItem(item);
                            setTelemetryModalOpen(true);
                          }}
                          className="btn btn-secondary btn-sm"
                          style={{ fontWeight: 600 }}
                        >
                          <ShieldCheck size={14} color="var(--primary-blue)" /> Review
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Telemetry Pagination */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', background: '#ffffff', borderTop: '1px solid var(--border-light)' }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Showing <strong>{telemetryItems.length > 0 ? (telemetryPage - 1) * 20 + 1 : 0}</strong> to <strong>{Math.min(telemetryPage * 20, telemetryTotal)}</strong> of <strong>{telemetryTotal}</strong> flagged records
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                onClick={() => setTelemetryPage(p => Math.max(1, p - 1))}
                disabled={telemetryPage === 1 || telemetryLoading}
                className="btn btn-secondary btn-sm"
              >
                Previous
              </button>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, padding: '0 8px' }}>
                Page {telemetryPage} of {telemetryTotalPages}
              </span>
              <button
                onClick={() => setTelemetryPage(p => Math.min(telemetryTotalPages, p + 1))}
                disabled={telemetryPage === telemetryTotalPages || telemetryLoading}
                className="btn btn-secondary btn-sm"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Legacy/Quick Observation Review Modal */}
      {activeTelemetryItem && (
        <ReviewModal
          isOpen={telemetryModalOpen}
          onClose={() => setTelemetryModalOpen(false)}
          onSuccess={() => {
            fetchTelemetryQueue();
            fetchCasesQueue();
          }}
          observation={{
            observation_id: activeTelemetryItem.observation_id,
            meter_id: activeTelemetryItem.meter_id,
            date: activeTelemetryItem.date,
            kwh: activeTelemetryItem.kwh,
            expected_lower: activeTelemetryItem.expected_lower,
            expected_upper: activeTelemetryItem.expected_upper,
            anomaly_direction: activeTelemetryItem.anomaly_direction,
            reason: activeTelemetryItem.reason,
            review_status: activeTelemetryItem.review_status,
          }}
        />
      )}

      {/* Deep Case Investigation Workspace Modal */}
      <CaseWorkspaceModal
        caseId={selectedCaseId}
        isOpen={caseWorkspaceOpen}
        onClose={() => setCaseWorkspaceOpen(false)}
        onCaseUpdated={() => {
          fetchCasesQueue();
          fetchTelemetryQueue();
        }}
      />
    </div>
  );
};
