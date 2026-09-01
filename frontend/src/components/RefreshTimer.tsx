interface RefreshTimerProps {
  countdown: number;
  isRefreshing: boolean;
  lastRefresh: Date;
  onRefresh: () => void;
}

export default function RefreshTimer({ countdown, isRefreshing, lastRefresh, onRefresh }: RefreshTimerProps) {
  const progress = countdown / 30;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 13, color: 'var(--text-dim)' }}>
      <span style={{ fontSize: 12 }}>
        Last: {lastRefresh.toLocaleTimeString()}
      </span>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        background: 'var(--bg-raised)',
        borderRadius: 9999,
        padding: '6px 12px',
      }}>
        <svg width="18" height="18" viewBox="0 0 20 20" style={{ transform: 'rotate(-90deg)' }}>
          <circle cx="10" cy="10" r="8" fill="none" stroke="var(--bg-overlay)" strokeWidth="2" />
          <circle
            cx="10" cy="10" r="8" fill="none"
            stroke="var(--brand-red)" strokeWidth="2"
            strokeDasharray={`${progress * 50.26} 50.26`}
            strokeLinecap="round"
          />
        </svg>
        <span style={{ fontSize: 12, fontFamily: 'monospace', width: 24, textAlign: 'center' }}>{countdown}s</span>
      </div>
      <button
        onClick={onRefresh}
        disabled={isRefreshing}
        style={{
          padding: 6,
          borderRadius: 8,
          opacity: isRefreshing ? 0.5 : 1,
          transition: 'opacity 0.15s',
        }}
        title="Refresh now"
      >
        <svg
          width="16" height="16" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          style={{ animation: isRefreshing ? 'spin 1s linear infinite' : 'none' }}
        >
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
        </svg>
        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      </button>
    </div>
  );
}
