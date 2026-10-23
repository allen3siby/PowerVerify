import React, { useState, useEffect } from 'react';
import {
  Activity,
  AlertOctagon,
  Clock,
  Download,
  Layers,
  RefreshCw,
  Sliders,
  Zap,
  CheckCircle2,
  AlertTriangle,
  History,
  TrendingUp,
  ChevronDown,
  ChevronUp,
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
import type {
  DatasetSummary,
  DashboardStats,
  ChartDataPoint,
  MeterListItem,
  ModelConfigDetailResponse,
  ModelRunSummary,
  ModelComparison,
} from '../types';

interface OverviewDashboardProps {
  onSelectMeter: (meterId: string) => void;
  onNavigateToQueue: () => void;
}

export const OverviewDashboard: React.FC<OverviewDashboardProps> = ({
  onSelectMeter,
  onNavigateToQueue,
}) => {
  const [summary, setSummary] = useState<DatasetSummary | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [chartPoints, setChartPoints] = useState<ChartDataPoint[]>([]);
  const [meters, setMeters] = useState<MeterListItem[]>([]);
  const [timeRange, setTimeRange] = useState<string>('30d');
  const [loading, setLoading] = useState<boolean>(true);
  const [reanalyzing, setReanalyzing] = useState<boolean>(false);
  const [modelConfig, setModelConfig] = useState<ModelConfigDetailResponse | null>(null);
  const [activeContamination, setActiveContamination] = useState<number>(0.03);
  const [sliderContamination, setSliderContamination] = useState<number>(0.03);
  const [recentRuns, setRecentRuns] = useState<ModelRunSummary[]>([]);
  const [latestComparison, setLatestComparison] = useState<ModelComparison | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState<boolean>(false);
  const [selectedMeterFilter, setSelectedMeterFilter] = useState<string>('');
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadData = async (range: string = timeRange, meterId?: string) => {
    setLoading(true);
    setLoadError(null);
    try {
      const [sumRes, statRes, chartRes, meterRes, cfgRes, runsRes] = await Promise.all([
        api.getDatasetSummary(),
        api.getDashboardStats(),
        api.getDashboardChart(range, meterId || undefined),
        api.getMeters(),
        api.getModelConfig().catch(() => null),
        api.getModelRuns(10).catch(() => []),
      ]);
      setSummary(sumRes);
      setStats(statRes);
      setChartPoints(chartRes?.points || []);
      setMeters(meterRes || []);
      if (cfgRes) {
        setModelConfig(cfgRes);
        const actContam = cfgRes.active_configuration?.contamination ?? statRes.contamination;
        setActiveContamination(actContam);
        setSliderContamination(actContam);
      } else if (statRes) {
        setActiveContamination(statRes.contamination);
        setSliderContamination(statRes.contamination);
      }
      setRecentRuns(runsRes || []);
    } catch (err: any) {
      console.error('Failed to load overview data', err);
      setLoadError(err?.message || 'Unable to connect to PowerVerify backend service.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleTimeRangeChange = (newRange: string) => {
    setTimeRange(newRange);
    loadData(newRange, selectedMeterFilter);
  };

  const handleMeterFilterChange = (mId: string) => {
    setSelectedMeterFilter(mId);
    loadData(timeRange, mId);
  };

  const handleReanalyze = async () => {
    setReanalyzing(true);
    setRunMessage(null);
    setRunError(null);
    try {
      const res = await api.rerunIsolationForest(sliderContamination, 150, 42);
      setActiveContamination(res.run.contamination);
      if (res.comparison) {
        setLatestComparison(res.comparison);
      }
      setRunMessage(res.message);
      await loadData(timeRange, selectedMeterFilter);
    } catch (err: any) {
      setRunError(err.message || 'Model re-analysis failed.');
    } finally {
      setReanalyzing(false);
    }
  };

  // Custom Chart Dot to render Red, Amber, and Purple anomaly markers
  const renderCustomDot = (props: any) => {
    const { cx, cy, payload } = props;
    if (!payload || !payload.is_anomaly) return null;

    let fill = '#9333ea'; // default pattern: purple
    if (payload.anomaly_direction === 'high') {
      fill = '#ef4444'; // Red for high anomaly
    } else if (payload.anomaly_direction === 'low') {
      fill = '#f59e0b'; // Amber for low anomaly
    } else if (payload.anomaly_direction === 'pattern') {
      fill = '#9333ea'; // Purple for pattern anomaly
    }

    return (
      <circle
        key={`dot-${payload.date}-${payload.meter_id || 'sys'}`}
        cx={cx}
        cy={cy}
        r={5.5}
        fill={fill}
        stroke="#ffffff"
        strokeWidth={2}
        style={{ cursor: 'pointer' }}
      />
    );
  };

  // Custom Tooltip component
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
            <span style={{ color: 'var(--text-muted)' }}>Target:</span>
            <strong>{data.meter_id ? `Meter ${data.meter_id}` : 'System Mean'}</strong>
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
          <div className="chart-tooltip-row">
            <span style={{ color: 'var(--text-muted)' }}>Severity Percentile:</span>
            <span>{((data.anomaly_score ?? data.anomaly_severity) * 100).toFixed(1)}%</span>
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

  return (
    <div className="page-container">
      {/* Top Dataset Verification Banner */}
      {summary && (
        <div className="card" style={{ background: 'linear-gradient(135deg, #ffffff 0%, #f0f7ff 100%)', borderColor: '#bfdbfe', padding: '18px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <span className="badge badge-normal" style={{ background: '#dbeafe', color: '#1e40af', fontWeight: 700 }}>
                  VERIFIED REAL CEEW DATASET
                </span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  Mathura & Bareilly Districts, Uttar Pradesh
                </span>
              </div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {summary.dataset_name}
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '18px', marginTop: '6px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                <span><strong>Period:</strong> {summary.start_date} to {summary.end_date}</span>
                <span>•</span>
                <span><strong>Meters:</strong> {summary.total_meters} Smart Meters</span>
                <span>•</span>
                <span><strong>Sampling:</strong> Daily Consumption Sum (t_kWh)</span>
                <span>•</span>
                <span><strong>Records:</strong> {summary.valid_readings.toLocaleString()} valid readings</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <a
                href={api.getExportReportUrl()}
                target="_blank"
                rel="noreferrer"
                className="btn btn-secondary"
                title="Download Academic Analysis Summary Report"
              >
                <Download size={15} /> Academic Report
              </a>
              <a
                href={api.getExportCsvUrl(true)}
                className="btn btn-primary"
                title="Download flagged anomalies CSV"
              >
                <Download size={15} /> Flagged CSV
              </a>
            </div>
          </div>
        </div>
      )}

      {/* KPI Stats Grid */}
      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-header">
              <span className="stat-label">Total Readings Analyzed</span>
              <div className="stat-icon" style={{ background: '#eff6ff', color: '#2563eb' }}>
                <Layers size={18} />
              </div>
            </div>
            <div className="stat-value">{stats.total_readings.toLocaleString()}</div>
            <div className="stat-meta">Across {stats.total_meters} distinct smart meters</div>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span className="stat-label">Flagged Anomalies</span>
              <div className="stat-icon" style={{ background: '#fef2f2', color: '#dc2626' }}>
                <AlertOctagon size={18} />
              </div>
            </div>
            <div className="stat-value" style={{ color: '#dc2626' }}>
              {stats.flagged_anomalies.toLocaleString()}
            </div>
            <div className="stat-meta">
              <span style={{ color: '#dc2626', fontWeight: 600 }}>{stats.high_anomalies} high</span>,{' '}
              <span style={{ color: '#d97706', fontWeight: 600 }}>{stats.low_anomalies} low</span>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-header">
              <span className="stat-label">Flagged Meters</span>
              <div className="stat-icon" style={{ background: '#fffbeb', color: '#d97706' }}>
                <Zap size={18} />
              </div>
            </div>
            <div className="stat-value">{stats.flagged_meters}</div>
            <div className="stat-meta">
              {((stats.flagged_meters / stats.total_meters) * 100).toFixed(1)}% of total smart meters
            </div>
          </div>

          <div
            className="stat-card"
            style={{ cursor: 'pointer', borderColor: stats.pending_reviews > 0 ? '#fde68a' : 'var(--border-color)' }}
            onClick={onNavigateToQueue}
          >
            <div className="stat-header">
              <span className="stat-label">Awaiting Review</span>
              <div className="stat-icon" style={{ background: '#f8fafc', color: '#475569' }}>
                <Clock size={18} />
              </div>
            </div>
            <div className="stat-value" style={{ color: stats.pending_reviews > 0 ? '#b45309' : '#0f172a' }}>
              {stats.pending_reviews}
            </div>
            <div className="stat-meta">
              {stats.resolved_reviews} resolved decisions • <strong style={{ color: 'var(--primary-blue)' }}>Go to Queue →</strong>
            </div>
          </div>
        </div>
      )}

      {/* Main Consumption Chart Card */}
      <div className="card">
        <div className="controls-row">
          <div>
            <h3 className="card-title">
              <Activity size={20} color="var(--primary-blue)" />
              {selectedMeterFilter ? `Smart Meter ${selectedMeterFilter} Consumption History` : 'Smart Meter Consumption Overview (System Mean & Anomalies)'}
            </h3>
            <p className="card-subtitle">
              Daily electricity usage (kWh) with historical expected range (trailing 30-day median ± 2.5 MAD) and Isolation Forest anomaly flags.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {/* Quick meter selector */}
            <select
              value={selectedMeterFilter}
              onChange={(e) => handleMeterFilterChange(e.target.value)}
              style={{
                padding: '6px 10px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-color)',
                fontSize: '0.85rem',
                background: '#ffffff',
                color: 'var(--text-primary)',
              }}
            >
              <option value="">System Overview (All Meters)</option>
              {meters.map((m) => (
                <option key={m.meter_id} value={m.meter_id}>
                  {m.meter_id} ({m.district}) - {m.anomaly_count} flags
                </option>
              ))}
            </select>

            {/* Time range picker */}
            <div className="time-range-group">
              {['30d', '90d', '1y', 'all'].map((range) => (
                <button
                  key={range}
                  className={`time-range-btn ${timeRange === range ? 'active' : ''}`}
                  onClick={() => handleTimeRangeChange(range)}
                >
                  {range.toUpperCase()}
                </button>
              ))}
            </div>

            {selectedMeterFilter && (
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => onSelectMeter(selectedMeterFilter)}
              >
                Inspect Meter →
              </button>
            )}
          </div>
        </div>

        {/* Legend description */}
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '16px', margin: '8px 0 16px 0', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 12, height: 12, borderRadius: 2, background: '#2563eb', display: 'inline-block' }} />
            <span>Observed Consumption (kWh)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 12, height: 12, borderRadius: 2, background: '#93c5fd', opacity: 0.5, display: 'inline-block' }} />
            <span>Expected Historical Range</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} />
            <span>High Usage Anomaly (Red)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
            <span>Low Usage Anomaly (Amber)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#9333ea', display: 'inline-block' }} />
            <span>Pattern Anomaly (Purple)</span>
          </div>
        </div>

        {/* Recharts Component */}
        <div style={{ width: '100%', height: 380 }}>
          {loading ? (
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', gap: '10px' }}>
              <RefreshCw className="spin" size={24} style={{ color: 'var(--primary-blue)' }} />
              <span>Loading smart-meter consumption history...</span>
            </div>
          ) : loadError ? (
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#b91c1c', background: '#fef2f2', borderRadius: '8px', padding: '20px', gap: '12px', textAlign: 'center' }}>
              <AlertTriangle size={32} />
              <div>
                <strong>Failed to load consumption data</strong>
                <div style={{ fontSize: '0.85rem', color: '#7f1d1d', marginTop: '4px', maxWidth: '600px' }}>{loadError}</div>
              </div>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => loadData(timeRange, selectedMeterFilter)}
                style={{ marginTop: '8px' }}
              >
                <RefreshCw size={14} style={{ marginRight: 6 }} /> Retry Connection
              </button>
            </div>
          ) : chartPoints.length === 0 ? (
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', gap: '8px', textAlign: 'center', padding: '20px' }}>
              <Activity size={28} style={{ opacity: 0.5 }} />
              <strong style={{ color: 'var(--text-secondary)' }}>No data points available for the selected period</strong>
              <span style={{ fontSize: '0.8rem', maxWidth: '520px' }}>
                The CEEW smart-meter dataset contains daily readings from May 1, 2019 to October 31, 2021. Try selecting <strong>1Y</strong> or <strong>ALL</strong>, or choose a different meter filter.
              </span>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => { setTimeRange('all'); loadData('all', selectedMeterFilter); }}
                style={{ marginTop: '6px' }}
              >
                View Full Dataset (ALL)
              </button>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartPoints} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: '#64748b' }}
                  tickLine={false}
                  minTickGap={30}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#64748b' }}
                  tickLine={false}
                  label={{ value: 'Daily kWh', angle: -90, position: 'insideLeft', style: { fill: '#64748b', fontSize: 11 } }}
                />
                <Tooltip content={<CustomTooltip />} />
                
                {/* Expected Upper & Lower Bounds */}
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
                  activeDot={{ r: 7, stroke: '#1d4ed8', strokeWidth: 2 }}
                  name="Consumption (kWh)"
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Model Settings & Academic Transparency Card */}
      <div className="card">
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h3 className="card-title">
              <Sliders size={18} color="var(--primary-blue)" /> Isolation Forest Anomaly Detection Configuration
            </h3>
            <p className="card-subtitle">
              Configurable scikit-learn unsupervised outlier threshold. Controls sensitivity and tracks model run history.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span className="badge badge-reviewed" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <CheckCircle2 size={12} /> Active Backend Model: {(activeContamination * 100).toFixed(1)}%
            </span>
            {modelConfig?.current_run && (
              <span className="badge badge-normal" style={{ fontSize: '0.75rem' }}>
                Run ID: {modelConfig.current_run.run_id}
              </span>
            )}
          </div>
        </div>

        {/* Status / Error Alerts */}
        {runMessage && (
          <div style={{ background: '#ecfdf5', color: '#065f46', border: '1px solid #a7f3d0', padding: '10px 14px', borderRadius: 'var(--radius-sm)', marginBottom: '16px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle2 size={16} />
            <span>{runMessage}</span>
          </div>
        )}
        {runError && (
          <div style={{ background: '#fef2f2', color: '#991b1b', border: '1px solid #fecaca', padding: '10px 14px', borderRadius: 'var(--radius-sm)', marginBottom: '16px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={16} />
            <span>{runError}</span>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '24px', alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.88rem' }}>
              <span style={{ fontWeight: 600 }}>Contamination Slider:</span>
              <strong style={{ color: sliderContamination !== activeContamination ? '#d97706' : 'var(--primary-blue)' }}>
                {(sliderContamination * 100).toFixed(1)}% expected outliers
                {sliderContamination !== activeContamination && ' (Unapplied)'}
              </strong>
            </div>
            <input
              type="range"
              min="0.01"
              max="0.08"
              step="0.005"
              value={sliderContamination}
              disabled={reanalyzing}
              onChange={(e) => setSliderContamination(parseFloat(e.target.value))}
              style={{ width: '100%', cursor: reanalyzing ? 'not-allowed' : 'pointer' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              <span>1.0% (Strict)</span>
              <span>3.0% (CEEW Default)</span>
              <span>8.0% (Broad)</span>
            </div>
          </div>

          <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', background: '#f8fafc', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
            <div><strong>Algorithm:</strong> scikit-learn Isolation Forest (150 trees, random_state=42)</div>
            <div style={{ marginTop: '4px' }}><strong>Features:</strong> Interval kWh, day delta, baseline ratio, robust z-score, calendar</div>
            <div style={{ marginTop: '4px' }}><strong>Thresholding:</strong> Trailing 30-day Median ± 2.5 * (1.4826 * MAD)</div>
          </div>

          <div>
            <button
              onClick={handleReanalyze}
              disabled={reanalyzing}
              className="btn btn-primary"
              style={{ width: '100%', justifyContent: 'center' }}
            >
              <RefreshCw size={16} className={reanalyzing ? 'spin' : ''} />
              {reanalyzing ? 'Re-analyzing 44,610 Readings...' : 'Re-run Isolation Forest'}
            </button>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: '6px' }}>
              Atomic pipeline • Preserves review history • Concurrency safe
            </div>
          </div>
        </div>

        {/* Model Run Comparison Summary (if comparison exists) */}
        {latestComparison && (
          <div style={{ marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <TrendingUp size={16} color="var(--primary-blue)" /> Model Run Comparison ({latestComparison.current_run_id} vs {latestComparison.previous_run_id})
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
              <div style={{ background: '#f8fafc', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Contamination Shift</div>
                <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                  {(latestComparison.previous_contamination * 100).toFixed(1)}% → {(latestComparison.current_contamination * 100).toFixed(1)}%
                </div>
              </div>
              <div style={{ background: '#eff6ff', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid #bfdbfe' }}>
                <div style={{ fontSize: '0.75rem', color: '#1e40af' }}>Newly Detected Findings</div>
                <div style={{ fontWeight: 700, fontSize: '1.1rem', color: '#1e40af' }}>
                  +{latestComparison.newly_detected_count}
                </div>
              </div>
              <div style={{ background: '#fef2f2', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid #fecaca' }}>
                <div style={{ fontSize: '0.75rem', color: '#991b1b' }}>No-Longer-Detected Findings</div>
                <div style={{ fontWeight: 700, fontSize: '1.1rem', color: '#991b1b' }}>
                  -{latestComparison.no_longer_detected_count}
                </div>
              </div>
              <div style={{ background: '#ecfdf5', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid #a7f3d0' }}>
                <div style={{ fontSize: '0.75rem', color: '#065f46' }}>Continuing Findings</div>
                <div style={{ fontWeight: 700, fontSize: '1.1rem', color: '#065f46' }}>
                  {latestComparison.continuing_count}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Model Run History Toggle & Panel */}
        <div style={{ marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <History size={16} /> Model Run Audit Trail ({recentRuns.length} recorded runs)
            </span>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setShowHistory(!showHistory)}
              style={{ fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '4px' }}
            >
              {showHistory ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {showHistory ? 'Hide Run History' : 'Show Run History'}
            </button>
          </div>

          {showHistory && (
            <div style={{ marginTop: '12px', maxHeight: '220px', overflowY: 'auto', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)' }}>
              <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: '#f8fafc', borderBottom: '1px solid var(--border-color)' }}>
                    <th style={{ padding: '8px 12px' }}>Run ID</th>
                    <th style={{ padding: '8px 12px' }}>Contamination</th>
                    <th style={{ padding: '8px 12px' }}>Trees</th>
                    <th style={{ padding: '8px 12px' }}>Anomalies</th>
                    <th style={{ padding: '8px 12px' }}>Status</th>
                    <th style={{ padding: '8px 12px' }}>Completed At</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No historical runs recorded yet.
                      </td>
                    </tr>
                  ) : (
                    recentRuns.map((r) => (
                      <tr key={r.run_id} style={{ borderBottom: '1px solid #f1f5f9', background: r.is_active ? '#eff6ff' : 'transparent' }}>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontWeight: r.is_active ? 700 : 400 }}>
                          {r.run_id} {r.is_active ? <span className="badge badge-reviewed" style={{ fontSize: '0.7rem', padding: '1px 4px' }}>ACTIVE</span> : null}
                        </td>
                        <td style={{ padding: '8px 12px' }}>{(r.contamination * 100).toFixed(1)}%</td>
                        <td style={{ padding: '8px 12px' }}>{r.n_estimators}</td>
                        <td style={{ padding: '8px 12px' }}>
                          <strong>{r.anomalies_flagged}</strong>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: '4px' }}>
                            (H:{r.high_anomalies} L:{r.low_anomalies} P:{r.pattern_anomalies})
                          </span>
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          <span className={`badge ${r.status === 'COMPLETED' ? 'badge-reviewed' : r.status === 'FAILED' ? 'badge-high' : 'badge-low'}`} style={{ fontSize: '0.7rem' }}>
                            {r.status}
                          </span>
                        </td>
                        <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>
                          {r.completed_at ? new Date(r.completed_at).toLocaleTimeString() : 'In Progress'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
