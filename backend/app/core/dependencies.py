import uuid
import jwt
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.chat_repository import ChatRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.repositories.chunk_repository import ChunkRepository
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.services.file_storage_service import FileStorageService
from app.services.chunk_persistence_service import ChunkPersistenceService
from app.services.chunk_service import ChunkingService
from app.services.document_processing_service import DocumentProcessingService
from app.services.extraction.pdf_extraction_service import PdfExtractionService
from app.services.embedding_service import EmbeddingService
from app.services.providers.nvidia_embedding_provider import NvidiaEmbeddingProvider
from app.services.retrieval_service import RetrievalService
from app.services.llm_service import LLMService
from app.services.providers.groq_llm_provider import GroqLLMProvider
from app.services.context_builder_service import ContextBuilderService
from app.services.rag_service import RagService
from app.models.user import User
from app.core.config import settings
from app.core.security import decode_access_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


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
    return AuthService(user_repository=user_repository)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    try:
        subject = decode_access_token(token)
        user_id = uuid.UUID(subject)
    except (ValueError, jwt.PyJWTError) as error:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    user_repository = UserRepository(db=db)
    user = user_repository.get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

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


def get_document_processing_service(
    db: Annotated[Session, Depends(get_db)],
) -> DocumentProcessingService:
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
    )


def get_embedding_service() -> EmbeddingService:
    if settings.embedding_provider == "nvidia":
        if not settings.nvidia_api_key:
            raise ValueError(
                "NVIDIA_API_KEY is required for NVIDIA embeddings"
            )

        provider = NvidiaEmbeddingProvider(
            api_key=settings.nvidia_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )

        return EmbeddingService(
            provider=provider,
            embedding_provider=settings.embedding_provider,
            embedding_model=settings.embedding_model,
            embedding_dimensions=settings.embedding_dimensions,
        )

    raise ValueError(
        f"Unsupported embedding provider: {settings.embedding_provider}"
    )


def get_retrieval_service(
    db: Annotated[Session, Depends(get_db)],
) -> RetrievalService:
    chunk_repository = ChunkRepository(db=db)
    embedding_service = get_embedding_service()

    return RetrievalService(
        embedding_service=embedding_service,
        chunk_repository=chunk_repository,
    )


def get_llm_service() -> LLMService:
    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is required for Groq LLMs"
            )
        provider = GroqLLMProvider(
            api_key=settings.groq_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
        )
        return LLMService(
            provider=provider,
        )

    raise ValueError(
        f"Unsupported LLM provider: {settings.llm_provider}"
    )


def get_rag_service(
    db: Annotated[Session, Depends(get_db)],
) -> RagService:
    retrieval_service = get_retrieval_service(db=db)
    context_builder_service = ContextBuilderService()
    llm_service = get_llm_service()

    return RagService(
        retrieval_service=retrieval_service,
        context_builder_service=context_builder_service,
        llm_service=llm_service,
    )
