import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'pfa-sidebar-collapsed'

export function useSidebar() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(collapsed))
    } catch {
      // stockage indisponible — l'état reste actif pour la session
    }
  }, [collapsed])

  const toggleSidebar = useCallback(() => setCollapsed((v) => !v), [])

  return { collapsed, toggleSidebar }
}
