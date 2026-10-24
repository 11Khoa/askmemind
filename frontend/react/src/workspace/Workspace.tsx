import { BookOpenText, LoaderCircle } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, ApiError, isAbortError } from '../lib/api'
import { MAX_FILE_SIZE_MB, MAX_FILE_SIZE_BYTES } from "../lib/constants";
import type {
  Chat,
  Citation,
  ChatMessage,
  Document,
  DocumentStatusEvent,
  User,
} from '../lib/types'
import { ConversationHeader } from './components/ConversationHeader'
import { ActionDialog } from './components/ActionDialog'
import { SourceViewer } from './components/SourceViewer'
import { Composer } from './components/Composer'
import { DocumentsPanel } from './components/DocumentsPanel'
import { MessageList } from './components/MessageList'
import { NoticeBanner } from './components/NoticeBanner'
import { Sidebar } from './components/Sidebar'
import { NewChatModal } from "./components/NewChatModal";
import type { Notice } from './types'

type WorkspaceProps = { onLogout: () => void; onAdmin: () => void }

const READY_STATUSES = new Set(['ready', 'completed'])
const FAILED_STATUSES = new Set(['processing_failed', 'failed'])

function isReadyDocument(document: Document) {
  return READY_STATUSES.has(document.status)
}

function applyDocumentEvent(document: Document, event: DocumentStatusEvent): Document {
  return {
    ...document,
    status: event.status,
    page_count: event.page_count ?? document.page_count,
    error_message: event.error_message,
    processing_attempt_id: event.processing_attempt_id ?? document.processing_attempt_id,
    updated_at: event.updated_at ?? document.updated_at,
  }
}

