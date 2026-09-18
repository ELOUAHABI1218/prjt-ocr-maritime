import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { UploadCloud, FileText, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import Panel from '../components/Panel.jsx'
import { PageHeader } from './DashboardPage.jsx'

const API_BASE = 'http://127.0.0.1:8000'

const DOC_TYPES = [
  { value: '', label: 'Détection automatique' },
  { value: 'DGD', label: 'DGD — Dangerous Cargo Declaration' },
  { value: 'DGM', label: 'DGM — Dangerous Cargo Manifest' },
  { value: 'HEALTH', label: 'Health — Maritime Declaration of Health' },
]

export default function UploadPage() {
  const { data } = useOutletContext()
  const [mode, setMode] = useState('pdf') // 'pdf' | 'json'

  return (
    <div>
      <PageHeader title="Importer un document" subtitle="Océrisation automatique ou import d'un JSON déjà extrait" />

      <div style={{ display: 'flex', gap: 4, marginTop: 20, marginBottom: 16 }}>
        <TabButton active={mode === 'pdf'} onClick={() => setMode('pdf')} icon={UploadCloud} label="Uploader un PDF (OCR)" />
        <TabButton active={mode === 'json'} onClick={() => setMode('json')} icon={FileText} label="Uploader un JSON déjà extrait" />
      </div>

      {mode === 'pdf' ? <PdfUpload onIngested={data.reload} /> : <JsonUpload onIngested={data.reload} />}
    </div>
  )
}

function TabButton({ active, onClick, icon: Icon, label }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        background: active ? 'var(--ink-2)' : 'transparent',
        border: '1px solid var(--hairline)',
        borderBottom: active ? '1px solid var(--ink-2)' : '1px solid var(--hairline)',
        color: active ? 'var(--text-primary)' : 'var(--text-muted)',
        fontSize: 12.5,
        padding: '8px 14px',
        borderRadius: '3px 3px 0 0',
      }}
    >
      <Icon size={14} strokeWidth={1.8} />
      {label}
    </button>
  )
}

/* ------------------------------------------------------------------ */
/* Upload PDF — nécessite que ocr_bridge.py soit branché sur tes vrais */
/* extracteurs (src/dgd_main.py, dgm_main.py, health_main.py...)       */
/* ------------------------------------------------------------------ */
function PdfUpload({ onIngested }) {
  const [file, setFile] = useState(null)
  const [docType, setDocType] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [state, setState] = useState({ status: 'idle' }) // idle | loading | success | error
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (state.status !== 'loading') return
    const start = Date.now()
    const interval = setInterval(() => setElapsed((Date.now() - start) / 1000), 100)
    return () => clearInterval(interval)
  }, [state.status])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
    const dropped = e.dataTransfer.files?.[0]
    if (dropped) setFile(dropped)
  }, [])

  const submit = async () => {
    if (!file) return
    setElapsed(0)
    setState({ status: 'loading' })
    try {
      const form = new FormData()
      form.append('file', file)
      if (docType) form.append('document_type_hint', docType)

      const res = await fetch(`${API_BASE}/ingest/upload-pdf`, { method: 'POST', body: form })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || `Erreur ${res.status}`)

      setState({ status: 'success', result: body })
      onIngested()
    } catch (err) {
      setState({ status: 'error', message: err.message })
    }
  }

  return (
    <Panel title="Océrisation" subtitle="Le PDF est traité par ton pipeline OCR (src/) puis ingéré automatiquement">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        style={{
          border: `1.5px dashed ${dragOver ? 'var(--accent-green)' : 'var(--hairline-bright)'}`,
          borderRadius: 3,
          padding: '40px 20px',
          textAlign: 'center',
          background: dragOver ? 'var(--ink-2)' : 'transparent',
          transition: 'border-color 120ms, background 120ms',
        }}
      >
        <UploadCloud size={28} strokeWidth={1.5} color="var(--text-muted)" style={{ marginBottom: 10 }} />
        <div style={{ fontSize: 13.5, color: 'var(--text-primary)', marginBottom: 4 }}>
          {file ? file.name : 'Glisse un fichier PDF ici, ou clique pour parcourir'}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginBottom: 14 }}>Formats acceptés : .pdf</div>
        <label
          style={{
            display: 'inline-block',
            fontSize: 12.5,
            border: '1px solid var(--hairline-bright)',
            padding: '6px 14px',
            borderRadius: 2,
            cursor: 'pointer',
            color: 'var(--text-muted)',
          }}
        >
          Parcourir…
          <input type="file" accept=".pdf" hidden onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </label>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 18 }}>
        <label style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Type de document</label>
        <select
          value={docType}
          onChange={(e) => setDocType(e.target.value)}
          style={{
            background: 'var(--ink-0)',
            border: '1px solid var(--hairline)',
            color: 'var(--text-primary)',
            fontSize: 12.5,
            padding: '6px 10px',
            borderRadius: 2,
          }}
        >
          {DOC_TYPES.map((t) => (
            <option key={t.value} value={t.value} style={{ background: 'var(--ink-0)', color: 'var(--text-primary)' }}>{t.label}</option>
          ))}
        </select>

        <button
          onClick={submit}
          disabled={!file || state.status === 'loading'}
          style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            background: file ? 'var(--accent-green-dim)' : 'var(--ink-2)',
            border: '1px solid var(--accent-green)',
            color: file ? 'var(--text-primary)' : 'var(--text-faint)',
            fontSize: 13,
            padding: '8px 18px',
            borderRadius: 2,
            opacity: !file || state.status === 'loading' ? 0.6 : 1,
          }}
        >
          {state.status === 'loading' && <Loader2 size={14} className="spin" />}
          Océriser &amp; ingérer
        </button>
      </div>

      <StatusBlock state={state} elapsed={elapsed} />
    </Panel>
  )
}

