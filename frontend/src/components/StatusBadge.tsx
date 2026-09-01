interface StatusBadgeProps {
  status: string;
}

const STATUS_CONFIG: Record<string, { bg: string; text: string; dot: string }> = {
  RUNNING: { bg: 'rgba(59,130,246,0.1)', text: '#60a5fa', dot: '#60a5fa' },
  SUCCESS: { bg: 'rgba(16,185,129,0.1)', text: '#34d399', dot: '#34d399' },
  SUCCEEDED: { bg: 'rgba(16,185,129,0.1)', text: '#34d399', dot: '#34d399' },
  FAILED: { bg: 'rgba(239,68,68,0.1)', text: '#f87171', dot: '#f87171' },
  TIMEDOUT: { bg: 'rgba(239,68,68,0.1)', text: '#f87171', dot: '#f87171' },
  PENDING: { bg: 'rgba(234,179,8,0.1)', text: '#facc15', dot: '#facc15' },
  CANCELED: { bg: 'rgba(107,114,128,0.1)', text: '#9ca3af', dot: '#9ca3af' },
  SKIPPED: { bg: 'rgba(107,114,128,0.1)', text: '#9ca3af', dot: '#9ca3af' },
  NO_RUNS: { bg: 'rgba(107,114,128,0.1)', text: '#6b7280', dot: '#6b7280' },
  UNKNOWN: { bg: 'rgba(107,114,128,0.1)', text: '#6b7280', dot: '#6b7280' },
  TERMINATED: { bg: 'rgba(107,114,128,0.1)', text: '#9ca3af', dot: '#9ca3af' },
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.UNKNOWN;

  return (
    <span className="badge" style={{ background: config.bg, color: config.text }}>
      <span style={{
        width: 6,
        height: 6,
        borderRadius: '50%',
        background: config.dot,
        animation: status === 'RUNNING' ? 'pulse 2s infinite' : 'none',
      }} />
      {status.replace(/_/g, ' ')}
      <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }`}</style>
    </span>
  );
}
