import React, { useState, useEffect } from 'react';
import {
  Activity,
  Zap,
  ShieldCheck,
  CheckSquare,
  UserCheck,
  CreditCard,
} from 'lucide-react';
import { OverviewDashboard } from './pages/OverviewDashboard';
import { MeterAnalysis } from './pages/MeterAnalysis';
import { ReviewQueue } from './pages/ReviewQueue';
import { AccountVerification } from './pages/AccountVerification';
import { BillingPayments } from './pages/BillingPayments';
import { api, authState } from './api';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'overview' | 'meter' | 'queue' | 'verification' | 'billing'>('overview');
  const [selectedMeterId, setSelectedMeterId] = useState<string>('BR02');
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [currentRole, setCurrentRole] = useState<'VERIFICATION_OFFICER' | 'ADMIN' | 'AUDITOR'>(
    (authState.getRole() as any) || 'VERIFICATION_OFFICER'
  );

  const refreshPendingCount = async () => {
    try {
      const stats = await api.getDashboardStats();
      setPendingCount(stats.pending_reviews);
    } catch (e) {
      // Ignore background refresh errors
    }
  };

  useEffect(() => {
    refreshPendingCount();
    const interval = setInterval(refreshPendingCount, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleSelectMeter = (meterId: string) => {
    setSelectedMeterId(meterId);
    setActiveTab('meter');
  };

  const handleRoleChange = (role: 'VERIFICATION_OFFICER' | 'ADMIN' | 'AUDITOR') => {
    setCurrentRole(role);
    const userId =
      role === 'ADMIN'
        ? 'admin_root'
        : role === 'AUDITOR'
        ? 'auditor_external'
        : 'officer_sharma';
    authState.setUser(role, userId);
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Application Header */}
      <header className="app-header">
        <div className="header-container">
          <div className="brand-wrapper">
            <div className="brand-logo-icon">
              <Zap size={22} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="brand-title">PowerVerify</span>
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                Smart-Meter Electricity Anomaly Verification
              </div>
            </div>
          </div>

          {/* Navigation Bar */}
          <nav className="nav-links">
            <button
              className={`nav-button ${activeTab === 'overview' ? 'active' : ''}`}
              onClick={() => setActiveTab('overview')}
            >
              <Activity size={17} /> Overview Dashboard
            </button>

            <button
              className={`nav-button ${activeTab === 'meter' ? 'active' : ''}`}
              onClick={() => setActiveTab('meter')}
            >
              <Zap size={17} /> Meter Analysis
            </button>

            <button
              className={`nav-button ${activeTab === 'verification' ? 'active' : ''}`}
              onClick={() => setActiveTab('verification')}
            >
              <CheckSquare size={17} /> Account Verification
            </button>

            <button
              className={`nav-button ${activeTab === 'billing' ? 'active' : ''}`}
              onClick={() => setActiveTab('billing')}
            >
              <CreditCard size={17} /> Billing & Payments
            </button>

            <button
              className={`nav-button ${activeTab === 'queue' ? 'active' : ''}`}
              onClick={() => { setActiveTab('queue'); refreshPendingCount(); }}
            >
              <ShieldCheck size={17} /> Review Queue
              {pendingCount > 0 && (
                <span className="nav-counter">{pendingCount}</span>
              )}
            </button>
          </nav>

          {/* RBAC Role Switcher */}
          <div className="role-switcher-badge" title="Simulate different role permissions across API and Workspace">
            <UserCheck size={15} color="var(--primary-blue)" />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Role:</span>
            <select
              className="role-switcher-select"
              value={currentRole}
              onChange={(e) => handleRoleChange(e.target.value as any)}
            >
              <option value="VERIFICATION_OFFICER">Verification Officer</option>
              <option value="ADMIN">Administrator</option>
              <option value="AUDITOR">Auditor (Read-Only)</option>
            </select>
          </div>
        </div>
      </header>

      {/* Main Page Content */}
      <main style={{ flex: 1 }}>
        {activeTab === 'overview' && (
          <OverviewDashboard
            onSelectMeter={handleSelectMeter}
            onNavigateToQueue={() => setActiveTab('queue')}
          />
        )}

        {activeTab === 'meter' && (
          <MeterAnalysis
            initialMeterId={selectedMeterId}
            onSelectMeter={handleSelectMeter}
          />
        )}

        {activeTab === 'verification' && (
          <AccountVerification
            onSelectMeter={handleSelectMeter}
          />
        )}

        {activeTab === 'billing' && (
          <BillingPayments
            onSelectMeter={handleSelectMeter}
            onNavigateToCase={(_caseId) => {
              setActiveTab('queue');
            }}
          />
        )}

        {activeTab === 'queue' && (
          <ReviewQueue
            onSelectMeter={handleSelectMeter}
          />
        )}
      </main>

      {/* Academic Footer */}
      <footer style={{ background: '#ffffff', borderTop: '1px solid var(--border-color)', padding: '16px 24px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
        <div style={{ maxWidth: '1400px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <strong>PowerVerify</strong> • Smart-Meter Consumption Anomaly Detection & Verification
          </div>
          <div>
            Council on Energy, Environment and Water (CEEW) Smart Meter Study Dataset (UP, India)
          </div>
          <div>
            Unsupervised Isolation Forest • Robust Historical MAD Thresholds • Human-in-the-Loop Review
          </div>
        </div>
      </footer>
    </div>
  );
};

export default App;
