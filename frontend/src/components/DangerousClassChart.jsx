import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell, ResponsiveContainer } from 'recharts'
import Panel from './Panel.jsx'

const CLASS_LABELS = {
  '1': 'Classe 1 — Explosifs',
  '6.2': 'Classe 6.2 — Infectieux',
  '7': 'Classe 7 — Radioactif',
}

const CLASS_COLORS = {
  '1': 'var(--danger)',
  '6.2': 'var(--warning)',
  '7': 'var(--accent-violet)',
}

export default function DangerousClassChart({ data, loading }) {
  const chartData = (data || []).map((d) => ({
    ...d,
    label: CLASS_LABELS[d.class] || `Classe ${d.class}`,
  }))

  return (
    <Panel title="Cargo dangereux détecté" subtitle="Occurrences par classe IMDG (DGD + DGM)">
      {loading ? (
        <EmptyState text="Chargement…" />
      ) : chartData.every((d) => d.count === 0) ? (
        <EmptyState text="Aucun cargo de classe 1 / 6.2 / 7 détecté actuellement." />
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16 }}>
          <CartesianGrid horizontal={false} stroke="var(--hairline)" />
          <XAxis type="number" allowDecimals={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} stroke="var(--hairline-bright)" />
          <YAxis
            type="category"
            dataKey="label"
            width={150}
            tick={{ fill: 'var(--text-muted)', fontSize: 11.5 }}
            stroke="var(--hairline-bright)"
          />
          <Tooltip
            contentStyle={{ background: 'var(--ink-0)', border: '1px solid var(--hairline-bright)', borderRadius: 2, fontSize: 12.5 }}
            labelStyle={{ color: 'var(--text-primary)' }}
            cursor={{ fill: 'var(--ink-2)' }}
          />
          <Bar dataKey="count" radius={[0, 2, 2, 0]} barSize={22}>
            {chartData.map((d) => (
              <Cell key={d.class} fill={CLASS_COLORS[d.class] || 'var(--accent-green)'} />
            ))}
          </Bar>
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
