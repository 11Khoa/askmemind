import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, isAbortError } from '../../lib/api'
import type { Citation } from '../../lib/types'
import { ActionDialog } from './ActionDialog'

export function SourceViewer({ citation, filename, onClose, documentOnly = false }: {
  citation: Citation; filename: string; onClose: () => void; documentOnly?: boolean
}) {
  const { t } = useTranslation()
  const [source, setSource] = useState<{ text: string; url: string; page: number } | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    let url: string | undefined
    let active = true
    const passageRequest = documentOnly ? Promise.resolve({ content: '', page_number: 1 })
      : api.sourcePassage(citation.document_id, citation.chunk_id)
    void passageRequest.then(async (passage) => {
      if (!active) return
      const page = passage.page_number || citation.page_number || 1
      setSource({ text: passage.content, url: '', page })
      const pdf = await api.documentPdf(citation.document_id, controller.signal)
      if (!active) return
      url = URL.createObjectURL(pdf)
      setSource({ text: passage.content, url, page })
    }).catch((caught: unknown) => {
      if (active && !isAbortError(caught)) setError(t('sources.unavailable'))
    })
    return () => { active = false; controller.abort(); if (url) URL.revokeObjectURL(url) }
  }, [citation, t, documentOnly])
  return (
    <ActionDialog title={filename} onClose={onClose} wide>
      {!source ? <p role={error ? 'alert' : 'status'}>{error || t('sources.loading')}</p> : <>
        <p className="source-page">{t('chat.page', { pageNumber: source.page })}</p>
        {source.text && <blockquote className="source-passage">{source.text}</blockquote>}
        {source.url ? <><a className="source-open" href={`${source.url}#page=${source.page}`} target="_blank" rel="noopener noreferrer">
          {t('sources.openPdf', { page: source.page })}
        </a>
        <iframe className="source-pdf" title={t('sources.pdfPreview')} src={`${source.url}#page=${source.page}`} /></>
          : <p role={error ? 'alert' : 'status'}>{error || t('sources.loading')}</p>}
      </>}
    </ActionDialog>
  )
}
