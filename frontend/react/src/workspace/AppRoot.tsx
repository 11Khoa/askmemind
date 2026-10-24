import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { Analytics } from '@vercel/analytics/react'
import { useTranslation } from 'react-i18next'
import { BookOpenText, LoaderCircle } from 'lucide-react'

import { api } from '../lib/api'
import { ApiError, restoreSession } from '../lib/http'
import { session } from '../lib/session'
import { AuthView } from './AuthView'
import { Workspace } from './Workspace'
import { AdminPanel } from './AdminPanel'
import './workspace.css'

// Consume the fragment before rendering analytics or any third-party content.
let resetSequence = 0
function consumeResetLink() {
  if (window.location.pathname.replace(/\/$/, '') !== '/reset-password') return null
  const token = new URLSearchParams(window.location.hash.slice(1)).get('token') || ''
  window.history.replaceState(null, '', window.location.pathname + window.location.search)
  return { token, id: ++resetSequence }
}
const initialResetLink = consumeResetLink()

function isAdminPath() {
  return window.location.pathname.replace(/\/$/, '') === '/admin'
}

export default function AppRoot() {
  const { t } = useTranslation()
  const sessionStatus = useSyncExternalStore(session.subscribe, session.status)
  const [resetLink, setResetLink] = useState(initialResetLink)
  const [authNotice, setAuthNotice] = useState('')
  const loggingOut = useRef(false)
  const lastLocation = useRef(window.location.href)
  const [view, setView] = useState(() => isAdminPath() ? 'admin' : 'workspace')

  function navigateView(next: 'admin' | 'workspace') {
    window.history.pushState(null, '', next === 'admin' ? '/admin' : '/')
    lastLocation.current = window.location.href
    setView(next)
  }

  useEffect(() => {
    if (resetLink || sessionStatus !== 'restoring') return
    void restoreSession().catch((error: unknown) => {
      if (!(error instanceof ApiError && error.status === 401)) {
        setAuthNotice(t('auth.sessionExpired'))
      }
    })
  }, [resetLink, sessionStatus, t])

  useEffect(() => {
    function navigate() {
      // A fragment navigation may emit both popstate and hashchange. Consume
      // a reset token once, while tracking our own pushState navigations too.
      if (window.location.href === lastLocation.current) return
      const link = consumeResetLink()
      lastLocation.current = window.location.href
      setView(isAdminPath() ? 'admin' : 'workspace')
      setResetLink(link)
    }
    window.addEventListener('hashchange', navigate)
    window.addEventListener('popstate', navigate)
    return () => {
      window.removeEventListener('hashchange', navigate)
      window.removeEventListener('popstate', navigate)
    }
  }, [])

  const logout = useCallback(async () => {
    if (loggingOut.current) return
    loggingOut.current = true
    try {
      await api.logout()
    } catch {
      setAuthNotice(t('auth.logoutFailed'))
    } finally {
      loggingOut.current = false
    }
  }, [t])

  function finishReset() {
    session.set(null)
    setResetLink(null)
    window.history.replaceState(null, '', '/')
    lastLocation.current = window.location.href
  }

  return (
    <>
      {!resetLink && sessionStatus === 'restoring' ? (
        <main className="loading-screen" aria-busy="true">
          <span className="brand-mark"><BookOpenText size={21} /></span>
          <LoaderCircle className="spin" size={25} />
          <p>{t('workspace.loading')}</p>
        </main>
      ) : resetLink || sessionStatus !== 'authenticated' ? (
        <AuthView
          key={resetLink?.id ?? 'sign-in'}
          onAuthenticated={(tokens) => { setAuthNotice(''); session.set(tokens) }}
          resetToken={resetLink?.token}
          onResetFinished={finishReset}
          notice={authNotice}
          onRetrySession={() => { setAuthNotice(''); session.startRestore() }}
        />
      ) : view === 'admin' ? (
        <AdminPanel onBack={() => navigateView('workspace')} />
      ) : (
        <Workspace onLogout={() => { void logout() }} onAdmin={() => navigateView('admin')} />
      )}
      <Analytics />
    </>
  )
}
