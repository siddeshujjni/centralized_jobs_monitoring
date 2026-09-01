import { useNavigate } from 'react-router-dom';
import StatusBadge from './StatusBadge';
import type { JobInfo } from '../api/client';

interface JobsTableProps {
  jobs: JobInfo[];
  loading: boolean;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '--';
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
  });
}

export default function JobsTable({ jobs, loading }: JobsTableProps) {
  const navigate = useNavigate();

  if (loading) {
    return (
      <div className="card">
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>Jobs</h3>
        {[...Array(5)].map((_, i) => (
          <div key={i} style={{ height: 48, background: 'var(--bg-raised)', borderRadius: 8, marginBottom: 8, animation: 'pulse 2s infinite' }} />
        ))}
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '20px 20px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
          Jobs <span style={{ color: 'var(--text-faint)', fontWeight: 400 }}>({jobs.length})</span>
        </h3>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Job Name</th>
              <th>Status</th>
              <th>Last Run</th>
              <th>Duration</th>
              <th>Schedule</th>
              <th style={{ width: 40 }}></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr
                key={job.job_id}
                onClick={() => navigate(`/jobs/${job.job_id}`)}
                style={{ cursor: 'pointer' }}
              >
                <td>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>ID: {job.job_id}</div>
                </td>
                <td><StatusBadge status={job.status} /></td>
                <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                  {formatTime(job.latest_run?.start_time ?? null)}
                </td>
                <td>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--text-dim)' }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>
                    {formatDuration(job.latest_run?.duration_seconds ?? null)}
                  </span>
                </td>
                <td style={{ fontSize: 12, color: 'var(--text-dim)', fontFamily: 'monospace', maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {job.schedule || '--'}
                </td>
                <td style={{ padding: '12px 12px' }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-faint)" strokeWidth="2"><polyline points="9 18 15 12 9 6" /></svg>
                </td>
              </tr>
            ))}
            {jobs.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: 40, fontSize: 14, color: 'var(--text-faint)' }}>
                  No jobs found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
