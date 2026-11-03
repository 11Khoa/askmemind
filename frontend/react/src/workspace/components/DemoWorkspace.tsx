import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api, ApiError } from '../../lib/api'
import { demoApi } from '../../lib/demo'
import type { DemoStatus } from '../../lib/demo'
import { ActionDialog } from './ActionDialog'
import './demo.css'

import { DemoContext, useDemo } from './demoContext'

export function DemoWorkspace({ children, onLogout }: { children: ReactNode; onLogout: () => void }) {
  const [phase, setPhase] = useState<'loading' | 'ready' | 'expired' | 'clearing' | 'cleanup_failed' | 'error'>('loading')
  const [status, setStatus] = useState<DemoStatus | null>(null)
  const [error, setError] = useState('')
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const pending = useRef<((accepted: boolean) => void) | null>(null)
  const expire = useCallback(() => {
    pending.current?.(false); pending.current = null
    setNoticeOpen(false); setDeleteOpen(false); setPhase('expired')
  }, [])

  useEffect(() => {
    let active = true
    void api.me().then(async (user) => {
      const data = user.is_demo ? await demoApi.status() : null
      if (active) { setStatus(data); setPhase('ready') }
    }).catch((caught: unknown) => {
      if (!active) return
      if (caught instanceof ApiError && caught.status === 410) setPhase('expired')
      else { setError(caught instanceof Error ? caught.message : 'Could not load account'); setPhase('error') }
    })
    return () => { active = false; pending.current?.(false); pending.current = null }
  }, [])

  useEffect(() => {
    if (phase !== 'ready' || !status?.expires_at) return
    const timer = setTimeout(expire, Math.max(0, Date.parse(status.expires_at) - Date.now()))
    return () => clearTimeout(timer)
  }, [status?.expires_at, phase, expire])

  useEffect(() => {
    if (!status?.is_demo || typeof BroadcastChannel === 'undefined') return
    const channel = new BroadcastChannel('askmemind-demo-reset')
    channel.onmessage = (event: MessageEvent<unknown>) => { if (event.data === 'reset') expire() }
    return () => channel.close()
  }, [status?.is_demo, expire])

  function notifyOtherTabs() {
    try {
      const channel = new BroadcastChannel('askmemind-demo-reset')
      channel.postMessage('reset'); channel.close()
    } catch { /* Session access is still enforced by the server. */ }
  }

  function closeNotice(accepted = false) {
    setNoticeOpen(false); pending.current?.(accepted); pending.current = null
  }
  async function beforeAction(upload = false): Promise<boolean> {
    if (!status?.is_demo) return true
    try {
      const latest = await demoApi.status()
      setStatus(latest)
      if (upload && !latest.upload_enabled) { setError('Admin đã tắt upload cho tài khoản demo này.'); return false }
      if (latest.notice_accepted) return true
      if (pending.current) return false
      setError(''); setNoticeOpen(true)
      return await new Promise<boolean>((resolve) => { pending.current = resolve })
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 410) expire()
      else setError(caught instanceof Error ? caught.message : 'Không thể kiểm tra phiên demo.')
      return false
    }
  }
  async function accept() {
    if (!status || busy) return
    setBusy(true); setError('')
    try { setStatus(await demoApi.accept(status.notice_version)); closeNotice(true) }
    catch (caught) {
      if (caught instanceof ApiError && caught.status === 410) expire()
      else {
        setError(caught instanceof Error ? caught.message : 'Không thể lưu xác nhận.')
        if (caught instanceof ApiError && caught.status === 428) {
          try { setStatus(await demoApi.status()) } catch { expire() }
        }
      }
    } finally { setBusy(false) }
  }
  async function clear() {
    setDeleteOpen(false); setPhase('clearing'); setError('')
    try { await demoApi.clear(); notifyOtherTabs(); setPhase('expired') }
    catch (caught) {
      if (caught instanceof ApiError && caught.status === 410) setPhase('expired')
      else { setError(caught instanceof Error ? caught.message : 'Không thể hoàn tất xóa dữ liệu.'); setPhase('cleanup_failed') }
    }
  }
  async function restart() {
    setPhase('loading'); setError('')
    try { setStatus(await demoApi.bootstrap()); setPhase('ready') }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Không thể tạo phiên demo.'); setPhase('expired') }
  }
  if (phase !== 'ready') return <main className="demo-session-screen">
    <h1>{phase === 'expired' ? 'Phiên demo đã kết thúc' : phase === 'cleanup_failed' ? 'Cần hoàn tất xóa dữ liệu' : phase === 'error' ? 'Không thể mở workspace' : 'Đang xử lý…'}</h1>
    {phase === 'expired' && <p>Phiên trước đã hết hạn hoặc được xóa. Bắt đầu phiên mới để tiếp tục.</p>}
    {error && <p role="alert">{error}</p>}
    {phase === 'expired' && <button onClick={() => void restart()}>Bắt đầu phiên demo mới</button>}
    {phase === 'cleanup_failed' && <button onClick={() => void clear()}>Thử xóa lại</button>}
    {['expired', 'cleanup_failed', 'error'].includes(phase) && <button onClick={onLogout}>Sign out</button>}
  </main>
  return <DemoContext value={{ status, beforeAction, requestDelete: () => { setError(''); setDeleteOpen(true) }, expire }}>
    {children}
    {error && !noticeOpen && !deleteOpen && <p className="demo-error" role="alert">{error}<button onClick={() => setError('')}>Đóng</button></p>}
    {noticeOpen && status && <ActionDialog title="Thông báo quyền riêng tư demo" busy={busy} onClose={() => closeNotice()}>
      <div className="demo-notice">
        <p>Đây là môi trường demo.</p>
        <p>Dữ liệu tải lên, câu hỏi và lịch sử trò chuyện sẽ tự động bị xóa khỏi hệ thống AskMeMind sau {status.retention_minutes} phút.</p>
        <p>Nội dung tài liệu và câu hỏi có thể được gửi đến NVIDIA và Groq để tạo embedding và câu trả lời.</p>
        <p>Không tải lên dữ liệu cá nhân, bí mật hoặc thông tin nhạy cảm.</p>
        <small>Thời hạn tính từ lúc bắt đầu phiên, không gia hạn khi upload hoặc chat. Xóa vật lý được xử lý theo lịch dọn dữ liệu.</small>
      </div>
      {error && <p role="alert">{error}</p>}
      <footer><button disabled={busy} onClick={() => closeNotice()}>Hủy</button><button disabled={busy} onClick={() => void accept()}>Tôi đã hiểu và tiếp tục</button></footer>
    </ActionDialog>}
    {deleteOpen && <ActionDialog title="Xóa dữ liệu demo của tôi" onClose={() => setDeleteOpen(false)}>
      <p>Xóa ngay toàn bộ tài liệu và cuộc trò chuyện được tạo trong phiên demo này. Hành động này không thể hoàn tác.</p>
      <p>Bạn có chắc muốn xóa toàn bộ dữ liệu trong phiên demo này không?</p>
      <footer><button onClick={() => setDeleteOpen(false)}>Hủy</button><button className="danger-button" onClick={() => void clear()}>Xóa dữ liệu demo của tôi</button></footer>
    </ActionDialog>}
  </DemoContext>
}

export function DemoSessionBanner() {
  const { status, requestDelete } = useDemo()
  if (!status?.is_demo) return null
  return <aside className="demo-session-banner" aria-label="Phiên demo">
    <div><strong>Demo · {status.retention_minutes} phút</strong>
      {status.expires_at && <small>Hết hạn: {new Date(status.expires_at).toLocaleString('vi-VN', { timeZone: 'Asia/Bangkok' })} GMT+7</small>}
      {!status.upload_enabled && <small>Admin đã tắt upload.</small>}
    </div><button onClick={requestDelete}>Xóa dữ liệu demo của tôi</button>
  </aside>
}
