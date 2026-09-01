import { useEffect, useState } from 'react';

interface SetupIssue {
  type: string;
  title: string;
  detail: string;
  fix: string;
}

interface SetupCheck {
  status: 'ok' | 'warning' | 'error';
  job_count: number;
  sp_identity: string | null;
  issues: SetupIssue[];
  warnings: SetupIssue[];
  info: { type: string; title: string; detail: string }[];
}

/**
 * Shown on the Dashboard when no jobs are visible or when the backend
 * detects a configuration problem (missing token, placeholder URL, etc.).
 * Gives the customer step-by-step guidance to fix their setup.
 */
export default function SetupBanner({ jobCount, loading }: { jobCount: number; loading: boolean }) {
  const [check, setCheck] = useState<SetupCheck | null>(null);
  const [expanded, setExpanded] = useState<number | null>(0);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Only fetch when jobs are 0 (after loading) or immediately on mount
    if (loading) return;
    fetch('/api/setup/check')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setCheck(data); })
      .catch(() => {});
  }, [loading, jobCount]);

  if (dismissed) return null;
  if (!check) return null;
  if (check.status === 'ok') return null;

  const items = [...check.issues, ...check.warnings];
  if (items.length === 0) return null;

  const isError = check.status === 'error';
  const borderColor = isError ? 'rgba(239,68,68,0.35)' : 'rgba(234,179,8,0.35)';
  const bgColor = isError ? 'rgba(239,68,68,0.06)' : 'rgba(234,179,8,0.06)';
  const titleColor = isError ? '#f87171' : '#fbbf24';
  const iconPath = isError
    ? 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'
    : 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z';

  return (
    <div style={{
      background: bgColor,
      border: `1px solid ${borderColor}`,
      borderRadius: 10,
      padding: 16,
      position: 'relative',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: items.length > 0 ? 12 : 0 }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={titleColor}
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 1 }}>
          <path d={iconPath} />
        </svg>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: titleColor }}>
            {isError ? 'Setup required — jobs cannot be loaded' : 'Setup warning — jobs may be incomplete'}
          </div>
          {check.sp_identity && (
            <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 2 }}>
              Authenticated as: <code style={{ color: 'var(--text-muted)', fontSize: 11 }}>{check.sp_identity}</code>
            </div>
          )}
        </div>
        <button
          onClick={() => setDismissed(true)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)', padding: 2 }}
          title="Dismiss"
        >
          ✕
        </button>
      </div>

      {/* Issues list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map((item, i) => (
          <div key={i} style={{
            background: 'rgba(0,0,0,0.2)',
            borderRadius: 8,
            overflow: 'hidden',
            border: '1px solid rgba(255,255,255,0.06)',
          }}>
            {/* Issue header — clickable to expand */}
            <button
              onClick={() => setExpanded(expanded === i ? null : i)}
              style={{
                width: '100%',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                textAlign: 'left',
                gap: 8,
              }}
            >
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' }}>
                {i + 1}. {item.title}
              </span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                style={{ transform: expanded === i ? 'rotate(180deg)' : 'none', flexShrink: 0 }}>
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>

            {expanded === i && (
              <div style={{ padding: '0 14px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                <p style={{ fontSize: 13, color: 'var(--text-dim)', margin: 0, lineHeight: 1.5 }}>
                  {item.detail}
                </p>
                <div style={{
                  background: 'rgba(0,0,0,0.3)',
                  borderRadius: 6,
                  padding: '10px 12px',
                  borderLeft: `3px solid ${titleColor}`,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: titleColor, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    How to fix
                  </div>
                  <pre style={{
                    fontSize: 12,
                    color: 'var(--text-muted)',
                    margin: 0,
                    whiteSpace: 'pre-wrap',
                    fontFamily: 'var(--font-mono, monospace)',
                    lineHeight: 1.6,
                  }}>
                    {item.fix}
                  </pre>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
