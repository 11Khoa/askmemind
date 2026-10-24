import type {
  Chat,
  ChatMessage,
  Document,
  User,
} from './types'
import { ApiError, authenticatedResponse, loginSession, logoutSession, request } from './http'

export { ApiError } from './http'
import { readSseStream } from './sse'
import { subscribeDocumentEvents } from './documentEvents'

type QuestionStreamHandlers = {
  onToken: (token: string) => void
  onReplace: (content: string) => void
  onFinal: (message: ChatMessage) => void
}

export function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

export const api = {
  login(email: string, password: string) {
    return loginSession(email, password)
  },

  register(email: string, password: string) {
    return request<User>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },

  logout() {
    return logoutSession()
  },

  forgotPassword(email: string) {
    return request<{ message: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    })
  },

  resetPassword(token: string, newPassword: string) {
    return request<void>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    })
  },

  me() {
    return request<User>('/auth/me', {}, true)
  },

  listDocuments(signal?: AbortSignal) {
    return request<Document[]>('/documents', { signal }, true)
  },

  deleteDocument(documentId: string) {
    return request<void>(`/documents/${documentId}`, { method: 'DELETE' }, true)
  },

  sourcePassage(documentId: string, chunkId: string) {
    return request<{ content: string; page_number: number | null }>(
      `/documents/${documentId}/chunks/${chunkId}`, {}, true,
    )
  },

  async documentPdf(documentId: string, signal: AbortSignal) {
    const response = await authenticatedResponse(`/documents/${documentId}/file`, { signal })
    return response.blob()
  },

  deleteChat(chatId: string) {
    return request<void>(`/chats/${chatId}`, { method: 'DELETE' }, true)
  },

  getDocument(documentId: string) {
    return request<Document>(`/documents/${documentId}`, {}, true)
  },

  retryDocument(documentId: string) {
    return request<Document>(`/documents/${documentId}/retry`, { method: 'POST' }, true)
  },

  uploadDocument(file: File) {
    const body = new FormData()
    body.append('file', file)
    return request<Document>(
      '/documents/upload',
      { method: 'POST', body },
      true,
    )
  },

  subscribeDocumentEvents,

  listChats() {
    return request<Chat[]>('/chats', {}, true)
  },

  createChat(title: string | null) {
    return request<Chat>(
      '/chats',
      {
        method: 'POST',
        body: JSON.stringify({ title }),
      },
      true,
    )
  },

  listMessages(chatId: string) {
    return request<ChatMessage[]>(
      `/chats/${chatId}/messages`,
      {},
      true,
    )
  },

  askQuestion(
    chatId: string,
    content: string,
    documentId: string | null,
    topK: number,
  ) {
    return request<ChatMessage>(
      `/chats/${chatId}/questions`,
      {
        method: 'POST',
        body: JSON.stringify({
          content,
          document_id: documentId,
          top_k: topK,
        }),
      },
      true,
    )
  },

  async streamQuestion(
    chatId: string,
    content: string,
    documentId: string | null,
    topK: number,
    handlers: QuestionStreamHandlers,
    signal?: AbortSignal,
  ) {
    const response = await authenticatedResponse(`/chats/${chatId}/questions/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        content,
        document_id: documentId,
        top_k: topK,
      }),
      signal,
    })

    await readSseStream(response, (frame) => {
      const data = frame.data as { token?: string; detail?: string }
      if (frame.event === 'token') {
        handlers.onToken(data.token || '')
      } else if (frame.event === 'replace') {
        handlers.onReplace(data.token || '')
      } else if (frame.event === 'final') {
        handlers.onFinal(frame.data as ChatMessage)
      } else if (frame.event === 'error') {
        throw new ApiError(data.detail || 'Streaming answer failed', 500)
      }
    })
  },
}
