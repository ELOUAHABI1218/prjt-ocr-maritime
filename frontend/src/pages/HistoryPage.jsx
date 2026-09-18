import { useEffect, useState } from 'react'
import { PageHeader } from './DashboardPage.jsx'
import Panel from '../components/Panel.jsx'

const API_BASE = 'http://127.0.0.1:8000'

const TYPE_COLOR = { DGD: 'var(--accent-blue)', DGM: 'var(--accent-navy)', HEALTH: 'var(--accent-steel)' }
const SEVERITY_COLOR = { CRITICAL: 'var(--danger)', HIGH: 'var(--warning)', MEDIUM: 'var(--accent-blue)', LOW: 'var(--text-muted)' }

export default function HistoryPage() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/history`)
      .then((r) => r.json())
      .then(setRows)
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div>
      <PageHeader title="Historique" subtitle="Documents océrisés, temps de traitement et alertes générées" />

      <div style={{ marginTop: 20 }}>
        <Panel title="Journal complet" subtitle={rows ? `${rows.length} document(s)` : undefined}>
          {error ? (
            <div style={{ color: 'var(--danger)', fontSize: 13 }}>Impossible de charger l'historique : {error}</div>
          ) : !rows ? (
            <div style={{ color: 'var(--text-faint)', fontSize: 13, padding: '20px 0' }}>Chargement…</div>
          ) : rows.length === 0 ? (
            <div style={{ color: 'var(--text-faint)', fontSize: 13, padding: '20px 0' }}>Aucun document ingéré pour l'instant.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {rows.map((r) => (
                <HistoryRow key={r.document_id} row={r} />
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}

function HistoryRow({ row }) {
  return (
    <div style={{ border: '1px solid var(--hairline)', borderRadius: 3, padding: '12px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span
            style={{
              fontFamily: 'var(--font-data)',
              fontSize: 11.5,
              color: TYPE_COLOR[row.document_type] || 'var(--text-muted)',
              border: `1px solid ${TYPE_COLOR[row.document_type] || 'var(--hairline)'}`,
              borderRadius: 2,
              padding: '2px 7px',
            }}
          >
            {row.document_type}
          </span>
          <span style={{ fontSize: 13.5, color: 'var(--text-primary)' }}>{row.ship_name || '—'}</span>
          <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>{row.source_file}</span>
        </div>

        <div style={{ display: 'flex', gap: 16, fontFamily: 'var(--font-data)', fontSize: 11.5, color: 'var(--text-muted)' }}>
          <span>Ingéré : {new Date(row.loaded_at).toLocaleString('fr-FR')}</span>
          <span>
            Océrisation :{' '}
            {row.ocr_seconds != null ? <strong style={{ color: 'var(--text-primary)' }}>{row.ocr_seconds}s</strong> : '—'}
          </span>
        </div>
      </div>

      {row.alerts.length > 0 && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 5 }}>
          {row.alerts.map((a) => (
            <div
              key={a.alert_id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 12,
                padding: '5px 8px',
                borderLeft: `2px solid ${SEVERITY_COLOR[a.severity] || 'var(--text-muted)'}`,
                background: 'var(--ink-0)',
                borderRadius: 2,
                opacity: a.acknowledged ? 0.55 : 1,
              }}
            >
              <span style={{ color: SEVERITY_COLOR[a.severity] || 'var(--text-muted)', fontFamily: 'var(--font-data)', fontSize: 10.5 }}>
                {a.severity}
              </span>
              <span style={{ color: 'var(--text-primary)' }}>{a.message}</span>
              {a.acknowledged && <span style={{ marginLeft: 'auto', fontSize: 10.5, color: 'var(--text-faint)' }}>résolue</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
