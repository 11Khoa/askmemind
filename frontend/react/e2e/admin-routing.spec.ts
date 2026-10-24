import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function mockSessions(page: Page, initial: 'admin' | 'user' | null) {
  let role = initial
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/login') {
      role = route.request().postDataJSON().email.startsWith('admin') ? 'admin' : 'user'
      return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    }
    if (path === '/api/auth/logout') {
      role = null
      return route.fulfill({ status: 204 })
    }
    if (path === '/api/auth/refresh') return role
      ? route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
      : route.fulfill({ status: 401, json: { detail: 'No session' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: role, role, email: `${role}@example.com` } })
    if (path === '/api/documents' || path === '/api/chats') return route.fulfill({ json: [] })
    if (path === '/api/documents/events') return route.fulfill({ contentType: 'text/event-stream', body: ': ready\n\n' })
    if (path === '/api/admin/users') return role === 'admin'
      ? route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } })
      : route.fulfill({ status: 403, json: { detail: 'Administrator permission required' } })
    return route.fulfill({ status: 404 })
  })
}

test('serves declared SPA routes without swallowing missing API routes', async ({ request }) => {
  for (const path of ['/', '/admin', '/admin/', '/reset-password', '/reset-password/']) {
    const response = await request.get(path)
    expect(response.status(), path).toBe(200)
    expect(await response.text()).toContain('<div id="root">')
  }
  // Vite intentionally has a generic fallback; only the production host must
  // prove that API errors are not rewritten into an HTML success response.
  if (test.info().config.configFile?.endsWith('playwright.production.config.ts')) {
    expect((await request.get('/api/missing')).status()).toBe(404)
  }
})

for (const path of ['/admin', '/admin/']) {
  test(`admin survives direct open and refresh at ${path}`, async ({ page }) => {
    await mockSessions(page, 'admin')
    expect((await page.goto(path))?.status()).toBe(200)
    await expect(page.getByRole('heading', { name: 'Administration', exact: true })).toBeVisible()
    expect((await page.reload())?.status()).toBe(200)
    await expect(page.getByRole('heading', { name: 'Administration', exact: true })).toBeVisible()
  })
}

test('browser back and forward keep the admin route and view in sync', async ({ page }) => {
  await mockSessions(page, 'admin')
  await page.goto('/')
  if ((page.viewportSize()?.width || 1440) < 1100) await page.getByRole('button', { name: 'Close documents', exact: true }).click()
  if ((page.viewportSize()?.width || 1440) < 760) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('button', { name: 'Administration', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Administration', exact: true })).toBeVisible()
  await page.goBack()
  await expect(page.locator('.workspace')).toBeVisible()
  await page.goForward()
  await expect(page.getByRole('heading', { name: 'Administration', exact: true })).toBeVisible()
})

test('admin can sign out and sign back in without a document 404', async ({ page }) => {
  await mockSessions(page, 'admin')
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Back to workspace' }).click()
  if ((page.viewportSize()?.width || 1440) < 1100) await page.getByRole('button', { name: 'Close documents', exact: true }).click()
  if ((page.viewportSize()?.width || 1440) < 760) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to your workspace' })).toBeVisible()
  expect((await page.reload())?.status()).toBe(200)
  await page.getByLabel('Email', { exact: true }).fill('admin@example.com')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.locator('form').getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.locator('.workspace')).toBeVisible()
})
