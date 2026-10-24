import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function ActionDialog({ title, onClose, busy = false, children, wide = false }: {
  title: string; onClose: () => void; busy?: boolean; children: ReactNode; wide?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const { t } = useTranslation()
  useEffect(() => {
    const dialog = ref.current
    const previous = document.activeElement as HTMLElement | null
    dialog?.showModal()
    return () => { dialog?.close(); previous?.focus() }
  }, [])
  return (
    <dialog ref={ref} className={`action-dialog ${wide ? 'action-dialog--wide' : ''}`}
      aria-labelledby="action-dialog-title"
      onCancel={(event) => { event.preventDefault(); if (!busy) onClose() }}>
      <header><h2 id="action-dialog-title">{title}</h2>
        <button className="icon-button" aria-label={t('common.close')} disabled={busy} onClick={onClose}>
          <X size={18} />
        </button>
      </header>
      {children}
    </dialog>
  )
}
