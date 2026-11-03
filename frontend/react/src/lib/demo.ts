import { request } from './http'
export type DemoStatus = {
  is_demo: boolean
  retention_minutes: number
  upload_enabled: boolean
  notice_version: string
  notice_accepted: boolean
  expires_at: string | null
}
export const demoApi = {
  status: () => request<DemoStatus>('/demo/status', {}, true),
  bootstrap: () => request<DemoStatus>('/demo/bootstrap', { method: 'POST' }, true),
  accept: (noticeVersion: string) => request<DemoStatus>('/demo/notice/accept', {
    method: 'POST', body: JSON.stringify({ notice_version: noticeVersion }),
  }, true),
  clear: () => request<{ deleted: boolean; requires_bootstrap: boolean }>('/demo/session', { method: 'DELETE' }, true),
}
