import { expect, test } from '@playwright/test'
import type { Document } from '../src/lib/types'

const initial: Document = {
  id: 'scan', user_id: 'user', filename: 'scan.pdf', original_filename: 'Long-scan.pdf',
  file_path: '/uploads/scan.pdf', content_type: 'application/pdf', file_size_bytes: 100,
  status: 'processing', processing_attempt_id: 'attempt', page_count: null,
  source_type: 'pdf', source_metadata: null, error_message: null,
  created_at: '2026-10-27T00:00:00Z', updated_at: '2026-10-27T00:00:00Z',
  processing_progress: { stage: 'ocr', current_page: 23, completed_pages: 22, total_pages: 144,
    started_at: '2026-10-27T00:00:00Z', finished_at: null },
}

test('elapsed time ticks, cancellation freezes it and Resume retains saved pages', async ({ page }, testInfo) => {
  await page.clock.install({ time: new Date('2026-10-27T00:00:20Z') })
  await page.clock.pauseAt(new Date('2026-10-27T00:00:21Z'))
  let document = { ...initial }
  let cancellations = 0
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'user', email: 'user@example.com', role: 'user' } })
    if (path === '/api/chats') return route.fulfill({ json: [] })
    if (path === '/api/documents') return route.fulfill({ json: [document] })
    if (path === '/api/documents/scan') return route.fulfill({ json: document })
    if (path === '/api/documents/events') return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' })
    if (path === '/api/documents/scan/cancel') {
      cancellations++
      expect(route.request().method()).toBe('POST')
      expect(route.request().headers().authorization).toBe('Bearer access')
      document = { ...document, status: 'cancelled', processing_attempt_id: null,
        updated_at: '2026-10-27T00:00:26Z', processing_progress: {
          ...document.processing_progress, stage: 'cancelled', finished_at: '2026-10-27T00:00:26Z',
        } }
      return route.fulfill({ json: document })
    }
    if (path === '/api/documents/scan/retry') {
      document = { ...document, status: 'processing', processing_attempt_id: 'resumed',
        updated_at: '2026-10-27T00:00:32Z', processing_progress: {
          stage: 'ocr', current_page: 23, completed_pages: 22, total_pages: 144, reused_pages: 22,
          started_at: '2026-10-27T00:00:32Z', finished_at: null,
        } }
      return route.fulfill({ status: 202, json: document })
    }
    return route.fulfill({ status: 404 })
  })
  await page.goto('/')
  const row = page.locator('.document-row', { hasText: 'Long-scan.pdf' })
  await expect(row.locator('.document-uploaded time')).toContainText('Uploaded at: 27 Oct 2026 · 07:00 GMT+7')
  await expect(row.locator('.document-uploaded time')).toHaveAttribute('datetime', initial.created_at)
  await expect(row.locator('.document-elapsed')).toHaveText('Elapsed: 00:21')
  await page.clock.fastForward(5000)
  await expect(row.locator('.document-elapsed')).toHaveText('Elapsed: 00:26')
  await row.getByRole('button', { name: 'Cancel processing Long-scan.pdf' }).click()
  await expect(row.locator('.status')).toHaveText('Cancelled')
  await expect(row).toContainText('22 pages are saved.')
  await expect(row.locator('.document-elapsed')).toHaveText('Duration: 00:26')
  await page.clock.fastForward(5000)
  await expect(row.locator('.document-elapsed')).toHaveText('Duration: 00:26')
  expect(cancellations).toBe(1)
  await page.screenshot({ path: testInfo.outputPath('cancelled-document.png'), fullPage: true })
  await row.getByRole('button', { name: 'Resume processing Long-scan.pdf' }).click()
  await expect(row).toContainText('Reused 22 saved pages.')
  await expect(row.locator('.document-uploaded time')).toHaveAttribute('datetime', initial.created_at)
  await expect(row.locator('.status')).toHaveText('Processing')
  await expect(row.getByRole('button', { name: 'Cancel processing Long-scan.pdf' })).toBeVisible()
})

test('administrator can cancel processing from the live table', async ({ page }) => {
  let document: Document = { ...initial }
  let cancelled = false
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'admin', email: 'admin@example.com', role: 'admin' } })
    if (path === '/api/admin/users') return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } })
    if (path === '/api/admin/documents') return route.fulfill({ json: {
      items: [{ ...document, owner_email: 'user@example.com' }], total: 1, page: 1, page_size: 20,
    } })
    if (path === '/api/admin/documents/events') return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' })
    if (path === '/api/documents/scan/cancel') {
      cancelled = true
      document = { ...document, status: 'cancelled', processing_attempt_id: null,
        updated_at: '2026-10-27T00:00:30Z', processing_progress: {
          ...document.processing_progress, stage: 'cancelled', finished_at: '2026-10-27T00:00:30Z',
        } }
      return route.fulfill({ json: document })
    }
    return route.fulfill({ status: 404 })
  })
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Documents', exact: true }).click()
  await page.getByRole('button', { name: 'Cancel processing Long-scan.pdf' }).click()
  await expect(page.locator('.admin-table-wrap')).toContainText('Processing cancelled. Saved work is kept.')
  await expect(page.locator('.admin-table-wrap .document-elapsed')).toHaveText('Duration: 00:30')
  expect(cancelled).toBe(true)
})
