import { expect, test } from '@playwright/test'
import type { Document } from '../src/lib/types'

const initial: Document = {
  id: 'scan', user_id: 'user', filename: 'scan.pdf', original_filename: 'Scan-144.pdf',
  file_path: '/uploads/scan.pdf', content_type: 'application/pdf', file_size_bytes: 100,
  status: 'processing', processing_attempt_id: 'attempt', page_count: null,
  source_type: 'pdf', source_metadata: null, error_message: null,
  created_at: '2026-10-27T00:00:00Z', updated_at: '2026-10-27T00:00:00Z',
  processing_progress: { stage: 'ocr', current_page: 3, completed_pages: 2, total_pages: 144 },
}

test('updates same-status OCR progress over SSE and restores it on reload', async ({ page }, testInfo) => {
  let document = { ...initial }
  let snapshot = { ...initial }
  let emit: (() => Promise<void>) | undefined
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'user', email: 'user@example.com', role: 'user' } })
    if (path === '/api/chats') return route.fulfill({ json: [] })
    if (path === '/api/documents') return route.fulfill({ json: [snapshot] })
    if (path === '/api/documents/scan') return route.fulfill({ json: snapshot })
    if (path === '/api/documents/events') {
      emit = () => route.fulfill({ contentType: 'text/event-stream', body: `data: ${JSON.stringify({
        ...document, document_id: document.id,
      })}\n\n` })
      return
    }
    return route.fulfill({ status: 404 })
  })
  await page.goto('/')
  const row = page.locator('.document-row', { hasText: 'Scan-144.pdf' })
  await expect(row).toContainText('Recognizing text: page 3 of 144')
  await expect.poll(() => Boolean(emit)).toBe(true)
  document = { ...document, updated_at: '2026-10-27T00:00:01Z',
    processing_progress: { stage: 'ocr', current_page: 23, completed_pages: 22, total_pages: 144 } }
  await emit!()
  await expect(row).toContainText('Recognizing text: page 23 of 144')
  await expect(row.getByRole('progressbar')).toHaveAttribute('value', '22')
  await expect(row.getByRole('progressbar')).toHaveAttribute('max', '144')
  snapshot = document
  await page.reload()
  await expect(row).toContainText('Recognizing text: page 23 of 144')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('ocr-progress.png'), fullPage: true })
})

test('explains failures safely and shows saved pages after retry', async ({ page }, testInfo) => {
  const rawError = 'internal-provider-url-and-secret-must-not-be-rendered'
  let document: Document = { ...initial, status: 'processing_failed', error_message: rawError,
    processing_progress: { stage: 'failed', error_code: 'ocr_timeout', completed_pages: 129, total_pages: 144 } }
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'user', email: 'user@example.com', role: 'user' } })
    if (path === '/api/chats') return route.fulfill({ json: [] })
    if (path === '/api/documents') return route.fulfill({ json: [document] })
    if (path === '/api/documents/scan') return route.fulfill({ json: document })
    if (path === '/api/documents/events') return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' })
    if (path === '/api/documents/scan/retry') {
      document = { ...document, status: 'processing', processing_attempt_id: 'retry', error_message: null,
        updated_at: '2026-10-27T00:01:00Z', processing_progress: {
          stage: 'ocr', current_page: 130, completed_pages: 129, total_pages: 144, reused_pages: 129,
        } }
      return route.fulfill({ status: 202, json: document })
    }
    return route.fulfill({ status: 404 })
  })
  await page.goto('/')
  const row = page.locator('.document-row', { hasText: 'Scan-144.pdf' })
  await expect(row).toContainText('Text recognition timed out.')
  await expect(row).toContainText('129 pages are saved.')
  await expect(page.getByText(rawError)).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('ocr-failed.png'), fullPage: true })
  await row.getByRole('button', { name: 'Retry processing Scan-144.pdf' }).click()
  await expect(row).toContainText('Recognizing text: page 130 of 144')
  await expect(row).toContainText('Reused 129 saved pages.')
  await expect(row.locator('.document-error')).toHaveCount(0)
})

test('administrators can read processing failures in the document table', async ({ page }, testInfo) => {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'admin', email: 'admin@example.com', role: 'admin' } })
    if (path === '/api/admin/users') return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } })
    if (path === '/api/admin/documents') return route.fulfill({ json: {
      items: [{ ...initial, owner_email: 'user@example.com', status: 'processing_failed',
        error_message: 'PDF does not contain extractable text', processing_progress: {
          stage: 'failed', error_code: 'no_text', completed_pages: 4, total_pages: 4,
        } }], total: 1, page: 1, page_size: 20,
    } })
    return route.fulfill({ status: 404 })
  })
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Documents', exact: true }).click()
  await expect(page.locator('.admin-table-wrap')).toContainText('No readable text was found.')
  await expect(page.locator('.admin-table-wrap')).toContainText('OCR confidence settings')
  await page.screenshot({ path: testInfo.outputPath('admin-processing-error.png'), fullPage: true })
})
