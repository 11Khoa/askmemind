import { ArrowLeft, Library, Users, Files, MessagesSquare, Activity, Search, RefreshCw, FileText, CheckCircle2, LoaderCircle, AlertTriangle, Eye, Trash2 } from 'lucide-react'
import { UploadedAt } from './components/UploadedAt'
import { useEffect, useState } from 'react'
import { DocumentProcessingFeedback } from './components/DocumentProcessingFeedback'
import type { FormEvent } from 'react'
import { api, ApiError, isAbortError } from '../lib/api'
import { subscribeDocumentEvents } from '../lib/documentEvents'
import type { DocumentConnectionState } from '../lib/documentEvents'
import { documentEventTimestamp } from '../lib/documentProgress'
import { reconcileAdminDocuments } from '../lib/adminDocumentEvents'
import { adminApi } from '../lib/admin'
import type { AdminTab, AdminRow, AdminDocument, AdminChat, AuditEvent, Page } from '../lib/admin'
import type { User, Citation, ChatMessage, DocumentStatusEvent } from '../lib/types'
import { ActionDialog } from './components/ActionDialog'
import { SourceViewer } from './components/SourceViewer'
import './admin.css'

type Pending = { kind: 'role' | 'active' | 'document' | 'chat'; id: string; name: string; role?: User['role']; active?: boolean }

function Pagination({ page, total, size, onPage }: { page: number; total: number; size: number; onPage: (page: number) => void }) {
  return <nav className="admin-pagination" aria-label="Pagination">
    <button disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
    <span>Page {page} of {Math.max(1, Math.ceil(total / size))} · {total} records</span>
    <button disabled={page * size >= total} onClick={() => onPage(page + 1)}>Next</button>
  </nav>
}

export function AdminPanel({ onBack }: { onBack: () => void }) {
  const [access, setAccess] = useState<'checking' | 'allowed' | 'denied'>('checking')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    void api.me().then((user) => {
      if (active) setAccess(user.role === 'admin' ? 'allowed' : 'denied')
    }).catch((caught: unknown) => {
      if (active) { setAccess('denied'); setError(caught instanceof Error ? caught.message : 'Could not verify permissions') }
    })
    return () => { active = false }
  }, [])
  if (access === 'allowed') return <AdminDashboard onBack={onBack} />
  return <main className="admin-shell"><p role={access === 'checking' ? 'status' : 'alert'}>
    {access === 'checking' ? 'Checking administrator permission…' : error || 'Administrator permission required'}
  </p><button onClick={onBack}>Back to workspace</button></main>
}

