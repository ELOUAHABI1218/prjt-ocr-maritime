const TONES = {
  neutral: { color: 'var(--text-primary)', glow: 'var(--hairline-bright)' },
  teal: { color: 'var(--accent-green)', glow: 'var(--accent-green-dim)' },
  danger: { color: 'var(--danger)', glow: 'var(--danger-dim)' },
  warning: { color: 'var(--warning)', glow: 'var(--warning-dim)' },
  ok: { color: 'var(--ok)', glow: 'var(--ok-dim)' },
}

function Kpi({ label, value, unit, tone = 'neutral', hint }) {
  const t = TONES[tone]
  return (
    <div
      style={{
        flex: '1 1 0',
        minWidth: 160,
        background: 'var(--ink-1)',
        border: '1px solid var(--hairline)',
        borderLeft: `2px solid ${t.color}`,
        borderRadius: 2,
        padding: '16px 18px',
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: 'var(--text-faint)',
          marginBottom: 10,
        }}
      >
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span
          style={{
            fontFamily: 'var(--font-data)',
            fontSize: 34,
            fontWeight: 600,
            lineHeight: 1,
            color: t.color,
          }}
        >
          {value}
        </span>
        {unit && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{unit}</span>}
      </div>
      {hint && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>{hint}</div>}
    </div>
  )
}

export default function KpiStrip({ summary, loading }) {
  if (loading || !summary) {
    return (
      <div style={{ display: 'flex', gap: 12 }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} style={{ flex: 1, height: 92, background: 'var(--ink-1)', border: '1px solid var(--hairline)', borderRadius: 2 }} />
        ))}
      </div>
    )
  }

  const alertsByType = summary.alerts_by_type || {}
  const dangerCount = alertsByType.DANGEROUS_CLASS || 0
  const healthCount = alertsByType.HEALTH_POSITIVE || 0
  const expiredCount = alertsByType.CERTIFICATE_EXPIRED || 0
  const outdatedCount = alertsByType.DOCUMENT_OUTDATED || 0
  const criticalTotal = dangerCount

  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      <Kpi label="Documents traités" value={summary.total_documents ?? 0} tone="neutral" />
      <Kpi label="Alertes ouvertes" value={summary.open_alerts ?? 0} tone={summary.open_alerts > 0 ? 'warning' : 'ok'} />
      <Kpi label="Cargo classé dangereux" value={criticalTotal} tone={criticalTotal > 0 ? 'danger' : 'ok'} hint="Classes 1 / 6.2 / 7" />
      <Kpi label="Alertes sanitaires" value={healthCount} tone={healthCount > 0 ? 'warning' : 'ok'} />
      <Kpi label="Certificats expirés" value={expiredCount} tone={expiredCount > 0 ? 'danger' : 'ok'} />
      <Kpi label="Documents obsolètes" value={outdatedCount} tone={outdatedCount > 0 ? 'warning' : 'ok'} hint="Référence &gt; 6 mois" />
    </div>
  )
}
