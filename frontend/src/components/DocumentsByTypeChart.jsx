import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import Panel from './Panel.jsx'

const TYPE_LABEL = { DGD: 'DGD', DGM: 'DGM', HEALTH: 'Health' }
const TYPE_COLOR = {
  DGD: 'var(--accent-green)',
  DGM: 'var(--accent-navy)',
  HEALTH: 'var(--accent-steel)',
}

export default function DocumentsByTypeChart({ documentsByType, loading }) {
  const data = Object.entries(documentsByType || {}).map(([type, count]) => ({
    type,
    name: TYPE_LABEL[type] || type,
    value: count,
  }))
  const total = data.reduce((sum, d) => sum + d.value, 0)

  return (
    <Panel title="Documents par type" subtitle="Répartition DGD / DGM / Health">
      {loading ? (
        <EmptyState text="Chargement…" />
      ) : total === 0 ? (
        <EmptyState text="Aucun document ingéré pour l'instant." />
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="42%"
            cy="50%"
            innerRadius={45}
            outerRadius={80}
            paddingAngle={3}
          >
            {data.map((d) => (
              <Cell key={d.type} fill={TYPE_COLOR[d.type] || 'var(--text-muted)'} stroke="var(--ink-1)" strokeWidth={2} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: 'var(--ink-0)', border: '1px solid var(--hairline-bright)', borderRadius: 2, fontSize: 12.5 }}
            labelStyle={{ color: 'var(--text-primary)' }}
          />
          <Legend
            layout="vertical"
            align="right"
            verticalAlign="middle"
            wrapperStyle={{ fontSize: 12, color: 'var(--text-muted)' }}
          />
          </PieChart>
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
