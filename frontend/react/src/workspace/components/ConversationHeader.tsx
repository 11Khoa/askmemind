import {
  Menu, PanelRightClose, PanelRightOpen, Settings2,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

type ConversationHeaderProps = {
  title: string
  sourceName: string
  topK: number
  documentsOpen: boolean
  onOpenNavigation: () => void
  onTopKChange: (value: number) => void
  onToggleDocuments: () => void
}

export function ConversationHeader({
  title,
  sourceName,
  topK,
  documentsOpen,
  onOpenNavigation,
  onTopKChange,
  onToggleDocuments,
}: ConversationHeaderProps) {
  const { t } = useTranslation()

  return (
    <header className="conversation-head">
      <button className="icon-button mobile-only" title={t('common.openNavigation')}
        onClick={onOpenNavigation}><Menu size={20} /></button>
      <div className="conversation-title">
        <h1>{title}</h1>
        <span>{sourceName}</span>
      </div>
      <div className="head-actions">
        <label className="top-k-control" title={t('controls.topKTitle')}>
          <Settings2 size={15} /><span>{t('controls.topK')}</span>
          <select value={topK}
            onChange={(event) => onTopKChange(Number(event.target.value))}>
            {[1, 3, 5, 8, 10].map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <button className="icon-button"
          title={documentsOpen ? t('controls.hideDocuments') : t('controls.showDocuments')}
          onClick={onToggleDocuments}>
          {documentsOpen
            ? <PanelRightClose size={19} />
            : <PanelRightOpen size={19} />}
        </button>
      </div>
    </header>
  )
}