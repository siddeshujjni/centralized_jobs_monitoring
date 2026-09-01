import { ReactNode, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import type { AlertConfig } from '../api/client';
import { useAppConfig } from '../hooks/useAppConfig';

interface SyncStatus {
  workspace_id: string;
  last_synced_at: string | null;
  job_count: number;
  run_count: number;
  error: string | null;
}

function LakebaseWidget() {
  const [status, setStatus] = useState<{ enabled: boolean; workspaces: SyncStatus[] } | null>(null);

  useEffect(() => {
    const load = () => {
      fetch('/api/cache/status')
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data) setStatus(data); })
        .catch(() => {});
    };
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  if (!status?.enabled) return null;

  const allSynced = status.workspaces.length > 0 && status.workspaces.every(w => w.last_synced_at && !w.error);
  const latestSync = status.workspaces.reduce<string | null>((latest, w) => {
    if (!w.last_synced_at) return latest;
    return !latest || w.last_synced_at > latest ? w.last_synced_at : latest;
  }, null);

  const ageSeconds = latestSync
    ? Math.round((Date.now() - new Date(latestSync).getTime()) / 1000)
    : null;

  const ageLabel = ageSeconds === null
    ? 'syncing…'
    : ageSeconds < 60
    ? `${ageSeconds}s ago`
    : `${Math.round(ageSeconds / 60)}m ago`;

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '8px 12px',
      margin: '0 12px 8px',
      background: allSynced ? 'rgba(99, 102, 241, 0.08)' : 'rgba(107, 114, 128, 0.08)',
      border: `1px solid ${allSynced ? 'rgba(99, 102, 241, 0.25)' : 'rgba(107, 114, 128, 0.2)'}`,
      borderRadius: 8,
      fontSize: 12,
    }}>
      {/* Lakebase icon — cylinder */}
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={allSynced ? '#818cf8' : '#6b7280'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
        <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
      </svg>
      <span style={{ color: allSynced ? '#a5b4fc' : '#9ca3af', fontWeight: 500 }}>
        Lakebase
      </span>
      <span style={{ marginLeft: 'auto', color: allSynced ? '#6366f1' : '#6b7280', fontSize: 10 }}>
        {ageLabel}
      </span>
    </div>
  );
}

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4' },
  { path: '/multi', label: 'Multi-Workspace', icon: 'M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z' },
  { path: '/anomalies', label: 'Anomalies', icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z' },
];

function NavIcon({ d }: { d: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

function AlertStatusWidget() {
  const [config, setConfig] = useState<AlertConfig | null>(null);

  useEffect(() => {
    fetch('/api/alerts/config')
      .then(res => res.ok ? res.json() : null)
      .then(data => { if (data) setConfig(data); })
      .catch(() => {});
  }, []);

  if (!config) return null;

  const isOn = config.enabled;

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '8px 12px',
      margin: '0 12px 8px',
      background: isOn ? 'rgba(34, 197, 94, 0.08)' : 'rgba(107, 114, 128, 0.08)',
      border: `1px solid ${isOn ? 'rgba(34, 197, 94, 0.2)' : 'rgba(107, 114, 128, 0.2)'}`,
      borderRadius: 8,
      fontSize: 12,
    }}>
      <span style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: isOn ? '#22c55e' : '#6b7280',
        flexShrink: 0,
        boxShadow: isOn ? '0 0 6px rgba(34, 197, 94, 0.5)' : 'none',
      }} />
      <span style={{ color: isOn ? '#86efac' : '#9ca3af', fontWeight: 500 }}>
        {isOn ? 'Alerts On' : 'Alerts Off'}
      </span>
      {isOn && config.active_alert_count > 0 && (
        <span style={{
          marginLeft: 'auto',
          background: 'rgba(239, 68, 68, 0.2)',
          color: '#f87171',
          borderRadius: 10,
          padding: '1px 7px',
          fontSize: 10,
          fontWeight: 700,
        }}>
          {config.active_alert_count}
        </span>
      )}
    </div>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const appConfig = useAppConfig();

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <aside style={{
        width: 256,
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
      }}>
        {/* Brand */}
        <div style={{ padding: 20, borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              background: 'linear-gradient(135deg, #E31837, #FF3621)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
            </div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: 'white', lineHeight: 1.2 }}>{appConfig.company_name}</div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.2 }}>Jobs Monitor</div>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: 12 }}>
          {NAV_ITEMS.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '10px 12px',
                  borderRadius: 8,
                  fontSize: 14,
                  fontWeight: 500,
                  marginBottom: 4,
                  color: isActive ? 'var(--brand-red)' : 'var(--text-dim)',
                  background: isActive ? 'rgba(227, 24, 55, 0.1)' : 'transparent',
                  transition: 'all 0.15s',
                }}
              >
                <NavIcon d={item.icon} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Alert Status */}
        <AlertStatusWidget />

        {/* Lakebase cache status */}
        <LakebaseWidget />

        {/* Footer */}
        <div style={{ padding: 16, borderTop: '1px solid var(--border)', textAlign: 'center' }}>
          <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>Powered by Databricks</span>
        </div>
      </aside>

      {/* Main content */}
      <main style={{ flex: 1, overflow: 'auto' }}>
        <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>{children}</div>
      </main>
    </div>
  );
}
