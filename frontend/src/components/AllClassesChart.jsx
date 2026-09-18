import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts'
import Panel from './Panel.jsx'

export default function AllClassesChart({ data, loading }) {
  const hasData = (data || []).some((d) => d.count > 0)

  return (
    <Panel title="Occurrences par classe" subtitle="Toutes classes IMDG confondues (DGD + DGM)">
      {loading ? (
        <EmptyState text="Chargement…" />
      ) : !hasData ? (
        <EmptyState text="Aucune classe détectée pour l'instant." />
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} margin={{ left: -12 }}>
            <CartesianGrid vertical={false} stroke="var(--hairline)" />
            <XAxis dataKey="class" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--hairline-bright)" />
            <YAxis allowDecimals={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--hairline-bright)" />
            <Tooltip
              contentStyle={{ background: 'var(--ink-0)', border: '1px solid var(--hairline-bright)', borderRadius: 2, fontSize: 12.5 }}
              labelStyle={{ color: 'var(--text-primary)' }}
              cursor={{ fill: 'var(--ink-2)' }}
              formatter={(value) => [value, 'Occurrences']}
              labelFormatter={(label) => `Classe ${label}`}
            />
            <Bar dataKey="count" radius={[2, 2, 0, 0]} fill="var(--accent-violet)" barSize={26} />
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
