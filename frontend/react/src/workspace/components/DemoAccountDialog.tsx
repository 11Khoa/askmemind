import { useState } from 'react'
import type { FormEvent } from 'react'
import type { User } from '../../lib/types'
import { adminApi } from '../../lib/admin'
import { ActionDialog } from './ActionDialog'
import './demo.css'

export function DemoAccountDialog({ user, onClose, onSaved }: { user: User; onClose: () => void; onSaved: () => void }) {
  const [enabled, setEnabled] = useState(user.is_demo || false)
  const [retention, setRetention] = useState(user.demo_retention_minutes || 60)
  const [upload, setUpload] = useState(user.demo_upload_enabled ?? true)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setSuccess('')
    try {
      await adminApi.demoConfig(user.id, { is_demo: enabled, demo_retention_minutes: retention, demo_upload_enabled: upload })
      onSaved(); onClose()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not save demo configuration') }
    finally { setBusy(false) }
  }
  async function clear() {
    if (busy) return
    setBusy(true); setError(''); setSuccess('')
    try { await adminApi.clearDemoData(user.id); setConfirm(false); setSuccess('All demo sessions and their data were deleted.'); onSaved() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not delete demo data') }
    finally { setBusy(false) }
  }
  return <ActionDialog title={`Demo settings · ${user.email}`} busy={busy} onClose={onClose}>
    <form className="demo-config-form" onSubmit={(event) => void save(event)}>
      <label><input type="checkbox" checked={enabled} disabled={busy || user.role === 'admin'} onChange={(event) => setEnabled(event.target.checked)} />Demo mode</label>
      <label>Retention (minutes)<input type="number" min={15} max={1440} required disabled={busy} value={retention} onChange={(event) => setRetention(event.target.valueAsNumber)} /></label>
      <label><input type="checkbox" checked={upload} disabled={busy} onChange={(event) => setUpload(event.target.checked)} />Allow demo uploads</label>
      <small>Retention is fixed when a session starts. Changes apply to new sessions. Mode changes sign out existing sessions. Delete all demo data before turning demo mode off. Existing non-demo data stays outside browser demo sessions.</small>
      {error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}
      {confirm ? <div className="demo-notice"><p>Delete all demo data for this account? This removes every browser’s demo documents and conversations. This cannot be undone.</p>
        <button type="button" disabled={busy} onClick={() => setConfirm(false)}>Keep demo data</button>
        <button type="button" className="danger-button" disabled={busy} onClick={() => void clear()}>Confirm delete all demo data</button></div>
        : <button type="button" className="danger-text" disabled={busy} onClick={() => { setConfirm(true); setError('') }}>Delete all demo data</button>}
      <footer><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button disabled={busy || confirm}>{busy ? 'Working…' : 'Save demo settings'}</button></footer>
    </form>
  </ActionDialog>
}
