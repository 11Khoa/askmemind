import {
  BookOpenText, ChevronDown, ChevronRight, LoaderCircle,
} from 'lucide-react'
import { useLayoutEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { ChatMessage, Citation, Document } from '../../lib/types'

type MessageListProps = {
  loading: boolean
  sending: boolean
  messages: ChatMessage[]
  documents: Document[]
  selectedDocumentName?: string
  expandedCitation: string | null
  onSuggestion: (question: string) => void
  onToggleCitation: (id: string | null) => void
}

export function MessageList({
  loading,
  sending,
  messages,
  documents,
  selectedDocumentName,
  expandedCitation,
  onSuggestion,
  onToggleCitation,
}: MessageListProps) {
  const { t } = useTranslation()
  const listRef = useRef<HTMLElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)

  function updateStickToBottom() {
    const list = listRef.current
    if (!list) return
    const distanceFromBottom = list.scrollHeight - list.scrollTop - list.clientHeight
    stickToBottomRef.current = distanceFromBottom < 96
  }

  useLayoutEffect(() => {
    const list = listRef.current
    if (!list || !stickToBottomRef.current) return
    list.scrollTop = list.scrollHeight
  }, [messages, sending])

  return (
    <section ref={listRef} className="message-list" aria-live="polite"
      onScroll={updateStickToBottom}>
      {loading ? (
        <div className="message-loading">
          <LoaderCircle className="spin" size={20} /> {t('chat.loadingConversation')}
        </div>
      ) : messages.length === 0 ? (
        <EmptyConversation documentName={selectedDocumentName}
          onSuggestion={onSuggestion} />
      ) : messages.map((message) => (
        <Message key={message.id} message={message} documents={documents}
          expandedCitation={expandedCitation}
          onToggleCitation={onToggleCitation} />
      ))}

      {sending && (
        <div className="message-row assistant-message">
          <div className="assistant-mark"><BookOpenText size={16} /></div>
          <div className="thinking">
            <span /><span /><span /><em>{t('chat.searchingSources')}</em>
          </div>
        </div>
      )}
      <div ref={endRef} />
    </section>
  )
}

function EmptyConversation({
  documentName,
  onSuggestion,
}: {
  documentName?: string
  onSuggestion: (question: string) => void
}) {
  const { t } = useTranslation()
  const suggestions = t('chat.suggestions', { returnObjects: true }) as string[]

  return (
    <div className="empty-conversation">
      <span className="empty-mark"><BookOpenText size={25} /></span>
      <h2>{t('chat.emptyTitle')}</h2>
      <p>{documentName
        ? t('chat.emptyWithDocument', { documentName })
        : t('chat.emptyWithoutDocument')}</p>
      <div className="suggestions">
        {suggestions.map((suggestion) => (
          <button key={suggestion} onClick={() => onSuggestion(suggestion)}>
            {suggestion}<ChevronRight size={15} />
          </button>
        ))}
      </div>
    </div>
  )
}

function Message({
  message,
  documents,
  expandedCitation,
  onToggleCitation,
}: {
  message: ChatMessage
  documents: Document[]
  expandedCitation: string | null
  onToggleCitation: (id: string | null) => void
}) {
  const { t } = useTranslation()

  if (message.role === 'user') {
    return (
      <div className="message-row user-message">
        <div className="message-content">{message.content}</div>
      </div>
    )
  }

  const citations = message.message_metadata?.citations || []
  return (
    <div className="message-row assistant-message">
      <div className="assistant-mark"><BookOpenText size={16} /></div>
      <div className="assistant-content">
        <div className="message-content markdown-content">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({href, children}) => (
                <a
                  href={href}
                  target='_blank'
                  rel='noopener noreferrer'
                >
                  {children}
                </a>
              ),
              img: () => null,
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
        {citations.length > 0 && (
          <div className="citations">
            <p>{t('chat.sources')}</p>
            {citations.map((citation) => {
              const key = `${message.id}-${citation.source_number}`
              return (
                <CitationItem key={key} citation={citation}
                  document={documents.find(
                    (item) => item.id === citation.document_id,
                  )}
                  expanded={expandedCitation === key}
                  onToggle={() => onToggleCitation(
                    expandedCitation === key ? null : key,
                  )} />
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function CitationItem({
  citation,
  document,
  expanded,
  onToggle,
}: {
  citation: Citation
  document?: Document
  expanded: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()

  return (
    <button className="citation" onClick={onToggle}>
      <span className="citation-number">{citation.source_number}</span>
      <span className="citation-copy">
        <strong>{document?.original_filename || t('chat.sourceFallback')}</strong>
        <small>
          {citation.page_number
            ? t('chat.page', { pageNumber: citation.page_number })
            : t('chat.pageUnavailable')}
          {' - '}{t('chat.chunk', { chunkNumber: citation.chunk_index + 1 })}
        </small>
        {expanded && (
          <em>{t('chat.evidenceUsed')}
            {citation.distance !== null
              ? ` - ${t('chat.distance', { distance: citation.distance.toFixed(3) })}`
              : ''}
          </em>
        )}
      </span>
      <ChevronDown className={expanded ? 'is-rotated' : ''} size={16} />
    </button>
  )
}