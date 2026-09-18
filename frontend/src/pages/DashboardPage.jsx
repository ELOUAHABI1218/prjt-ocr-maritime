import { useOutletContext, Link } from 'react-router-dom'
import KpiStrip from '../components/KpiStrip.jsx'
import DangerousClassChart from '../components/DangerousClassChart.jsx'
import ClassPercentageChart from '../components/ClassPercentageChart.jsx'
import HealthQuestionsChart from '../components/HealthQuestionsChart.jsx'
import DocumentsByTypeChart from '../components/DocumentsByTypeChart.jsx'
import AlertsTimeline from '../components/AlertsTimeline.jsx'
import AlertsTable from '../components/AlertsTable.jsx'

export default function DashboardPage() {
  const { data } = useOutletContext()
  const { summary, dangerousClasses, healthQuestions, timeline, alerts, documents, loading, error, resolveAlert } = data

  return (
    <div>
      <PageHeader
        title="Vue d'ensemble"
        subtitle="Déclarations DGD / DGM / Santé — Port de Tanger Med"
      />

      <div style={{ marginTop: 20 }}>
        <KpiStrip summary={summary} loading={loading} />
      </div>

      {/* Rangée principale — activité dans le temps + répartition globale */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr', gap: 14, marginTop: 14 }}>
        <AlertsTimeline data={timeline} alerts={alerts} loading={loading} />
        <DocumentsByTypeChart documentsByType={summary?.documents_by_type} loading={loading} />
      </div>

      {/* Rangée secondaire — analyse par classe */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 14, marginTop: 14 }}>
        <ClassPercentageChart documents={documents} loading={loading} />
        <DangerousClassChart data={dangerousClasses} loading={loading} />
      </div>

      {/* Questionnaire sanitaire — pleine largeur, lisible sur 9 questions */}
      <div style={{ marginTop: 14 }}>
        <HealthQuestionsChart data={healthQuestions} loading={loading} />
      </div>

      {/* Journal des alertes récentes */}
      <div style={{ marginTop: 14 }}>
        <AlertsTable alerts={(alerts || []).slice(0, 8)} loading={loading} onResolve={resolveAlert} error={error} />
        {alerts && alerts.length > 8 && (
          <div style={{ textAlign: 'right', marginTop: 8 }}>
            <Link to="/alertes" style={{ fontSize: 12.5, color: 'var(--accent-blue)', textDecoration: 'none' }}>
              Voir toutes les alertes →
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}

export function PageHeader({ title, subtitle, action }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
      <div>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 600 }}>{title}</h1>
        {subtitle && <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}
