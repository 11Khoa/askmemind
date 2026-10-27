import { useTranslation } from 'react-i18next'
import { useEffect, useState } from 'react'
import type { Document, DocumentProcessingProgress } from '../../lib/types'
import { elapsedProcessingSeconds, formatProcessingDuration, processingErrorCode, stageCounter } from '../../lib/documentProgress'

function ProcessingElapsed({ progress, running }: { progress: DocumentProcessingProgress | null | undefined; running: boolean }) {
  const { t } = useTranslation()
  const [now, setNow] = useState(Date.now)
  const ticking = running && Boolean(progress?.started_at) && !progress?.finished_at
  useEffect(() => {
    if (!ticking) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [ticking, progress?.started_at])
  const seconds = elapsedProcessingSeconds(progress, now)
  if (seconds === null || (!running && !progress?.finished_at)) return null
  return <span className="document-elapsed" aria-live="off">
    {t(ticking ? 'documents.elapsed' : 'documents.duration', { duration: formatProcessingDuration(seconds) })}
  </span>
}

export function DocumentProcessingFeedback({ document }: { document: Document }) {
  const { t } = useTranslation()
  const failed = ['failed', 'processing_failed'].includes(document.status)
  const cancelled = document.status === 'cancelled'
  const processing = ['processing', 'uploaded'].includes(document.status)
  const progress = document.processing_progress
  if (!failed && !processing && !cancelled) return progress?.started_at && progress.finished_at
    ? <div className="document-feedback"><ProcessingElapsed progress={progress} running={false} /></div> : null
  const stage = progress?.stage || 'queued'
  const count = progress ? stageCounter(progress) : null
  const pages = progress?.completed_pages || 0
  return <div aria-live="polite" className={`document-feedback ${failed ? 'document-feedback--error' : ''}`}>
    {failed || cancelled ? <>
      <p className={failed ? 'document-error' : 'document-cancelled'}>{cancelled
        ? t('documents.cancelled') : t(`documents.errors.${processingErrorCode(document)}`)}</p>
      {pages > 0 && <small>{t('documents.progress.saved', { count: pages })}</small>}
    </> : <div>
      <p>{stage === 'ocr' || stage === 'extracting'
        ? t(`documents.progress.${stage}`, { page: progress?.current_page || pages, total: progress?.total_pages || '?' })
        : stage === 'embedding'
          ? t('documents.progress.embedding', { completed: count?.completed || 0, total: count?.total || '?' })
          : t(`documents.progress.${stage}`, t('documents.progress.queued'))}</p>
      {count && stage !== 'queued' && <progress aria-label={t('documents.progress.stageProgress')}
        max={count.total} value={count.completed} />}
      {(progress?.reused_pages || 0) > 0 && <small>{t('documents.progress.reused', { count: progress?.reused_pages })}</small>}
    </div>}
    <ProcessingElapsed progress={progress} running={processing} />
  </div>
}
