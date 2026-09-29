import { BookOpenText, LoaderCircle } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, ApiError } from '../lib/api'
import { MAX_FILE_SIZE_MB, MAX_FILE_SIZE_BYTES } from "../lib/constants";
import type {
  Chat,
  ChatMessage,
  Document,
  DocumentStatusEvent,
  User,
} from '../lib/types'
import { ConversationHeader } from './components/ConversationHeader'
import { Composer } from './components/Composer'
import { DocumentsPanel } from './components/DocumentsPanel'
import { MessageList } from './components/MessageList'
import { NoticeBanner } from './components/NoticeBanner'
import { Sidebar } from './components/Sidebar'
import type { Notice } from './types'

type WorkspaceProps = { token: string; onLogout: () => void }

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
  }
}

export function Workspace({ token, onLogout }: WorkspaceProps) {
  const { t } = useTranslation()
  const [user, setUser] = useState<User | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const documentsRef = useRef<Document[]>([])
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

  const handleError = useCallback((caught: unknown) => {
    if (caught instanceof ApiError && caught.status === 401) {
      onLogout()
      return
    }
    setNotice({
      kind: 'error',
      message: caught instanceof Error ? caught.message : t('common.genericError'),
    })
  }, [onLogout, t])

  useEffect(() => {
    documentsRef.current = documents
  }, [documents])

  useEffect(() => {
    async function loadWorkspace() {
      try {
        const [currentUser, currentDocuments, currentChats] = await Promise.all([
          api.me(token), api.listDocuments(token), api.listChats(token),
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
  }, [handleError, token])

  useEffect(() => api.subscribeDocumentEvents(
    token,
    (event) => {
      const currentDocument = documentsRef.current.find(
        (document) => document.id === event.document_id,
      )
      if (!currentDocument) return

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
    },
    handleError,
  ), [handleError, t, token])

  useEffect(() => {
    if (!selectedChatId) return
    let active = true
    api.listMessages(token, selectedChatId)
      .then((result) => { if (active) setMessages(result) })
      .catch((caught) => { if (active) handleError(caught) })
      .finally(() => { if (active) setLoadingMessages(false) })
    return () => { active = false }
  }, [handleError, selectedChatId, token])

  function selectChat(chatId: string) {
    setLoadingMessages(true)
    setSelectedChatId(chatId)
    setSidebarOpen(false)
    setCitationOpen(null)
  }

  async function createChat(title: string | null = null) {
    try {
      const chat = await api.createChat(token, title)
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

    try {
      await api.streamQuestion(
        token,
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
      )
    } catch (caught) {
      setMessages((current) => current.filter((message) => (
        message.id !== optimisticUserId && message.id !== streamingAssistantId
      )))
      setQuestion(content)
      handleError(caught)
    } finally {
      setSending(false)
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
      const document = await api.uploadDocument(token, file)
      setDocuments((current) => {
        const nextDocuments = [
          document,
          ...current.filter((item) => item.id !== document.id),
        ]
        documentsRef.current = nextDocuments
        return nextDocuments
      })
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
    } catch (caught) {
      handleError(caught)
    } finally {
      setUploading(false)
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
        onNewChat={() => void createChat()}
        onSelectChat={selectChat}
        onLogout={onLogout}
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
          />
        </div>
        <p className="composer-hint">{t('workspace.composerHint')}</p>
      </section>

      <DocumentsPanel
        documents={documents}
        selectedDocumentId={selectedDocumentId}
        open={documentsOpen}
        uploading={uploading}
        onClose={() => setDocumentsOpen(false)}
        onSelectDocument={setSelectedDocumentId}
        onUpload={(file) => void uploadDocument(file)}
      />
    </main>
  )
}
