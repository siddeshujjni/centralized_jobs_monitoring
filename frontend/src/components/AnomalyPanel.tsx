import { Link } from 'react-router-dom';
import type { Anomaly } from '../api/client';

interface AnomalyPanelProps {
  anomalies: Anomaly[];
  loading: boolean;
  compact?: boolean;
}

const SEVERITY_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  critical: { bg: 'rgba(239,68,68,0.1)', text: '#f87171', border: 'rgba(239,68,68,0.3)' },
  high: { bg: 'rgba(249,115,22,0.1)', text: '#fb923c', border: 'rgba(249,115,22,0.3)' },
  medium: { bg: 'rgba(234,179,8,0.1)', text: '#facc15', border: 'rgba(234,179,8,0.3)' },
  low: { bg: 'rgba(59,130,246,0.1)', text: '#60a5fa', border: 'rgba(59,130,246,0.3)' },
};

function formatAnomalyType(type: string): string {
  return type.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export default function AnomalyPanel({ anomalies, loading, compact = false }: AnomalyPanelProps) {
  if (loading) {
    return (
      <div className="card">
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>Active Anomalies</h3>
        {[...Array(3)].map((_, i) => (
          <div key={i} style={{ height: 64, background: 'var(--bg-raised)', borderRadius: 8, marginBottom: 8, animation: 'pulse 2s infinite' }} />
        ))}
      </div>
    );
  }

  const displayAnomalies = compact ? anomalies.slice(0, 5) : anomalies;

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
          Active Anomalies{' '}
          <span style={{ color: 'var(--text-faint)', fontWeight: 400 }}>({anomalies.length})</span>
        </h3>
        {compact && anomalies.length > 5 && (
          <Link to="/anomalies" style={{ fontSize: 12, color: 'var(--brand-red)' }}>View all</Link>
        )}
      </div>

      {anomalies.length === 0 ? (
        <div style={{ padding: '32px 0', textAlign: 'center' }}>
          <div style={{
            width: 40, height: 40, borderRadius: '50%', background: 'rgba(16,185,129,0.1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px',
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#34d399" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>No anomalies detected</div>
          <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 4 }}>All jobs are running normally</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {displayAnomalies.map((anomaly, idx) => {
            const colors = SEVERITY_COLORS[anomaly.severity] || SEVERITY_COLORS.low;
            return (
              <Link
                key={`${anomaly.job_id}-${anomaly.anomaly_type}-${idx}`}
                to={`/jobs/${anomaly.job_id}`}
                style={{
                  display: 'block',
                  padding: 12,
                  borderRadius: 8,
                  border: `1px solid ${colors.border}`,
                  background: colors.bg,
                  transition: 'filter 0.15s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span className="badge" style={{ background: colors.bg, color: colors.text, fontSize: 10, padding: '0 6px' }}>
                    {anomaly.severity.toUpperCase()}
                  </span>
                  <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                    {formatAnomalyType(anomaly.anomaly_type)}
                  </span>
                </div>
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {anomaly.job_name}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>{anomaly.message}</div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
