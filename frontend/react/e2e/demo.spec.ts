import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function setup(page: Page) {
  let accepted = false
  let deleted = false
  let uploads = 0
  let bootstraps = 0
  const expiry = new Date(Date.now() + 60 * 60 * 1000).toISOString()
  const document = { id: 'demo-document', user_id: 'demo', original_filename: 'My-private-demo.pdf',
    filename: 'stored.pdf', file_path: '/uploads/stored.pdf', content_type: 'application/pdf',
    status: 'ready', page_count: 1, file_size_bytes: 100, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
  const status = () => ({ is_demo: true, retention_minutes: 75, upload_enabled: true,
    notice_version: 'v2', notice_accepted: accepted, expires_at: expiry })
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json: { access_token: 'token', token_type: 'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json: { id: 'demo', email: 'demo@example.com', role: 'user', is_demo: true } })
    if (path === '/api/demo/status') return route.fulfill({ json: status() })
    if (path === '/api/demo/notice/accept') {
      expect(route.request().headers()['x-csrf-protection']).toBe('1')
      expect(route.request().postDataJSON()).toEqual({ notice_version: 'v2' })
      accepted = true; return route.fulfill({ json: status() })
    }
    if (path === '/api/demo/session') {
      expect(route.request().method()).toBe('DELETE')
      expect(route.request().headers()['x-csrf-protection']).toBe('1')
      expect(route.request().postData()).toBeNull()
      deleted = true; accepted = false; return route.fulfill({ json: { deleted: true, requires_bootstrap: true } })
    }
    if (path === '/api/demo/bootstrap') { bootstraps++; return route.fulfill({ json: status() }) }
    if (path === '/api/documents/upload') {
      expect(accepted).toBe(true); uploads++
      return route.fulfill({ status: 202, json: document })
    }
    if (path === '/api/documents') return route.fulfill({ json: !deleted && uploads ? [document] : [] })
    if (path === '/api/chats') return route.fulfill({ json: [] })
    if (path === '/api/documents/events') return route.fulfill({ contentType: 'text/event-stream', body: ': ready\n\n' })
    return route.fulfill({ status: 404 })
  })
  return { uploads: () => uploads, bootstraps: () => bootstraps }
}

