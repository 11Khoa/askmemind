import {
  ChevronRight, FileText, Library, LoaderCircle, RotateCw, Search, Upload, X, Trash2, Square,
} from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useTranslation } from 'react-i18next'

import type { DocumentConnectionState } from '../../lib/documentEvents'
import type { Document } from '../../lib/types'
import { MAX_FILE_SIZE_MB } from "../../lib/constants";
import { DocumentProcessingFeedback } from './DocumentProcessingFeedback'

type DocumentsPanelProps = {
  documents: Document[]
  selectedDocumentId: string | null
  open: boolean
  uploading: boolean
  retryingIds: ReadonlySet<string>
  cancellingIds: ReadonlySet<string>
  onCancel: (documentId: string) => void
  onClose: () => void
  onSelectDocument: (documentId: string | null) => void
  onUpload: (file: File) => void
  onRetry: (documentId: string) => void
  onDelete: (document: Document) => void
  busy: boolean
  connectionState: DocumentConnectionState
  canDelete: boolean
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function DocumentsPanel({
  documents,
  selectedDocumentId,
  open,
  uploading,
  retryingIds,
  cancellingIds,
  onCancel,
  onClose,
  onSelectDocument,
  onUpload,
  onRetry,
  onDelete,
  busy,
  canDelete,
  connectionState,
}: DocumentsPanelProps) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const filteredDocuments = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    if (!normalizedQuery) return documents
    return documents.filter((document) =>
      document.original_filename.toLocaleLowerCase().includes(normalizedQuery),
    )
  }, [documents, query])

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) onUpload(file)
  }

  return (
    <aside className={`documents-panel ${open ? 'is-open' : ''}`}>
      <div className="documents-head">
        <div><p className="eyebrow">{t('documents.knowledgeBase')}</p><h2>{t('documents.title')}</h2></div>
        <button className="icon-button panel-close" title={t('documents.close')}
          onClick={onClose}><X size={18} /></button>
      </div>

      <button className="upload-button"
        onClick={() => fileInputRef.current?.click()}
        disabled={uploading}>
        {uploading
          ? <LoaderCircle className="spin" size={17} />
          : <Upload size={17} />}
        {uploading ? t('documents.processingPdf') : t('documents.uploadPdf')}
      </button>
      <input ref={fileInputRef} type="file" accept="application/pdf,.pdf"
        hidden onChange={handleFileChange} />

      <label className="document-search">
        <Search size={16} />
        <input placeholder={t('documents.find')} aria-label={t('documents.find')}
          value={query}
          onChange={(event) => setQuery(event.target.value)} />
      </label>

      <div className="document-list">
        <button
          className={`document-item all-documents ${selectedDocumentId === null ? 'is-active' : ''}`}
          onClick={() => onSelectDocument(null)}>
          <span className="file-icon"><Library size={18} /></span>
          <span className="document-copy">
            <strong>{t('documents.allDocuments')}</strong>
            <small>{t('documents.sources', { count: documents.length })}</small>
          </span>
          <ChevronRight size={16} />
        </button>

        {filteredDocuments.map((document) => {
          const isReady = ['ready', 'completed'].includes(document.status)
          const cancelled = document.status === 'cancelled'
          const failed = ['processing_failed', 'failed', 'cancelled'].includes(document.status)
          const processing = ['processing', 'uploaded'].includes(document.status)
          const retrying = retryingIds.has(document.id)
          const cancelling = cancellingIds.has(document.id)
          return (
            <div key={document.id} className="document-row">
              <button
                disabled={!isReady}
                title={isReady ? undefined : t('documents.notReadyTitle')}
                className={`document-item ${selectedDocumentId === document.id ? 'is-active' : ''}`}
                onClick={() => onSelectDocument(document.id)}>
                <span className="file-icon"><FileText size={18} /></span>
                <span className="document-copy">
                  <strong>{document.original_filename}</strong>
                  <small>
                    {document.page_count ? `${t('documents.pages', { count: document.page_count })} - ` : ''}
                    {formatBytes(document.file_size_bytes)}
                  </small>
                  <span className={`status status--${document.status}`}>
                    {t(`documents.status.${document.status}`, document.status)}
                  </span>
                </span>
                <ChevronRight size={16} />
              </button>
              {failed && (
                <button className="document-retry" disabled={retrying}
                  title={t(cancelled ? 'documents.resumeTitle' : 'documents.retryTitle', { filename: document.original_filename })}
                  aria-label={t(cancelled ? 'documents.resumeTitle' : 'documents.retryTitle', { filename: document.original_filename })}
                  onClick={() => onRetry(document.id)}>
                  {retrying ? <LoaderCircle size={14} className="spin" /> : <RotateCw size={14} />}
                  {retrying ? t('documents.retrying') : t(cancelled ? 'documents.resume' : 'documents.retry')}
                </button>
              )}
              {processing && <button className="document-cancel" disabled={cancelling || retrying}
                aria-label={t('documents.cancelTitle', { filename: document.original_filename })}
                onClick={() => onCancel(document.id)}>
                {cancelling ? <LoaderCircle size={14} className="spin" /> : <Square size={13} />}
                {t(cancelling ? 'documents.cancelling' : 'documents.cancel')}
              </button>}
              {canDelete && <button className="icon-button delete-action" disabled={busy || retrying}
                aria-label={t('documents.deleteNamed', { filename: document.original_filename })}
                onClick={() => onDelete(document)}><Trash2 size={15} /></button>}
              <DocumentProcessingFeedback document={document} />
            </div>
          )
        })}

        {documents.length > 0 && filteredDocuments.length === 0 && (
          <div className="document-empty">
            <Search size={18} />
            <span>{t('documents.noMatches', { query: query.trim() })}</span>
          </div>
        )}
      </div>

      <div className="documents-foot">
        <strong>{t('documents.documentsCount', { count: documents.length })}</strong>
        {connectionState === 'reconnecting' && <span aria-live="polite">{t('documents.reconnecting')}</span>}
        <span>{t('documents.uploadLimit', {fileLimit: MAX_FILE_SIZE_MB})}</span>
      </div>
    </aside>
  )
}
