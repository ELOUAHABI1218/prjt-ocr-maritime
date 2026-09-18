import { useMemo } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts'
import Panel from './Panel.jsx'

const SEVERITY_COLOR = { CRITICAL: 'var(--danger)', HIGH: 'var(--warning)', MEDIUM: 'var(--accent-blue)', LOW: 'var(--text-muted)' }

export default function AlertsTimeline({ data, alerts, loading }) {
  const chartData = (data || []).map((d) => ({
    ...d,
    label: d.date.slice(5), // MM-DD
  }))
  const hasSignal = chartData.some((d) => d.count > 0)

  // Regroupe les alertes par jour (clé YYYY-MM-DD), pour afficher au survol
  // de quel(s) document(s) elles viennent — pas juste le total.
  const alertsByDay = useMemo(() => {
    const map = {}
    for (const a of alerts || []) {
      const day = (a.created_at || '').slice(0, 10)
      if (!day) continue
      if (!map[day]) map[day] = []
      map[day].push(a)
    }
    return map
  }, [alerts])

  return (
    <Panel title="Activité des alertes" subtitle="Alertes générées par jour — survole un point pour voir leur origine">
      {loading ? (
        <EmptyState text="Chargement…" />
      ) : !hasSignal ? (
        <EmptyState text="Aucune alerte générée sur la période." />
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={chartData} margin={{ left: -20, right: 8 }}>
          <defs>
            <linearGradient id="alertGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent-blue)" stopOpacity={0.5} />
              <stop offset="100%" stopColor="var(--accent-blue)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--hairline)" />
          <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 10.5 }} stroke="var(--hairline-bright)" interval={4} />
          <YAxis allowDecimals={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--hairline-bright)" />
          <Tooltip
            content={<SourceTooltip alertsByDay={alertsByDay} />}
            cursor={{ stroke: 'var(--accent-blue)', strokeWidth: 1 }}
          />
          <Area type="monotone" dataKey="count" name="Alertes" stroke="var(--accent-blue)" strokeWidth={2} fill="url(#alertGradient)" />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Panel>
  )
}

function SourceTooltip({ active, payload, alertsByDay }) {
  if (!active || !payload || !payload.length) return null
  const point = payload[0].payload
  const dayAlerts = alertsByDay[point.date] || []

  return (
    <div
      style={{
        background: 'var(--ink-0)',
        border: '1px solid var(--hairline-bright)',
        borderRadius: 2,
        padding: '10px 12px',
        fontSize: 12,
        maxWidth: 280,
      }}
    >
      <div style={{ color: 'var(--text-primary)', fontWeight: 600, marginBottom: dayAlerts.length ? 6 : 0 }}>
        {point.date} — {point.count} alerte{point.count !== 1 ? 's' : ''}
      </div>
      {dayAlerts.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {dayAlerts.slice(0, 6).map((a) => (
            <div key={a.alert_id} style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: SEVERITY_COLOR[a.severity] || 'var(--text-muted)', flexShrink: 0 }} />
              <span style={{ color: 'var(--text-muted)' }}>
                <strong style={{ color: 'var(--text-primary)' }}>{a.ship_name || a.source_file || `Doc #${a.document_id}`}</strong>
                {' '}({a.document_type || '?'})
              </span>
            </div>
          ))}
          {dayAlerts.length > 6 && (
            <div style={{ color: 'var(--text-faint)', fontSize: 11 }}>+ {dayAlerts.length - 6} autre(s)</div>
          )}
        </div>
      )}
    </div>
  )
}

function EmptyState({ text }) {
  return (
    <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 13 }}>
      {text}
    </div>
  )
}
