import { expect, test } from '@playwright/test'

for (const failure of ['network', 'eof'] as const) {
  test(`recovers ${failure} document events and missed updates without a network error banner`, async ({ page }) => {
    let connections = 0
    let document = {
      id: 'document-1', original_filename: 'Reconnect.pdf', status: 'processing',
      file_size_bytes: 100, page_count: null as number | null, error_message: null,
      processing_attempt_id: 'attempt-1', updated_at: '2026-10-24T00:00:00Z',
    }
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'access', token_type: 'bearer' } })
      if (path === '/api/auth/me') return route.fulfill({ json: { id: 'user-1', email: 'user@example.com', role: 'user' } })
      if (path === '/api/chats') return route.fulfill({ json: [] })
      if (path === '/api/documents') return route.fulfill({ json: [document] })
      // Disable polling as a recovery mechanism: this test must recover through
      // SSE reconnect + snapshot reconciliation, without a replayed Redis event.
      if (path === '/api/documents/document-1') return route.fulfill({ status: 503, json: { detail: 'Temporary outage' } })
      if (path === '/api/documents/events') {
        connections += 1
        if (connections === 1) {
          if (failure === 'network') return route.abort('failed')
          return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' })
        }
        document = { ...document, status: 'ready', page_count: 2, updated_at: '2026-10-24T00:01:00Z' }
        return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' })
      }
      return route.fulfill({ status: 404 })
    })
    await page.goto('/')
    const row = page.locator('.document-row', { hasText: 'Reconnect.pdf' })
    await expect(row.locator('.status')).toHaveText('Ready', { timeout: 10_000 })
    expect(connections).toBeGreaterThanOrEqual(2)
    await expect(row.locator('.document-item')).toBeEnabled()
    await expect(page.locator('.notice--error')).toHaveCount(0)
    await expect(page.getByText(/Network error|Failed to fetch|Temporary outage/, { exact: false })).toHaveCount(0)
  })
}
