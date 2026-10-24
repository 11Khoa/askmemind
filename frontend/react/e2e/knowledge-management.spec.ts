import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

const sourcePdf = readFileSync(new URL('./fixtures/source.pdf', import.meta.url))

test.beforeEach(async ({ page }) => {
  let documents = [{
    id: 'document-1', original_filename: 'source.pdf', status: 'ready', page_count: 3,
    file_size_bytes: 100, created_at: '2026-10-24T00:00:00Z', updated_at: '2026-10-24T00:00:00Z',
  }]
  let chats = [{ id: 'chat-1', title: 'Research', updated_at: '2026-10-24T00:00:00Z' }]
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'user-1', email: 'owner@example.com' } })
    if (path === '/api/documents/events') return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' })
    if (path === '/api/documents') return route.fulfill({ json: documents })
    if (path === '/api/chats') return route.fulfill({ json: chats })
    if (path === '/api/chats/chat-1/messages') return route.fulfill({ json: [{
      id: 'message-1', chat_id: 'chat-1', role: 'assistant', message_index: 1,
      content: 'RRF combines ranks [Source 1].',
      message_metadata: { citations: [{ source_number: 1, document_id: 'document-1', chunk_id: 'chunk-1', chunk_index: 0, page_number: 3, distance: 0.1 }] },
    }] })
    if (path === '/api/documents/document-1/chunks/chunk-1') {
      expect(route.request().headers().authorization).toBe('Bearer access')
      return route.fulfill({ json: { content: 'Reciprocal rank fusion combines rankings.', page_number: 3 } })
    }
    if (path === '/api/documents/document-1/file') {
      expect(route.request().headers().authorization).toBe('Bearer access')
      expect(new URL(route.request().url()).search).toBe('')
      return route.fulfill({ contentType: 'application/pdf', body: sourcePdf })
    }
    if (path === '/api/documents/document-1' && method === 'DELETE') {
      documents = []
      return route.fulfill({ status: 204 })
    }
    if (path === '/api/chats/chat-1' && method === 'DELETE') {
      chats = []
      return route.fulfill({ status: 204 })
    }
    return route.fulfill({ status: 404 })
  })
  await page.goto('/')
})

test('opens an authenticated passage and PDF at the cited page', async ({ page }, testInfo) => {
  if ((page.viewportSize()?.width || 1440) < 1100) {
    await page.getByRole('button', { name: 'Close documents', exact: true }).click()
  }
  await page.getByRole('button', { name: /source.pdf Page 3/ }).click()
  await page.getByRole('button', { name: 'View passage and PDF' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('Reciprocal rank fusion combines rankings.')
  await expect(dialog.getByRole('link', { name: 'Open PDF at page 3' })).toHaveAttribute('href', /^blob:.*#page=3$/)
  await expect(dialog.locator('iframe')).toHaveAttribute('src', /^blob:.*#page=3$/)
  await page.screenshot({ path: testInfo.outputPath('source-viewer.png') })
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(dialog).toHaveCount(0)
})

test('requires confirmation to delete sources and conversations', async ({ page }) => {
  // On mobile, the document panel is toggled from the conversation header.
  await page.getByRole('button', { name: 'Delete document source.pdf' }).click()
  let dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByRole('button', { name: 'Delete document source.pdf' })).toBeVisible()
  await page.getByRole('button', { name: 'Delete document source.pdf' }).click()
  dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Delete permanently' }).click()
  await expect(page.getByRole('button', { name: 'Delete document source.pdf' })).toHaveCount(0)
  if ((page.viewportSize()?.width || 1440) < 760) {
    await page.getByRole('button', { name: 'Close documents', exact: true }).click()
    await page.getByRole('button', { name: 'Open navigation' }).click()
  }
  await page.getByRole('button', { name: 'Delete conversation Research' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete permanently' }).click()
  await expect(page.getByRole('button', { name: 'Delete conversation Research' })).toHaveCount(0)
})
