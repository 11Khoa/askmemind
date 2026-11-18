import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { api } from '../src/lib/api'
import { session } from '../src/lib/session'
const fetchMock=vi.fn<typeof fetch>()
const handlers=()=>({onToken:vi.fn(),onReplace:vi.fn(),onFinal:vi.fn()})
beforeEach(()=>{fetchMock.mockReset();vi.stubGlobal('fetch',fetchMock);session.set({access_token:'access',token_type:'bearer'})})
afterEach(()=>{session.set(null);vi.unstubAllGlobals()})
it('rejects EOF after partial tokens without a final event',async()=>{
 fetchMock.mockResolvedValue(new Response('event: token\ndata: {"token":"partial"}\n\n',{headers:{'Content-Type':'text/event-stream'}}))
 const h=handlers()
 await expect(api.streamQuestion('chat','question',null,3,h)).rejects.toMatchObject({status:502})
 expect(h.onToken).toHaveBeenCalledWith('partial');expect(h.onFinal).not.toHaveBeenCalled()
})
it('accepts a completed final answer',async()=>{
 const message={id:'answer',content:'Answer',role:'assistant'}
 fetchMock.mockResolvedValue(new Response(`event: final\ndata: ${JSON.stringify(message)}\n\n`,{headers:{'Content-Type':'text/event-stream'}}))
 const h=handlers();await api.streamQuestion('chat','question',null,3,h)
 expect(h.onFinal).toHaveBeenCalledWith(message)
})
it('rejects an HTML success fallback instead of reporting completion',async()=>{
 fetchMock.mockResolvedValue(new Response('<html>fallback</html>',{headers:{'Content-Type':'text/html'}}))
 await expect(api.streamQuestion('chat','question',null,3,handlers())).rejects.toMatchObject({status:502})
})
it('keeps server error events as failures',async()=>{
 fetchMock.mockResolvedValue(new Response('event: error\ndata: {"detail":"Unavailable"}\n\n',{headers:{'Content-Type':'text/event-stream'}}))
 await expect(api.streamQuestion('chat','question',null,3,handlers())).rejects.toThrow('Unavailable')
})
