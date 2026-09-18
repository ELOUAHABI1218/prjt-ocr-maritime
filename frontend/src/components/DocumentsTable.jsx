import Panel from './Panel.jsx'

const TYPE_COLOR = {
  DGD: 'var(--accent-green)',
  DGM: 'var(--accent-navy)',
  HEALTH: 'var(--accent-steel)',
}

export default function DocumentsTable({ documents, loading, filterType, onFilterType }) {
  return (
    <Panel
      title="Documents récents"
      subtitle={`${documents?.length ?? 0} document(s)`}
      action={
        <div style={{ display: 'flex', gap: 4 }}>
          {['ALL', 'DGD', 'DGM', 'HEALTH'].map((t) => (
            <button
              key={t}
              onClick={() => onFilterType(t)}
              style={{
                background: filterType === t ? 'var(--ink-2)' : 'transparent',
                border: '1px solid var(--hairline)',
                color: filterType === t ? 'var(--text-primary)' : 'var(--text-muted)',
                fontSize: 11.5,
                padding: '5px 10px',
                borderRadius: 2,
              }}
            >
              {t === 'ALL' ? 'Tous' : t}
            </button>
          ))}
        </div>
      }
    >
      {loading ? (
        <div style={{ color: 'var(--text-faint)', fontSize: 13, padding: '20px 0' }}>Chargement…</div>
      ) : !documents || documents.length === 0 ? (
        <div style={{ color: 'var(--text-faint)', fontSize: 13, padding: '20px 0' }}>Aucun document ingéré pour l'instant.</div>
      ) : (
        <div style={{ maxHeight: 280, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--text-faint)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                <th style={th}>Type</th>
                <th style={th}>Navire</th>
                <th style={th}>IMO</th>
                <th style={th}>Ingéré le</th>
                <th style={th}>Alertes</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((d) => (
                <tr key={d.document_id} style={{ borderTop: '1px solid var(--hairline)' }}>
                  <td style={td}>
                    <span style={{ color: TYPE_COLOR[d.document_type] || 'var(--text-muted)', fontFamily: 'var(--font-data)', fontSize: 12 }}>
                      {d.document_type}
                    </span>
                  </td>
                  <td style={{ ...td, color: 'var(--text-primary)' }}>{d.ship_name || '—'}</td>
                  <td style={{ ...td, fontFamily: 'var(--font-data)', color: 'var(--text-muted)', fontSize: 12 }}>{d.imo_number || '—'}</td>
                  <td style={{ ...td, fontFamily: 'var(--font-data)', color: 'var(--text-muted)', fontSize: 12 }}>
                    {d.loaded_at ? new Date(d.loaded_at).toLocaleDateString('fr-FR') : '—'}
                  </td>
                  <td style={td}>
                    {d.alert_count > 0 ? (
                      <span style={{ color: 'var(--danger)', fontFamily: 'var(--font-data)' }}>{d.alert_count}</span>
                    ) : (
                      <span style={{ color: 'var(--ok)' }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

const th = { padding: '0 10px 8px 0', fontWeight: 500 }
const td = { padding: '9px 10px 9px 0', verticalAlign: 'top' }
