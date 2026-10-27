import { request } from './http'
import type { User, Document, Chat, ChatMessage } from './types'

export type Page<T> = { items: T[]; total: number; page: number; page_size: number }
export type AdminDocument = Document & { owner_email: string }
export type AdminChat = Chat & { owner_email: string }
export type AuditEvent = {
  id: number; actor_id: string | null; target_user_id: string | null; action: string
  resource_id: string | null; outcome: string; request_id: string | null
  actor_email?: string | null; target_email?: string | null
  details: Record<string, unknown> | null; created_at: string
}
export type AdminTab = 'users' | 'documents' | 'chats' | 'activity'
export type AdminRow = User | AdminDocument | AdminChat | AuditEvent

export const adminApi = {
  list(tab: AdminTab, page: number, q: string, userId: string, signal?: AbortSignal) {
    const params = new URLSearchParams({ page: String(page), page_size: '20', q })
    if (userId && tab !== 'users') params.set('user_id', userId)
    return request<Page<AdminRow>>(`/admin/${tab}?${params}`, { signal }, true)
  },
  createUser(payload: { email: string; password: string; role: User['role'] }) {
    return request<User>('/admin/users', { method: 'POST', body: JSON.stringify(payload) }, true)
  },
  updateUser(id: string, payload: { role?: User['role']; is_active?: boolean }) {
    return request<User>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }, true)
  },
  messages(id: string, page: number) {
    return request<Page<ChatMessage>>(`/admin/chats/${id}/messages?page=${page}&page_size=20`, {}, true)
  },
}
