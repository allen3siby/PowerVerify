import React, { useState, useEffect } from 'react';
import {
  X,
  ShieldAlert,
  Clock,
  User,
  Activity,
  Send,
  FileText,
  History,
  ChevronRight,
  AlertTriangle,
} from 'lucide-react';
import { api, authState } from '../api';
import type {
  CaseDetail,
  CaseStatus,
  CasePriority,
} from '../types';

interface CaseWorkspaceModalProps {
  caseId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onCaseUpdated: () => void;
}

export const CaseWorkspaceModal: React.FC<CaseWorkspaceModalProps> = ({
  caseId,
  isOpen,
  onClose,
  onCaseUpdated,
}) => {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'notes' | 'audit'>('overview');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Status transition state
  const [targetStatus, setTargetStatus] = useState<string>('');
  const [statusReason, setStatusReason] = useState<string>('');
  const [statusSubmitting, setStatusSubmitting] = useState<boolean>(false);

  // Assignment state
  const [assigneeOfficer, setAssigneeOfficer] = useState<string>('');
  const [assignmentReason, setAssignmentReason] = useState<string>('');
  const [assignSubmitting, setAssignSubmitting] = useState<boolean>(false);

  // Note state
  const [newNote, setNewNote] = useState<string>('');
  const [noteSubmitting, setNoteSubmitting] = useState<boolean>(false);

  // Decision state
  const [decision, setDecision] = useState<string>('Discrepancy Confirmed');
  const [decisionReason, setDecisionReason] = useState<string>('');
  const [decisionSubmitting, setDecisionSubmitting] = useState<boolean>(false);

  const isAuditor = authState.getRole() === 'AUDITOR';

  const fetchDetail = async () => {
    if (!caseId) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await api.getCaseDetail(caseId);
      setDetail(data);
      if (data.case.status === 'OPEN') setTargetStatus('ASSIGNED');
      else if (data.case.status === 'ASSIGNED') setTargetStatus('UNDER_REVIEW');
      else if (data.case.status === 'UNDER_REVIEW') setTargetStatus('RESOLVED');
      else setTargetStatus(data.case.status);

      setAssigneeOfficer(data.case.assigned_officer || 'officer_sharma');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load case investigation details');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';

      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          onClose();
        }
      };
      window.addEventListener('keydown', handleKeyDown);

      if (caseId) {
        fetchDetail();
      }

      return () => {
        document.body.style.overflow = originalOverflow;
        window.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [isOpen, caseId, onClose]);

  if (!isOpen || !caseId) return null;

  const handleStatusChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!statusReason.trim()) {
      alert('A valid reason is required for state transitions.');
      return;
    }
    setStatusSubmitting(true);
    try {
      await api.updateCaseStatus(caseId, targetStatus as CaseStatus, statusReason);
      setStatusReason('');
      await fetchDetail();
      onCaseUpdated();
    } catch (err: any) {
      alert(`Status transition error: ${err.message}`);
    } finally {
      setStatusSubmitting(false);
    }
  };

  const handleAssignment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!assigneeOfficer.trim()) {
      alert('Officer ID is required.');
      return;
    }
    setAssignSubmitting(true);
    try {
      await api.assignCase(caseId, assigneeOfficer, assignmentReason || 'Routine officer assignment');
      setAssignmentReason('');
      await fetchDetail();
      onCaseUpdated();
    } catch (err: any) {
      alert(`Assignment error: ${err.message}`);
    } finally {
      setAssignSubmitting(false);
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNote.trim()) return;
    setNoteSubmitting(true);
    try {
      await api.addCaseNote(caseId, newNote.trim());
      setNewNote('');
      await fetchDetail();
    } catch (err: any) {
      alert(`Note submission error: ${err.message}`);
    } finally {
      setNoteSubmitting(false);
    }
  };

  const handleSubmitDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!decisionReason.trim()) {
      alert('Review decision requires a documented justification.');
      return;
    }
    setDecisionSubmitting(true);
    try {
      await api.submitCaseDecision(caseId, decision, decisionReason);
      setDecisionReason('');
      await fetchDetail();
      onCaseUpdated();
    } catch (err: any) {
      alert(`Decision recording error: ${err.message}`);
    } finally {
      setDecisionSubmitting(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const s = status.toLowerCase().replace('_', '-');
    return <span className={`badge status-${s}`}>{status}</span>;
  };

  const getPriorityBadge = (p: CasePriority | string) => {
    const s = p.toLowerCase();
    return <span className={`badge priority-${s}`}>{p}</span>;
  };

  return (
    <div className="modal-overlay" style={{ zIndex: 120 }}>
      <div
        className="modal-content"
        style={{
          maxWidth: '1000px',
          width: '94%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          padding: 0,
        }}
      >
        {/* Workspace Header */}
        <div className="modal-header" style={{ padding: '16px 24px', background: '#ffffff', borderBottom: '1px solid var(--border-color)' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '0.8rem', fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-muted)' }}>
                {detail?.case.case_id || caseId}
              </span>
              {detail && getStatusBadge(detail.case.status)}
              {detail && getPriorityBadge(detail.case.priority)}
            </div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '4px' }}>
              {detail?.case.title || 'Case Investigation Workspace'}
            </h3>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
          >
            <X size={22} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div style={{ display: 'flex', gap: '8px', padding: '10px 24px', background: '#f8fafc', borderBottom: '1px solid var(--border-color)' }}>
          <button
            className={`sub-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            <Activity size={15} /> Case & Consumer Profile
          </button>
          <button
            className={`sub-tab-btn ${activeTab === 'notes' ? 'active' : ''}`}
            onClick={() => setActiveTab('notes')}
          >
            <FileText size={15} /> Officer Notes ({detail?.notes.length ?? 0})
          </button>
          <button
            className={`sub-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            <History size={15} /> Audit Trail ({detail?.audit_events.length ?? 0})
          </button>
        </div>

        {/* Body Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
          {loading ? (
            <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
              <Clock size={32} className="spin" style={{ marginBottom: '12px' }} />
              <div>Loading case records and telemetry evidence...</div>
            </div>
          ) : errorMsg ? (
            <div style={{ padding: '24px', background: 'var(--badge-red-bg)', color: 'var(--badge-red-text)', borderRadius: 'var(--radius-sm)' }}>
              {errorMsg}
            </div>
          ) : detail ? (
            <>
              {/* TAB 1: OVERVIEW */}
              {activeTab === 'overview' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {/* Reopened / Recurrence Banner */}
                  {detail.audit_events.some((e) => e.action === 'DISCREPANCY_RECURRED' || e.action === 'REOPEN_CASE') && (
                    <div
                      style={{
                        padding: '12px 16px',
                        background: '#fffbeb',
                        border: '1px solid #fde68a',
                        borderRadius: 'var(--radius-sm)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                        color: '#92400e',
                        fontSize: '0.85rem',
                      }}
                    >
                      <AlertTriangle size={18} color="#d97706" />
                      <div>
                        <strong>Reopened / Recurring Investigation:</strong> This case was reopened or experienced a recurring discrepancy observation. Prior resolution decisions and earlier verification runs are preserved in the audit log.
                      </div>
                    </div>
                  )}

                  {/* Account Summary Banner */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                      gap: '16px',
                      padding: '16px',
                      background: '#f8fafc',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border-color)',
                    }}
                  >
                    <div>
                      <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Consumer ID</span>
                      <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--primary-blue)' }}>
                        {detail.account?.consumer_id || detail.case.consumer_id}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        {detail.account?.consumer_name || 'CEEW Monitored Household'}
                      </div>
                    </div>
                    <div>
                      <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Smart Meter ID</span>
                      <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {detail.account?.meter_id || detail.case.meter_id || 'N/A'}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        District: {detail.account?.district || 'Bareilly'}
                      </div>
                    </div>
                    <div>
                      <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Connection & Tariff</span>
                      <div style={{ fontSize: '0.92rem', fontWeight: 600 }}>
                        {detail.account?.tariff_category || 'Domestic (LMV-1)'}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        Load: {detail.account?.sanctioned_load_kw ?? 2.0} kW • {detail.account?.connection_status || 'ACTIVE'}
                      </div>
                    </div>
                    <div>
                      <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Assigned Officer</span>
                      <div style={{ fontSize: '0.92rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <User size={14} /> {detail.case.assigned_officer || 'Unassigned'}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                        Updated: {detail.case.updated_at.substring(0, 16).replace('T', ' ')}
                      </div>
                    </div>
                  </div>

                  {/* Finding Evidence Panel */}
                  <div className="card" style={{ padding: '18px 20px' }}>
                    <h4 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <ShieldAlert size={16} color="var(--primary-blue)" /> Telemetry Finding & ML Evidence
                    </h4>
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '14px' }}>
                      {detail.case.description}
                    </p>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', background: '#f1f5f9', padding: '14px', borderRadius: 'var(--radius-sm)' }}>
                      <div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Source Finding ID</span>
                        <div style={{ fontSize: '0.82rem', fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
                          {detail.case.source_finding_id || 'N/A'}
                        </div>
                      </div>
                      <div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Finding Category</span>
                        <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                          {detail.case.finding_category}
                        </div>
                      </div>
                      <div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Verification Run ID</span>
                        <div style={{ fontSize: '0.82rem', fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
                          {detail.case.verification_id || 'Initial ML Detection'}
                        </div>
                      </div>
                      <div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Current Decision</span>
                        <div style={{ fontSize: '0.85rem', fontWeight: 700, color: (detail.case.decision && detail.case.decision !== 'PENDING') ? 'var(--primary-blue)' : 'var(--text-muted)' }}>
                          {(detail.case.decision && detail.case.decision !== 'PENDING') ? detail.case.decision : 'Pending Review'}
                        </div>
                      </div>
                    </div>

                    {detail.case.decision && detail.case.decision !== 'PENDING' && detail.case.decision_reason && (
                      <div style={{ marginTop: '14px', padding: '12px', background: '#eff6ff', borderRadius: 'var(--radius-sm)', border: '1px solid #bfdbfe' }}>
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#1d4ed8', marginBottom: '4px' }}>
                          RECORDED DECISION JUSTIFICATION ({detail.case.resolved_at ? detail.case.resolved_at.substring(0, 16).replace('T', ' ') : 'Resolution Recorded'})
                        </div>
                        <div style={{ fontSize: '0.85rem', color: '#1e3a8a' }}>
                          {detail.case.decision_reason}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Actions Grid (Workflow Controls) */}
                  {!isAuditor && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
                      {/* State Transition Box */}
                      <div className="card" style={{ padding: '18px 20px' }}>
                        <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '12px' }}>
                          Workflow Transition
                        </h4>
                        <form onSubmit={handleStatusChange}>
                          <div style={{ marginBottom: '12px' }}>
                            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                              Next Status
                            </label>
                            <select
                              value={targetStatus}
                              onChange={(e) => setTargetStatus(e.target.value)}
                              style={{ width: '100%', padding: '7px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.85rem' }}
                            >
                              <option value="OPEN">OPEN (Reopen)</option>
                              <option value="ASSIGNED">ASSIGNED</option>
                              <option value="UNDER_REVIEW">UNDER_REVIEW</option>
                              <option value="PENDING_INFO">PENDING_INFO</option>
                              <option value="ESCALATED">ESCALATED</option>
                              <option value="RESOLVED">RESOLVED</option>
                              <option value="CLOSED">CLOSED</option>
                            </select>
                          </div>
                          <div style={{ marginBottom: '12px' }}>
                            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                              Transition Reason *
                            </label>
                            <input
                              type="text"
                              placeholder="e.g., Assigned to meter specialist for field triage"
                              value={statusReason}
                              onChange={(e) => setStatusReason(e.target.value)}
                              style={{ width: '100%', padding: '7px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.85rem' }}
                            />
                          </div>
                          <button
                            type="submit"
                            disabled={statusSubmitting}
                            className="btn btn-secondary btn-sm"
                            style={{ width: '100%' }}
                          >
                            {statusSubmitting ? 'Updating...' : 'Apply Status Transition'}
                          </button>
                        </form>
                      </div>

                      {/* Assignment & Officer Controls */}
                      <div className="card" style={{ padding: '18px 20px' }}>
                        <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '12px' }}>
                          Assign Officer
                        </h4>
                        <form onSubmit={handleAssignment}>
                          <div style={{ marginBottom: '12px' }}>
                            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                              Verification Officer
                            </label>
                            <select
                              value={assigneeOfficer}
                              onChange={(e) => setAssigneeOfficer(e.target.value)}
                              style={{ width: '100%', padding: '7px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.85rem' }}
                            >
                              <option value="officer_sharma">Officer Sharma (Zone 1)</option>
                              <option value="officer_patel">Officer Patel (Mathura Field)</option>
                              <option value="officer_verma">Officer Verma (Bareilly North)</option>
                              <option value="admin_root">Administrator</option>
                            </select>
                          </div>
                          <div style={{ marginBottom: '12px' }}>
                            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                              Assignment Reason / Context
                            </label>
                            <input
                              type="text"
                              placeholder="e.g., Primary meter inspector for cluster"
                              value={assignmentReason}
                              onChange={(e) => setAssignmentReason(e.target.value)}
                              style={{ width: '100%', padding: '7px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.85rem' }}
                            />
                          </div>
                          <button
                            type="submit"
                            disabled={assignSubmitting}
                            className="btn btn-secondary btn-sm"
                            style={{ width: '100%' }}
                          >
                            {assignSubmitting ? 'Assigning...' : 'Assign Case'}
                          </button>
                        </form>
                      </div>
                    </div>
                  )}

                  {/* Formal Decision Submission Box */}
                  {!isAuditor && (
                    <div className="card" style={{ padding: '20px', borderLeft: '4px solid var(--primary-blue)' }}>
                      <h4 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '6px' }}>
                        Submit Formal Verification Decision
                      </h4>
                      <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                        Submitting an authorized decision will set case status to <strong>RESOLVED</strong>, write an immutable audit log entry, and synchronize legacy review state.
                      </p>
                      <form onSubmit={handleSubmitDecision}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '14px' }}>
                          <div>
                            <label style={{ fontSize: '0.82rem', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                              Review Decision *
                            </label>
                            <select
                              value={decision}
                              onChange={(e) => setDecision(e.target.value)}
                              style={{ width: '100%', padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.88rem' }}
                            >
                              {detail.case.finding_category === 'BILLING_DISCREPANCY' ? (
                                <>
                                  <option value="Discrepancy Confirmed">Discrepancy Confirmed (Tariff or Meter Mismatch)</option>
                                  <option value="Explained Discrepancy">Explained Discrepancy (Documented Adjustment / Authorized)</option>
                                  <option value="Insufficient Evidence">Insufficient Evidence (Telemetry Coverage Incomplete)</option>
                                  <option value="Bill Correction Required">Bill Correction Required (Reroute for Rebilling)</option>
                                  <option value="Corrected and Verified">Corrected and Verified (Bill Corrected)</option>
                                  <option value="Authorized Exception">Authorized Exception (Approved Variance)</option>
                                  <option value="False Positive">False Positive (Expected Tariff / Usage Variance)</option>
                                  <option value="Escalated">Escalated (Field Audit Required)</option>
                                  <option value="Other / Unresolved">Other / Unresolved</option>
                                </>
                              ) : (
                                <>
                                  <option value="Discrepancy Confirmed">Discrepancy Confirmed (Meter / Phase Issue)</option>
                                  <option value="False Positive">False Positive (Seasonal / Load Fluctuation)</option>
                                  <option value="Insufficient Evidence">Insufficient Evidence (Data Incomplete)</option>
                                  <option value="Escalated">Escalated (Field Audit Required)</option>
                                  <option value="Other / Unresolved">Other / Unresolved</option>
                                </>
                              )}
                            </select>
                          </div>
                          <div>
                            <label style={{ fontSize: '0.82rem', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                              Decision Reason & Evidence Reference *
                            </label>
                            <input
                              type="text"
                              required
                              placeholder="e.g., Verified high AC usage during heatwave; no tampering observed"
                              value={decisionReason}
                              onChange={(e) => setDecisionReason(e.target.value)}
                              style={{ width: '100%', padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.88rem' }}
                            />
                          </div>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                          <button
                            type="submit"
                            disabled={decisionSubmitting}
                            className="btn btn-primary"
                          >
                            {decisionSubmitting ? 'Submitting Decision...' : 'Record Authorized Decision'}
                          </button>
                        </div>
                      </form>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: NOTES */}
              {activeTab === 'notes' && (
                <div>
                  {!isAuditor && (
                    <form onSubmit={handleAddNote} style={{ marginBottom: '24px' }}>
                      <label style={{ fontSize: '0.82rem', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                        Add Officer Investigation Note
                      </label>
                      <div style={{ display: 'flex', gap: '10px' }}>
                        <textarea
                          rows={3}
                          value={newNote}
                          onChange={(e) => setNewNote(e.target.value)}
                          placeholder="Document meter inspection observations, phone contact with consumer, or cross-checks..."
                          style={{
                            flex: 1,
                            padding: '10px',
                            borderRadius: 'var(--radius-sm)',
                            border: '1px solid var(--border-color)',
                            fontSize: '0.85rem',
                          }}
                        />
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
                        <button
                          type="submit"
                          disabled={noteSubmitting || !newNote.trim()}
                          className="btn btn-secondary btn-sm"
                        >
                          <Send size={14} /> {noteSubmitting ? 'Saving...' : 'Add Note'}
                        </button>
                      </div>
                    </form>
                  )}

                  <h4 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '14px' }}>
                    Note History ({detail.notes.length})
                  </h4>

                  {detail.notes.length === 0 ? (
                    <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', background: '#f8fafc', borderRadius: 'var(--radius-sm)' }}>
                      No officer notes recorded for this case yet.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {detail.notes.map((note) => (
                        <div
                          key={note.id}
                          style={{
                            background: '#f8fafc',
                            border: '1px solid var(--border-light)',
                            borderRadius: 'var(--radius-sm)',
                            padding: '12px 16px',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <User size={13} /> {note.author_id} ({note.author_role})
                            </span>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              {note.created_at.substring(0, 19).replace('T', ' ')}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
                            {note.note_text}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: AUDIT TRAIL */}
              {activeTab === 'audit' && (
                <div>
                  <div style={{ marginBottom: '16px' }}>
                    <h4 style={{ fontSize: '0.95rem', fontWeight: 700 }}>
                      Immutable Case Audit Trail
                    </h4>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      Structured, append-only chronological log of all case actions, state transitions, assignments, and decision events.
                    </p>
                  </div>

                  <div className="audit-timeline">
                    {detail.audit_events.map((evt) => (
                      <div key={evt.event_id} className="audit-timeline-item">
                        <div className="audit-timeline-dot" />
                        <div className="audit-timeline-content">
                          <div className="audit-timeline-header">
                            <div>
                              <strong style={{ fontSize: '0.85rem', color: 'var(--primary-blue)' }}>
                                {evt.action}
                              </strong>
                              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '8px' }}>
                                by {evt.actor_id} ({evt.actor_role})
                              </span>
                            </div>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              {evt.created_at.substring(0, 19).replace('T', ' ')}
                            </span>
                          </div>

                          {(evt.previous_value || evt.new_value) && (
                            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '4px 0' }}>
                              {evt.previous_value && <span style={{ textDecoration: 'line-through', color: 'var(--text-muted)' }}>{evt.previous_value}</span>}
                              {evt.previous_value && evt.new_value && <ChevronRight size={12} style={{ display: 'inline', margin: '0 4px' }} />}
                              {evt.new_value && <strong>{evt.new_value}</strong>}
                            </div>
                          )}

                          {evt.reason && (
                            <div style={{ fontSize: '0.8rem', fontStyle: 'italic', color: 'var(--text-secondary)' }}>
                              Reason: &ldquo;{evt.reason}&rdquo;
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="modal-footer" style={{ padding: '12px 24px' }}>
          <button onClick={onClose} className="btn btn-secondary btn-sm">
            Close Investigation Workspace
          </button>
        </div>
      </div>
    </div>
  );
};
