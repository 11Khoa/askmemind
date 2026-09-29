import type {
  Chat,
  ChatMessage,
  Document,
  TokenResponse,
  User,
} from './types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: unknown }
      if (typeof payload.detail === 'string') {
        message = payload.detail
      } else if (payload.detail) {
        message = JSON.stringify(payload.detail)
      }
    } catch {
      // Keep the HTTP fallback message when the response is not JSON.
    }
    throw new ApiError(message, response.status)
  }

  return response.json() as Promise<T>
}

export const api = {
  login(email: string, password: string) {
    return request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },

  register(email: string, password: string) {
    return request<User>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },

  me(token: string) {
    return request<User>('/auth/me', {}, token)
  },

  listDocuments(token: string) {
    return request<Document[]>('/documents', {}, token)
  },

  uploadDocument(token: string, file: File) {
    const body = new FormData()
    body.append('file', file)
    return request<Document>(
      '/documents/upload',
      { method: 'POST', body },
      token,
    )
  },

  listChats(token: string) {
    return request<Chat[]>('/chats', {}, token)
  },

  createChat(token: string, title: string | null) {
    return request<Chat>(
      '/chats',
      {
        method: 'POST',
        body: JSON.stringify({ title }),
      },
      token,
    )
  },

  listMessages(token: string, chatId: string) {
    return request<ChatMessage[]>(
      `/chats/${chatId}/messages`,
      {},
      token,
    )
  },

  askQuestion(
    token: string,
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
      token,
    )
  },
}