export function Workspace({ onLogout, onAdmin }: WorkspaceProps) {
  const { t } = useTranslation()
  const [user, setUser] = useState<User | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const documentsRef = useRef<Document[]>([])
  const documentEventsRef = useRef(new Map<string, DocumentStatusEvent>())
  const retryingRef = useRef(new Set<string>())
  const [retryingIds, setRetryingIds] = useState<ReadonlySet<string>>(new Set())
  const abortRef = useRef<AbortController | null>(null)
  const [chats, setChats] = useState<Chat[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [topK, setTopK] = useState(5)
  const [loading, setLoading] = useState(true)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [sending, setSending] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [documentsOpen, setDocumentsOpen] = useState(true)
  const [citationOpen, setCitationOpen] = useState<string | null>(null)
  const [newChatOpen, setNewChatOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ kind: 'chat' | 'document'; id: string; name: string } | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [viewSource, setViewSource] = useState<Citation | null>(null)


  const handleError = useCallback((caught: unknown) => {
    if (caught instanceof ApiError && caught.status === 401) {
      return
    }
    setNotice({
      kind: 'error',
      message: caught instanceof Error ? caught.message : t('common.genericError'),
    })
  }, [t])

  useEffect(() => {
    documentsRef.current = documents
  }, [documents])

  useEffect(() => {
    async function loadWorkspace() {
      try {
        const [currentUser, currentDocuments, currentChats] = await Promise.all([
          api.me(), api.listDocuments(), api.listChats(),
        ])
        setUser(currentUser)
        setDocuments(currentDocuments)
        setChats(currentChats)
        setSelectedDocumentId(
          currentDocuments.find(isReadyDocument)?.id || null,
        )
        if (currentChats.length > 0) {
          setLoadingMessages(true)
          setSelectedChatId(currentChats[0].id)
        }
      } catch (caught) {
        handleError(caught)
      } finally {
        setLoading(false)
      }
    }
    void loadWorkspace()
  }, [handleError])

  const receiveDocumentEvent = useCallback((event: DocumentStatusEvent) => {
    const currentDocument = documentsRef.current.find(
      (document) => document.id === event.document_id,
    )
    const eventTime = event.updated_at ? Date.parse(event.updated_at) : null
    const currentTime = currentDocument ? Date.parse(currentDocument.updated_at) : null
    if (eventTime !== null && currentTime !== null && eventTime < currentTime) return
    const cached = documentEventsRef.current.get(event.document_id)
    if (!cached?.updated_at || eventTime === null || eventTime >= Date.parse(cached.updated_at)) {
      documentEventsRef.current.set(event.document_id, event)
    }
    if (!currentDocument) return
    const sameAttempt = event.processing_attempt_id === undefined ||
      event.processing_attempt_id === currentDocument.processing_attempt_id
    // A newer attempt may have been initiated in another browser tab.
    if (!sameAttempt && !(eventTime !== null && currentTime !== null && eventTime > currentTime)) return
    if (sameAttempt && currentDocument.status === event.status) return
    if (sameAttempt && event.status === 'processing' &&
        (READY_STATUSES.has(currentDocument.status) || FAILED_STATUSES.has(currentDocument.status))) return

    const updatedDocument = applyDocumentEvent(currentDocument, event)
    documentsRef.current = documentsRef.current.map((document) => (
      document.id === event.document_id ? updatedDocument : document
    ))
    setDocuments(documentsRef.current)

    if (READY_STATUSES.has(event.status)) {
      setSelectedDocumentId((current) => current || event.document_id)
      setNotice({
        kind: 'success',
        message: t('documents.readyToSearch', {
          filename: updatedDocument.original_filename,
        }),
      })
    } else if (FAILED_STATUSES.has(event.status)) {
      setNotice({
        kind: 'error',
        message: t('documents.failedToProcess', {
          filename: updatedDocument.original_filename,
        }),
      })
    }
  }, [t])

  useEffect(() => api.subscribeDocumentEvents(receiveDocumentEvent, handleError),
    [receiveDocumentEvent, handleError])

  useEffect(() => {
    const processing = documents.filter((document) => document.status === 'processing')
    if (processing.length === 0) return
    let active = true
    let polling = false
    // Redis Pub/Sub is not replayed: reconcile missed events after reconnect/reload.
    const timer = window.setInterval(async () => {
      if (polling) return
      polling = true
      try {
        const latest = await Promise.all(processing.map((document) => api.getDocument(document.id)))
        if (active) latest.forEach((document) => receiveDocumentEvent({
          document_id: document.id,
          processing_attempt_id: document.processing_attempt_id,
          status: document.status,
          page_count: document.page_count,
          error_message: document.error_message,
          updated_at: document.updated_at,
        }))
      } catch (caught) {
        if (active) handleError(caught)
      } finally {
        polling = false
      }
    }, 2000)
    return () => { active = false; window.clearInterval(timer) }
  }, [documents, receiveDocumentEvent, handleError])

  useEffect(() => {
    if (!selectedChatId) return
    let active = true
    api.listMessages(selectedChatId)
      .then((result) => { if (active) setMessages(result) })
      .catch((caught) => { if (active) handleError(caught) })
      .finally(() => { if (active) setLoadingMessages(false) })
    return () => { active = false }
  }, [handleError, selectedChatId])

  useEffect(() => () => abortRef.current?.abort(), [])

  function stopStreaming() {
    abortRef.current?.abort()
  }

  function selectChat(chatId: string) {
    setLoadingMessages(true)
    setSelectedChatId(chatId)
    setSidebarOpen(false)
    setCitationOpen(null)
  }

  async function createNamedChat(title: string | null) {
    setNewChatOpen(false)
    await createChat(title)
  }

  async function createChat(title: string | null = null) {
    try {
      const chat = await api.createChat(title)
      setChats((current) => [chat, ...current])
      setSelectedChatId(chat.id)
      setMessages([])
      setSidebarOpen(false)
      return chat
    } catch (caught) {
      handleError(caught)
      return null
    }
  }

  async function sendQuestion() {
    const content = question.trim()
    if (!content || sending) return
    setQuestion('')
    setNotice(null)
    setSending(true)

    let chatId = selectedChatId
    if (!chatId) {
      const created = await createChat(content.slice(0, 64))
      chatId = created?.id || null
    }
    if (!chatId) {
      setSending(false)
      setQuestion(content)
      return
    }

    const createdAt = new Date().toISOString()
    const messageIndex = messages.length
    const optimisticUserId = `optimistic-user-${Date.now()}`
    const streamingAssistantId = `streaming-assistant-${Date.now()}`
    const optimistic: ChatMessage = {
      id: optimisticUserId,
      chat_id: chatId,
      message_index: messageIndex,
      role: 'user',
      content,
      message_metadata: null,
      created_at: createdAt,
    }
    const streamingAssistant: ChatMessage = {
      id: streamingAssistantId,
      chat_id: chatId,
      message_index: messageIndex + 1,
      role: 'assistant',
      content: '',
      message_metadata: null,
      created_at: createdAt,
    }
    setMessages((current) => [...current, optimistic, streamingAssistant])

    const controller = new AbortController()
    abortRef.current = controller

    try {
      await api.streamQuestion(
        chatId,
        content,
        selectedDocumentId,
        topK,
        {
          onToken: (chunk) => {
            setMessages((current) => current.map((message) => (
              message.id === streamingAssistantId
                ? { ...message, content: message.content + chunk }
                : message
            )))
          },
          onReplace: (replacement) => {
            setMessages((current) => current.map((message) => (
              message.id === streamingAssistantId
                ? { ...message, content: replacement }
                : message
            )))
          },
          onFinal: (answer) => {
            setMessages((current) => current.map((message) => (
              message.id === streamingAssistantId ? answer : message
            )))
          },
        },
        controller.signal
      )
    } catch (caught) {
      if(isAbortError(caught)){
        setMessages((current) => current.filter((message) => !(message.id === streamingAssistantId && message.content === '')))
        return
      }
      setMessages((current) => current.filter((message) => (
        message.id !== optimisticUserId && message.id !== streamingAssistantId
      )))
      setQuestion(content)
      handleError(caught)
    } finally {
      setSending(false)
      if(abortRef.current === controller) abortRef.current = null
    }
  }

  async function uploadDocument(file: File) {
    if (file.type !== 'application/pdf') {
      setNotice({ kind: 'error', message: t('documents.choosePdf') })
      return
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setNotice({ kind: 'error', message: t('documents.pdfTooLarge', {fileLimit: MAX_FILE_SIZE_MB}) })
      return
    }

    setUploading(true)
    setNotice(null)
    try {
      const document = await api.uploadDocument(file)
      const nextDocuments = [document, ...documentsRef.current.filter((item) => item.id !== document.id)]
      documentsRef.current = nextDocuments
      setDocuments(nextDocuments)
      if (isReadyDocument(document)) {
        setSelectedDocumentId(document.id)
        setNotice({
          kind: 'success',
          message: t('documents.readyToSearch', {
            filename: document.original_filename,
          }),
        })
      } else {
        setNotice({
          kind: 'success',
          message: t('documents.processingStarted', {
            filename: document.original_filename,
          }),
        })
      }
      const event = documentEventsRef.current.get(document.id)
      if (event) receiveDocumentEvent(event)
    } catch (caught) {
      handleError(caught)
      try {
        const latest = await api.listDocuments()
        documentsRef.current = latest
        setDocuments(latest)
      } catch { /* The original upload error remains visible. */ }
    } finally {
      setUploading(false)
    }
  }

  async function retryDocument(documentId: string) {
    if (retryingRef.current.has(documentId)) return
    retryingRef.current.add(documentId)
    setRetryingIds(new Set(retryingRef.current))
    documentEventsRef.current.delete(documentId)
    setNotice(null)
    try {
      const document = await api.retryDocument(documentId)
      const next = documentsRef.current.map((item) => item.id === documentId ? document : item)
      documentsRef.current = next
      setDocuments(next)
      setNotice({ kind: 'success', message: t('documents.processingStarted', {
        filename: document.original_filename,
      }) })
      // A short job may finish and emit SSE before the 202 response arrives.
      const event = documentEventsRef.current.get(documentId)
      if (event) receiveDocumentEvent(event)
    } catch (caught) {
      handleError(caught)
      // Includes an ambiguous network failure after the server accepted the retry.
      try {
        const document = await api.getDocument(documentId)
        const next = documentsRef.current.map((item) => item.id === documentId ? document : item)
        documentsRef.current = next
        setDocuments(next)
      } catch { /* Keep the failed row available for another attempt. */ }
    } finally {
      retryingRef.current.delete(documentId)
      setRetryingIds(new Set(retryingRef.current))
    }
  }

  if (loading) {
    return (
      <main className="loading-screen">
        <span className="brand-mark"><BookOpenText size={21} /></span>
        <LoaderCircle className="spin" size={25} />
        <p>{t('workspace.loading')}</p>
      </main>
    )
  }

  async function confirmDelete() {
    if (!deleteTarget || deleting) return
    setDeleting(true)
    setDeleteError('')
    try {
      if (deleteTarget.kind === 'chat') {
        await api.deleteChat(deleteTarget.id)
        setChats((current) => current.filter((chat) => chat.id !== deleteTarget.id))
        if (selectedChatId === deleteTarget.id) { setSelectedChatId(null); setMessages([]) }
      } else {
        await api.deleteDocument(deleteTarget.id)
        setDocuments((current) => current.filter((document) => document.id !== deleteTarget.id))
        documentEventsRef.current.delete(deleteTarget.id)
        if (selectedDocumentId === deleteTarget.id) setSelectedDocumentId(null)
        // Remove cached source material immediately, including before resync.
        setMessages((current) => current.map((message) => ({ ...message,
          message_metadata: message.message_metadata ? {
            ...message.message_metadata, context: '',
            citations: message.message_metadata.citations?.filter((citation) => citation.document_id !== deleteTarget.id),
          } : null,
        })))
      }
      setDeleteTarget(null)
    } catch (caught) {
      setDeleteError(caught instanceof Error ? caught.message : t('common.genericError'))
    } finally { setDeleting(false) }
  }

  const currentChat = chats.find((chat) => chat.id === selectedChatId)
  const selectedDocument = documents.find(
    (document) => document.id === selectedDocumentId,
  )
  const streamingHasContent = messages.some((message) => (
    message.id.startsWith('streaming-assistant-') && message.content.length > 0
  ))

  return (
    <main className="workspace">
      {sidebarOpen && (
        <button className="mobile-scrim" aria-label={t('common.closeNavigation')}
          onClick={() => setSidebarOpen(false)} />
      )}

      <Sidebar
        user={user}
        chats={chats}
        selectedChatId={selectedChatId}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => void setNewChatOpen(true)}
        onSelectChat={selectChat}
        onLogout={onLogout}
        onAdmin={onAdmin}
        busy={sending || deleting}
        onDeleteChat={(chat) => { setDeleteError(''); setDeleteTarget({ kind: 'chat', id: chat.id, name: chat.title || t('chat.untitledConversation') }) }}
      />

      <section className="conversation">
        <ConversationHeader
          title={currentChat?.title || t('workspace.newConversation')}
          sourceName={selectedDocument?.original_filename || t('workspace.allDocumentsSearch')}
          topK={topK}
          documentsOpen={documentsOpen}
          onOpenNavigation={() => setSidebarOpen(true)}
          onTopKChange={setTopK}
          onToggleDocuments={() => setDocumentsOpen((current) => !current)}
        />

        <MessageList
          loading={loadingMessages}
          sending={sending && !streamingHasContent}
          messages={messages}
          documents={documents}
          selectedDocumentName={selectedDocument?.original_filename}
          expandedCitation={citationOpen}
          onSuggestion={setQuestion}
          onToggleCitation={setCitationOpen}
          onViewSource={setViewSource}
        />
        <div className='conversation-last'>
          <NoticeBanner notice={notice} onDismiss={() => setNotice(null)} />

          <Composer
            question={question}
            sending={sending}
            documentsCount={documents.length}
            selectedDocumentName={selectedDocument?.original_filename}
            onQuestionChange={setQuestion}
            onSend={() => void sendQuestion()}
            onStop={stopStreaming}
          />
        </div>
        <p className="composer-hint">{t('workspace.composerHint')}</p>
      </section>

      <DocumentsPanel
        documents={documents}
        selectedDocumentId={selectedDocumentId}
        open={documentsOpen}
        uploading={uploading}
        retryingIds={retryingIds}
        canDelete={user?.role === 'admin'}
        busy={sending || deleting}
        onDelete={(document) => { setDeleteError(''); setDeleteTarget({ kind: 'document', id: document.id, name: document.original_filename }) }}
        onClose={() => setDocumentsOpen(false)}
        onSelectDocument={setSelectedDocumentId}
        onUpload={(file) => void uploadDocument(file)}
        onRetry={(documentId) => void retryDocument(documentId)}
      />

      {deleteTarget && <ActionDialog title={t('deletion.title', { name: deleteTarget.name })}
        busy={deleting} onClose={() => setDeleteTarget(null)}>
        <p>{t(`deletion.${deleteTarget.kind}`)}</p>
        {deleteError && <p role="alert">{deleteError}</p>}
        <footer><button disabled={deleting} onClick={() => setDeleteTarget(null)}>{t('deletion.cancel')}</button>
          <button className="danger-button" disabled={deleting} onClick={() => void confirmDelete()}>
            {t(deleting ? 'deletion.working' : 'deletion.confirm')}
          </button></footer>
      </ActionDialog>}
      {viewSource && <SourceViewer citation={viewSource}
        filename={documents.find((document) => document.id === viewSource.document_id)?.original_filename || t('chat.sourceFallback')}
        onClose={() => setViewSource(null)} />}
      <NewChatModal
        open={newChatOpen}
        onClose={() => setNewChatOpen(false)}
        onCreate={(title) => void createNamedChat(title)}
      />
    </main>
  )
}
