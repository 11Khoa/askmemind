import logging
import uuid
from pathlib import Path
from functools import lru_cache

import jwt
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from redis import Redis

from app.agents.retrieval_agent import (
    KeywordQueryRewriteTool,
    RetrievalAgent,
    RetrievalSearchTool,
)
from app.database import SessionLocal, get_db
from app.repositories.chat_repository import ChatRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.chunk_repository import ChunkRepository
from app.services.auth_service import AuthService
from app.services.token_store import TokenStore
from app.services.password_reset_service import PasswordResetService
from app.services.reset_email_service import ResetEmailService
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.services.file_storage_service import FileStorageService
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.chunk_service import ChunkingService
from app.services.document_events import document_event_broker
from app.services.document_processing_service import DocumentProcessingService
from app.services.extraction.pdf_extraction_service import PdfExtractionService
from app.services.embedding_service import EmbeddingService
from app.services.providers.nvidia_embedding_provider import NvidiaEmbeddingProvider
from app.services.retrieval_service import RetrievalService
from app.services.guardrail_service import GuardrailService
from app.services.reranking_service import RerankingService
from app.services.llm_service import LLMService
from app.services.providers.groq_llm_provider import GroqLLMProvider
from app.services.context_builder_service import ContextBuilderService
from app.services.rag_service import RagService
from app.models.user import User
from app.core.config import settings
from app.core.security import AccessTokenPayload, decode_access_token
from app.core.logging import bind_user_id, log_event

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
logger = logging.getLogger(__name__)


def get_chat_service(
    db: Annotated[Session, Depends(get_db)],
) -> ChatService:
    user_repository = UserRepository(db=db)
    chat_repository = ChatRepository(db=db)
    rag_service = get_rag_service(db=db)

    return ChatService(
        chat_repository=chat_repository,
        user_repository=user_repository,
        rag_service=rag_service,
    )


def get_auth_service(
    db: Annotated[Session, Depends(get_db)],
) -> AuthService:
    user_repository = UserRepository(db=db)
    return AuthService(
        user_repository=user_repository,
        refresh_token_repository=RefreshTokenRepository(db=db),
    )


def get_password_reset_service(
    db: Annotated[Session, Depends(get_db)],
) -> PasswordResetService:
    return PasswordResetService(
        UserRepository(db),
        PasswordResetRepository(db),
        ResetEmailService(settings),
    )


@lru_cache
def get_token_store() -> TokenStore:
    return TokenStore(
        Redis.from_url(
            settings.redis_url,
            socket_timeout=2,
            socket_connect_timeout=2,
            decode_responses=True,
        )
    )


def get_current_access_payload(
    token: Annotated[str, Depends(oauth2_scheme)],
    token_store: Annotated[TokenStore, Depends(get_token_store)],
) -> AccessTokenPayload:
    try:
        token_payload = decode_access_token(token)
        uuid.UUID(token_payload.subject)
    except (ValueError, jwt.PyJWTError) as error:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    if token_store.is_revoked(token_payload.jti):
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_payload


