const BASE_URL = 'http://127.0.0.1:8000'

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText} — ${body}`)
  }
  return res.json()
}

export const api = {
  documents: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/documents${qs ? `?${qs}` : ''}`)
  },
  document: (id) => request(`/documents/${id}`),
  alerts: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/alerts${qs ? `?${qs}` : ''}`)
  },
  resolveAlert: (id) => request(`/alerts/${id}/acknowledge`, { method: 'PATCH' }),
  summary: () => request('/stats/summary'),
}
