import React, { useState, useEffect } from 'react';
import { X, CheckCircle, AlertTriangle, ShieldCheck, History, Clock } from 'lucide-react';
import { api } from '../api';
import type { DecisionRecord } from '../types';

interface ReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  observation: {
    observation_id: string;
    meter_id: string;
    date: string;
    kwh: number;
    expected_lower?: number | null;
    expected_upper?: number | null;
    anomaly_direction: string;
    reason: string;
    review_status: string;
    review_decision?: string;
    detection_method?: string;
    case_status?: string | null;
  } | null;
}

export const ReviewModal: React.FC<ReviewModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  observation,
}) => {
  const [selectedDecision, setSelectedDecision] = useState<string>('Mark for Field Visit');
  const [notes, setNotes] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [history, setHistory] = useState<DecisionRecord[]>([]);
  const [showHistory, setShowHistory] = useState<boolean>(false);

  // Lock background body scroll when open and listen for Escape key
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

      return () => {
        document.body.style.overflow = originalOverflow;
        window.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [isOpen, onClose]);

  useEffect(() => {
    if (observation && isOpen) {
      setNotes('');
      // Set sensible initial selection based on direction
      if (observation.anomaly_direction === 'high') {
        setSelectedDecision('Mark for Field Visit');
      } else {
        setSelectedDecision('Acknowledge / No Further Action');
      }

      // Fetch audit history
      api.getReviewHistory(observation.observation_id)
        .then(setHistory)
        .catch(console.error);
    }
  }, [observation, isOpen]);

  if (!isOpen || !observation) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.submitReview(observation.observation_id, selectedDecision, notes);
      onSuccess();
      onClose();
    } catch (err: any) {
      alert(`Error submitting decision: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const isReviewed = observation.review_status &&
    observation.review_status !== 'Pending Review' &&
    observation.review_status !== 'PENDING' &&
    observation.review_status !== 'Normal';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '620px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxSizing: 'border-box',
        }}
      >
        {/* Modal Header */}
        <div className="modal-header">
          <div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Investigate Anomaly Observation
            </h3>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              Meter <strong style={{ color: 'var(--primary-blue)' }}>{observation.meter_id}</strong> • Date: <strong>{observation.date}</strong>
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-muted)',
              padding: '4px',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Scrollable Modal Body */}
        <div className="modal-body" style={{ overflowY: 'auto', flex: '1 1 auto' }}>
          {/* Observation Summary Box */}
          <div
            style={{
              background: '#f8fafc',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-sm)',
              padding: '14px',
              marginBottom: '16px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '8px' }}>
              <div>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Observed Reading
                </span>
                <div style={{ fontSize: '1.35rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {observation.kwh.toFixed(2)} <span style={{ fontSize: '0.85rem', fontWeight: 500 }}>kWh</span>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Historical Expected Range
                </span>
                <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  {observation.expected_lower?.toFixed(2) ?? '0.00'} – {observation.expected_upper?.toFixed(2) ?? '0.00'} kWh
                </div>
              </div>
            </div>

            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', borderTop: '1px solid #e2e8f0', paddingTop: '8px', marginTop: '6px' }}>
              <strong>Flag Reason:</strong> {observation.reason}
            </div>

            <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '10px', fontSize: '0.78rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Review Status:</span>
                <span className={`badge ${isReviewed ? 'badge-reviewed' : 'badge-pending'}`}>
                  {isReviewed ? <CheckCircle size={11} /> : <Clock size={11} />} {isReviewed ? 'REVIEWED' : 'PENDING'}
                </span>
              </div>

              {observation.review_decision && observation.review_decision !== 'PENDING' && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Effective Decision:</span>
                  <span className={`badge ${
                    observation.review_decision === 'Mark for Field Visit' ? 'badge-field' :
                    observation.review_decision === 'High Usage Authorized' ? 'badge-auth' : 'badge-ack'
                  }`}>
                    {observation.review_decision}
                  </span>
                </div>
              )}

              {observation.case_status && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Case:</span>
                  <span className={`badge status-${observation.case_status.toLowerCase().replace('_', '-')}`}>
                    {observation.case_status}
                  </span>
                </div>
              )}
            </div>
          </div>

          <form id="review-decision-form" onSubmit={handleSubmit}>
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '8px', color: 'var(--text-primary)' }}>
                Select Verification Decision:
              </label>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {/* Decision 1: Acknowledge */}
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-sm)',
                    border: `1px solid ${selectedDecision === 'Acknowledge / No Further Action' ? 'var(--primary-blue)' : 'var(--border-color)'}`,
                    background: selectedDecision === 'Acknowledge / No Further Action' ? 'var(--primary-light)' : '#ffffff',
                    cursor: 'pointer',
                    minHeight: '44px',
                  }}
                >
                  <input
                    type="radio"
                    name="decision"
                    value="Acknowledge / No Further Action"
                    checked={selectedDecision === 'Acknowledge / No Further Action'}
                    onChange={(e) => setSelectedDecision(e.target.value)}
                    style={{ marginTop: '3px' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.88rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <CheckCircle size={15} color="#475569" /> Acknowledge / No Further Action
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Observation has been investigated and deemed acceptable or benign without physical technician dispatch.
                    </div>
                  </div>
                </label>

                {/* Decision 2: Field Visit */}
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-sm)',
                    border: `1px solid ${selectedDecision === 'Mark for Field Visit' ? '#f59e0b' : 'var(--border-color)'}`,
                    background: selectedDecision === 'Mark for Field Visit' ? '#fffbeb' : '#ffffff',
                    cursor: 'pointer',
                    minHeight: '44px',
                  }}
                >
                  <input
                    type="radio"
                    name="decision"
                    value="Mark for Field Visit"
                    checked={selectedDecision === 'Mark for Field Visit'}
                    onChange={(e) => setSelectedDecision(e.target.value)}
                    style={{ marginTop: '3px' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.88rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <AlertTriangle size={15} color="#b45309" /> Mark for Field Visit
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Flag for physical site inspection (check meter wiring, seal integrity, bypass or load tamper).
                    </div>
                  </div>
                </label>

                {/* Decision 3: Authorized */}
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    padding: '12px 14px',
                    borderRadius: 'var(--radius-sm)',
                    border: `1px solid ${selectedDecision === 'High Usage Authorized' ? '#10b981' : 'var(--border-color)'}`,
                    background: selectedDecision === 'High Usage Authorized' ? '#ecfdf5' : '#ffffff',
                    cursor: 'pointer',
                    minHeight: '44px',
                  }}
                >
                  <input
                    type="radio"
                    name="decision"
                    value="High Usage Authorized"
                    checked={selectedDecision === 'High Usage Authorized'}
                    onChange={(e) => setSelectedDecision(e.target.value)}
                    style={{ marginTop: '3px' }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.88rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <ShieldCheck size={15} color="#047857" /> High Usage Authorized
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Elevated consumption confirmed as permitted (e.g. approved temporary load, wedding celebration, or seasonal peak).
                    </div>
                  </div>
                </label>
              </div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '6px', color: 'var(--text-primary)' }}>
                Reviewer Notes (Optional):
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Document your findings, customer communication, or instructions for field technician..."
                rows={3}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.85rem',
                  fontFamily: 'inherit',
                  resize: 'vertical',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Decision History Accordion */}
            {history.length > 0 && (
              <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: '12px' }}>
                <button
                  type="button"
                  onClick={() => setShowHistory(!showHistory)}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--primary-blue)',
                    fontSize: '0.82rem',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '4px 0',
                  }}
                >
                  <History size={14} /> {showHistory ? 'Hide Decision History' : `View Past Decisions (${history.length})`}
                </button>

                {showHistory && (
                  <div
                    style={{
                      marginTop: '10px',
                      maxHeight: '180px',
                      overflowY: 'auto',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                      paddingRight: '4px',
                    }}
                  >
                    {history.map((rec) => (
                      <div
                        key={rec.id}
                        style={{
                          background: '#f8fafc',
                          padding: '10px 12px',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--border-color)',
                          fontSize: '0.78rem',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontWeight: 600, marginBottom: '2px' }}>
                          <span style={{ color: 'var(--text-primary)' }}>{rec.decision}</span>
                          <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: '0.72rem' }}>
                            {rec.created_at.slice(0, 16).replace('T', ' ')}
                          </span>
                        </div>
                        {rec.notes && <div style={{ color: 'var(--text-secondary)', marginTop: '2px' }}>Note: {rec.notes}</div>}
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem', marginTop: '2px' }}>
                          Status transition: {rec.previous_status} → {rec.new_status}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </form>
        </div>

        {/* Persistent Sticky Action Footer */}
        <div className="modal-footer">
          <button type="button" onClick={onClose} className="btn btn-secondary" disabled={loading}>
            Cancel
          </button>
          <button type="submit" form="review-decision-form" className="btn btn-primary" disabled={loading}>
            {loading ? 'Recording...' : 'Record Decision'}
          </button>
        </div>
      </div>
    </div>
  );
};
