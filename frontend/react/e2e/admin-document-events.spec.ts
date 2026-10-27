import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

async function setup(page: Page, recover = false) {
  let connections = 0
  let privateConnections = 0
  let current: Route | undefined
  const queries: URLSearchParams[] = []
  let document = {
    id: 'doc', user_id: 'owner', owner_email: 'owner@example.com', original_filename: 'Report.pdf',
    status: 'processing', processing_attempt_id: 'attempt', page_count: null,
    file_size_bytes: 51200, created_at: '2026-10-25T18:30:00Z',
    error_message: null, updated_at: '2026-10-27T00:00:00Z',
    processing_progress: { stage: 'ocr', current_page: 7, completed_pages: 6, total_pages: 144,
      completed_chunks: 0, total_chunks: 10 },
  }
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url()), path = url.pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'admin', email: 'admin@example.com', role: 'admin' } })
    if (path === '/api/admin/users') return route.fulfill({ json: { items: [
      { id: 'owner', email: 'owner@example.com', role: 'user', is_active: true },
    ], total: 1, page: 1, page_size: 20 } })
    if (path === '/api/admin/documents') {
      queries.push(url.searchParams)
      return route.fulfill({ json: { items: [document], total: 40,
        page: Number(url.searchParams.get('page')), page_size: 20 } })
    }
    if (path === '/api/documents/events') { privateConnections++; return route.abort() }
    if (path === '/api/admin/documents/events') {
      connections++
      if (recover) {
        if (connections === 1) return route.abort('failed')
        document = { ...document, updated_at: '2026-10-27T00:02:00Z', processing_progress: {
          ...document.processing_progress, stage: 'embedding', completed_chunks: 5,
        } }
        return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' })
      }
      current = route
      return
    }
    return route.fulfill({ status: 404 })
  })
  return {
    queries, connections: () => connections, privateConnections: () => privateConnections,
    emit: async (events: object[]) => {
      expect(current).toBeTruthy()
      await current!.fulfill({ contentType: 'text/event-stream',
        body: events.map((event) => `event: document_status\ndata: ${JSON.stringify(event)}\n\n`).join('') })
    },
  }
}

test('admin SSE updates filtered page in place and stops when leaving documents', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/admin')
  expect(state.connections()).toBe(0)
  await page.getByRole('button', { name: 'View documents', exact: true }).click()
  const search = page.getByRole('textbox', { name: 'Search administration' })
  await search.fill('Report')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByText(/Page 2 of 2/)).toBeVisible()
  await expect.poll(() => state.connections()).toBeGreaterThanOrEqual(3)
  await state.emit([
    { document_id: 'other-doc', user_id: 'other-user', status: 'ready', updated_at: '2026-10-27T00:01:00Z' },
    { document_id: 'doc', user_id: 'owner', status: 'processing', page_count: null, error_message: null,
      processing_attempt_id: 'attempt', updated_at: '2026-10-27T00:01:00Z',
      processing_progress: { stage: 'ocr', current_page: 23, completed_pages: 22, total_pages: 144 } },
  ])
  await expect(page.locator('.admin-table-wrap')).toContainText('Recognizing text: page 23 of 144')
  await expect(page.locator('.admin-uploaded time')).toHaveAttribute('datetime', '2026-10-25T18:30:00Z')
  await expect(page.locator('.admin-uploaded time')).toContainText('26 Oct 2026')
  await expect(page.locator('.admin-uploaded time')).toContainText('01:30 GMT+7')
  await expect(page.getByRole('region', { name: 'Document summary' })).toContainText('Matching documents40')
  await expect(page.getByRole('region', { name: 'Document summary' })).toContainText('Processing on this page1')
  await expect(search).toHaveValue('Report')
  await expect(page.getByText(/Page 2 of 2/)).toBeVisible()
  expect(state.queries.at(-1)?.get('user_id')).toBe('owner')
  expect(state.queries.at(-1)?.get('q')).toBe('Report')
  expect(state.queries.at(-1)?.get('page')).toBe('2')
  expect(state.privateConnections()).toBe(0)
  await page.getByRole('button', { name: 'Users', exact: true }).click()
  const count = state.connections()
  await page.waitForTimeout(1300) // Longer than the reconnect delay; cleanup must cancel it.
  expect(state.connections()).toBe(count)
})

test('admin reconnect restores missed progress from the filtered snapshot', async ({ page }) => {
  const state = await setup(page, true)
  await page.goto('/admin')
  await page.getByRole('button', { name: 'View documents', exact: true }).click()
  await expect(page.locator('.admin-table-wrap')).toContainText('Indexing passages: 5 of 10', { timeout: 10_000 })
  expect(state.connections()).toBeGreaterThanOrEqual(2)
  expect(state.queries.at(-1)?.get('user_id')).toBe('owner')
  // This fixture intentionally ends each stream after the snapshot; the UI
  // should accurately show reconnection instead of claiming a live connection.
  await expect(page.locator('.admin-live-state')).toHaveText('Reconnecting live document updates…')
})
