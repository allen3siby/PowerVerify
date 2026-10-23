import React, { useState, useEffect } from 'react';
import {
  Activity,
  AlertCircle,
  Calendar,
  MapPin,
  Search,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { api } from '../api';
import type { MeterListItem, MeterHistoryResponse, ChartDataPoint } from '../types';
import { ReviewModal } from '../components/ReviewModal';

interface MeterAnalysisProps {
  initialMeterId?: string;
  onSelectMeter?: (meterId: string) => void;
}

export const MeterAnalysis: React.FC<MeterAnalysisProps> = ({
  initialMeterId,
}) => {
  const [meters, setMeters] = useState<MeterListItem[]>([]);
  const [selectedMeterId, setSelectedMeterId] = useState<string>(initialMeterId || 'BR02');
  const [history, setHistory] = useState<MeterHistoryResponse | null>(null);
  const [timeRange, setTimeRange] = useState<string>('90d');
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedObservation, setSelectedObservation] = useState<ChartDataPoint | null>(null);
  const [reviewModalOpen, setReviewModalOpen] = useState<boolean>(false);
  const [searchFilter, setSearchFilter] = useState<string>('');

  // Load meters list on mount
  useEffect(() => {
    api.getMeters().then((list) => {
      setMeters(list);
      if (initialMeterId && list.some(m => m.meter_id === initialMeterId)) {
        setSelectedMeterId(initialMeterId);
      } else if (list.length > 0) {
        setSelectedMeterId(list[0].meter_id);
      }
    }).catch(console.error);
  }, [initialMeterId]);

  // Load selected meter history
  const loadMeterHistory = async (mId: string, range: string) => {
    setLoading(true);
    try {
      const data = await api.getMeterHistory(mId, range);
      setHistory(data);
      // Select the first flagged observation as default active card if available
      const firstAnom = data.points.find(p => p.is_anomaly);
      if (firstAnom) {
        setSelectedObservation(firstAnom);
      } else if (data.points.length > 0) {
        setSelectedObservation(data.points[data.points.length - 1]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedMeterId) {
      loadMeterHistory(selectedMeterId, timeRange);
    }
  }, [selectedMeterId, timeRange]);

  const handleMeterChange = (newMeterId: string) => {
    setSelectedMeterId(newMeterId);
  };

  const currentMeterInfo = meters.find(m => m.meter_id === selectedMeterId);

  // Custom Chart Dot to render Red, Amber, and Purple anomaly markers
  const renderCustomDot = (props: any) => {
    const { cx, cy, payload } = props;
    if (!payload || !payload.is_anomaly) return null;

    let fill = '#9333ea'; // default pattern: purple
    if (payload.anomaly_direction === 'high') {
      fill = '#ef4444'; // Red for high
    } else if (payload.anomaly_direction === 'low') {
      fill = '#f59e0b'; // Amber for low
    } else if (payload.anomaly_direction === 'pattern') {
      fill = '#9333ea'; // Purple for pattern
    }

    const isSelected = selectedObservation?.date === payload.date;

    return (
      <circle
        key={`dot-${payload.date}`}
        cx={cx}
        cy={cy}
        r={isSelected ? 7.5 : 5.5}
        fill={fill}
        stroke={isSelected ? '#1e40af' : '#ffffff'}
        strokeWidth={isSelected ? 3 : 2}
        style={{ cursor: 'pointer' }}
        onClick={() => setSelectedObservation(payload)}
      />
    );
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data: ChartDataPoint = payload[0].payload;
      const isHigh = data.anomaly_direction === 'high';
      const isLow = data.anomaly_direction === 'low';
      const isPattern = data.anomaly_direction === 'pattern';

      const badgeClass = isHigh ? 'badge-high' : isLow ? 'badge-low' : isPattern ? 'badge-pattern' : 'badge-normal';
      const directionLabel = isHigh ? 'HIGH USAGE' : isLow ? 'LOW USAGE' : isPattern ? 'PATTERN' : 'NORMAL';
      const observedVal = (data.observed_consumption ?? data.kwh).toFixed(2);
      const isReviewed = data.review_status && data.review_status !== 'Pending Review' && data.review_status !== 'PENDING' && data.review_status !== 'Normal';

      return (
        <div className="chart-tooltip">
          <div className="chart-tooltip-header">
            <span>{data.date}</span>
            {data.is_anomaly ? (
              <span className={`badge ${badgeClass}`}>
                {directionLabel} ANOMALY
              </span>
            ) : (
              <span className="badge badge-normal">Normal</span>
            )}
          </div>
          <div className="chart-tooltip-row">
            <span style={{ color: 'var(--text-muted)' }}>Observed:</span>
            <strong>{observedVal} kWh</strong>
          </div>
          <div className="chart-tooltip-row">
            <span style={{ color: 'var(--text-muted)' }}>Expected Range:</span>
            <span>{data.expected_lower?.toFixed(2)} – {data.expected_upper?.toFixed(2)} kWh</span>
          </div>
          <div className="chart-tooltip-row">
            <span style={{ color: 'var(--text-muted)' }}>Detection Method:</span>
            <span style={{ fontWeight: 600 }}>{data.detection_method || (data.is_anomaly ? 'STATISTICAL_MAD' : 'NORMAL')}</span>
          </div>
          <div className="chart-tooltip-row">
            <span style={{ color: 'var(--text-muted)' }}>Direction:</span>
            <span style={{ fontWeight: 600, textTransform: 'uppercase' }}>{data.anomaly_direction}</span>
          </div>
          <div style={{ marginTop: '8px', borderTop: '1px solid #f1f5f9', paddingTop: '6px', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            <strong>Analysis:</strong> {data.reason}
          </div>
          {data.is_anomaly && (
            <div style={{ marginTop: '6px', borderTop: '1px dashed #e2e8f0', paddingTop: '6px', fontSize: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-muted)' }}>Review Status:</span>
                <span className={`badge ${isReviewed ? 'badge-reviewed' : 'badge-pending'}`}>
                  {isReviewed ? 'REVIEWED' : 'PENDING'}
                </span>
              </div>
              {data.review_decision && data.review_decision !== 'PENDING' && data.review_decision !== 'Pending Review' && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Decision:</span>
                  <strong>{data.review_decision}</strong>
                </div>
              )}
              {data.case_status && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Case Status:</span>
                  <span className={`badge status-${data.case_status.toLowerCase().replace('_', '-')}`}>{data.case_status}</span>
                </div>
              )}
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  const filteredMeters = meters.filter(m =>
    m.meter_id.toLowerCase().includes(searchFilter.toLowerCase()) ||
    m.district.toLowerCase().includes(searchFilter.toLowerCase())
  );

  return (
    <div className="page-container">
      {/* Top Selector Card */}
      <div className="card" style={{ padding: '16px 20px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={20} color="var(--primary-blue)" />
              <label style={{ fontWeight: 600, fontSize: '0.92rem' }}>Select Smart Meter:</label>
            </div>

            <select
              value={selectedMeterId}
              onChange={(e) => handleMeterChange(e.target.value)}
              style={{
                padding: '8px 14px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-color)',
                fontSize: '0.92rem',
                fontWeight: 600,
                color: 'var(--primary-blue)',
                background: '#ffffff',
                minWidth: '220px',
              }}
            >
              {filteredMeters.map((m) => (
                <option key={m.meter_id} value={m.meter_id}>
                  {m.meter_id} — {m.district} ({m.anomaly_count} flags)
                </option>
              ))}
            </select>

            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-muted)' }} />
              <input
                type="text"
                placeholder="Filter meter list..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                style={{
                  padding: '6px 10px 6px 30px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.82rem',
                  width: '160px',
                }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Interval Filter:</span>
            <div className="time-range-group">
              {['30d', '90d', '1y', 'all'].map((range) => (
                <button
                  key={range}
                  className={`time-range-btn ${timeRange === range ? 'active' : ''}`}
                  onClick={() => setTimeRange(range)}
                >
                  {range.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Meter Metadata & Key Numbers Grid */}
      {currentMeterInfo && history && (
        <div className="stats-grid" style={{ marginBottom: '20px' }}>
          <div className="stat-card">
            <div className="stat-header">
              <span className="stat-label">Meter & District</span>
              <div className="stat-icon" style={{ background: '#eff6ff', color: '#1e40af' }}>
                <MapPin size={18} />
              </div>
            </div>
            <div className="stat-value">{currentMeterInfo.meter_id}</div>
            <div className="stat-meta">{currentMeterInfo.district} District, Uttar Pradesh</div>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span className="stat-label">Observed History</span>
              <div className="stat-icon" style={{ background: '#f8fafc', color: '#475569' }}>
                <Calendar size={18} />
              </div>
            </div>
            <div className="stat-value">{history.total_readings} <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>Days</span></div>
            <div className="stat-meta">Daily CEEW interval observations</div>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span className="stat-label">Consumption Baseline</span>
              <div className="stat-icon" style={{ background: '#ecfdf5', color: '#047857' }}>
                <Activity size={18} />
              </div>
            </div>
            <div className="stat-value">{history.mean_kwh.toFixed(2)} <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>kWh/d</span></div>
            <div className="stat-meta">Median: {history.median_kwh.toFixed(2)} kWh/day</div>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span className="stat-label">Flagged Anomalies</span>
              <div className="stat-icon" style={{ background: '#fef2f2', color: '#b91c1c' }}>
                <AlertCircle size={18} />
              </div>
            </div>
            <div className="stat-value" style={{ color: '#b91c1c' }}>{history.anomaly_count}</div>
            <div className="stat-meta">
              {currentMeterInfo.high_anomaly_count} High, {currentMeterInfo.low_anomaly_count} Low
            </div>
          </div>
        </div>
      )}

      {/* High-Resolution Interactive Chart */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <Activity size={20} color="var(--primary-blue)" /> Daily Consumption & Historical MAD Thresholds ({selectedMeterId})
            </h3>
            <p className="card-subtitle">
              Click any point or dot marker to inspect data-derived explanation and record review decision.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '16px', fontSize: '0.82rem' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444' }} /> High Usage
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#f59e0b' }} /> Low Usage
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#9333ea' }} /> Pattern Anomaly
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: 12, height: 3, background: '#93c5fd' }} /> Expected Range
            </span>
          </div>
        </div>

        <div style={{ width: '100%', height: 400 }}>
          {loading ? (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
              Loading consumption history for {selectedMeterId}...
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={history?.points || []}
                margin={{ top: 10, right: 20, left: 0, bottom: 20 }}
                onClick={(e: any) => {
                  if (e && e.activePayload && e.activePayload.length) {
                    setSelectedObservation(e.activePayload[0].payload);
                  }
                }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} minTickGap={30} />
                <YAxis
                  tick={{ fontSize: 11, fill: '#64748b' }}
                  label={{ value: 'Daily kWh', angle: -90, position: 'insideLeft', style: { fill: '#64748b', fontSize: 11 } }}
                />
                <Tooltip content={<CustomTooltip />} />

                {/* Historical Expected Bounds Band */}
                <Area
                  type="monotone"
                  dataKey="expected_upper"
                  stroke="#93c5fd"
                  strokeDasharray="4 4"
                  fill="#eff6ff"
                  fillOpacity={0.6}
                  name="Expected Range"
                />
                <Area
                  type="monotone"
                  dataKey="expected_lower"
                  stroke="#93c5fd"
                  strokeDasharray="4 4"
                  fill="#ffffff"
                  fillOpacity={1}
                />

                {/* Actual Consumption Line */}
                <Line
                  type="monotone"
                  dataKey="kwh"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={renderCustomDot}
                  activeDot={{ r: 7 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Selected Observation Inspection Card */}
      {selectedObservation && (
        <div className="card" style={{ borderColor: selectedObservation.is_anomaly ? (selectedObservation.anomaly_direction === 'high' ? '#fecaca' : selectedObservation.anomaly_direction === 'pattern' ? '#e9d5ff' : '#fde68a') : 'var(--border-color)' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
            <div style={{ flex: 1, minWidth: '280px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  Selected Date: <strong style={{ color: 'var(--text-primary)' }}>{selectedObservation.date}</strong>
                </span>
                {selectedObservation.is_anomaly ? (
                  <span className={`badge ${selectedObservation.anomaly_direction === 'high' ? 'badge-high' : selectedObservation.anomaly_direction === 'pattern' ? 'badge-pattern' : 'badge-low'}`}>
                    {selectedObservation.anomaly_direction.toUpperCase()} ANOMALY
                  </span>
                ) : (
                  <span className="badge badge-normal">Normal Reading</span>
                )}
                <span className={`badge ${
                  selectedObservation.review_status === 'Pending Review' || selectedObservation.review_status === 'PENDING' ? 'badge-pending' :
                  selectedObservation.review_status === 'Mark for Field Visit' ? 'badge-field' :
                  selectedObservation.review_status === 'High Usage Authorized' ? 'badge-auth' : 'badge-ack'
                }`}>
                  Status: {selectedObservation.review_status}
                </span>
              </div>

              <div style={{ display: 'flex', gap: '24px', margin: '14px 0', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Observed Value</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {selectedObservation.kwh.toFixed(2)} <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>kWh</span>
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Trailing Median</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    {selectedObservation.trailing_median?.toFixed(2) ?? '0.00'} <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>kWh</span>
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Historical Expected Bounds</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    {selectedObservation.expected_lower?.toFixed(2) ?? '0.00'} – {selectedObservation.expected_upper?.toFixed(2) ?? '0.00'} <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>kWh</span>
                  </div>
                </div>
              </div>

              <div style={{ background: '#f8fafc', padding: '12px 16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)', fontSize: '0.88rem' }}>
                <strong style={{ color: 'var(--text-primary)' }}>Data-Derived Analytical Explanation:</strong>
                <p style={{ color: 'var(--text-secondary)', marginTop: '4px' }}>
                  {selectedObservation.reason}
                </p>
              </div>
            </div>

            <div>
              <button
                onClick={() => setReviewModalOpen(true)}
                className="btn btn-primary"
                style={{ padding: '10px 20px', fontSize: '0.95rem' }}
              >
                <ShieldCheck size={18} /> Record Review Decision
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Review Modal */}
      {selectedObservation && (
        <ReviewModal
          isOpen={reviewModalOpen}
          onClose={() => setReviewModalOpen(false)}
          onSuccess={() => {
            loadMeterHistory(selectedMeterId, timeRange);
          }}
          observation={{
            observation_id: `${selectedMeterId}_${selectedObservation.date}`,
            meter_id: selectedMeterId,
            date: selectedObservation.date,
            kwh: selectedObservation.kwh,
            expected_lower: selectedObservation.expected_lower,
            expected_upper: selectedObservation.expected_upper,
            anomaly_direction: selectedObservation.anomaly_direction,
            reason: selectedObservation.reason,
            review_status: selectedObservation.review_status,
          }}
        />
      )}
    </div>
  );
};