function AdminDashboard({ onBack }: { onBack: () => void }) {
  const [tab, setTab] = useState<AdminTab>('users')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [owner, setOwner] = useState<{ id: string; email: string } | null>(null)
  const [revision, setRevision] = useState(0)
  const key = JSON.stringify([tab, page, query, owner?.id, revision])
  const [result, setResult] = useState<{ key: string; data: Page<AdminRow> } | null>(null)
  const [error, setError] = useState<{ key: string; message: string } | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)
  const [cancelling, setCancelling] = useState<string | null>(null)
  const [actionError, setActionError] = useState('')
  const [source, setSource] = useState<{ citation: Citation; filename: string; documentOnly: boolean } | null>(null)
  const [chat, setChat] = useState<AdminChat | null>(null)
  const [connection, setConnection] = useState<DocumentConnectionState>('connecting')
  const [liveIssue, setLiveIssue] = useState<{ key: string; message: string } | null>(null)

  useEffect(() => {
    let active = true
    const lifetime = new AbortController()
    let accessRevoked = false
    let visible = new Set<string>()
    const buffered = new Map<string, DocumentStatusEvent>()
    let timer: ReturnType<typeof setTimeout> | undefined
    let inFlight = false
    let refreshPending = false
    let lastSnapshot = 0

    function reportError(caught: unknown) {
      if (!active || isAbortError(caught)) return
      if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
        accessRevoked = true
        lifetime.abort()
        clearTimeout(timer)
        setError({ key, message: 'Administrator access is no longer available.' })
        setLiveIssue({ key, message: 'Live updates stopped: administrator permission required.' })
      } else {
        setLiveIssue({ key, message: 'Live updates are temporarily unavailable. Use Refresh to check the latest status.' })
      }
    }
    function scheduleSnapshot() {
      if (!active || accessRevoked || timer) return
      timer = setTimeout(() => {
        timer = undefined
        void loadSnapshot(lifetime.signal).catch(reportError)
      }, Math.max(0, 2000 - (Date.now() - lastSnapshot)))
    }
    async function loadSnapshot(signal: AbortSignal) {
      if (inFlight) { refreshPending = true; return }
      inFlight = true
      lastSnapshot = Date.now()
      try {
        let data = await adminApi.list(tab, page, query, owner?.id || '', signal)
        if (!active || accessRevoked || signal.aborted) return
        if (tab === 'documents') {
          for (const event of buffered.values()) data = reconcileAdminDocuments(data, event)
        }
        visible = new Set(data.items.map((row) => String(row.id)))
        setResult({ key, data })
        setError(null)
        setLiveIssue(null)
      } finally {
        inFlight = false
        if (refreshPending && active) { refreshPending = false; scheduleSnapshot() }
      }
    }
    void loadSnapshot(lifetime.signal).catch((caught: unknown) => {
      if (active && !isAbortError(caught)) setError({ key, message: caught instanceof Error ? caught.message : 'Could not load administration data' })
    })
    const stop = tab === 'documents' ? subscribeDocumentEvents((event) => {
      if (!active || accessRevoked || (owner?.id && event.user_id && event.user_id !== owner.id)) return
      const previous = buffered.get(event.document_id)
      const time = documentEventTimestamp(event.updated_at), old = documentEventTimestamp(previous?.updated_at)
      if (time !== null && old !== null && time < old) return
      buffered.set(event.document_id, event)
      if (buffered.size > 500) {
        const oldest = buffered.keys().next().value
        if (oldest !== undefined) buffered.delete(oldest)
      }
      setResult((current) => {
        if (current?.key !== key) return current
        const next = reconcileAdminDocuments(current.data, event)
        return next === current.data ? current : { key, data: next }
      })
      if (!visible.has(event.document_id)) scheduleSnapshot()
    }, reportError, {
      endpoint: '/admin/documents/events', onState: setConnection,
      onConnected: loadSnapshot,
    }) : undefined
    return () => { active = false; lifetime.abort(); stop?.(); clearTimeout(timer) }
  }, [key, tab, page, query, owner?.id])

  function changeTab(next: AdminTab) { setTab(next); setPage(1); setSearch(''); setQuery('') }
  async function cancelProcessing(document: AdminDocument) {
    if (cancelling) return
    setCancelling(document.id)
    setActionError('')
    try {
      await api.cancelDocument(document.id)
      // Refresh this exact query scope and abort older in-flight snapshots.
      setRevision((value) => value + 1)
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Could not cancel document processing')
      if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) setRevision((value) => value + 1)
    } finally { setCancelling(null) }
  }
  function ask(action: Pending) { setActionError(''); setPending(action) }
  function openDocument(document: AdminDocument) {
    setSource({ filename: document.original_filename, documentOnly: true, citation: {
      document_id: document.id, chunk_id: '', source_number: 1, chunk_index: 0, page_number: 1,
      start_time_seconds: null, end_time_seconds: null, distance: null,
    } })
  }
  async function confirmAction() {
    if (!pending || busy) return
    setBusy(true); setActionError('')
    try {
      if (pending.kind === 'role') await adminApi.updateUser(pending.id, { role: pending.role })
      else if (pending.kind === 'active') await adminApi.updateUser(pending.id, { is_active: pending.active })
      else if (pending.kind === 'document') await api.deleteDocument(pending.id)
      else await api.deleteChat(pending.id)
      setPending(null); setRevision((value) => value + 1)
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Action failed')
    } finally { setBusy(false) }
  }
  const data = result?.key === key ? result.data : null
  const currentError = error?.key === key ? error.message : null
  const title = tab[0].toUpperCase() + tab.slice(1)
  const documents = tab === 'documents' && data ? data.items as AdminDocument[] : []
  const sections = { users: Users, documents: Files, chats: MessagesSquare, activity: Activity }
  const descriptions = {
    users: 'Manage accounts, permissions and access.',
    documents: 'Manage uploads and monitor document processing.',
    chats: 'Inspect conversations and their sources.',
    activity: 'Review recorded activity and administration actions.',
  }


  return <main className="admin-shell admin-dashboard">
    <aside className="admin-sidebar">
      <div className="admin-brand"><Library size={27} /><strong>AskMeMind</strong></div>
      <p className="admin-section-label">Administration</p>
      <nav className="admin-tabs" aria-label="Administration sections">
        {(['users', 'documents', 'chats', 'activity'] as const).map((item) => {
          const Icon = sections[item]
          return <button key={item} aria-current={tab === item ? 'page' : undefined} onClick={() => changeTab(item)}>
            <Icon size={19} />{item[0].toUpperCase() + item.slice(1)}
          </button>
        })}
      </nav>
      <button className="admin-back" onClick={onBack}><ArrowLeft size={17} />Back to workspace</button>
    </aside>
    <section className="admin-main">
    <header className="admin-header">
      <div><p className="eyebrow">Administration</p><h1>{title}</h1><p className="admin-description">{descriptions[tab]}</p></div>
      {tab === 'documents' && <p className={`admin-live-state ${liveIssue?.key === key ? 'has-issue' : ''}`} aria-live="polite">
        <span className={`admin-live-dot ${connection === 'connected' && liveIssue?.key !== key ? 'is-connected' : ''}`} />
        {liveIssue?.key === key ? liveIssue.message : connection === 'connected'
          ? 'Live document updates connected' : connection === 'reconnecting'
            ? 'Reconnecting live document updates…' : 'Connecting live document updates…'}
      </p>}
    </header>
    {tab === 'documents' && data && !currentError && <section className="admin-metrics" aria-label="Document summary">
      <article><span className="admin-metric-icon"><Files size={23} /></span><div><span>Matching documents</span><strong>{data.total}</strong></div></article>
      <article><span className="admin-metric-icon is-ready"><CheckCircle2 size={23} /></span><div><span>Ready on this page</span><strong>{documents.filter((doc) => ['ready', 'completed'].includes(doc.status)).length}</strong></div></article>
      <article><span className="admin-metric-icon is-processing"><LoaderCircle size={23} /></span><div><span>Processing on this page</span><strong>{documents.filter((doc) => ['processing', 'uploaded'].includes(doc.status)).length}</strong></div></article>
      <article><span className="admin-metric-icon is-failed"><AlertTriangle size={23} /></span><div><span>Failed on this page</span><strong>{documents.filter((doc) => ['failed', 'processing_failed'].includes(doc.status)).length}</strong></div></article>
    </section>}
    <div className="admin-data-panel">
    <div className="admin-toolbar"><form onSubmit={(event) => { event.preventDefault(); setQuery(search); setPage(1) }}>
      <Search size={18} aria-hidden="true" /><input aria-label="Search administration" maxLength={100} placeholder={tab === 'users' ? 'Find email' : tab === 'activity' ? 'Find action' : 'Find name or title'} value={search} onChange={(event) => setSearch(event.target.value)} />
      <button type="submit">Search</button></form>
      <button onClick={() => setRevision((value) => value + 1)}><RefreshCw size={16} />Refresh</button>
      {tab === 'users' && <button onClick={() => setCreateOpen(true)}>Create user</button>}
    </div>
    {actionError && !pending && <p role="alert">{actionError}</p>}
    {owner && tab !== 'users' && <p className="admin-filter">Showing user: {owner.email} <button onClick={() => { setOwner(null); setPage(1) }}>Clear user filter</button></p>}
    {currentError ? <p role="alert">{currentError}</p> : !data ? <p role="status">Loading administration…</p> : <>
      {data.items.length === 0 ? <p>No records found.</p> : <div className="admin-table-wrap" role="region" aria-label="Administration records" tabIndex={0}><table>
        <thead><tr>{(tab === 'users' ? ['Email', 'Role', 'Status', 'Actions'] : tab === 'activity' ? ['Time', 'Actor / target', 'Action', 'Result', 'Resource / request'] : tab === 'documents' ? ['Document', 'Owner', 'Uploaded at', 'Status', 'Processing', 'Actions'] : ['Owner', 'Conversation', 'Status / updated', 'Actions']).map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
        <tbody>{data.items.map((row) => {
          if (tab === 'users') {
            const user = row as User
            return <tr key={user.id}><td>{user.email}<small>{user.id}</small></td><td>{user.role}</td><td>{user.is_active ? 'Active' : 'Disabled'}</td>
              <td className="admin-actions"><button onClick={() => ask({ kind: 'role', id: user.id, name: user.email, role: user.role === 'admin' ? 'user' : 'admin' })}>{user.role === 'admin' ? 'Make user' : 'Make admin'}</button>
                <button onClick={() => ask({ kind: 'active', id: user.id, name: user.email, active: !user.is_active })}>{user.is_active ? 'Disable' : 'Enable'}</button>
                {(['documents', 'chats', 'activity'] as const).map((section) => <button key={section} onClick={() => { setOwner({ id: user.id, email: user.email }); changeTab(section) }}>View {section}</button>)}</td></tr>
          }
          if (tab === 'activity') {
            const event = row as AuditEvent
            return <tr key={event.id}><td>{new Date(event.created_at).toLocaleString()}</td><td>{event.actor_email || event.actor_id || 'Anonymous / server'}<small>{event.target_user_id ? `Target: ${event.target_email || event.target_user_id}` : ''}</small></td><td>{event.action}
              {event.details && <details><summary>Details</summary><pre>{JSON.stringify(event.details, null, 2)}</pre></details>}</td><td>{event.outcome}</td><td>{event.resource_id || '—'}<small>{event.request_id}</small></td></tr>
          }
          if (tab === 'documents') {
            const document = row as AdminDocument
            const processing = ['processing', 'uploaded'].includes(document.status)
            return <tr key={document.id}>
              <td><div className="admin-document-name"><span className="admin-pdf-icon"><FileText size={21} /></span><div>
                <strong title={document.id}>{document.original_filename}</strong>
                <small>{document.page_count ? `${document.page_count} pages · ` : ''}{!Number.isFinite(document.file_size_bytes) ? '—' : document.file_size_bytes < 1024 * 1024 ? `${Math.max(1, Math.round(document.file_size_bytes / 1024))} KB` : `${(document.file_size_bytes / (1024 * 1024)).toFixed(1)} MB`}</small>
              </div></div></td>
              <td className="admin-owner">{document.owner_email}</td>
              <td className="admin-uploaded"><UploadedAt value={document.created_at} /></td>
              <td><span className={`admin-status admin-status--${document.status}`}>
                {document.status === 'completed' ? 'Ready' : document.status === 'processing_failed' ? 'Failed' : document.status[0].toUpperCase() + document.status.slice(1)}
              </span></td>
              <td className="admin-processing">{['ready', 'completed'].includes(document.status) &&
                !(document.processing_progress?.started_at && document.processing_progress.finished_at)
                ? <span className="admin-no-duration">—</span> : <DocumentProcessingFeedback document={document} />}</td>
              <td><div className="admin-actions admin-document-actions">
                {processing && <button className="admin-cancel" disabled={Boolean(cancelling)}
                  aria-label={`Cancel processing ${document.original_filename}`} onClick={() => void cancelProcessing(document)}>
                  {cancelling === document.id ? 'Cancelling…' : 'Cancel processing'}
                </button>}
                <button className="admin-icon-action" title="View PDF" aria-label="View PDF" onClick={() => openDocument(document)}><Eye size={18} /></button>
                <button className="danger-text admin-icon-action" title="Delete document" aria-label="Delete document" onClick={() => ask({ kind: 'document', id: document.id, name: `${document.original_filename} (${document.owner_email})` })}><Trash2 size={17} /></button>
              </div></td>
            </tr>
          }
          const conversation = row as AdminChat
          return <tr key={conversation.id}><td>{conversation.owner_email}</td><td>{conversation.title || 'Untitled conversation'}</td><td>{new Date(conversation.updated_at).toLocaleString()}</td><td className="admin-actions">
            <button onClick={() => setChat(conversation)}>View messages</button><button className="danger-text" onClick={() => ask({ kind: 'chat', id: conversation.id, name: `${conversation.title || 'Conversation'} (${conversation.owner_email})` })}>Delete conversation</button></td></tr>
        })}</tbody></table></div>}
      <Pagination page={page} total={data.total} size={data.page_size} onPage={setPage} />
    </>}
    {tab === 'documents' && <p className="admin-timezone">Upload times shown in GMT+7. Status counts reflect the current page.</p>}
    </div>
    <p className="admin-notice">Administrator access: you can inspect all users’ documents, conversations and recorded activity. Your actions are audited.</p>
    </section>
    {createOpen && <CreateUser onClose={() => setCreateOpen(false)} onCreated={() => { setCreateOpen(false); setPage(1); setRevision((value) => value + 1) }} />}
    {pending && <ActionDialog title={`Confirm: ${pending.name}`} busy={busy} onClose={() => setPending(null)}>
      <p>{pending.kind === 'role' ? `Change this account to role ${pending.role}? Existing sessions will be invalidated.` : pending.kind === 'active' ? `${pending.active ? 'Enable' : 'Disable'} this account? Existing sessions will be invalidated.` : `Permanently delete this ${pending.kind}? This cannot be undone.`}</p>
      {actionError && <p role="alert">{actionError}</p>}<footer><button disabled={busy} onClick={() => setPending(null)}>Cancel</button><button className="danger-button" disabled={busy} onClick={() => void confirmAction()}>{busy ? 'Working…' : 'Confirm action'}</button></footer>
    </ActionDialog>}
    {source && <SourceViewer citation={source.citation} filename={source.filename} documentOnly={source.documentOnly} onClose={() => setSource(null)} />}
    {chat && <ChatInspector chat={chat} onClose={() => setChat(null)} onSource={(citation) => { setChat(null); setSource({ citation, filename: 'Source document', documentOnly: false }) }} />}
  </main>
}

