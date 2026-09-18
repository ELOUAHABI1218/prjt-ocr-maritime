import { useOutletContext } from 'react-router-dom'
import AlertsTable from '../components/AlertsTable.jsx'
import { PageHeader } from './DashboardPage.jsx'

export default function AlertsPage() {
  const { data } = useOutletContext()
  const { alerts, loading, error, resolveAlert } = data

  const openCount = (alerts || []).filter((a) => !a.resolved).length

  return (
    <div>
      <PageHeader
        title="Alertes"
        subtitle={`${openCount} alerte${openCount !== 1 ? 's' : ''} ouverte${openCount !== 1 ? 's' : ''}`}
      />
      <div style={{ marginTop: 20 }}>
        <AlertsTable alerts={alerts} loading={loading} onResolve={resolveAlert} error={error} />
      </div>
    </div>
  )
}
