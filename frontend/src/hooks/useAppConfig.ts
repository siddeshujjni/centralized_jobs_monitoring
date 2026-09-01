import { useEffect, useState } from 'react';

export interface AppConfig {
  company_name: string;
  app_name: string;
  lakebase_enabled?: boolean;
  /** AI analysis is optional and disabled by default (ENABLE_AI_ANALYSIS). */
  ai_enabled?: boolean;
}

const DEFAULT_CONFIG: AppConfig = {
  company_name: 'Databricks',
  app_name: 'Databricks Jobs Monitor',
  lakebase_enabled: false,
  ai_enabled: false,
};

/**
 * Fetches non-sensitive app configuration from /api/config, including whether
 * the optional AI analysis feature is enabled. Falls back to safe defaults.
 */
export function useAppConfig(): AppConfig {
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  useEffect(() => {
    fetch('/api/config')
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) setConfig({ ...DEFAULT_CONFIG, ...data }); })
      .catch(() => {});
  }, []);
  return config;
}
