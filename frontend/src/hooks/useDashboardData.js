import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const REFRESH_MS = 30_000
const STATS_BASE = 'http://127.0.0.1:8000/stats'

export function useDashboardData(docFilter = 'ALL') {
  const [summary, setSummary] = useState(null)
  const [dangerousClasses, setDangerousClasses] = useState(null)
  const [healthQuestions, setHealthQuestions] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [alerts, setAlerts] = useState(null)
  const [documents, setDocuments] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const loadAll = useCallback(async () => {
    try {
      const [s, dc, hq, tl, al, docs] = await Promise.all([
        api.summary(),
        fetch(`${STATS_BASE}/dangerous-classes`).then((r) => r.json()),
        fetch(`${STATS_BASE}/health-questions`).then((r) => r.json()),
        fetch(`${STATS_BASE}/alerts-timeline?days=30`).then((r) => r.json()),
        api.alerts({ limit: 200 }),
        api.documents(docFilter === 'ALL' ? {} : { document_type: docFilter }),
      ])
      setSummary(s)
      setDangerousClasses(dc)
      setHealthQuestions(hq)
      setTimeline(tl)
      setAlerts(al)
      setDocuments(docs)
      setError(null)
      setLastUpdated(new Date())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [docFilter])

  useEffect(() => {
    loadAll()
    const interval = setInterval(loadAll, REFRESH_MS)
    return () => clearInterval(interval)
  }, [loadAll])

  const resolveAlert = async (alertId) => {
    setAlerts((prev) => prev.map((a) => (a.alert_id === alertId ? { ...a, acknowledged: true } : a)))
    try {
      await api.resolveAlert(alertId)
    } catch {
      loadAll()
    }
  }

  return {
    summary,
    dangerousClasses,
    healthQuestions,
    timeline,
    alerts,
    documents,
    loading,
    error,
    lastUpdated,
    reload: loadAll,
    resolveAlert,
  }
}
