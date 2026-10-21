import { expect, test } from '@playwright/test'

test('forgot password shows a generic confirmation and lets the user sign in', async ({ page }) => {
  let sent: unknown
  await page.route('**/api/auth/forgot-password', async (route) => {
    sent = route.request().postDataJSON()
    await route.fulfill({ status: 202, json: { message: 'If the account exists...' } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Forgot password?' }).click()
  await page.getByLabel('Email', { exact: true }).fill('user@example.com')
  await page.getByRole('button', { name: 'Send reset link' }).click()
  await expect(page.getByRole('status')).toContainText('If an account exists')
  expect(sent).toEqual({ email: 'user@example.com' })
  await page.getByRole('button', { name: 'Back to sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to your workspace' })).toBeVisible()
})

test('reset removes the token fragment, validates confirmation and submits once', async ({ page }, testInfo) => {
  const token = 'a'.repeat(64)
  const sent: unknown[] = []
  await page.route('**/api/auth/reset-password', async (route) => {
    sent.push(route.request().postDataJSON())
    await route.fulfill({ status: 204 })
  })
  await page.goto(`/reset-password#token=${token}`)
  await expect(page.getByRole('heading', { name: 'Set a new password' })).toBeVisible()
  expect(new URL(page.url()).hash).toBe('')
  await page.getByLabel('New password', { exact: true }).fill('new-password')
  await page.getByLabel('Confirm new password', { exact: true }).fill('different-password')
  await page.getByRole('button', { name: 'Reset password', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('The passwords do not match.')
  expect(sent).toHaveLength(0)
  await page.screenshot({ path: testInfo.outputPath('reset-password.png'), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByLabel('Confirm new password', { exact: true }).fill('new-password')
  await page.getByRole('button', { name: 'Reset password', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Your password has been updated')
  expect(sent).toEqual([{ token, new_password: 'new-password' }])
  await page.getByRole('button', { name: 'Back to sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to your workspace' })).toBeVisible()
  expect(new URL(page.url()).pathname).toBe('/')
})

test('missing reset token and expired reset link allow recovery', async ({ page }) => {
  await page.goto('/reset-password')
  await expect(page.getByRole('alert')).toContainText('This reset link is incomplete')
  await expect(page.getByRole('button', { name: 'Reset password', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Request a new reset link' }).click()
  await expect(page.getByLabel('Email', { exact: true })).toBeVisible()

  await page.route('**/api/auth/reset-password', (route) => route.fulfill({ status: 400, json: { detail: 'Invalid or expired reset token' } }))
  await page.goto(`/reset-password#token=${'b'.repeat(64)}`)
  await page.getByLabel('New password', { exact: true }).fill('new-password')
  await page.getByLabel('Confirm new password', { exact: true }).fill('new-password')
  await page.getByRole('button', { name: 'Reset password', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Invalid or expired reset token')
})

test('login refreshes once, logout revokes the current pair and tokens stay out of storage', async ({ page }, testInfo) => {
  let refreshes = 0
  let logout: unknown
  const old = { access_token: 'old-access', refresh_token: 'old-refresh', token_type: 'bearer' }
  const next = { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer' }
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/login') return route.fulfill({ json: old })
    if (path === '/api/auth/refresh') {
      refreshes += 1
      await new Promise((resolve) => setTimeout(resolve, 100))
      return route.fulfill({ json: next })
    }
    if (route.request().headers().authorization !== 'Bearer new-access') {
      return route.fulfill({ status: 401, json: { detail: 'Expired' } })
    }
    if (path === '/api/auth/me') {
      return route.fulfill({ json: { id: 'user', email: 'user@example.com', is_active: true } })
    }
    if (path === '/api/auth/logout') {
      logout = route.request().postDataJSON()
      return route.fulfill({ status: 204 })
    }
    if (path === '/api/documents/events') {
      return route.fulfill({ contentType: 'text/event-stream', body: ': heartbeat\n\n' })
    }
    return route.fulfill({ json: [] })
  })
  await page.goto('/')
  await page.getByLabel('Email', { exact: true }).fill('user@example.com')
  await page.getByLabel('Password', { exact: true }).fill('password')
  await page.locator('form').getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'What would you like to understand?' })).toBeVisible()
  expect(refreshes).toBe(1)
  expect(await page.evaluate(() => ({ ...localStorage, ...sessionStorage }))).toEqual({})
  if (testInfo.project.name === 'mobile') await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to your workspace' })).toBeVisible()
  expect(logout).toEqual({ refresh_token: 'new-refresh' })
})
