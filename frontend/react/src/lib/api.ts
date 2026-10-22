import type {
  Chat,
  ChatMessage,
  Document,
  DocumentStatusEvent,
  User,
} from './types'
import { ApiError, authenticatedResponse, loginSession, logoutSession, request } from './http'

export { ApiError } from './http'

type SseFrame = {
  event: string
  data: unknown
}

type QuestionStreamHandlers = {
  onToken: (token: string) => void
  onReplace: (content: string) => void
  onFinal: (message: ChatMessage) => void
}

function parseSseFrame(frame: string): SseFrame | null {
  const event = frame
    .split('\n')
    .find((line) => line.startsWith('event:'))
    ?.slice(6)
    .trim() || 'message'
  const data = frame
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')

  if (!data) return null
  return { event, data: JSON.parse(data) as unknown }
}

async function readSseStream(
  response: Response,
  onFrame: (frame: SseFrame) => void,
) {
  if (!response.body) {
    throw new ApiError('Streaming response did not include a body', response.status)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''

    for (const rawFrame of frames) {
      const frame = parseSseFrame(rawFrame)
      if (frame) onFrame(frame)
    }
  }
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

  listDocuments() {
    return request<Document[]>('/documents', {}, true)
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

  subscribeDocumentEvents(
    onEvent: (event: DocumentStatusEvent) => void,
    onError: (error: unknown) => void,
  ) {
    const controller = new AbortController()

    void (async () => {
      try {
        const response = await authenticatedResponse('/documents/events', {
          signal: controller.signal,
        })

        await readSseStream(response, (frame) => {
          onEvent(frame.data as DocumentStatusEvent)
        })
      } catch (error) {
        if (!controller.signal.aborted && !isAbortError(error)) {
          onError(error)
        }
      }
    })()

    return () => controller.abort()
  },

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
