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

type AuthViewProps = {
  onAuthenticated: (token: string) => void
}

export function AuthView({ onAuthenticated }: AuthViewProps) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSubmitting(true)

    try {
      if (mode === 'register') {
        await api.register(email, password)
      }
      const token = await api.login(email, password)
      onAuthenticated(token.access_token)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t('auth.unableToSignIn'))
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
              {mode === 'login'
                ? t('auth.heading.loginEyebrow')
                : t('auth.heading.registerEyebrow')}
            </p>
            <h2>
              {mode === 'login'
                ? t('auth.heading.loginTitle')
                : t('auth.heading.registerTitle')}
            </h2>
            <p>
              {mode === 'login'
                ? t('auth.heading.loginDescription')
                : t('auth.heading.registerDescription')}
            </p>
          </div>

          <div className="segmented" aria-label={t('auth.modeLabel')}>
            <button
              type="button"
              className={mode === 'login' ? 'is-active' : ''}
              onClick={() => { setMode('login'); setError('') }}
            >
              {t('auth.signIn')}
            </button>
            <button
              type="button"
              className={mode === 'register' ? 'is-active' : ''}
              onClick={() => { setMode('register'); setError('') }}
            >
              {t('auth.register')}
            </button>
          </div>

          <form onSubmit={submit} className="auth-form">
            <label>
              {t('auth.email')}
              <input
                type="email"
                autoComplete="email"
                placeholder={t('auth.emailPlaceholder')}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              {t('auth.password')}
              <input
                type="password"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                placeholder={t('auth.passwordPlaceholder')}
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>

            {error && <div className="form-error" role="alert">{error}</div>}

            <button className="primary-button auth-submit" disabled={submitting}>
              {submitting ? <LoaderCircle className="spin" size={18} /> : <LockKeyhole size={17} />}
              {mode === 'login' ? t('auth.signIn') : t('auth.createAccount')}
              {!submitting && <ArrowRight size={17} />}
            </button>
          </form>

          <p className="auth-footnote">{t('auth.footnote')}</p>
        </div>
      </section>
    </main>
  )
}