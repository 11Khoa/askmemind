import { useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ArrowRight,
  BookOpenText,
  Check,
  FileSearch,
  LoaderCircle,
  LockKeyhole,
} from 'lucide-react'

import { api } from '../lib/api'
import type { TokenResponse } from '../lib/types'

type AuthMode = 'login' | 'register' | 'forgot' | 'reset'

type AuthViewProps = {
  onAuthenticated: (tokens: TokenResponse) => void
  resetToken?: string
  onResetFinished: () => void
  notice?: string
  onRetrySession: () => void
}

export function AuthView({ onAuthenticated, resetToken, onResetFinished, notice, onRetrySession }: AuthViewProps) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<AuthMode>(resetToken === undefined ? 'login' : 'reset')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [completed, setCompleted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const invalidReset = mode === 'reset' && (!resetToken || resetToken.length < 32 || resetToken.length > 256)

  function changeMode(next: AuthMode) {
    setMode(next)
    setError('')
    setPassword('')
    setConfirmation('')
    setCompleted(false)
    if (resetToken !== undefined && next === 'login') onResetFinished()
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (mode === 'reset' && password !== confirmation) {
      setError(t('auth.passwordMismatch'))
      return
    }
    setSubmitting(true)

    try {
      if (mode === 'forgot') {
        await api.forgotPassword(email)
        setCompleted(true)
        return
      }
      if (mode === 'reset') {
        if (invalidReset) return
        await api.resetPassword(resetToken!, password)
        setPassword('')
        setConfirmation('')
        setCompleted(true)
        return
      }
      if (mode === 'register') {
        await api.register(email, password)
      }
      const token = await api.login(email, password)
      onAuthenticated(token)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t('common.genericError'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-product" aria-label={t('auth.previewLabel')}>
        <div className="brand brand--light">
          <span className="brand-mark"><BookOpenText size={20} /></span>
          <span>{t('brand.name')}</span>
        </div>

        <div className="auth-product-copy">
          <p className="eyebrow">{t('auth.eyebrow')}</p>
          <h1>{t('auth.heroTitle')}</h1>
          <p>{t('auth.heroDescription')}</p>
        </div>

        <div className="source-preview">
          <div className="source-preview-head">
            <span><FileSearch size={17} /> {t('auth.sourceEvidence')}</span>
            <span className="confidence"><Check size={13} /> {t('auth.verified')}</span>
          </div>
          <blockquote>{t('auth.sourceQuote')}</blockquote>
          <div className="source-preview-meta">
            <span>{t('auth.sourceFile')}</span>
            <span>{t('auth.sourcePage')}</span>
          </div>
        </div>
      </section>

      <section className="auth-panel">
        <div className="auth-form-wrap">
          <div className="mobile-brand brand">
            <span className="brand-mark"><BookOpenText size={19} /></span>
            <span>{t('brand.name')}</span>
          </div>

          <div className="auth-heading">
            <p className="eyebrow">
              {t(`auth.heading.${mode}Eyebrow`)}
            </p>
            <h2>
              {t(`auth.heading.${mode}Title`)}
            </h2>
            <p>
              {t(`auth.heading.${mode}Description`)}
            </p>
          </div>

          {(mode === 'login' || mode === 'register') && <div className="segmented" aria-label={t('auth.modeLabel')}>
            <button
              type="button"
              className={mode === 'login' ? 'is-active' : ''}
              disabled={submitting}
              onClick={() => changeMode('login')}
            >
              {t('auth.signIn')}
            </button>
            <button
              type="button"
              className={mode === 'register' ? 'is-active' : ''}
              disabled={submitting}
              onClick={() => changeMode('register')}
            >
              {t('auth.register')}
            </button>
          </div>}

          {notice && <div className="form-error" role="alert">{notice}</div>}
          {notice && <button className="auth-link" type="button" disabled={submitting} onClick={onRetrySession}>
            {t('auth.retrySession')}
          </button>}
          {completed && (
            <div className="form-success" role="status">
              {t(mode === 'forgot' ? 'auth.resetEmailSent' : 'auth.passwordResetSuccess')}
            </div>
          )}
          {invalidReset && <div className="form-error" role="alert">{t('auth.invalidResetLink')}</div>}

          {!completed && !invalidReset && <form onSubmit={submit} className="auth-form">
            {mode !== 'reset' && <label>
              {t('auth.email')}
              <input
                type="email"
                autoComplete="email"
                placeholder={t('auth.emailPlaceholder')}
                value={email}
                disabled={submitting}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>}
            {mode !== 'forgot' && <label>
              {t(mode === 'reset' ? 'auth.newPassword' : 'auth.password')}
              <input
                type="password"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                placeholder={t('auth.passwordPlaceholder')}
                minLength={8}
                maxLength={128}
                value={password}
                disabled={submitting}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>}
            {mode === 'reset' && <label>
              {t('auth.confirmPassword')}
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                value={confirmation}
                disabled={submitting}
                onChange={(event) => setConfirmation(event.target.value)}
                required
              />
            </label>}

            {error && <div className="form-error" role="alert">{error}</div>}

            <button className="primary-button auth-submit" disabled={submitting}>
              {submitting ? <LoaderCircle className="spin" size={18} /> : <LockKeyhole size={17} />}
              {t({ login: 'auth.signIn', register: 'auth.createAccount', forgot: 'auth.sendResetLink', reset: 'auth.resetPassword' }[mode])}
              {!submitting && <ArrowRight size={17} />}
            </button>
          </form>}

          {(mode === 'login' || mode === 'reset') && !completed && (
            <button className="auth-link" type="button" disabled={submitting} onClick={() => changeMode('forgot')}>
              {t(mode === 'reset' ? 'auth.requestNewLink' : 'auth.forgotPassword')}
            </button>
          )}
          {(mode === 'forgot' || mode === 'reset') && (
            <button className="auth-link" type="button" disabled={submitting} onClick={() => changeMode('login')}>
              {t('auth.backToSignIn')}
            </button>
          )}

          <p className="auth-footnote">{t('auth.footnote')}</p>
        </div>
      </section>
    </main>
  )
}
