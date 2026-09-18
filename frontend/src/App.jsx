import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import UploadPage from './pages/UploadPage.jsx'
import DocumentsPage from './pages/DocumentsPage.jsx'
import AlertsPage from './pages/AlertsPage.jsx'
import HistoryPage from './pages/HistoryPage.jsx'
import { useDashboardData } from './hooks/useDashboardData.js'

export default function App() {
  const data = useDashboardData()

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout data={data} />}>
          <Route index element={<DashboardPage />} />
          <Route path="/import" element={<UploadPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/alertes" element={<AlertsPage />} />
          <Route path="/historique" element={<HistoryPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
