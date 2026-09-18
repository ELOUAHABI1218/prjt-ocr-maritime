import { useState } from 'react'
import Panel from './Panel.jsx'

const SEVERITY_STYLE = {
  CRITICAL: { color: 'var(--danger)', label: 'Critique' },
  HIGH: { color: 'var(--warning)', label: 'Élevée' },
  MEDIUM: { color: 'var(--accent-green)', label: 'Moyenne' },
  LOW: { color: 'var(--text-muted)', label: 'Faible' },
}

const TYPE_LABEL = {
  DANGEROUS_CLASS: 'Cargo dangereux',
  HEALTH_POSITIVE: 'Réponse sanitaire',
  CERTIFICATE_EXPIRED: 'Certificat expiré',
  DOCUMENT_OUTDATED: 'Document obsolète',
}

const DOC_TYPE_COLOR = {
  DGD: 'var(--accent-green)',
  DGM: 'var(--accent-navy)',
  HEALTH: 'var(--accent-steel)',
}

export default function AlertsTable({ alerts, loading, onResolve, error }) {
  const [filter, setFilter] = useState('OPEN')

  const filtered = (alerts || []).filter((a) => {
    if (filter === 'OPEN') return !a.acknowledged
    if (filter === 'RESOLVED') return a.acknowledged
    return true
  })

  return (
    <Panel
      title="Journal des alertes"
      subtitle={`${filtered.length} entrée${filtered.length !== 1 ? 's' : ''}`}
      action={
        <div style={{ display: 'flex', gap: 4 }}>
          {[
            ['OPEN', 'Ouvertes'],
            ['RESOLVED', 'Résolues'],
            ['ALL', 'Toutes'],
          ].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              style={{
                background: filter === key ? 'var(--ink-2)' : 'transparent',
                border: '1px solid var(--hairline)',
                color: filter === key ? 'var(--text-primary)' : 'var(--text-muted)',
                fontSize: 11.5,
                padding: '5px 10px',
                borderRadius: 2,
              }}
            >
              {label}
            </button>
          ))}
        </div>
      }
    >
      {error && (
        <div style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 12 }}>
          Impossible de charger les alertes — vérifie que l'API tourne sur localhost:8000. ({error})
        </div>
      )}

      {loading ? (
        <div style={{ color: 'var(--text-faint)', fontSize: 13, padding: '20px 0' }}>Chargement…</div>
      ) : filtered.length === 0 ? (
        <div style={{ color: 'var(--text-faint)', fontSize: 13, padding: '20px 0' }}>
          {filter === 'OPEN' ? 'Aucune alerte ouverte. Tout est en ordre.' : 'Aucune entrée dans ce filtre.'}
        </div>
      ) : (
        <div style={{ maxHeight: 320, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--text-faint)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                <th style={th}>Sévérité</th>
                <th style={th}>Document</th>
                <th style={th}>Type</th>
                <th style={th}>Message</th>
                <th style={th}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => {
                const sev = SEVERITY_STYLE[a.severity] || SEVERITY_STYLE.MEDIUM
                return (
                  <tr key={a.alert_id} style={{ borderTop: '1px solid var(--hairline)' }}>
                    <td style={td}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: sev.color }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: sev.color, display: 'inline-block' }} />
                        {sev.label}
                      </span>
                    </td>
                    <td style={{ ...td, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      <span style={{ color: DOC_TYPE_COLOR[a.document_type] || 'var(--text-muted)', fontFamily: 'var(--font-data)', fontSize: 11.5 }}>
                        {a.document_type || '—'}
                      </span>
                      <div style={{ color: 'var(--text-primary)', fontSize: 12.5, marginTop: 2 }}>{a.ship_name || a.source_file || `#${a.document_id}`}</div>
                    </td>
                    <td style={{ ...td, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{TYPE_LABEL[a.alert_type] || a.alert_type}</td>
                    <td style={{ ...td, color: 'var(--text-primary)' }}>{a.message}</td>
                    <td style={{ ...td, textAlign: 'right' }}>
                      {!a.acknowledged && (
                        <button
                          onClick={() => onResolve(a.alert_id)}
                          style={{
                            background: 'transparent',
                            border: '1px solid var(--accent-green-dim)',
                            color: 'var(--accent-green)',
                            fontSize: 11.5,
                            padding: '4px 10px',
                            borderRadius: 2,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          Résoudre
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

const th = { padding: '0 10px 8px 0', fontWeight: 500 }
const td = { padding: '10px 10px 10px 0', verticalAlign: 'top' }
