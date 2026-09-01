/**
 * AIInsightsPanel - Displays Claude AI-generated analysis for a job or workspace.
 */

import { useState } from 'react';
import type { JobAIInsight, WorkspaceAIInsight, RemediationStep } from '../api/client';

interface HealthGaugeProps {
  score: number;
}

function HealthGauge({ score }: HealthGaugeProps) {
  const color =
    score >= 80 ? '#22c55e' :
    score >= 60 ? '#eab308' :
    score >= 40 ? '#f97316' :
    '#ef4444';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <div style={{
        width: 72,
        height: 72,
        borderRadius: '50%',
        background: `conic-gradient(${color} ${score * 3.6}deg, #2a2a2a ${score * 3.6}deg)`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
      }}>
        <div style={{
          width: 56,
          height: 56,
          borderRadius: '50%',
          background: '#1a1a1a',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 16,
          fontWeight: 700,
          color,
        }}>
          {score}
        </div>
      </div>
      <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Health Score</span>
    </div>
  );
}

const IMPACT_COLORS: Record<string, string> = {
  High: '#ef4444',
  Medium: '#eab308',
  Low: '#3b82f6',
};

function RemediationStepsPanel({ steps }: { steps: RemediationStep[] }) {
  if (!steps || steps.length === 0) return null;

  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Remediation Steps
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {steps.map((step, i) => {
          const impactColor = IMPACT_COLORS[step.estimated_impact] || '#6b7280';
          return (
            <div key={i} style={{
              background: '#1a1a1a',
              border: '1px solid #2a2a2a',
              borderLeft: `3px solid ${impactColor}`,
              borderRadius: 8,
              padding: '12px 14px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                {/* Priority badge */}
                <span style={{
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  background: 'rgba(99, 102, 241, 0.2)',
                  color: '#818cf8',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 11,
                  fontWeight: 700,
                  flexShrink: 0,
                }}>
                  {step.priority}
                </span>
                {/* Action title */}
                <span style={{ fontSize: 13, fontWeight: 600, color: 'white', flex: 1 }}>
                  {step.action}
                </span>
                {/* Impact badge */}
                <span style={{
                  background: impactColor + '18',
                  color: impactColor,
                  border: `1px solid ${impactColor}33`,
                  borderRadius: 4,
                  padding: '1px 8px',
                  fontSize: 10,
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  flexShrink: 0,
                }}>
                  {step.estimated_impact} Impact
                </span>
                {/* Automated chip */}
                {step.automated && (
                  <span style={{
                    background: 'rgba(34, 197, 94, 0.15)',
                    color: '#4ade80',
                    border: '1px solid rgba(34, 197, 94, 0.3)',
                    borderRadius: 4,
                    padding: '1px 8px',
                    fontSize: 10,
                    fontWeight: 600,
                    flexShrink: 0,
                  }}>
                    Automated
                  </span>
                )}
              </div>
              <p style={{ fontSize: 12, color: '#9ca3af', lineHeight: 1.6, margin: 0, paddingLeft: 30 }}>
                {step.detail}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const RISK_COLORS: Record<string, string> = {
  low: '#22c55e',
  medium: '#eab308',
  high: '#f97316',
  critical: '#ef4444',
};

interface JobAIInsightsPanelProps {
  jobId: number;
  jobName: string;
  workspaceId?: string;
}

export function JobAIInsightsPanel({ jobId, jobName, workspaceId }: JobAIInsightsPanelProps) {
  const [insight, setInsight] = useState<JobAIInsight | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runAnalysis() {
    setLoading(true);
    setError(null);
    setInsight(null);
    try {
      const wsParam = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
      const res = await fetch(`/api/ai/jobs/${jobId}/analyze${wsParam}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: JobAIInsight = await res.json();
      setInsight(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: 20,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* AI spark icon */}
          <div style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 16,
          }}>✦</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'white' }}>AI Analysis</div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>Powered by Claude (Databricks Foundation Models)</div>
          </div>
        </div>
        <button
          onClick={runAnalysis}
          disabled={loading}
          style={{
            background: loading ? '#2a2a2a' : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            color: 'white',
            border: 'none',
            borderRadius: 6,
            padding: '7px 16px',
            fontSize: 13,
            fontWeight: 500,
            cursor: loading ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          {loading ? (
            <>
              <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>⟳</span>
              Analysing…
            </>
          ) : (
            <>✦ {insight ? 'Re-analyse' : 'Run AI Analysis'}</>
          )}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 6,
          padding: '10px 14px',
          fontSize: 13,
          color: '#f87171',
        }}>
          {error}
        </div>
      )}

      {/* Loading placeholder */}
      {loading && !insight && (
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-dim)', fontSize: 13 }}>
          Claude is analysing <strong style={{ color: 'white' }}>{jobName}</strong>…<br />
          <span style={{ fontSize: 11, opacity: 0.7 }}>This usually takes 5–15 seconds</span>
        </div>
      )}

      {/* Insight */}
      {insight && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Score + Risk + Summary */}
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
            <HealthGauge score={insight.health_score} />
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{
                  background: RISK_COLORS[insight.risk_level] + '22',
                  color: RISK_COLORS[insight.risk_level],
                  border: `1px solid ${RISK_COLORS[insight.risk_level]}44`,
                  borderRadius: 4,
                  padding: '2px 8px',
                  fontSize: 11,
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}>
                  {insight.risk_level} risk
                </span>
              </div>
              <p style={{ fontSize: 13, color: '#d1d5db', lineHeight: 1.6, margin: 0 }}>
                {insight.summary}
              </p>
            </div>
          </div>

          {/* Root Cause */}
          {insight.root_cause && (
            <div style={{
              background: 'rgba(239,68,68,0.06)',
              border: '1px solid rgba(239,68,68,0.2)',
              borderRadius: 6,
              padding: '10px 14px',
            }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#f87171', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Root Cause
              </div>
              <p style={{ fontSize: 13, color: '#fca5a5', margin: 0, lineHeight: 1.6 }}>
                {insight.root_cause}
              </p>
            </div>
          )}

          {/* Recommendations */}
          {insight.recommendations.length > 0 && (
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Recommendations
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {insight.recommendations.map((rec, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, fontSize: 13, color: '#d1d5db', lineHeight: 1.5 }}>
                    <span style={{ color: '#6366f1', fontWeight: 700, flexShrink: 0 }}>{i + 1}.</span>
                    <span>{rec}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Remediation Steps */}
          {insight.remediation_steps && insight.remediation_steps.length > 0 && (
            <RemediationStepsPanel steps={insight.remediation_steps} />
          )}

          {/* Predicted Next Issue */}
          {insight.predicted_next_issue && (
            <div style={{
              background: 'rgba(245,158,11,0.06)',
              border: '1px solid rgba(245,158,11,0.2)',
              borderRadius: 6,
              padding: '10px 14px',
            }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#fbbf24', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                ⚡ Predictive Alert
              </div>
              <p style={{ fontSize: 13, color: '#fde68a', margin: 0, lineHeight: 1.6 }}>
                {insight.predicted_next_issue}
              </p>
            </div>
          )}

          {/* Footer */}
          <div style={{ fontSize: 11, color: 'var(--text-dim)', borderTop: '1px solid var(--border)', paddingTop: 8 }}>
            Analysis generated at {new Date(insight.generated_at).toLocaleTimeString()} · Model: Claude Sonnet 4.5
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !insight && !error && (
        <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--text-dim)', fontSize: 13 }}>
          Click <strong style={{ color: 'white' }}>Run AI Analysis</strong> to get Claude's assessment of this job —<br />
          health score, root cause analysis, and actionable recommendations.
        </div>
      )}
    </div>
  );
}


interface WorkspaceAIInsightsPanelProps {
  compact?: boolean;
}

export function WorkspaceAIInsightsPanel({ compact }: WorkspaceAIInsightsPanelProps) {
  const [insight, setInsight] = useState<WorkspaceAIInsight | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runAnalysis() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/ai/workspace/analyze');
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: WorkspaceAIInsight = await res.json();
      setInsight(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid rgba(99,102,241,0.3)',
      borderRadius: 10,
      padding: compact ? 16 : 20,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: insight ? 16 : 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 14,
          }}>✦</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'white' }}>Workspace AI Health Check</div>
            {!compact && <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>Claude analyses all jobs and anomalies</div>}
          </div>
        </div>
        <button
          onClick={runAnalysis}
          disabled={loading}
          style={{
            background: loading ? '#2a2a2a' : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            color: 'white',
            border: 'none',
            borderRadius: 6,
            padding: '6px 14px',
            fontSize: 12,
            fontWeight: 500,
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? '⟳ Analysing…' : insight ? '↺ Refresh' : 'Analyse'}
        </button>
      </div>

      {error && (
        <div style={{ fontSize: 12, color: '#f87171', marginTop: 8 }}>{error}</div>
      )}

      {loading && (
        <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 12, textAlign: 'center', padding: '16px 0' }}>
          Claude is reviewing your entire workspace…
        </div>
      )}

      {insight && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Score + Summary */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <HealthGauge score={insight.overall_health_score} />
            <p style={{ fontSize: 13, color: '#d1d5db', lineHeight: 1.6, margin: 0, flex: 1 }}>
              {insight.summary}
            </p>
          </div>

          {/* Critical Jobs */}
          {insight.critical_jobs.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#f87171', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Needs Attention
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {insight.critical_jobs.map((name, i) => (
                  <span key={i} style={{
                    background: 'rgba(239,68,68,0.1)',
                    color: '#fca5a5',
                    border: '1px solid rgba(239,68,68,0.2)',
                    borderRadius: 4,
                    padding: '2px 8px',
                    fontSize: 11,
                  }}>
                    {name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Top Risks */}
          {insight.top_risks.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Top Risks
              </div>
              {insight.top_risks.map((risk, i) => (
                <div key={i} style={{ fontSize: 12, color: '#fde68a', marginBottom: 3 }}>⚠ {risk}</div>
              ))}
            </div>
          )}

          {/* Recommendations */}
          {insight.recommendations.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Recommendations
              </div>
              {insight.recommendations.map((rec, i) => (
                <div key={i} style={{ fontSize: 12, color: '#d1d5db', marginBottom: 4, display: 'flex', gap: 6 }}>
                  <span style={{ color: '#6366f1', fontWeight: 700 }}>{i + 1}.</span>
                  <span>{rec}</span>
                </div>
              ))}
            </div>
          )}

          <div style={{ fontSize: 10, color: 'var(--text-dim)', borderTop: '1px solid var(--border)', paddingTop: 6 }}>
            {new Date(insight.generated_at).toLocaleTimeString()}
          </div>
        </div>
      )}
    </div>
  );
}
