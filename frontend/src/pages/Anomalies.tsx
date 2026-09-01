import { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { Anomaly } from '../api/client';
import { useAutoRefresh } from '../hooks/useAutoRefresh';
import RefreshTimer from '../components/RefreshTimer';

const SEVERITY_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  critical: { bg: 'rgba(239,68,68,0.1)', text: '#f87171', border: 'rgba(239,68,68,0.3)' },
  high: { bg: 'rgba(249,115,22,0.1)', text: '#fb923c', border: 'rgba(249,115,22,0.3)' },
  medium: { bg: 'rgba(234,179,8,0.1)', text: '#facc15', border: 'rgba(234,179,8,0.3)' },
  low: { bg: 'rgba(59,130,246,0.1)', text: '#60a5fa', border: 'rgba(59,130,246,0.3)' },
};

const ALL_SEVERITIES = ['critical', 'high', 'medium', 'low'];
const ALL_TYPES = ['duration_spike', 'failure_rate', 'long_running', 'missed_schedule', 'consecutive_failures'];

function formatAnomalyType(type: string): string {
  return type.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export default function AnomaliesPage() {
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const res = await api.getAnomalies();
      setAnomalies(res.anomalies);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, []);

  const { countdown, lastRefresh, isRefreshing, refresh } = useAutoRefresh(fetchData, 30000);

  const filtered = anomalies.filter((a) => {
    if (severityFilter && a.severity !== severityFilter) return false;
    if (typeFilter && a.anomaly_type !== typeFilter) return false;
    return true;
  });

  const filterBtnStyle = (active: boolean, color?: string): React.CSSProperties => ({
    padding: '4px 10px',
    borderRadius: 6,
    fontSize: 12,
    fontWeight: 500,
    background: active ? (color || 'var(--bg-overlay)') : 'transparent',
    color: active ? 'white' : 'var(--text-dim)',
    cursor: 'pointer',
    transition: 'all 0.15s',
    border: 'none',
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: 'white' }}>Anomalies</h1>
          <p style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 2 }}>Detected issues across all monitored jobs</p>
        </div>
        <RefreshTimer countdown={countdown} isRefreshing={isRefreshing} lastRefresh={lastRefresh} onRefresh={refresh} />
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '12px 16px', fontSize: 13, color: '#f87171' }}>
          {error}
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: 4 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" /></svg>
          Filters:
        </span>
        <button onClick={() => setSeverityFilter(null)} style={filterBtnStyle(severityFilter === null)}>All Severity</button>
        {ALL_SEVERITIES.map((s) => (
          <button
            key={s}
            onClick={() => setSeverityFilter(severityFilter === s ? null : s)}
            style={filterBtnStyle(severityFilter === s, SEVERITY_STYLES[s]?.bg)}
          >
            <span style={{ color: severityFilter === s ? SEVERITY_STYLES[s]?.text : undefined }}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </span>
          </button>
        ))}
        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
        <button onClick={() => setTypeFilter(null)} style={filterBtnStyle(typeFilter === null)}>All Types</button>
        {ALL_TYPES.map((t) => (
          <button key={t} onClick={() => setTypeFilter(typeFilter === t ? null : t)} style={filterBtnStyle(typeFilter === t)}>
            {formatAnomalyType(t)}
          </button>
        ))}
      </div>

      <p style={{ fontSize: 12, color: 'var(--text-faint)' }}>
        Showing {filtered.length} of {anomalies.length} anomalies
      </p>

      {/* Anomaly Cards */}
      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} style={{ height: 128, background: 'var(--bg-raised)', borderRadius: 12, animation: 'pulse 2s infinite' }} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="card" style={{ padding: '64px 0', textAlign: 'center' }}>
          <div style={{
            width: 48, height: 48, borderRadius: '50%', background: 'rgba(16,185,129,0.1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px',
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#34d399" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <p style={{ fontSize: 14, color: 'var(--text-dim)' }}>
            {anomalies.length === 0 ? 'No anomalies detected' : 'No anomalies match the current filters'}
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {filtered.map((anomaly, idx) => {
            const styles = SEVERITY_STYLES[anomaly.severity] || SEVERITY_STYLES.low;
            return (
              <Link
                key={`${anomaly.job_id}-${anomaly.anomaly_type}-${idx}`}
                to={`/jobs/${anomaly.job_id}`}
                className="card"
                style={{ border: `1px solid ${styles.border}`, transition: 'filter 0.15s' }}
              >
                <div style={{ display: 'flex', alignItems: 'start', gap: 12 }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 8, background: styles.bg,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={styles.text} strokeWidth="2">
                      <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span className="badge" style={{ background: styles.bg, color: styles.text, fontSize: 10 }}>
                        {anomaly.severity.toUpperCase()}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                        {formatAnomalyType(anomaly.anomaly_type)}
                      </span>
                    </div>
                    <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-secondary)' }}>{anomaly.job_name}</p>
                    <p style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>{anomaly.message}</p>
                    {anomaly.current_value !== null && anomaly.expected_value !== null && (
                      <div style={{ display: 'flex', gap: 16, marginTop: 10 }}>
                        <div>
                          <span style={{ fontSize: 10, color: 'var(--text-faint)', display: 'block' }}>Current</span>
                          <span style={{ fontSize: 12, fontWeight: 600, color: styles.text }}>
                            {anomaly.current_value.toLocaleString()}
                          </span>
                        </div>
                        <div>
                          <span style={{ fontSize: 10, color: 'var(--text-faint)', display: 'block' }}>Expected</span>
                          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-dim)' }}>
                            {anomaly.expected_value.toLocaleString()}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>
                    Detected: {new Date(anomaly.detected_at).toLocaleString()}
                  </span>
                  <span style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'monospace' }}>Job #{anomaly.job_id}</span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
