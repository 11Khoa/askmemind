import { CircleAlert, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { Notice } from '../types'

type NoticeBannerProps = {
  notice: Notice | null
  onDismiss: () => void
}

export function NoticeBanner({ notice, onDismiss }: NoticeBannerProps) {
  const { t } = useTranslation()

  if (!notice) return null

  return (
    <div className={`notice notice--${notice.kind}`} role="status">
      <CircleAlert size={16} />
      <span>{notice.message}</span>
      <button type="button" title={t('common.dismiss')} onClick={onDismiss}>
        <X size={15} />
      </button>
    </div>
  )
}