import { expect, test } from '@playwright/test'

test.beforeEach(async ({ context }) => {
  await context.route('**/api/auth/refresh', (route) =>
    route.fulfill({ status: 401, json: { detail: 'No refresh cookie' } }))
})

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


test('HttpOnly cookie survives reload/reopening, rotates across tabs and clears on logout', async ({ page, context }, testInfo) => {
  let refreshes = 0
  let logoutCookie = ''
  let logoutBody: string | null = null
  let currentCookie = ''
  const validAccess = new Set<string>()
  const usedCookies = new Set<string>()
  const cookieHeader = (value: string, maxAge = 3600) =>
    `askmemind_refresh=${value}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${maxAge}`

  await context.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const headers = await route.request().allHeaders()
    const rawCookie = headers.cookie?.match(/(?:^|; *)askmemind_refresh=([^;]+)/)?.[1] || ''
    if (path === '/api/auth/login') {
      expect(headers['x-csrf-protection']).toBe('1')
      currentCookie = 'original-cookie'
      return route.fulfill({
        json: { access_token: 'expired-access', token_type: 'bearer' },
        headers: { 'Set-Cookie': cookieHeader(currentCookie) },
      })
    }
    if (path === '/api/auth/refresh') {
      expect(route.request().postData()).toBeNull()
      expect(headers['x-csrf-protection']).toBe('1')
      if (!rawCookie || rawCookie !== currentCookie || usedCookies.has(rawCookie)) {
        return route.fulfill({ status: 401, json: { detail: 'Invalid refresh cookie' } })
      }
      usedCookies.add(rawCookie)
      refreshes += 1
      await new Promise((resolve) => setTimeout(resolve, 100))
      currentCookie = `rotated-cookie-${refreshes}`
      const access = `new-access-${refreshes}`
      validAccess.add(`Bearer ${access}`)
      return route.fulfill({
        json: { access_token: access, token_type: 'bearer' },
        headers: { 'Set-Cookie': cookieHeader(currentCookie) },
      })
    }
    if (!validAccess.has(headers.authorization)) {
      return route.fulfill({ status: 401, json: { detail: 'Expired access token' } })
    }
    if (path === '/api/auth/me') {
      return route.fulfill({ json: { id: 'user', email: 'user@example.com', is_active: true } })
    }
    if (path === '/api/auth/logout') {
      expect(headers['x-csrf-protection']).toBe('1')
      logoutCookie = rawCookie
      logoutBody = route.request().postData()
      currentCookie = ''
      return route.fulfill({ status: 204, headers: { 'Set-Cookie': cookieHeader('', 0) } })
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
  expect(await page.evaluate(() => ({ local: { ...localStorage }, tab: { ...sessionStorage } }))).toEqual({ local: {}, tab: {} })
  expect(await page.evaluate(() => document.cookie)).not.toContain('askmemind_refresh')
  const cookie = (await context.cookies()).find((item) => item.name === 'askmemind_refresh')
  expect(cookie?.httpOnly).toBe(true)
  expect(cookie?.expires).toBeGreaterThan(Date.now() / 1000)

  await page.reload()
  await expect(page.getByRole('heading', { name: 'What would you like to understand?' })).toBeVisible()
  expect(refreshes).toBe(2)
  const other = await context.newPage()
  await other.goto('/')
  await expect(other.getByRole('heading', { name: 'What would you like to understand?' })).toBeVisible()
  expect(refreshes).toBe(3)
  await Promise.all([page.reload(), other.reload()])
  for (const tab of [page, other]) {
    await expect(tab.getByRole('heading', { name: 'What would you like to understand?' })).toBeVisible()
  }
  expect(refreshes).toBe(5)
  await page.close()
  const reopened = await context.newPage()
  await reopened.goto('/')
  await expect(reopened.getByRole('heading', { name: 'What would you like to understand?' })).toBeVisible()
  expect(refreshes).toBe(6)
  if (testInfo.project.name === 'mobile') await other.getByRole('button', { name: 'Open navigation' }).click()
  await other.getByRole('button', { name: 'Sign out' }).click()
  for (const tab of [other, reopened]) {
    await expect(tab.getByRole('heading', { name: 'Sign in to your workspace' })).toBeVisible()
  }
  expect(logoutCookie).toBe('rotated-cookie-6')
  expect(logoutBody).toBeNull()
  expect((await context.cookies()).find((item) => item.name === 'askmemind_refresh')).toBeUndefined()
  await reopened.reload()
  await expect(reopened.getByRole('heading', { name: 'Sign in to your workspace' })).toBeVisible()
  expect(refreshes).toBe(6)
})

test('startup outages show a retry and an absent cookie returns quietly to sign-in', async ({ page, context }) => {
  let attempts = 0
  await context.route('**/api/auth/refresh', async (route) => {
    attempts += 1
    await route.fulfill(attempts === 1
      ? { status: 503, json: { detail: 'Auth temporarily unavailable' } }
      : { status: 401, json: { detail: 'No refresh cookie' } })
  })
  await page.goto('/')
  await expect(page.getByRole('alert')).toContainText('Your session could not be restored')
  await page.getByRole('button', { name: 'Retry restoring session' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to your workspace' })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(attempts).toBe(2)
})

test('cookie authentication works with blocked browser storage', async ({ page, context }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Blocked', 'SecurityError') } })
    Object.defineProperty(window, 'sessionStorage', { get() { throw new DOMException('Blocked', 'SecurityError') } })
  })
  await context.route('**/api/auth/login', (route) => route.fulfill({
    json: { access_token: 'memory-only', token_type: 'bearer' },
    headers: { 'Set-Cookie': 'askmemind_refresh=opaque; HttpOnly; SameSite=Lax; Path=/; Max-Age=3600' },
  }))
  await context.route('**/api/auth/me', (route) => route.fulfill({ json: { id: 'user', email: 'user@example.com' } }))
  await context.route('**/api/documents', (route) => route.fulfill({ json: [] }))
  await context.route('**/api/chats', (route) => route.fulfill({ json: [] }))
  await context.route('**/api/documents/events', (route) => route.fulfill({ contentType: 'text/event-stream', body: ': ping\n\n' }))
  await page.goto('/')
  await page.getByLabel('Email', { exact: true }).fill('user@example.com')
  await page.getByLabel('Password', { exact: true }).fill('password')
  await page.locator('form').getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'What would you like to understand?' })).toBeVisible()
})

test('legacy access and refresh tokens are removed instead of reused', async ({ page }) => {
  await page.addInitScript(() => {
    for (const storage of [localStorage, sessionStorage]) {
      storage.setItem('askmemind_access_token', 'legacy-access')
      storage.setItem('askmemind_refresh_token', 'legacy-refresh')
    }
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Sign in to your workspace' })).toBeVisible()
  expect(await page.evaluate(() => ({ local: { ...localStorage }, tab: { ...sessionStorage } }))).toEqual({ local: {}, tab: {} })
})
