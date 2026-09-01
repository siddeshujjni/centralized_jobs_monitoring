import { useState, useCallback } from 'react';
import { api } from '../api/client';
import type { JobInfo, Anomaly, DashboardSummary } from '../api/client';
import { useAutoRefresh } from '../hooks/useAutoRefresh';
import SummaryCards from '../components/SummaryCards';
import JobsTable from '../components/JobsTable';
import AnomalyPanel from '../components/AnomalyPanel';
import RefreshTimer from '../components/RefreshTimer';
import { WorkspaceAIInsightsPanel } from '../components/AIInsightsPanel';
import SetupBanner from '../components/SetupBanner';
import { useAppConfig } from '../hooks/useAppConfig';

export default function Dashboard() {
  const { ai_enabled } = useAppConfig();
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [jobsRes, anomaliesRes, summaryRes] = await Promise.all([
        api.getJobs(),
        api.getAnomalies(),
        api.getDashboardSummary(),
      ]);
      setJobs(jobsRes.jobs);
      setAnomalies(anomaliesRes.anomalies);
      setSummary(summaryRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, []);

  const { countdown, lastRefresh, isRefreshing, refresh } = useAutoRefresh(fetchData, 30000);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: 'white' }}>Jobs Dashboard</h1>
          <p style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 2 }}>Real-time monitoring and anomaly detection</p>
        </div>
        <RefreshTimer
          countdown={countdown}
          isRefreshing={isRefreshing}
          lastRefresh={lastRefresh}
          onRefresh={refresh}
        />
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '12px 16px', fontSize: 13, color: '#f87171' }}>
          {error}
        </div>
      )}

      <SetupBanner jobCount={jobs.length} loading={loading} />

      {/* Summary Cards */}
      <SummaryCards summary={summary} loading={loading} />

      {/* Main Content Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 24 }}>
        <JobsTable jobs={jobs} loading={loading} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <AnomalyPanel anomalies={anomalies} loading={loading} compact />
          {ai_enabled && <WorkspaceAIInsightsPanel compact />}
        </div>
      </div>
    </div>
  );
}
