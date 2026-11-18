import { expect,test } from '@playwright/test'

test('locks question submission before the asynchronous demo check', async ({page})=>{
  let checks=0,questions=0,block=false
  let release: (()=>void)|undefined
  const gate=new Promise<void>(resolve=>{release=resolve})
  const now=new Date().toISOString()
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname
    if(path==='/api/auth/refresh')return route.fulfill({json:{access_token:'access',token_type:'bearer'}})
    if(path==='/api/auth/me')return route.fulfill({json:{id:'user',email:'demo@example.com',role:'user',is_demo:true}})
    if(path==='/api/demo/status'){
      checks++;if(block)await gate
      return route.fulfill({json:{is_demo:true,retention_minutes:60,notice_version:'v1',notice_accepted:true,upload_enabled:true,expires_at:new Date(Date.now()+3600000).toISOString()}})
    }
    if(path==='/api/documents')return route.fulfill({json:[]})
    if(path==='/api/documents/events')return route.fulfill({contentType:'text/event-stream',body:': ready\n\n'})
    if(path==='/api/chats')return route.fulfill({json:[{id:'chat',user_id:'user',title:'Question test',created_at:now,updated_at:now}]})
    if(path==='/api/chats/chat/messages')return route.fulfill({json:[]})
    if(path==='/api/chats/chat/questions/stream'){
      questions++
      return route.fulfill({contentType:'text/event-stream',body:`event: final\ndata: ${JSON.stringify({id:'answer',chat_id:'chat',role:'assistant',content:'Answer',message_index:1,created_at:now,message_metadata:null})}\n\n`})
    }
    return route.fulfill({status:404})
  })
  await page.goto('/')
  if((page.viewportSize()?.width||1440)<1100)await page.getByRole('button',{name:'Close documents',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Question test'})).toBeVisible()
  const initialChecks=checks
  block=true
  await page.locator('textarea').fill('One question')
  await page.getByRole('button',{name:'Send question',exact:true}).dblclick({delay:30})
  await expect.poll(()=>checks).toBe(initialChecks+1)
  expect(questions).toBe(0)
  release!()
  await expect.poll(()=>questions).toBe(1)
  await expect(page.locator('textarea')).toBeEnabled()
})
