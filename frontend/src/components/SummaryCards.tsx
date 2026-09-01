import type { DashboardSummary } from '../api/client';

interface SummaryCardsProps {
  summary: DashboardSummary | null;
  loading: boolean;
}

const CARDS: Array<{
  key: keyof DashboardSummary;
  label: string;
  color: string;
  bg: string;
  iconPath: string;
}> = [
  {
    key: 'total_jobs',
    label: 'Total Jobs',
    color: 'var(--text-secondary)',
    bg: 'rgba(107,114,128,0.15)',
    iconPath: 'M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2zM16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16',
  },
  {
    key: 'running',
    label: 'Running Now',
    color: 'var(--blue)',
    bg: 'rgba(59,130,246,0.1)',
    iconPath: 'M5 3l14 9-14 9V3z',
  },
  {
    key: 'failed',
    label: 'Failed',
    color: 'var(--red)',
    bg: 'rgba(239,68,68,0.1)',
    iconPath: 'M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z',
  },
  {
    key: 'anomaly_count',
    label: 'Active Anomalies',
    color: 'var(--yellow)',
    bg: 'rgba(234,179,8,0.1)',
    iconPath: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  },
];

export default function SummaryCards({ summary, loading }: SummaryCardsProps) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
      {CARDS.map((card) => {
        const value = summary ? summary[card.key] : 0;
        return (
          <div key={card.key} className="card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{
              width: 44,
              height: 44,
              borderRadius: 8,
              background: card.bg,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={card.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d={card.iconPath} />
              </svg>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{card.label}</div>
              {loading ? (
                <div style={{ height: 28, width: 48, background: 'var(--bg-raised)', borderRadius: 4, marginTop: 4, animation: 'pulse 2s infinite' }} />
              ) : (
                <div style={{ fontSize: 28, fontWeight: 700, color: card.color, lineHeight: 1.2 }}>{value}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
