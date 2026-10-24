import { expect, test } from '@playwright/test'

const failedDocument = {
  id: 'document-1', user_id: 'user-1', filename: 'stored.pdf',
  original_filename: 'AI-engineer.pdf', file_path: '/uploads/stored.pdf',
  content_type: 'application/pdf', file_size_bytes: 123456,
  status: 'processing_failed', page_count: 3, source_type: 'pdf',
  source_metadata: null, error_message: 'Embedding provider unavailable',
  processing_attempt_id: 'previous-attempt',
  created_at: '2026-10-22T00:00:00Z', updated_at: '2026-10-22T00:00:00Z',
}

test('retry stays on the same document, blocks repeated clicks and reconciles missed SSE', async ({ page }, testInfo) => {
  let document = { ...failedDocument }
  let retries = 0
  let acceptRetry: (() => void) | undefined
  const gate = new Promise<void>((resolve) => { acceptRetry = resolve })
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'user-1', email: 'user@example.com' } })
    if (path === '/api/chats') return route.fulfill({ json: [] })
    if (path === '/api/documents') return route.fulfill({ json: [document] })
    if (path === '/api/documents/events') return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' })
    if (path === '/api/documents/document-1/retry') {
      retries += 1
      expect(route.request().method()).toBe('POST')
      expect(route.request().headers().authorization).toBe('Bearer access')
      await gate
      document = { ...document, status: 'processing', processing_attempt_id: 'new-attempt', error_message: '' }
      return route.fulfill({ status: 202, json: document })
    }
    if (path === '/api/documents/document-1') return route.fulfill({ json: document })
    return route.fulfill({ status: 404 })
  })
  await page.goto('/')
  const row = page.locator('.document-row', { hasText: 'AI-engineer.pdf' })
  const retry = row.getByRole('button', { name: 'Retry processing AI-engineer.pdf' })
  await expect(retry).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('document-failed.png'), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await retry.click()
  await expect(retry).toBeDisabled()
  await expect(retry).toContainText('Retrying...')
  expect(retries).toBe(1)
  acceptRetry!()
  await expect(row.locator('.status')).toHaveText('Processing')
  await expect(retry).toHaveCount(0)
  await expect(page.locator('.document-row')).toHaveCount(1)
  document = { ...document, status: 'ready' }
  await expect(row.locator('.status')).toHaveText('Ready', { timeout: 7000 })
  await expect(row.locator('.document-item')).toBeEnabled()
  await expect(page.getByRole('status')).toContainText('AI-engineer.pdf is ready to search.')
  await page.screenshot({ path: testInfo.outputPath('document-ready.png'), fullPage: true })
})

test('retry errors keep the failed row and allow another attempt', async ({ page }) => {
  let retries = 0
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'user-1', email: 'user@example.com' } })
    if (path === '/api/chats') return route.fulfill({ json: [] })
    if (path === '/api/documents') return route.fulfill({ json: [failedDocument] })
    if (path === '/api/documents/document-1') return route.fulfill({ json: failedDocument })
    if (path === '/api/documents/events') return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' })
    if (path.endsWith('/retry')) {
      retries += 1
      return route.fulfill({ status: 503, json: { detail: 'Could not queue document processing. Please retry.' } })
    }
    return route.fulfill({ status: 404 })
  })
  await page.goto('/')
  const retry = page.getByRole('button', { name: 'Retry processing AI-engineer.pdf' })
  await retry.click()
  await expect(page.getByRole('status')).toContainText('Could not queue')
  await expect(retry).toBeEnabled()
  await retry.click()
  await expect.poll(() => retries).toBe(2)
  await expect(page.locator('.document-row')).toHaveCount(1)
})

test('SSE can finish a retry before the acceptance response arrives', async ({ page }) => {
  let emitEvent: (() => Promise<void>) | undefined
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'user-1', email: 'user@example.com' } })
    if (path === '/api/chats') return route.fulfill({ json: [] })
    if (path === '/api/documents') return route.fulfill({ json: [failedDocument] })
    if (path === '/api/documents/events') {
      emitEvent = () => route.fulfill({ contentType: 'text/event-stream', body: `data: ${JSON.stringify({
        document_id: 'document-1', status: 'ready', processing_attempt_id: 'new-attempt', page_count: 3, error_message: null,
      })}\n\n` })
      return
    }
    if (path.endsWith('/retry')) {
      await emitEvent!()
      await new Promise((resolve) => setTimeout(resolve, 150))
      return route.fulfill({ status: 202, json: { ...failedDocument, status: 'processing', processing_attempt_id: 'new-attempt', error_message: null } })
    }
    return route.fulfill({ status: 404 })
  })
  await page.goto('/')
  await expect.poll(() => Boolean(emitEvent)).toBe(true)
  await page.getByRole('button', { name: 'Retry processing AI-engineer.pdf' }).click()
  await expect(page.locator('.document-row .status')).toHaveText('Ready')
  await expect(page.getByRole('status')).toContainText('is ready to search')
})

test('new attempts from another tab update the row and stale events cannot regress it', async ({ page }) => {
  let sendEvents: (() => Promise<void>) | undefined
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'user-1', email: 'user@example.com' } })
    if (path === '/api/chats') return route.fulfill({ json: [] })
    if (path === '/api/documents') return route.fulfill({ json: [failedDocument] })
    if (path === '/api/documents/events') {
      sendEvents = () => route.fulfill({ contentType: 'text/event-stream', body: [
        { document_id: 'document-1', status: 'ready', processing_attempt_id: 'another-tab-attempt', updated_at: '2026-10-22T00:02:00Z', page_count: 3, error_message: null },
        { document_id: 'document-1', status: 'processing_failed', processing_attempt_id: 'previous-attempt', updated_at: failedDocument.updated_at, page_count: 3, error_message: 'Old failure' },
        { document_id: 'document-1', status: 'processing', processing_attempt_id: 'another-tab-attempt', updated_at: '2026-10-22T00:02:00Z', page_count: 3, error_message: null },
      ].map((event) => `data: ${JSON.stringify(event)}\n\n`).join('') })
      return
    }
    return route.fulfill({ status: 404 })
  })
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Retry processing AI-engineer.pdf' })).toBeVisible()
  await expect.poll(() => Boolean(sendEvents)).toBe(true)
  await sendEvents!()
  await expect(page.locator('.document-row .status')).toHaveText('Ready')
  await expect(page.getByRole('button', { name: 'Retry processing AI-engineer.pdf' })).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('is ready to search')
})