test('demo notice gates upload and self-delete resets every old document before bootstrap', async ({ page }, testInfo) => {
  const state = await setup(page)
  await page.goto('/')
  await expect(page.getByRole('complementary', { name: 'Phiên demo' })).toContainText('75 phút')
  const pdf = { name: 'private.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\nfile') }
  await page.locator('input[type=file]').setInputFiles(pdf)
  const notice = page.getByRole('dialog', { name: 'Thông báo quyền riêng tư demo' })
  await expect(notice).toContainText('sau 75 phút')
  await expect(notice).toContainText('NVIDIA và Groq')
  await expect(notice.getByRole('checkbox')).toHaveCount(0)
  expect(state.uploads()).toBe(0)
  await page.screenshot({ path: testInfo.outputPath('privacy-notice.png'), fullPage:true })
  await notice.getByRole('button', { name: 'Hủy', exact: true }).click()
  expect(state.uploads()).toBe(0)
  await page.locator('input[type=file]').setInputFiles(pdf)
  await notice.getByRole('button', { name: 'Tôi đã hiểu và tiếp tục' }).click()
  await expect(page.locator('.document-row')).toContainText('My-private-demo.pdf')
  expect(state.uploads()).toBe(1)
  if ((page.viewportSize()?.width || 1440) < 1100) await page.getByRole('button', { name:'Close documents',exact:true }).click()
  await page.getByRole('button', { name: 'Xóa dữ liệu demo của tôi', exact: true }).click()
  const confirm = page.getByRole('dialog', { name: 'Xóa dữ liệu demo của tôi' })
  await expect(confirm).toContainText('Bạn có chắc muốn xóa toàn bộ dữ liệu trong phiên demo này không?')
  await confirm.getByRole('button', { name: 'Xóa dữ liệu demo của tôi', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Phiên demo đã kết thúc' })).toBeVisible()
  await expect(page.locator('.document-row')).toHaveCount(0)
  await page.getByRole('button', { name: 'Bắt đầu phiên demo mới' }).click()
  await expect(page.locator('.document-row')).toHaveCount(0)
  await expect(page.locator('.documents-panel')).toBeVisible()
  expect(state.bootstraps()).toBe(1)
  expect(await page.evaluate(() => Object.keys(localStorage).some((key) => /demo/i.test(key)))).toBe(false)
  expect(await page.evaluate(() => Object.keys(sessionStorage).some((key) => /demo/i.test(key)))).toBe(false)
  await page.screenshot({ path: testInfo.outputPath('new-demo-session.png'), fullPage: true })
})

test('demo notice opens before chat creation and cancel sends no chat', async ({ page }) => {
  await setup(page)
  let chatWrites = 0
  await page.route('**/api/chats', async (route) => {
    if (route.request().method() === 'POST') chatWrites++
    return route.fulfill({ json: [] })
  })
  await page.goto('/')
  await page.locator('textarea').fill('My private question')
  await page.locator('textarea').press('Enter')
  const notice=page.getByRole('dialog', { name: 'Thông báo quyền riêng tư demo' })
  await expect(notice).toBeVisible()
  expect(chatWrites).toBe(0)
  await notice.getByRole('button', { name:'Hủy', exact:true }).click()
  expect(chatWrites).toBe(0)
  await expect(page.locator('textarea')).toHaveValue('My private question')
})

test('admin finds email and updates demo configuration using user id only', async ({ page }, testInfo) => {
  let config = { is_demo: false, demo_retention_minutes:60, demo_upload_enabled:true }
  let deleted = false
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url()), path=url.pathname
    if (path === '/api/auth/refresh') return route.fulfill({ json:{ access_token:'token',token_type:'bearer' } })
    if (path === '/api/auth/me') return route.fulfill({ json:{ id:'root',role:'admin',email:'admin@example.com' } })
    if (path === '/api/admin/users') return route.fulfill({ json:{ items:[{ id:'user-uuid',role:'user',email:'demo@example.com',is_active:true,...config }],page:1,page_size:20,total:1 } })
    if (path === '/api/admin/users/user-uuid/demo-config') {
      expect(route.request().headers()['x-csrf-protection']).toBe('1')
      config=route.request().postDataJSON()
      expect(config).toEqual({ is_demo:true,demo_retention_minutes:90,demo_upload_enabled:false })
      return route.fulfill({ json:{ id:'user-uuid',email:'demo@example.com',role:'user',...config } })
    }
    if (path === '/api/admin/users/user-uuid/demo-data') { deleted=true; return route.fulfill({ json:{ deleted:true,sessions_deleted:2 } }) }
    return route.fulfill({ status:404 })
  })
  await page.goto('/admin')
  await page.getByRole('textbox', { name:'Search administration' }).fill('demo@example.com')
  await page.getByRole('button', { name:'Search',exact:true }).click()
  await page.getByRole('button', { name:'Demo settings',exact:true }).click()
  const dialog=page.getByRole('dialog')
  await dialog.getByRole('checkbox', { name:'Demo mode',exact:true }).check()
  await dialog.getByRole('spinbutton', { name:'Retention (minutes)' }).fill('90')
  await dialog.getByRole('checkbox', { name:'Allow demo uploads' }).uncheck()
  await page.screenshot({ path:testInfo.outputPath('admin-demo-settings.png'),fullPage:true })
  await dialog.getByRole('button', { name:'Save demo settings' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name:'Demo settings',exact:true }).click()
  await dialog.getByRole('button', { name:'Delete all demo data',exact:true }).click()
  expect(deleted).toBe(false)
  await dialog.getByRole('button', { name:'Confirm delete all demo data',exact:true }).click()
  await expect(dialog.getByRole('status')).toContainText('deleted')
  expect(deleted).toBe(true)
})


test('demo expiry closes the workspace before another action can send data', async ({ page }) => {
  await page.clock.install({ time:new Date() })
  await setup(page)
  await page.goto('/')
  await expect(page.locator('.workspace')).toBeVisible()
  await page.clock.fastForward(61*60*1000)
  await expect(page.getByRole('heading', { name:'Phiên demo đã kết thúc' })).toBeVisible()
  await expect(page.locator('.workspace')).toHaveCount(0)
})
