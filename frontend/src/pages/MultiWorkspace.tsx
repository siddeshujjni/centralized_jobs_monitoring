import { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type {
  MultiWorkspaceSummary,
  WorkspaceSummary,
  AnomalyWithWorkspace,
  JobInfoWithWorkspace,
} from '../api/client';
import { useAutoRefresh } from '../hooks/useAutoRefresh';
import RefreshTimer from '../components/RefreshTimer';
import StatusBadge from '../components/StatusBadge';

const ENV_COLORS: Record<string, { bg: string; text: string }> = {
  production: { bg: 'rgba(239,68,68,0.15)', text: '#ef4444' },
  staging: { bg: 'rgba(249,115,22,0.15)', text: '#f97316' },
  development: { bg: 'rgba(59,130,246,0.15)', text: '#3b82f6' },
  unknown: { bg: 'rgba(107,114,128,0.15)', text: '#6b7280' },
};

const CLOUD_LABELS: Record<string, string> = {
  aws: 'AWS',
  azure: 'Azure',
  gcp: 'GCP',
  unknown: '',
};

const SEVERITY_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  critical: { bg: 'rgba(239,68,68,0.1)', text: '#f87171', border: 'rgba(239,68,68,0.3)' },
  high: { bg: 'rgba(249,115,22,0.1)', text: '#fb923c', border: 'rgba(249,115,22,0.3)' },
  medium: { bg: 'rgba(234,179,8,0.1)', text: '#facc15', border: 'rgba(234,179,8,0.3)' },
  low: { bg: 'rgba(59,130,246,0.1)', text: '#60a5fa', border: 'rgba(59,130,246,0.3)' },
};

