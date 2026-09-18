import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, UploadCloud, FileStack, ShieldAlert, History, Menu, Sun, Moon } from 'lucide-react'
import Logo from './Logo.jsx'
import { useSidebar } from '../hooks/useSidebar.js'
import { useTheme } from '../hooks/useTheme.js'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/import', label: 'Importer un document', icon: UploadCloud },
  { to: '/documents', label: 'Documents', icon: FileStack },
  { to: '/alertes', label: 'Alertes', icon: ShieldAlert },
  { to: '/historique', label: 'Historique', icon: History },
]

export default function Layout({ data }) {
  const { collapsed, toggleSidebar } = useSidebar()
  const { theme, toggleTheme } = useTheme()

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />

      {collapsed && (
        <button
          onClick={toggleSidebar}
          title="Afficher le menu"
          style={{
            position: 'fixed',
            top: 16,
            left: 16,
            zIndex: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 36,
            height: 36,
            background: 'var(--ink-1)',
            border: '1px solid var(--hairline-bright)',
            borderRadius: 4,
            color: 'var(--text-primary)',
          }}
        >
          <Menu size={16} />
        </button>
      )}

      <div style={{ flex: 1, minWidth: 0 }}>
        <TopBar connectionOk={!data.error} lastUpdated={data.lastUpdated} theme={theme} onToggleTheme={toggleTheme} />
        <main style={{ maxWidth: 1320, margin: '0 auto', padding: '24px 28px 60px' }}>
          <Outlet context={{ data }} />
        </main>
      </div>
    </div>
  )
}

function Sidebar({ collapsed, onToggle }) {
  return (
    <aside
      style={{
        width: collapsed ? 0 : 240,
        flexShrink: 0,
        background: 'var(--ink-1)',
        borderRight: collapsed ? 'none' : '1px solid var(--hairline)',
        display: 'flex',
        flexDirection: 'column',
        position: 'sticky',
        top: 0,
        height: '100vh',
        transition: 'width 200ms ease',
        overflow: 'hidden',
      }}
    >
      <button
        onClick={onToggle}
        title="Cliquer pour masquer le menu"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '20px 20px 18px',
          borderBottom: '1px solid var(--hairline)',
          background: 'transparent',
          border: 'none',
          borderBottomWidth: 1,
          borderBottomStyle: 'solid',
          borderBottomColor: 'var(--hairline)',
          cursor: 'pointer',
          width: '100%',
          textAlign: 'left',
          minWidth: 240,
        }}
      >
        <Logo size={30} />
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 13.5, fontWeight: 600, lineHeight: 1.15, whiteSpace: 'nowrap' }}>Tanger Med</div>
          <div style={{ fontSize: 10.5, color: 'var(--text-faint)', letterSpacing: '0.05em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>Port Authority</div>
        </div>
      </button>

      <nav style={{ padding: '14px 10px', display: 'flex', flexDirection: 'column', gap: 2, minWidth: 240 }}>
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '9px 12px',
              borderRadius: 3,
              fontSize: 13.5,
              textDecoration: 'none',
              color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
              background: isActive ? 'var(--ink-2)' : 'transparent',
              borderLeft: isActive ? '2px solid var(--accent-blue)' : '2px solid transparent',
              whiteSpace: 'nowrap',
            })}
          >
            <Icon size={16} strokeWidth={1.8} style={{ flexShrink: 0 }} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div style={{ marginTop: 'auto', padding: '16px 20px', fontSize: 10.5, color: 'var(--text-faint)', borderTop: '1px solid var(--hairline)', minWidth: 240 }}>
        Surveillance automatisée des déclarations cargo dangereux et sanitaires — PFA 2026
      </div>
    </aside>
  )
}

function TopBar({ connectionOk, lastUpdated, theme, onToggleTheme }) {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '16px 28px',
        borderBottom: '1px solid var(--hairline)',
      }}
    >
      <button
        onClick={onToggleTheme}
        title={theme === 'dark' ? 'Passer en thème clair' : 'Passer en thème sombre'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 7,
          background: 'transparent',
          border: '1px solid var(--hairline)',
          color: 'var(--text-muted)',
          fontSize: 12,
          padding: '6px 12px',
          borderRadius: 3,
        }}
      >
        {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
        {theme === 'dark' ? 'Thème clair' : 'Thème sombre'}
      </button>

      <div style={{ textAlign: 'right' }}>
        <div style={{ fontFamily: 'var(--font-data)', fontSize: 11.5, color: connectionOk ? 'var(--ok)' : 'var(--danger)' }}>
          {connectionOk ? '● Connecté' : '● API injoignable'}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 2 }}>
          {lastUpdated ? `Mis à jour à ${lastUpdated.toLocaleTimeString('fr-FR')}` : 'Chargement initial…'}
        </div>
      </div>
    </header>
  )
}
