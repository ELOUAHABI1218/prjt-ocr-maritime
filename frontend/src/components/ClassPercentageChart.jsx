import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, LabelList, ResponsiveContainer } from 'recharts'
import Panel from './Panel.jsx'

const API_BASE = 'http://127.0.0.1:8000'

const BAR_COLORS = [
  'var(--accent-blue)', 'var(--accent-navy)', 'var(--accent-steel)',
  '#5aa9e6', '#0d3b66', '#a3c9e8', '#1e5f8c', '#3d7ab5', '#082747', '#4a7fb5',
]

export default function ClassPercentageChart({ documents, loading }) {
  const cargoDocuments = (documents || []).filter((d) => d.document_type === 'DGD' || d.document_type === 'DGM')
  const [selectedId, setSelectedId] = useState(null)
  const [breakdown, setBreakdown] = useState(null)
  const [fetching, setFetching] = useState(false)

  useEffect(() => {
    if (!selectedId && cargoDocuments.length > 0) {
      setSelectedId(cargoDocuments[0].document_id)
    }
  }, [cargoDocuments, selectedId])

  useEffect(() => {
    if (!selectedId) return
    setFetching(true)
    fetch(`${API_BASE}/documents/${selectedId}/class-breakdown`)
      .then((r) => r.json())
      .then(setBreakdown)
      .finally(() => setFetching(false))
  }, [selectedId])

  const selectedDoc = cargoDocuments.find((d) => d.document_id === selectedId)
  const chartData = breakdown ? [...breakdown.breakdown].sort((a, b) => b.percentage - a.percentage) : []
  const chartHeight = Math.max(180, chartData.length * 32)

  return (
    <Panel
      title="Répartition des classes par fichier"
      subtitle="Pourcentage de chaque classe IMDG dans un DGD ou DGM précis"
      action={
        cargoDocuments.length > 0 && (
          <select
            value={selectedId || ''}
            onChange={(e) => setSelectedId(Number(e.target.value))}
            style={{
              background: 'var(--ink-0)',
              border: '1px solid var(--hairline)',
              color: 'var(--text-primary)',
              fontSize: 12,
              padding: '5px 8px',
              borderRadius: 2,
              maxWidth: 180,
            }}
          >
            {cargoDocuments.map((d) => (
              <option key={d.document_id} value={d.document_id} style={{ background: 'var(--ink-1)', color: 'var(--text-primary)' }}>
                {d.document_type} — {d.ship_name || d.source_file}
              </option>
            ))}
          </select>
        )
      }
    >
      {loading || fetching ? (
        <EmptyState text="Chargement…" height={220} />
      ) : cargoDocuments.length === 0 ? (
        <EmptyState text="Aucun document DGD ou DGM ingéré pour l'instant." height={220} />
      ) : !breakdown || breakdown.total === 0 ? (
        <EmptyState text="Aucune classe renseignée dans ce document." height={220} />
      ) : (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 40 }}>
            <XAxis type="number" hide domain={[0, 100]} />
            <YAxis
              type="category"
              dataKey="class"
              width={130}
              tick={{ fill: 'var(--text-muted)', fontSize: 11.5 }}
              stroke="var(--hairline-bright)"
            />
            <Tooltip
              contentStyle={{ background: 'var(--ink-0)', border: '1px solid var(--hairline-bright)', borderRadius: 2, fontSize: 12.5 }}
              labelStyle={{ color: 'var(--text-primary)' }}
              formatter={(value, _name, item) => [`${value}% (${item.payload.count} ligne(s))`, 'Part']}
            />
            <Bar dataKey="percentage" radius={[0, 3, 3, 0]} barSize={18}>
              {chartData.map((d, i) => (
                <Cell
                  key={d.class}
                  fill={d.class.startsWith('Autre') ? 'var(--hairline-bright)' : BAR_COLORS[i % BAR_COLORS.length]}
                />
              ))}
              <LabelList
                dataKey="percentage"
                position="right"
                formatter={(v) => `${v}%`}
                style={{ fill: 'var(--text-primary)', fontSize: 11.5, fontFamily: 'var(--font-data)' }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
      {selectedDoc && breakdown && breakdown.total > 0 && (
        <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--text-faint)' }}>
          {breakdown.total} ligne(s) de marchandise dans {selectedDoc.source_file}
          {chartData.some((d) => d.class.startsWith('Autre')) && (
            <> · certaines lignes n'ont pas pu être rattachées à une classe claire (bruit d'extraction OCR sur ce fichier)</>
          )}
        </div>
      )}
    </Panel>
  )
}

function EmptyState({ text, height }) {
  return (
    <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 13 }}>
      {text}
    </div>
  )
}
