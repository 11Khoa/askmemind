import { useState } from 'react'

import { AuthView } from './AuthView'
import { Workspace } from './Workspace'
import './workspace.css'

const TOKEN_KEY = 'askmemind_access_token'

export default function AppRoot() {
  const [token, setToken] = useState<string | null>(() =>
    window.localStorage.getItem(TOKEN_KEY),
  )

  function authenticate(accessToken: string) {
    window.localStorage.setItem(TOKEN_KEY, accessToken)
    setToken(accessToken)
  }

  function logout() {
    window.localStorage.removeItem(TOKEN_KEY)
    setToken(null)
  }

  if (!token) {
    return <AuthView onAuthenticated={authenticate} />
  }

  return <Workspace token={token} onLogout={logout} />
}
