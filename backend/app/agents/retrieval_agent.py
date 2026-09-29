import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.core.logging import log_event
from app.services.guardrail_service import GuardrailService
from app.services.retrieval_service import RetrievedChunk, RetrievalService

logger = logging.getLogger(__name__)


class SearchDocumentsTool(Protocol):
    def search(
        self,
        query: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None,
        top_k: int,
    ) -> list[RetrievedChunk]: ...


class RewriteQueryTool(Protocol):
    def rewrite(self, query: str) -> str: ...


class RetrievalSearchTool:
    """Expose document retrieval behind a small agent tool boundary."""

    def __init__(self, retrieval_service: RetrievalService) -> None:
        self.retrieval_service = retrieval_service

    def search(
        self,
        query: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None,
        top_k: int,
    ) -> list[RetrievedChunk]:
        return self.retrieval_service.retrieve_relevant_chunks(
            query=query,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )


class KeywordQueryRewriteTool:
    """Create a deterministic keyword query without another external API call."""

    @staticmethod
    def _strip_diacritics(value: str) -> str:
        normalized = unicodedata.normalize("NFD", value.replace("đ", "d"))
        return "".join(
            char for char in normalized if not unicodedata.combining(char)
        )

    _STOP_WORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "are",
            "can",
            "could",
            "do",
            "does",
            "for",
            "from",
            "how",
            "in",
            "is",
            "it",
            "my",
            "of",
            "on",
            "please",
            "the",
            "to",
            "what",
            "when",
            "where",
            "which",
            "who",
            "why",
            "with",
            "cac",
            "cho",
            "co",
            "cua",
            "de",
            "do",
            "dung",
            "duoc",
            "gi",
            "khac",
            "khi",
            "khong",
            "la",
            "lam",
            "ma",
            "mot",
            "nao",
            "nay",
            "neu",
            "nhung",
            "nhu",
            "the",
            "thi",
            "trong",
            "tu",
            "va",
            "voi",
        }
    )

    def rewrite(self, query: str) -> str:
        tokens = re.findall(r"[^\W_]+", query.casefold())
        keywords = list(
            dict.fromkeys(
                token
                for token in tokens
                # Diacritic stripping is used only for stop-word lookup. It can
                # collide with meaningful Vietnamese nouns, so keep the emitted
                # token unchanged for accented full-text matching.
                if len(token) > 1
                and self._strip_diacritics(token) not in self._STOP_WORDS
            )
        )
        rewritten = " ".join(keywords)
        normalized_query = " ".join(query.casefold().split())
        if rewritten and rewritten != normalized_query:
            return rewritten
        return query.strip()


@dataclass
class RetrievalAgentState:
    question: str
    rewritten_query: str | None = None
    documents: list[RetrievedChunk] = field(default_factory=list)
    retrieval_score: float = 0.0
    retry_count: int = 0
    decisions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRetrievalResult:
    chunks: list[RetrievedChunk]
    state: RetrievalAgentState


class RetrievalAgent:
    def __init__(
        self,
        search_tool: SearchDocumentsTool,
        rewrite_tool: RewriteQueryTool,
        guardrail_service: GuardrailService,
        minimum_confidence: float,
        max_retries: int = 1,
    ) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")

        self.search_tool = search_tool
        self.rewrite_tool = rewrite_tool
        self.guardrail_service = guardrail_service
        self.minimum_confidence = minimum_confidence
        self.max_retries = max_retries

    def retrieve(
        self,
        question: str,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None,
        top_k: int,
    ) -> AgentRetrievalResult:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        state = RetrievalAgentState(question=question)
        active_query = question

        while True:
            chunks = self.search_tool.search(
                query=active_query,
                user_id=user_id,
                document_id=document_id,
                top_k=top_k,
            )
            confidence = self._best_confidence(chunks)
            if confidence >= state.retrieval_score:
                state.documents = chunks
                state.retrieval_score = confidence

            relevant = self.guardrail_service.has_sufficient_evidence(
                retrieved_chunks=chunks,
                minimum_confidence=self.minimum_confidence,
            )
            decision = "accept" if relevant else "rewrite"
            state.decisions.append(decision)
            log_event(
                logger,
                logging.INFO,
                "agent.retrieval.decision",
                decision=decision,
                attempt=state.retry_count + 1,
                rewritten=state.rewritten_query is not None,
                confidence=round(confidence, 4),
                retrieved_chunks=len(chunks),
            )

            if relevant:
                return AgentRetrievalResult(chunks=state.documents, state=state)

            if state.retry_count >= self.max_retries:
                state.decisions.append("max_retries_reached")
                return AgentRetrievalResult(chunks=state.documents, state=state)

            rewritten_query = self.rewrite_tool.rewrite(active_query)
            if self._normalize(rewritten_query) == self._normalize(active_query):
                state.decisions.append("query_unchanged")
                log_event(
                    logger,
                    logging.INFO,
                    "agent.retrieval.stopped",
                    reason="query_unchanged",
                    retry_count=state.retry_count,
                )
                return AgentRetrievalResult(chunks=state.documents, state=state)

            state.rewritten_query = rewritten_query
            state.retry_count += 1
            active_query = rewritten_query

    def _best_confidence(self, chunks: list[RetrievedChunk]) -> float:
        return max(
            (
                self.guardrail_service.calculate_confidence(chunk)
                for chunk in chunks
            ),
            default=0.0,
        )

    @staticmethod
    def _normalize(query: str) -> str:
        return " ".join(query.casefold().split())
