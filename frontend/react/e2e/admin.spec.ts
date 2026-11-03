import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

const pdf = readFileSync(new URL('./fixtures/source.pdf', import.meta.url))
const now = '2026-10-24T00:00:00Z'

async function setup(page: import('@playwright/test').Page, role: 'admin' | 'user') {
  const users = [
    { id: 'admin-1', email: 'admin@example.com', role: 'admin', is_active: true },
    { id: 'user-1', email: 'client@example.com', role: 'user', is_active: true },
  ]
  const documents = [{ id: 'doc-1', user_id: 'user-1', owner_email: 'client@example.com', original_filename: 'Private.pdf', status: 'ready', page_count: 3, file_size_bytes: 100, created_at: '2026-10-23T18:32:00Z', updated_at: now }]
  const chats = [{ id: 'chat-1', user_id: 'user-1', owner_email: 'client@example.com', title: 'Private conversation', updated_at: now }]
  const writes: { path: string; body: unknown }[] = []
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const method = route.request().method()
    const list = (items: unknown[], total = items.length) => route.fulfill({ json: { items, total, page: Number(url.searchParams.get('page') || 1), page_size: 20 } })
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { ...users[role === 'admin' ? 0 : 1], role } })
    if (path === '/api/documents') return route.fulfill({ json: documents })
    if (path === '/api/chats') return route.fulfill({ json: chats })
    if (path === '/api/documents/events') return route.fulfill({ contentType: 'text/event-stream', body: ': ready\n\n' })
    if (path === '/api/chats/chat-1/messages') return route.fulfill({ json: [] })
    if (path.startsWith('/api/admin') && role !== 'admin') return route.fulfill({ status: 403, json: { detail: 'Administrator permission required' } })
    if (path === '/api/admin/users' && method === 'POST') {
      const body = route.request().postDataJSON()
      writes.push({ path, body })
      const user = { id: 'new-user', email: body.email, role: body.role, is_active: true }
      users.push(user)
      return route.fulfill({ status: 201, json: user })
    }
    if (path.startsWith('/api/admin/users/') && method === 'PATCH') {
      const body = route.request().postDataJSON()
      writes.push({ path, body })
      if (path.endsWith('/admin-1')) return route.fulfill({ status: 409, json: { detail: 'Cannot remove the last active administrator' } })
      const user = users.find((item) => path.endsWith('/' + item.id))!
      Object.assign(user, body)
      return route.fulfill({ json: user })
    }
    if (path === '/api/admin/users') return list(users)
    if (path === '/api/admin/documents') return list(documents)
    if (path === '/api/admin/chats') return list(chats)
    if (path === '/api/admin/chats/chat-1/messages') return list([{ id: 'm-1', role: 'user', content: 'What did this client ask?', message_metadata: null }])
    if (path === '/api/admin/activity') return list([{ id: 1, actor_id: 'admin-1', target_user_id: 'user-1', action: 'admin.user.update', outcome: 'success', details: { after: { role: 'admin' } }, created_at: now, request_id: 'request-1', resource_id: 'user-1' }])
    if (path === '/api/documents/doc-1/file') {
      expect(route.request().headers().authorization).toBe('Bearer access')
      return route.fulfill({ contentType: 'application/pdf', body: pdf })
    }
    if (path === '/api/documents/doc-1' && method === 'DELETE') {
      writes.push({ path, body: null }); documents.splice(0)
      return route.fulfill({ status: 204 })
    }
    return route.fulfill({ status: 404 })
  })
  return writes
}

test('ordinary users have no delete or administration controls and cannot open admin data', async ({ page }) => {
  await setup(page, 'user')
  await page.goto('/')
  await expect(page.getByText('client@example.com', { exact: true })).toBeAttached()
  await expect(page.getByRole('button', { name: 'Administration', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Delete (document|conversation)/ })).toHaveCount(0)
  await page.goto('/admin')
  await expect(page.getByRole('alert')).toContainText('Administrator permission required')
  await expect(page.getByRole('table')).toHaveCount(0)
})

test('admin selects roles at creation and sees last-admin protection', async ({ page }, testInfo) => {
  const writes = await setup(page, 'admin')
  await page.goto('/admin')
  await expect(page.getByRole('table')).toContainText('client@example.com')
  const adminRow = page.getByRole('row').filter({ hasText: 'admin@example.com' })
  await adminRow.getByRole('button', { name: 'Make user', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm action' }).click()
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('last active administrator')
  await page.screenshot({ path: testInfo.outputPath('last-admin-protection.png'), fullPage: true })
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click()
  await page.getByRole('button', { name: 'Create user', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Email', { exact: true }).fill('new@example.com')
  await dialog.getByLabel('Initial password').fill('public-test-password')
  await dialog.getByLabel('Role', { exact: true }).selectOption('admin')
  await dialog.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.getByRole('table')).toContainText('new@example.com')
  expect(writes.find((write) => write.path === '/api/admin/users')?.body).toEqual({ email: 'new@example.com', password: 'public-test-password', role: 'admin' })
})

test('admin inspects other users documents, conversations and activity', async ({ page }, testInfo) => {
  const writes = await setup(page, 'admin')
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Documents', exact: true }).click()
  await expect(page.getByRole('table')).toContainText('client@example.com')
  await expect(page.getByRole('columnheader', { name: 'Uploaded at', exact: true })).toBeVisible()
  const uploaded = page.locator('.admin-uploaded time')
  await expect(uploaded).toHaveAttribute('datetime', '2026-10-23T18:32:00Z')
  await expect(uploaded).toContainText('24 Oct 2026')
  await expect(uploaded).toContainText('01:32 GMT+7')
  await page.screenshot({ path: testInfo.outputPath('admin-documents-redesign.png'), fullPage: true })
  await page.getByRole('button', { name: 'View PDF', exact: true }).click()
  await expect(page.getByRole('dialog').getByRole('link', { name: 'Open PDF at page 1' })).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Delete document', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm action' }).click()
  await expect(page.getByText('No records found.')).toBeVisible()
  expect(writes.some((write) => write.path === '/api/documents/doc-1')).toBe(true)
  await page.getByRole('button', { name: 'Chats', exact: true }).click()
  await page.getByRole('button', { name: 'View messages', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('What did this client ask?')
  await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Activity', exact: true }).click()
  await expect(page.getByRole('table')).toContainText('admin.user.update')
  await page.screenshot({ path: testInfo.outputPath('admin-activity.png'), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
