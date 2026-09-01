const BASE = '';

export interface JobRun {
  run_id: number;
  job_id: number;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number | null;
  state: string;
  result_state: string | null;
  trigger: string | null;
  run_name: string | null;
  run_page_url: string | null;
}

export interface JobInfo {
  job_id: number;
  name: string;
  creator: string | null;
  created_time: string | null;
  schedule: string | null;
  latest_run: JobRun | null;
  status: string;
}

export interface JobStats {
  job_id: number;
  job_name: string;
  total_runs: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  avg_duration_seconds: number;
  min_duration_seconds: number;
  max_duration_seconds: number;
  p95_duration_seconds: number;
  last_run_time: string | null;
}

export interface Anomaly {
  job_id: number;
  job_name: string;
  anomaly_type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  message: string;
  detected_at: string;
  current_value: number | null;
  expected_value: number | null;
}

export interface DashboardSummary {
  total_jobs: number;
  running: number;
  failed: number;
  success: number;
  pending: number;
  anomaly_count: number;
}

export interface RemediationStep {
  priority: number;
  action: string;
  detail: string;
  estimated_impact: 'High' | 'Medium' | 'Low';
  automated: boolean;
}

export interface JobAIInsight {
  job_id: number;
  job_name: string;
  health_score: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  summary: string;
  root_cause: string | null;
  recommendations: string[];
  remediation_steps: RemediationStep[];
  predicted_next_issue: string | null;
  generated_at: string;
}

export interface AlertConfig {
  enabled: boolean;
  recipients_count: number;
  min_severity: string;
  poll_interval_seconds: number;
  smtp_host: string;
  active_alert_count: number;
}

export interface WorkspaceAIInsight {
  overall_health_score: number;
  critical_jobs: string[];
  summary: string;
  top_risks: string[];
  recommendations: string[];
  generated_at: string;
}

export interface WorkspaceInfo {
  workspace_id: string;
  workspace_name: string;
  workspace_url: string;
  environment: 'production' | 'staging' | 'development' | 'unknown';
  cloud: 'aws' | 'azure' | 'gcp' | 'unknown';
}

export interface WorkspaceSummary {
  workspace_id: string;
  workspace_name: string;
  environment: string;
  total_jobs: number;
  running: number;
  failed: number;
  success: number;
  anomaly_count: number;
  error?: string | null;
}

export interface MultiWorkspaceSummary {
  workspaces: WorkspaceSummary[];
  totals: {
    total_jobs: number;
    running: number;
    failed: number;
    anomaly_count: number;
  };
}

export interface JobInfoWithWorkspace extends JobInfo {
  workspace_id: string;
  workspace_name: string;
  workspace_url: string;
  environment: string;
}

export interface AnomalyWithWorkspace extends Anomaly {
  workspace_id: string;
  workspace_name: string;
  workspace_url: string;
  environment: string;
}

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

function wsParam(workspaceId?: string) {
  return workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
}

export const api = {
  getJobs: (workspaceId?: string) => fetchJSON<{ jobs: JobInfo[] }>(`/api/jobs${wsParam(workspaceId)}`),
  getJobRuns: (jobId: number, workspaceId?: string) => fetchJSON<{ runs: JobRun[] }>(`/api/jobs/${jobId}/runs${wsParam(workspaceId)}`),
  getJobStats: (jobId: number, workspaceId?: string) => fetchJSON<JobStats>(`/api/jobs/${jobId}/stats${wsParam(workspaceId)}`),
  getAnomalies: (workspaceId?: string) => fetchJSON<{ anomalies: Anomaly[] }>(`/api/anomalies${wsParam(workspaceId)}`),
  getDashboardSummary: () => fetchJSON<DashboardSummary>('/api/dashboard/summary'),
  getHealth: () => fetchJSON<{ status: string }>('/api/health'),

  // Multi-workspace endpoints
  getWorkspaces: () => fetchJSON<{ workspaces: WorkspaceInfo[] }>('/api/workspaces'),
  getMultiSummary: () => fetchJSON<MultiWorkspaceSummary>('/api/multi/summary'),
  getMultiAnomalies: () => fetchJSON<{ anomalies: AnomalyWithWorkspace[] }>('/api/multi/anomalies'),
  getMultiJobs: () => fetchJSON<{ jobs: JobInfoWithWorkspace[] }>('/api/multi/jobs'),
  getWorkspaceJobs: (wsId: string) => fetchJSON<{ jobs: JobInfo[] }>(`/api/workspaces/${wsId}/jobs`),
  getWorkspaceAnomalies: (wsId: string) => fetchJSON<{ anomalies: Anomaly[] }>(`/api/workspaces/${wsId}/anomalies`),
  getWorkspaceSummary: (wsId: string) => fetchJSON<DashboardSummary>(`/api/workspaces/${wsId}/summary`),

  // Alert endpoints
  getAlertConfig: () => fetchJSON<AlertConfig>('/api/alerts/config'),
  getActiveAlerts: () => fetchJSON<{ alerts: Array<{ workspace_id: string; job_id: number; anomaly_type: string; first_seen: string }> }>('/api/alerts/active'),
  sendTestAlert: () => fetchJSON<{ success: boolean; message?: string }>('/api/alerts/test'),
};
