import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../lib/api'
import { adminApi } from '../lib/admin'
import type { AdminTab, AdminRow, AdminDocument, AdminChat, AuditEvent, Page } from '../lib/admin'
import type { User, Citation, ChatMessage } from '../lib/types'
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
  const [actionError, setActionError] = useState('')
  const [source, setSource] = useState<{ citation: Citation; filename: string; documentOnly: boolean } | null>(null)
  const [chat, setChat] = useState<AdminChat | null>(null)

  useEffect(() => {
    let active = true
    void adminApi.list(tab, page, query, owner?.id || '').then((data) => {
      if (active) setResult({ key, data })
    }).catch((caught: unknown) => {
      if (active) setError({ key, message: caught instanceof Error ? caught.message : 'Could not load administration data' })
    })
    return () => { active = false }
  }, [key, tab, page, query, owner?.id])

  function changeTab(next: AdminTab) { setTab(next); setPage(1); setSearch(''); setQuery('') }
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

  return <main className="admin-shell">
    <header className="admin-header"><div><p className="eyebrow">AskMeMind</p><h1>Administration</h1></div>
      <button onClick={onBack}>Back to workspace</button></header>
    <p className="admin-notice">Administrator access: you can inspect all users’ documents, conversations and recorded activity. Your actions are audited.</p>
    <nav className="admin-tabs" aria-label="Administration sections">{(['users', 'documents', 'chats', 'activity'] as const).map((item) =>
      <button key={item} aria-current={tab === item ? 'page' : undefined} onClick={() => changeTab(item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}</nav>
    <div className="admin-toolbar"><form onSubmit={(event) => { event.preventDefault(); setQuery(search); setPage(1) }}>
      <input aria-label="Search administration" maxLength={100} placeholder={tab === 'users' ? 'Find email' : tab === 'activity' ? 'Find action' : 'Find name or title'} value={search} onChange={(event) => setSearch(event.target.value)} />
      <button type="submit">Search</button></form>
      <button onClick={() => setRevision((value) => value + 1)}>Refresh</button>
      {tab === 'users' && <button onClick={() => setCreateOpen(true)}>Create user</button>}
    </div>
    {owner && tab !== 'users' && <p className="admin-filter">Showing user: {owner.email} <button onClick={() => { setOwner(null); setPage(1) }}>Clear user filter</button></p>}
    {currentError ? <p role="alert">{currentError}</p> : !data ? <p role="status">Loading administration…</p> : <>
      {data.items.length === 0 ? <p>No records found.</p> : <div className="admin-table-wrap" role="region" aria-label="Administration records" tabIndex={0}><table>
        <thead><tr>{(tab === 'users' ? ['Email', 'Role', 'Status', 'Actions'] : tab === 'activity' ? ['Time', 'Actor / target', 'Action', 'Result', 'Resource / request'] : ['Owner', tab === 'documents' ? 'Document' : 'Conversation', 'Status / updated', 'Actions']).map((label) => <th key={label}>{label}</th>)}</tr></thead>
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
            return <tr key={document.id}><td>{document.owner_email}</td><td>{document.original_filename}<small>{document.id}</small></td><td>{document.status}</td><td className="admin-actions">
              <button onClick={() => openDocument(document)}>View PDF</button><button className="danger-text" onClick={() => ask({ kind: 'document', id: document.id, name: `${document.original_filename} (${document.owner_email})` })}>Delete document</button></td></tr>
          }
          const conversation = row as AdminChat
          return <tr key={conversation.id}><td>{conversation.owner_email}</td><td>{conversation.title || 'Untitled conversation'}</td><td>{new Date(conversation.updated_at).toLocaleString()}</td><td className="admin-actions">
            <button onClick={() => setChat(conversation)}>View messages</button><button className="danger-text" onClick={() => ask({ kind: 'chat', id: conversation.id, name: `${conversation.title || 'Conversation'} (${conversation.owner_email})` })}>Delete conversation</button></td></tr>
        })}</tbody></table></div>}
      <Pagination page={page} total={data.total} size={data.page_size} onPage={setPage} />
    </>}
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
