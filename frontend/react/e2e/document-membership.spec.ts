import { expect, test } from '@playwright/test'
import type { Route } from '@playwright/test'

test('discovers a remote upload on SSE reconnect and removes a remote deletion', async ({ page }) => {
  let visible=false, lists=0
  let stream: Route | undefined
  const now=new Date().toISOString()
  const document={id:'remote',user_id:'user',filename:'remote.pdf',original_filename:'Remote-upload.pdf',
    status:'ready',page_count:1,file_size_bytes:100,created_at:now,updated_at:now}
  await page.route('**/api/**', async route=>{
    const path=new URL(route.request().url()).pathname
    if(path==='/api/auth/refresh')return route.fulfill({json:{access_token:'access',token_type:'bearer'}})
    if(path==='/api/auth/me')return route.fulfill({json:{id:'user',email:'user@example.com',role:'user'}})
    if(path==='/api/chats')return route.fulfill({json:[]})
    if(path==='/api/documents'){lists++;return route.fulfill({json:visible?[document]:[]})}
    if(path==='/api/documents/events'){if(stream)return route.fulfill({contentType:'text/event-stream',body:': connected\n\n'});stream=route;return}
    return route.fulfill({status:404})
  })
  await page.goto('/')
  await expect(page.locator('.workspace')).toBeVisible()
  await expect.poll(()=>Boolean(stream)).toBe(true)
  visible=true
  await stream!.fulfill({contentType:'text/event-stream',body:': connected\n\n'})
  await expect(page.locator('.document-row')).toContainText('Remote-upload.pdf')
  const old=lists
  visible=false
  await expect.poll(()=>lists, {timeout:10000}).toBeGreaterThan(old)
  await expect(page.locator('.document-row')).toHaveCount(0)
})
