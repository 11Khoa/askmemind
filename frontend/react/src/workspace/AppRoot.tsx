import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { Analytics } from '@vercel/analytics/react'
import { useTranslation } from 'react-i18next'

import { api } from '../lib/api'
import { session } from '../lib/session'
import { AuthView } from './AuthView'
import { Workspace } from './Workspace'
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
try {
  window.localStorage.removeItem('askmemind_access_token')
} catch {
  // Authentication also works when browser storage is unavailable.
}

export default function AppRoot() {
  const { t } = useTranslation()
  const authenticated = useSyncExternalStore(session.subscribe, session.isAuthenticated)
  const [resetLink, setResetLink] = useState(initialResetLink)
  const [authNotice, setAuthNotice] = useState('')
  const loggingOut = useRef(false)

  useEffect(() => {
    let lastUrl = window.location.href
    function navigate() {
      if (window.location.href === lastUrl) return
      const link = consumeResetLink()
      lastUrl = window.location.href
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
      session.set(null)
      loggingOut.current = false
    }
  }, [t])

  function finishReset() {
    session.set(null)
    setResetLink(null)
    window.history.replaceState(null, '', '/')
  }

  return (
    <>
      {resetLink || !authenticated ? (
        <AuthView
          key={resetLink?.id ?? 'sign-in'}
          onAuthenticated={(tokens) => { setAuthNotice(''); session.set(tokens) }}
          resetToken={resetLink?.token}
          onResetFinished={finishReset}
          notice={authNotice}
        />
      ) : (
        <Workspace onLogout={() => { void logout() }} />
      )}
      <Analytics />
    </>
  )
}
