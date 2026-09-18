import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend, ResponsiveContainer } from 'recharts'
import Panel from './Panel.jsx'

export default function HealthQuestionsChart({ data, loading }) {
  const chartData = (data || []).map((d) => ({ ...d, total: d.yes + d.no }))
  const hasData = chartData.some((d) => d.total > 0)

  return (
    <Panel title="Questionnaire sanitaire" subtitle="Réponses par question, tous documents Health confondus">
      {loading ? (
        <EmptyState text="Chargement…" />
      ) : !hasData ? (
        <EmptyState text="Aucun document Health ingéré pour l'instant." />
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} margin={{ left: -12 }}>
          <CartesianGrid vertical={false} stroke="var(--hairline)" />
          <XAxis dataKey="question" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--hairline-bright)" />
          <YAxis allowDecimals={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--hairline-bright)" />
          <Tooltip
            contentStyle={{ background: 'var(--ink-0)', border: '1px solid var(--hairline-bright)', borderRadius: 2, fontSize: 12.5 }}
            labelStyle={{ color: 'var(--text-primary)' }}
            cursor={{ fill: 'var(--ink-2)' }}
          />
          <Legend wrapperStyle={{ fontSize: 11.5, color: 'var(--text-muted)' }} />
          <Bar dataKey="no" name="NON" stackId="a" fill="var(--hairline-bright)" radius={[0, 0, 0, 0]} />
          <Bar dataKey="yes" name="OUI" stackId="a" fill="var(--danger)" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Panel>
  )
}

function EmptyState({ text }) {
  return (
    <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 13 }}>
      {text}
    </div>
  )
}
