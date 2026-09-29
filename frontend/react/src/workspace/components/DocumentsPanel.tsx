import {
  ChevronRight, FileText, Library, LoaderCircle, Search, Upload, X,
} from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useTranslation } from 'react-i18next'

import type { Document } from '../../lib/types'

type DocumentsPanelProps = {
  documents: Document[]
  selectedDocumentId: string | null
  open: boolean
  uploading: boolean
  onClose: () => void
  onSelectDocument: (documentId: string | null) => void
  onUpload: (file: File) => void
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
  onClose,
  onSelectDocument,
  onUpload,
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
          return (
            <button key={document.id}
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
        <span>{t('documents.uploadLimit')}</span>
      </div>
    </aside>
  )
}