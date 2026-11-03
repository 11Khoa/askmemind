import { CalendarDays } from 'lucide-react'
import './uploadedAt.css'

const dateFormat = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Bangkok',
})
const timeFormat = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'Asia/Bangkok',
})

export function UploadedAt({ value, compact = false }: { value: string; compact?: boolean }) {
  const date = new Date(value)
  if (!value || Number.isNaN(date.getTime())) return <span className="uploaded-at">—</span>
  return <time className={`uploaded-at ${compact ? 'uploaded-at--compact' : ''}`} dateTime={value}
    title={`Uploaded at ${dateFormat.format(date)}, ${timeFormat.format(date)} GMT+7`}>
    {compact && <CalendarDays size={13} aria-hidden="true" />}
    <span>{compact && 'Uploaded at: '}{dateFormat.format(date)}{compact ? ' · ' : <br />}
      <span className="uploaded-at-time">{timeFormat.format(date)} GMT+7</span></span>
  </time>
}
