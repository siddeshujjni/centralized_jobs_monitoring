import { useState, useEffect } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import { api } from '../api/client';
import type { JobRun, JobStats, Anomaly } from '../api/client';
import DurationChart from '../components/DurationChart';
import StatusBadge from '../components/StatusBadge';
import AnomalyPanel from '../components/AnomalyPanel';
import { JobAIInsightsPanel } from '../components/AIInsightsPanel';
import { useAppConfig } from '../hooks/useAppConfig';

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined || seconds === 0) return '--';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatTime(iso: string | null): string {
  if (!iso) return '--';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function StatCard({ icon, iconColor, label, value, subtitle }: {
  icon: string;
  iconColor: string;
  label: string;
  value: string;
  subtitle?: string;
}) {
  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={iconColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d={icon} />
        </svg>
        <span style={{ fontSize: 11, color: 'var(--text-dim)', fontWeight: 500 }}>{label}</span>
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color: iconColor, lineHeight: 1.2 }}>{value}</div>
      {subtitle && <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 4 }}>{subtitle}</div>}
    </div>
  );
}

export default function JobDetail() {
  const { ai_enabled } = useAppConfig();
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const jobId = Number(id);
  const workspaceId = searchParams.get('workspace_id') || undefined;

  const [runs, setRuns] = useState<JobRun[]>([]);
  const [stats, setStats] = useState<JobStats | null>(null);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError(null);
        const [runsRes, statsRes, anomaliesRes] = await Promise.all([
          api.getJobRuns(jobId, workspaceId),
          api.getJobStats(jobId, workspaceId),
          api.getAnomalies(workspaceId),
        ]);
        setRuns(runsRes.runs);
        setStats(statsRes);
        setAnomalies(anomaliesRes.anomalies.filter((a) => a.job_id === jobId));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch data');
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [jobId, workspaceId]);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div style={{ height: 32, width: 200, background: 'var(--bg-raised)', borderRadius: 6, animation: 'pulse 2s infinite' }} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} style={{ height: 96, background: 'var(--bg-raised)', borderRadius: 12, animation: 'pulse 2s infinite' }} />
          ))}
        </div>
        <div style={{ height: 300, background: 'var(--bg-raised)', borderRadius: 12, animation: 'pulse 2s infinite' }} />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Header */}
      <div>
        <Link to="/" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text-dim)', marginBottom: 12 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6" /></svg>
          Back to Dashboard
        </Link>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: 'white' }}>{stats?.job_name || `Job ${jobId}`}</h1>
        <p style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 2 }}>Job ID: {jobId}</p>
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '12px 16px', fontSize: 13, color: '#f87171' }}>
          {error}
        </div>
      )}

      {/* Stats Cards */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
          <StatCard
            icon="M22 11.08V12a10 10 0 11-5.93-9.14M22 4L12 14.01l-3-3"
            iconColor="var(--green)"
            label="Success Rate"
            value={`${stats.success_rate}%`}
            subtitle={`${stats.success_count}/${stats.total_runs} runs`}
          />
          <StatCard
            icon="M12 2a10 10 0 100 20 10 10 0 000-20zM12 6v6l4 2"
            iconColor="var(--blue)"
            label="Avg Duration"
            value={formatDuration(stats.avg_duration_seconds)}
            subtitle={`Min: ${formatDuration(stats.min_duration_seconds)} / Max: ${formatDuration(stats.max_duration_seconds)}`}
          />
          <StatCard
            icon="M18 20V10M12 20V4M6 20v-6"
            iconColor="var(--purple)"
            label="P95 Duration"
            value={formatDuration(stats.p95_duration_seconds)}
          />
          <StatCard
            icon="M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z"
            iconColor="var(--red)"
            label="Failures"
            value={String(stats.failure_count)}
            subtitle={`of ${stats.total_runs} total runs`}
          />
        </div>
      )}

      {/* Chart + Anomalies */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 24 }}>
        <DurationChart runs={runs} />
        <AnomalyPanel anomalies={anomalies} loading={false} />
      </div>

      {/* AI Analysis Panel (optional — shown only when ENABLE_AI_ANALYSIS=true) */}
      {ai_enabled && (
        <JobAIInsightsPanel jobId={jobId} jobName={stats?.job_name || `Job ${jobId}`} workspaceId={workspaceId} />
      )}

      {/* Run History Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '20px 20px 12px' }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
            Run History <span style={{ color: 'var(--text-faint)', fontWeight: 400 }}>({runs.length})</span>
          </h3>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Status</th>
                <th>Start Time</th>
                <th>Duration</th>
                <th>Trigger</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id}>
                  <td style={{ fontSize: 12, fontFamily: 'monospace', color: 'var(--text-dim)' }}>{run.run_id}</td>
                  <td><StatusBadge status={run.result_state || run.state} /></td>
                  <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>{formatTime(run.start_time)}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>{formatDuration(run.duration_seconds)}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>{run.trigger || '--'}</td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 40, fontSize: 14, color: 'var(--text-faint)' }}>
                    No runs found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