/* ------------------------------------------------------------------ */
/* Upload JSON déjà extrait — utilise /ingest/upload, déjà testé       */
/* ------------------------------------------------------------------ */
function JsonUpload({ onIngested }) {
  const [file, setFile] = useState(null)
  const [state, setState] = useState({ status: 'idle' })

  const submit = async () => {
    if (!file) return
    setState({ status: 'loading' })
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API_BASE}/ingest/upload`, { method: 'POST', body: form })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || `Erreur ${res.status}`)
      setState({ status: 'success', result: body })
      onIngested()
    } catch (err) {
      setState({ status: 'error', message: err.message })
    }
  }

  return (
    <Panel title="Import direct d'un JSON" subtitle="Fichier déjà produit par tes scripts *_main.py (ex: output/DGM-ex-1_result.json)">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <label
          style={{
            display: 'inline-block',
            fontSize: 12.5,
            border: '1px solid var(--hairline-bright)',
            padding: '7px 14px',
            borderRadius: 2,
            cursor: 'pointer',
            color: 'var(--text-muted)',
          }}
        >
          Choisir un fichier .json
          <input type="file" accept=".json" hidden onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </label>
        <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{file?.name || 'Aucun fichier sélectionné'}</span>

        <button
          onClick={submit}
          disabled={!file || state.status === 'loading'}
          style={{
            marginLeft: 'auto',
            background: file ? 'var(--accent-green-dim)' : 'var(--ink-2)',
            border: '1px solid var(--accent-green)',
            color: file ? 'var(--text-primary)' : 'var(--text-faint)',
            fontSize: 13,
            padding: '8px 18px',
            borderRadius: 2,
            opacity: !file || state.status === 'loading' ? 0.6 : 1,
          }}
        >
          Ingérer
        </button>
      </div>

      <StatusBlock state={state} />
    </Panel>
  )
}

function StatusBlock({ state, elapsed }) {
  if (state.status === 'idle') return null

  if (state.status === 'loading') {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, fontSize: 13, color: 'var(--text-muted)' }}>
        <Loader2 size={14} className="spin" />
        Océrisation en cours… {typeof elapsed === 'number' && <span style={{ fontFamily: 'var(--font-data)' }}>{elapsed.toFixed(1)}s</span>}
      </div>
    )
  }

  if (state.status === 'success') {
    const r = state.result
    const alertList = r.alerts || []
    return (
      <div style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: 12, border: '1px solid var(--ok)', borderRadius: 2, background: 'var(--ok-dim)' }}>
          <CheckCircle2 size={18} color="var(--ok)" style={{ flexShrink: 0, marginTop: 1 }} />
          <div style={{ fontSize: 13 }}>
            Document ingéré avec succès (#{r.document_id}).{' '}
            {alertList.length > 0
              ? `${alertList.length} alerte(s) active(s) pour ce document.`
              : 'Aucune alerte déclenchée.'}
            <div style={{ marginTop: 6, display: 'flex', gap: 16, fontFamily: 'var(--font-data)', fontSize: 12, color: 'var(--text-muted)' }}>
              {typeof r.ocr_seconds === 'number' && <span>Océrisation : <strong style={{ color: 'var(--text-primary)' }}>{r.ocr_seconds}s</strong></span>}
              {typeof r.pipeline_seconds === 'number' && <span>Pipeline complet : <strong style={{ color: 'var(--text-primary)' }}>{r.pipeline_seconds}s</strong></span>}
            </div>
          </div>
        </div>

        {alertList.length > 0 && (
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {alertList.map((a) => (
              <AlertRow key={a.alert_id} alert={a} />
            ))}
          </div>
        )}

        {r.extracted_json && <JsonViewer data={r.extracted_json} />}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginTop: 16, padding: 12, border: '1px solid var(--danger)', borderRadius: 2, background: 'var(--danger-dim)' }}>
      <XCircle size={18} color="var(--danger)" style={{ flexShrink: 0, marginTop: 1 }} />
      <div style={{ fontSize: 13 }}>{state.message}</div>
    </div>
  )
}

const SEVERITY_COLOR = { CRITICAL: 'var(--danger)', HIGH: 'var(--warning)', MEDIUM: 'var(--accent-green)', LOW: 'var(--text-muted)' }

function AlertRow({ alert }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '8px 10px', border: '1px solid var(--hairline)', borderLeft: `2px solid ${SEVERITY_COLOR[alert.severity] || 'var(--text-muted)'}`, borderRadius: 2, fontSize: 12.5 }}>
      <span style={{ color: SEVERITY_COLOR[alert.severity] || 'var(--text-muted)', fontFamily: 'var(--font-data)', fontSize: 11, whiteSpace: 'nowrap' }}>
        {alert.severity}
      </span>
      <span style={{ color: 'var(--text-primary)' }}>{alert.message}</span>
    </div>
  )
}

function JsonViewer({ data }) {
  const [open, setOpen] = useState(true)

  return (
    <div style={{ marginTop: 10, border: '1px solid var(--hairline)', borderRadius: 2 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--ink-0)',
          border: 'none',
          borderBottom: open ? '1px solid var(--hairline)' : 'none',
          color: 'var(--text-muted)',
          fontSize: 12,
          padding: '8px 12px',
          fontFamily: 'var(--font-data)',
        }}
      >
        <span>JSON extrait</span>
        <span>{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <pre
          style={{
            margin: 0,
            padding: 14,
            maxHeight: 380,
            overflow: 'auto',
            fontFamily: 'var(--font-data)',
            fontSize: 12,
            lineHeight: 1.6,
            color: 'var(--text-primary)',
            background: 'var(--ink-0)',
          }}
        >
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  )
}