function CreateUser({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<User['role']>('user')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return
    setBusy(true); setError('')
    try { await adminApi.createUser({ email, password, role }); setPassword(''); onCreated() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not create user') }
    finally { setBusy(false) }
  }
  return <ActionDialog title="Create user" busy={busy} onClose={onClose}><form className="admin-user-form" onSubmit={(event) => void submit(event)}>
    <label>Email<input type="email" autoComplete="off" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
    <label>Initial password<input type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
    <label htmlFor="admin-new-role">Role</label><select id="admin-new-role" value={role} onChange={(event) => setRole(event.target.value as User['role'])}><option value="user">User</option><option value="admin">Admin</option></select>
    <p>Share the initial password securely. It is never included in activity logs.</p>{error && <p role="alert">{error}</p>}
    <footer><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button disabled={busy}>{busy ? 'Creating…' : 'Create account'}</button></footer>
  </form></ActionDialog>
}

function ChatInspector({ chat, onClose, onSource }: { chat: AdminChat; onClose: () => void; onSource: (citation: Citation) => void }) {
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page<ChatMessage> | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    void adminApi.messages(chat.id, page).then((result) => { if (active) setData(result) })
      .catch((caught: unknown) => { if (active) setError(caught instanceof Error ? caught.message : 'Could not load messages') })
    return () => { active = false }
  }, [chat.id, page])
  return <ActionDialog title={chat.title || 'Conversation'} onClose={onClose} wide><p>Owner: {chat.owner_email}</p>
    {error ? <p role="alert">{error}</p> : !data || data.page !== page ? <p role="status">Loading messages…</p> : <>
      {data.items.length === 0 && <p>No messages.</p>}{data.items.map((message) => <article className="admin-message" key={message.id}><strong>{message.role}</strong><p>{message.content}</p>
        {message.message_metadata?.citations?.map((citation) => <button key={citation.source_number} onClick={() => onSource(citation)}>View source {citation.source_number} · page {citation.page_number || '—'}</button>)}</article>)}
      <Pagination page={page} total={data.total} size={data.page_size} onPage={setPage} />
    </>}
  </ActionDialog>
}
