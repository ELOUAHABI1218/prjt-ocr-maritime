export default function Panel({ title, subtitle, action, children, className = '' }) {
  return (
    <div
      className={`panel ${className}`}
      style={{
        background: 'var(--ink-1)',
        border: '1px solid var(--hairline)',
        borderRadius: 2,
        position: 'relative',
        padding: '20px 22px 22px',
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
      }}
    >
      {/* repères d'angle, dans l'esprit cadran d'instrument */}
      <Corner style={{ top: -1, left: -1, borderRight: 'none', borderBottom: 'none' }} />
      <Corner style={{ top: -1, right: -1, borderLeft: 'none', borderBottom: 'none' }} />
      <Corner style={{ bottom: -1, left: -1, borderRight: 'none', borderTop: 'none' }} />
      <Corner style={{ bottom: -1, right: -1, borderLeft: 'none', borderTop: 'none' }} />

      {(title || action) && (
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            {title && (
              <h2
                style={{
                  margin: 0,
                  fontFamily: 'var(--font-display)',
                  fontSize: 13,
                  fontWeight: 600,
                  letterSpacing: '0.09em',
                  textTransform: 'uppercase',
                  color: 'var(--text-muted)',
                }}
              >
                {title}
              </h2>
            )}
            {subtitle && (
              <p style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--text-faint)' }}>{subtitle}</p>
            )}
          </div>
          {action}
        </div>
      )}
      {children}
    </div>
  )
}

function Corner({ style }) {
  return (
    <span
      style={{
        position: 'absolute',
        width: 10,
        height: 10,
        border: '1px solid var(--hairline-bright)',
        pointerEvents: 'none',
        ...style,
      }}
    />
  )
}
