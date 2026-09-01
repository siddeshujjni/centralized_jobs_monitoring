import type { JobRun } from '../api/client';

interface DurationChartProps {
  runs: JobRun[];
}

const STATUS_COLORS: Record<string, string> = {
  SUCCESS: '#10B981',
  SUCCEEDED: '#10B981',
  FAILED: '#EF4444',
  TIMEDOUT: '#EF4444',
  RUNNING: '#3B82F6',
  CANCELED: '#6B7280',
  PENDING: '#EAB308',
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h${m}m`;
}

export default function DurationChart({ runs }: DurationChartProps) {
  const chartData = [...runs]
    .reverse()
    .filter((r) => r.duration_seconds !== null && r.duration_seconds > 0)
    .map((run) => ({
      label: run.start_time
        ? new Date(run.start_time).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
        : `#${run.run_id}`,
      duration: Math.round(run.duration_seconds || 0),
      status: run.result_state || run.state,
    }));

  if (chartData.length === 0) {
    return (
      <div className="card">
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>Run Duration History</h3>
        <div style={{ height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 14 }}>
          No run data available
        </div>
      </div>
    );
  }

  const maxDuration = Math.max(...chartData.map((d) => d.duration));
  const barWidth = Math.max(20, Math.min(40, Math.floor(600 / chartData.length) - 8));

  return (
    <div className="card">
      <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 16 }}>Run Duration History</h3>
      <div style={{ height: 250, display: 'flex', flexDirection: 'column' }}>
        {/* Chart area */}
        <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end', gap: 4, paddingBottom: 24, position: 'relative', minHeight: 0 }}>
          {/* Y-axis labels */}
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 24, width: 50, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>{formatDuration(maxDuration)}</span>
            <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>{formatDuration(maxDuration / 2)}</span>
            <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>0s</span>
          </div>
          {/* Bars */}
          <div style={{ marginLeft: 56, flex: 1, display: 'flex', alignItems: 'flex-end', gap: 4, height: '100%' }}>
            {chartData.map((d, i) => {
              const height = maxDuration > 0 ? (d.duration / maxDuration) * 100 : 0;
              const color = STATUS_COLORS[d.status] || '#6B7280';
              return (
                <div
                  key={i}
                  style={{ flex: 1, maxWidth: barWidth, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}
                  title={`${d.label}: ${formatDuration(d.duration)} (${d.status})`}
                >
                  <div style={{
                    width: '100%',
                    height: `${Math.max(height, 2)}%`,
                    background: color,
                    borderRadius: '3px 3px 0 0',
                    opacity: 0.8,
                    transition: 'height 0.3s ease',
                    minHeight: 2,
                  }} />
                </div>
              );
            })}
          </div>
        </div>
        {/* X-axis labels */}
        <div style={{ marginLeft: 56, display: 'flex', gap: 4 }}>
          {chartData.map((d, i) => (
            <div key={i} style={{ flex: 1, maxWidth: barWidth, textAlign: 'center', fontSize: 9, color: 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {i % Math.max(1, Math.floor(chartData.length / 8)) === 0 ? d.label : ''}
            </div>
          ))}
        </div>
      </div>
      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 12 }}>
        {[['SUCCESS', '#10B981'], ['FAILED', '#EF4444'], ['RUNNING', '#3B82F6']].map(([label, color]) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: color }} />
            <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
