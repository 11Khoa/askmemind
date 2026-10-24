import { LoaderCircle, Paperclip, Send } from 'lucide-react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { useAutoResizeTextarea } from '../hooks/useAutoResizeTextarea'

type ComposerProps = {
  question: string
  sending: boolean
  documentsCount: number
  selectedDocumentName?: string
  onQuestionChange: (value: string) => void
  onSend: () => void
  onStop: () => void
}

export function Composer({
  question,
  sending,
  documentsCount,
  selectedDocumentName,
  onQuestionChange,
  onSend,
  onStop,
}: ComposerProps) {
  const { t } = useTranslation()
  const inputRef = useAutoResizeTextarea(question)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSend()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      onSend()
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <textarea ref={inputRef} rows={1} value={question} maxLength={8000}
        onChange={(event) => onQuestionChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={documentsCount
          ? t('chat.askDocumentsPlaceholder')
          : t('chat.uploadToAskPlaceholder')}
        disabled={sending} />
      <div className="composer-foot">
        <div className="composer-source">
          <Paperclip size={15} />
          <span>{selectedDocumentName ||
            (documentsCount ? t('chat.selectedAllDocuments') : t('chat.noDocumentsYet'))}</span>
        </div>
        {sending ? (
          <button type='button' className='send-button' title={t('chat.stopGenerating')} onClick={onStop}>
            <LoaderCircle size={15} />
          </button>
        ) : (
          <button className="send-button" title={t('chat.sendQuestion')}
            disabled={!question.trim()}>
              <Send size={17} />
          </button>
        )

        }
      </div>
    </form>
  )
}