function formatAnomalyType(type: string): string {
  return type
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function EnvBadge({ env }: { env: string }) {
  const color = ENV_COLORS[env] || ENV_COLORS.unknown;
  return (
    <span
      className="badge"
      style={{ background: color.bg, color: color.text, fontSize: 10 }}
    >
      {env.toUpperCase()}
    </span>
  );
}

export default function MultiWorkspace() {
  const [summary, setSummary] = useState<MultiWorkspaceSummary | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyWithWorkspace[]>([]);
  const [jobs, setJobs] = useState<JobInfoWithWorkspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedWorkspace, setSelectedWorkspace] = useState<string | null>(null);
  const [jobPage, setJobPage] = useState(0);
  const [sortKey, setSortKey] = useState<'workspace_name' | 'name' | 'status' | 'environment'>('workspace_name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const PAGE_SIZE = 100;

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [summaryRes, anomaliesRes, jobsRes] = await Promise.all([
        api.getMultiSummary(),
        api.getMultiAnomalies(),
        api.getMultiJobs(),
      ]);
      setSummary(summaryRes);
      setAnomalies(anomaliesRes.anomalies);
      setJobs(jobsRes.jobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, []);

  const { countdown, lastRefresh, isRefreshing, refresh } = useAutoRefresh(fetchData, 60000);

  const handleSort = (key: typeof sortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
    setJobPage(0);
  };

  const filteredJobs = selectedWorkspace
    ? jobs.filter((j) => j.workspace_id === selectedWorkspace)
    : jobs;
  const sortedJobs = [...filteredJobs].sort((a, b) => {
    const aVal = (a[sortKey] ?? '').toString().toLowerCase();
    const bVal = (b[sortKey] ?? '').toString().toLowerCase();
    if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });
  const totalPages = Math.ceil(sortedJobs.length / PAGE_SIZE);
  const pagedJobs = sortedJobs.slice(jobPage * PAGE_SIZE, (jobPage + 1) * PAGE_SIZE);

  const filteredAnomalies = selectedWorkspace
    ? anomalies.filter((a) => a.workspace_id === selectedWorkspace)
    : anomalies;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: 'white' }}>Multi-Workspace Overview</h1>
          <p style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 2 }}>
            Aggregate monitoring across all Databricks workspaces
          </p>
        </div>
        <RefreshTimer
          countdown={countdown}
          isRefreshing={isRefreshing}
          lastRefresh={lastRefresh}
          onRefresh={refresh}
        />
      </div>

      {error && (
        <div
          style={{
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: 8,
            padding: '12px 16px',
            fontSize: 13,
            color: '#f87171',
          }}
        >
          {error}
        </div>
      )}

      {/* Global Totals Bar */}
      {summary && (
        <div
          className="card"
          style={{
            display: 'flex',
            gap: 32,
            alignItems: 'center',
            padding: '14px 24px',
          }}
        >
          <span style={{ fontSize: 13, color: 'var(--text-dim)', fontWeight: 600 }}>
            All Workspaces
          </span>
          <div style={{ width: 1, height: 24, background: 'var(--border)' }} />
          <StatValue label="Workspaces" value={summary.workspaces.length} />
          <StatValue label="Total Jobs" value={summary.totals.total_jobs} />
          <StatValue label="Running" value={summary.totals.running} color="#60a5fa" />
          <StatValue label="Failed" value={summary.totals.failed} color="#f87171" />
          <StatValue label="Anomalies" value={summary.totals.anomaly_count} color="#fb923c" />
          {selectedWorkspace && (
            <>
              <div style={{ flex: 1 }} />
              <button
                onClick={() => { setSelectedWorkspace(null); setJobPage(0); }}
                style={{
                  padding: '4px 12px',
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: 500,
                  background: 'var(--bg-overlay)',
                  color: 'var(--text-dim)',
                  cursor: 'pointer',
                  border: 'none',
                }}
              >
                Clear filter
              </button>
            </>
          )}
        </div>
      )}

      {/* Workspace Cards Grid */}
      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              style={{
                height: 160,
                background: 'var(--bg-raised)',
                borderRadius: 12,
                animation: 'pulse 2s infinite',
              }}
            />
          ))}
        </div>
      ) : (
        summary && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 16,
            }}
          >
            {summary.workspaces.map((ws) => (
              <WorkspaceCard
                key={ws.workspace_id}
                workspace={ws}
                isSelected={selectedWorkspace === ws.workspace_id}
                onClick={() => {
                  setSelectedWorkspace(selectedWorkspace === ws.workspace_id ? null : ws.workspace_id);
                  setJobPage(0);
                }}
              />
            ))}
          </div>
        )
      )}

      {/* Main Content Grid: Jobs + Anomalies */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 24 }}>
        {/* Cross-workspace jobs table */}
        <div className="card">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 16,
            }}
          >
            <h2 style={{ fontSize: 15, fontWeight: 600, color: 'white' }}>
              Jobs
              {selectedWorkspace && (
                <span style={{ fontSize: 12, color: 'var(--text-dim)', fontWeight: 400, marginLeft: 8 }}>
                  (filtered)
                </span>
              )}
            </h2>
            <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
              {filteredJobs.length} jobs
            </span>
          </div>
          {loading ? (
            <div style={{ height: 200, background: 'var(--bg-raised)', borderRadius: 8, animation: 'pulse 2s infinite' }} />
          ) : filteredJobs.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--text-dim)', textAlign: 'center', padding: 32 }}>
              No jobs found
            </p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    <SortableTh label="Workspace" sortKey="workspace_name" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                    <SortableTh label="Job Name" sortKey="name" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                    <SortableTh label="Status" sortKey="status" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                    <SortableTh label="Env" sortKey="environment" activeSortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                  </tr>
                </thead>
                <tbody>
                  {pagedJobs.map((job, idx) => (
                    <tr
                      key={`${job.workspace_id}-${job.job_id}-${idx}`}
                      style={{ borderBottom: '1px solid var(--border)' }}
                    >
                      <td style={tdStyle}>
                        <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                          {job.workspace_name}
                        </span>
                      </td>
                      <td style={tdStyle}>
                        <Link
                          to={`/jobs/${job.job_id}?workspace_id=${encodeURIComponent(job.workspace_id)}`}
                          style={{ color: 'var(--text-secondary)', fontWeight: 500 }}
                        >
                          {job.name}
                        </Link>
                      </td>
                      <td style={tdStyle}>
                        <StatusBadge status={job.status} />
                      </td>
                      <td style={tdStyle}>
                        <EnvBadge env={job.environment} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {totalPages > 1 && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderTop: '1px solid var(--border)' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                    {jobPage * PAGE_SIZE + 1}–{Math.min((jobPage + 1) * PAGE_SIZE, sortedJobs.length)} of {sortedJobs.length} jobs
                  </span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={() => setJobPage(p => Math.max(0, p - 1))}
                      disabled={jobPage === 0}
                      style={{ padding: '4px 10px', fontSize: 12, borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-overlay)', color: jobPage === 0 ? 'var(--text-faint)' : 'var(--text-secondary)', cursor: jobPage === 0 ? 'default' : 'pointer' }}
                    >
                      ← Prev
                    </button>
                    <span style={{ fontSize: 12, color: 'var(--text-dim)', padding: '4px 8px' }}>
                      {jobPage + 1} / {totalPages}
                    </span>
                    <button
                      onClick={() => setJobPage(p => Math.min(totalPages - 1, p + 1))}
                      disabled={jobPage >= totalPages - 1}
                      style={{ padding: '4px 10px', fontSize: 12, borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-overlay)', color: jobPage >= totalPages - 1 ? 'var(--text-faint)' : 'var(--text-secondary)', cursor: jobPage >= totalPages - 1 ? 'default' : 'pointer' }}
                    >
                      Next →
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Cross-workspace anomalies panel */}
        <div className="card">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 16,
            }}
          >
            <h2 style={{ fontSize: 15, fontWeight: 600, color: 'white' }}>Anomalies</h2>
            <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>
              {filteredAnomalies.length} detected
            </span>
          </div>
          {loading ? (
            <div style={{ height: 200, background: 'var(--bg-raised)', borderRadius: 8, animation: 'pulse 2s infinite' }} />
          ) : filteredAnomalies.length === 0 ? (
            <div style={{ padding: '32px 0', textAlign: 'center' }}>
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: '50%',
                  background: 'rgba(16,185,129,0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px',
                }}
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#34d399"
                  strokeWidth="2"
                >
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-dim)' }}>No anomalies detected</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 500, overflowY: 'auto' }}>
              {filteredAnomalies.map((anomaly, idx) => {
                const styles = SEVERITY_STYLES[anomaly.severity] || SEVERITY_STYLES.low;
                return (
                  <Link
                    key={`${anomaly.workspace_id}-${anomaly.job_id}-${anomaly.anomaly_type}-${idx}`}
                    to={`/jobs/${anomaly.job_id}?workspace_id=${encodeURIComponent(anomaly.workspace_id)}`}
                    style={{
                      display: 'block',
                      padding: 12,
                      background: 'var(--bg-raised)',
                      borderRadius: 8,
                      borderLeft: `3px solid ${styles.text}`,
                      textDecoration: 'none',
                      transition: 'background 0.15s',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-overlay)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-raised)')}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
                      <span
                        className="badge"
                        style={{ background: styles.bg, color: styles.text, fontSize: 10 }}
                      >
                        {anomaly.severity.toUpperCase()}
                      </span>
                      <EnvBadge env={anomaly.environment} />
                      <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
                        {anomaly.workspace_name}
                      </span>
                    </div>
                    <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)' }}>
                      {anomaly.job_name}
                    </p>
                    <p style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>
                      {formatAnomalyType(anomaly.anomaly_type)}: {anomaly.message}
                    </p>
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Sub-components
   -------------------------------------------------------------------------- */

function StatValue({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--text-faint)', textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: color || 'white' }}>{value}</div>
    </div>
  );
}

function WorkspaceCard({
  workspace,
  isSelected,
  onClick,
}: {
  workspace: WorkspaceSummary;
  isSelected: boolean;
  onClick: () => void;
}) {
  const envColor = ENV_COLORS[workspace.environment] || ENV_COLORS.unknown;

  return (
    <button
      onClick={onClick}
      className="card"
      style={{
        width: '100%',
        textAlign: 'left',
        cursor: 'pointer',
        border: isSelected ? `2px solid ${envColor.text}` : '1px solid var(--border)',
        transition: 'all 0.15s',
        outline: 'none',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: workspace.error ? '#6b7280' : envColor.text,
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: 'white',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {workspace.workspace_name}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <EnvBadge env={workspace.environment} />
          {CLOUD_LABELS[workspace.environment] !== undefined && null}
        </div>
      </div>

      {workspace.error ? (
        <div
          style={{
            fontSize: 12,
            color: '#f87171',
            background: 'rgba(239,68,68,0.08)',
            borderRadius: 6,
            padding: '8px 10px',
          }}
        >
          Connection error: {workspace.error.length > 80 ? workspace.error.slice(0, 80) + '...' : workspace.error}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
          <MiniStat label="Total" value={workspace.total_jobs} />
          <MiniStat label="Running" value={workspace.running} color="#60a5fa" />
          <MiniStat label="Failed" value={workspace.failed} color="#f87171" />
          <MiniStat label="Anomalies" value={workspace.anomaly_count} color="#fb923c" />
        </div>
      )}
    </button>
  );
}

function MiniStat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 16, fontWeight: 700, color: color || 'white' }}>{value}</div>
      <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>{label}</div>
    </div>
  );
}

type SortableKey = 'workspace_name' | 'name' | 'status' | 'environment';

function SortableTh({
  label,
  sortKey,
  activeSortKey,
  sortDir,
  onSort,
}: {
  label: string;
  sortKey: SortableKey;
  activeSortKey: SortableKey;
  sortDir: 'asc' | 'desc';
  onSort: (key: SortableKey) => void;
}) {
  const isActive = sortKey === activeSortKey;
  return (
    <th
      style={{
        ...thStyle,
        cursor: 'pointer',
        userSelect: 'none',
        color: isActive ? 'var(--text-secondary)' : 'var(--text-faint)',
      }}
      onClick={() => onSort(sortKey)}
    >
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        {label}
        <span style={{ fontSize: 10, opacity: isActive ? 1 : 0.3 }}>
          {isActive ? (sortDir === 'asc' ? '▲' : '▼') : '▲'}
        </span>
      </span>
    </th>
  );
}

/* --------------------------------------------------------------------------
   Table styles
   -------------------------------------------------------------------------- */

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '8px 12px',
  fontSize: 11,
  color: 'var(--text-faint)',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
};

const tdStyle: React.CSSProperties = {
  padding: '10px 12px',
};
