import type {
  Chat,
  ChatMessage,
  Document,
  DocumentStatusEvent,
  TokenResponse,
  User,
} from './types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

type SseFrame = {
  event: string
  data: unknown
}

type QuestionStreamHandlers = {
  onToken: (token: string) => void
  onReplace: (content: string) => void
  onFinal: (message: ChatMessage) => void
}

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

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
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

  subscribeDocumentEvents(
    token: string,
    onEvent: (event: DocumentStatusEvent) => void,
    onError: (error: unknown) => void,
  ) {
    const controller = new AbortController()

    void (async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/documents/events`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new ApiError(
            `Document event stream failed with status ${response.status}`,
            response.status,
          )
        }

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

  async streamQuestion(
    token: string,
    chatId: string,
    content: string,
    documentId: string | null,
    topK: number,
    handlers: QuestionStreamHandlers,
  ) {
    const response = await fetch(`${API_BASE_URL}/chats/${chatId}/questions/stream`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        content,
        document_id: documentId,
        top_k: topK,
      }),
    })

    if (!response.ok) {
      let message = `Request failed with status ${response.status}`
      try {
        const payload = (await response.json()) as { detail?: unknown }
        if (typeof payload.detail === 'string') message = payload.detail
      } catch {
        // Keep the HTTP fallback message when the response is not JSON.
      }
      throw new ApiError(message, response.status)
    }

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
