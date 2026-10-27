export type User = {
  role: 'user' | 'admin'
  id: string
  email: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export type DocumentStatus =
  | 'uploaded'
  | 'processing'
  | 'ready'
  | 'processing_failed'
  | 'failed'
  | string

export type DocumentProcessingProgress = {
  stage?: 'queued' | 'extracting' | 'ocr' | 'chunking' | 'embedding' | 'ready' | 'failed'
  completed_pages?: number
  total_pages?: number
  current_page?: number | null
  reused_pages?: number
  completed_chunks?: number
  total_chunks?: number
  failed_stage?: string | null
  error_code?: string | null
}

export type DocumentStatusEvent = {
  user_id?: string
  processing_progress?: DocumentProcessingProgress | null
  updated_at?: string | null
  processing_attempt_id?: string | null
  document_id: string
  status: DocumentStatus
  page_count: number | null
  error_message: string | null
}

export type Document = {
  processing_progress?: DocumentProcessingProgress | null
  processing_attempt_id?: string | null
  id: string
  user_id: string
  filename: string
  original_filename: string
  file_path: string
  content_type: string
  file_size_bytes: number
  status: DocumentStatus
  page_count: number | null
  source_type: string
  source_metadata: Record<string, unknown> | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export type Chat = {
  id: string
  user_id: string
  title: string | null
  created_at: string
  updated_at: string
}

export type Citation = {
  source_number: number
  document_id: string
  chunk_id: string
  chunk_index: number
  page_number: number | null
  start_time_seconds: number | null
  end_time_seconds: number | null
  distance: number | null
}

export type MessageMetadata = {
  citations?: Citation[]
  context?: string
}

export type ChatMessage = {
  id: string
  chat_id: string
  message_index: number
  role: 'user' | 'assistant'
  content: string
  message_metadata: MessageMetadata | null
  created_at: string
}

export type TokenResponse = {
  access_token: string
  token_type: string
}

