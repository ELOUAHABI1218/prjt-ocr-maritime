import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DocumentsTable from '../components/DocumentsTable.jsx'
import { PageHeader } from './DashboardPage.jsx'

export default function DocumentsPage() {
  const { data } = useOutletContext()
  const { documents, loading } = data
  const [filterType, setFilterType] = useState('ALL')

  const filtered = filterType === 'ALL' ? documents : (documents || []).filter((d) => d.document_type === filterType)

  return (
    <div>
      <PageHeader title="Documents" subtitle="Tous les documents océrisés et ingérés" />
      <div style={{ marginTop: 20 }}>
        <DocumentsTable documents={filtered} loading={loading} filterType={filterType} onFilterType={setFilterType} />
      </div>
    </div>
  )
}