def get_current_user(
    token_payload: Annotated[AccessTokenPayload, Depends(get_current_access_payload)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user_id = uuid.UUID(token_payload.subject)
    user_repository = UserRepository(db=db)
    user = user_repository.get_user_by_id(user_id)

    if (
        user is None
        or not user.is_active
        or user.token_version != token_payload.token_version
    ):
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    bind_user_id(user.id)
    return user


def get_document_service(
    db: Annotated[Session, Depends(get_db)],
) -> DocumentService:
    user_repository = UserRepository(db=db)
    document_repository = DocumentRepository(db=db)

    return DocumentService(
        document_repository=document_repository,
        user_repository=user_repository,
    )


def get_file_storage_service() -> FileStorageService:
    return FileStorageService(upload_dir=str(settings.resolved_upload_dir))


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    # Read role from the current DB-backed user, never a client/JWT role claim.
    if getattr(user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Administrator permission required")
    return user


def build_document_processing_service(db: Session) -> DocumentProcessingService:
    chunk_repository = ChunkRepository(db=db)
    document_repository = DocumentRepository(db=db)

    chunk_persistence_service = ChunkPersistenceService(
        chunk_repository=chunk_repository,
    )
    embedding_service = get_embedding_service()

    return DocumentProcessingService(
        document_repository=document_repository,
        extraction_service=PdfExtractionService(),
        chunking_service=ChunkingService(),
        chunk_persistence_service=chunk_persistence_service,
        embedding_service=embedding_service,
        unit_of_work=db,
        embedding_batch_size=settings.embedding_batch_size,
    )


def get_document_processing_service(
    db: Annotated[Session, Depends(get_db)],
) -> DocumentProcessingService:
    return build_document_processing_service(db=db)


def process_document_in_background(
    document_id: uuid.UUID,
    file_path: Path,
    request_id: str | None,
    user_id: uuid.UUID,
    processing_attempt_id: uuid.UUID | None = None,
) -> None:
    db = SessionLocal()
    repository = DocumentRepository(db=db)

    try:
        with repository.processing_lock(document_id) as acquired:
            if not acquired:
                return
            document = repository.get_document_by_id(document_id=document_id)
            if (
                document is None
                or document.user_id != user_id
                or document.status != "processing"
                or document.processing_attempt_id != processing_attempt_id
            ):
                return
            try:
                service = build_document_processing_service(db=db)
                service.process_document(document_id=document_id, file_path=file_path)
            except Exception as error:
                db.rollback()
                repository.fail_attempt(document_id, processing_attempt_id, str(error))
                log_event(
                    logger,
                    logging.ERROR,
                    "document.processing.background_failed",
                    request_id=request_id,
                    user_id=str(user_id),
                    document_id=str(document_id),
                    error_type=type(error).__name__,
                )
            document = repository.get_document_by_id(document_id=document_id)
            if document is not None:
                try:
                    document_event_broker.publish(
                        user_id,
                        {
                            "document_id": str(document.id),
                            "status": document.status,
                            "page_count": document.page_count,
                            "error_message": document.error_message,
                            "updated_at": (
                                document.updated_at.isoformat()
                                if document.updated_at
                                else None
                            ),
                            "processing_attempt_id": (
                                str(document.processing_attempt_id)
                                if document.processing_attempt_id
                                else None
                            ),
                        },
                    )
                except Exception as error:
                    # SSE is best effort; notification failure must not undo ready.
                    log_event(
                        logger,
                        logging.WARNING,
                        "document.processing.event_failed",
                        request_id=request_id,
                        user_id=str(user_id),
                        document_id=str(document_id),
                        error_type=type(error).__name__,
                    )
    finally:
        db.close()


def get_embedding_service() -> EmbeddingService:
    if settings.embedding_provider == "nvidia":
        if not settings.nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY is required for NVIDIA embeddings")

        provider = NvidiaEmbeddingProvider(
            api_key=settings.nvidia_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
        )

        return EmbeddingService(
            provider=provider,
            embedding_provider=settings.embedding_provider,
            embedding_model=settings.embedding_model,
            embedding_dimensions=settings.embedding_dimensions,
        )

    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")


def get_retrieval_service(
    db: Annotated[Session, Depends(get_db)],
) -> RetrievalService:
    chunk_repository = ChunkRepository(db=db)
    embedding_service = get_embedding_service()

    return RetrievalService(
        embedding_service=embedding_service,
        chunk_repository=chunk_repository,
        hybrid_search_enabled=settings.hybrid_search_enabled,
        embedding_v2_enabled=settings.embedding_v2_enabled,
    )


def get_llm_service() -> LLMService:
    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required for Groq LLMs")
        provider = GroqLLMProvider(
            api_key=settings.groq_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
        )
        return LLMService(
            provider=provider,
        )

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")


def get_reranking_service() -> RerankingService:
    return RerankingService()


def get_guardrail_service() -> GuardrailService:
    return GuardrailService()


def get_retrieval_agent(
    retrieval_service: RetrievalService,
    guardrail_service: GuardrailService,
) -> RetrievalAgent:
    return RetrievalAgent(
        search_tool=RetrievalSearchTool(retrieval_service),
        rewrite_tool=KeywordQueryRewriteTool(),
        guardrail_service=guardrail_service,
        minimum_confidence=settings.agentic_retrieval_min_confidence,
        max_retries=settings.agentic_retrieval_max_retries,
    )


def get_rag_service(
    db: Annotated[Session, Depends(get_db)],
) -> RagService:
    retrieval_service = get_retrieval_service(db=db)
    context_builder_service = ContextBuilderService()
    llm_service = get_llm_service()
    reranking_service = get_reranking_service()
    guardrail_service = get_guardrail_service()
    retrieval_agent = get_retrieval_agent(
        retrieval_service=retrieval_service,
        guardrail_service=guardrail_service,
    )

    return RagService(
        retrieval_service=retrieval_service,
        context_builder_service=context_builder_service,
        llm_service=llm_service,
        reranking_service=reranking_service,
        reranker_enabled=settings.reranker_enabled,
        reranker_candidate_k=settings.reranker_candidate_k,
        guardrail_service=guardrail_service,
        retrieval_min_confidence=settings.retrieval_min_confidence,
        citation_validation_enabled=settings.citation_validation_enabled,
        retrieval_agent=retrieval_agent,
        agentic_retrieval_enabled=settings.agentic_retrieval_enabled,
    )
