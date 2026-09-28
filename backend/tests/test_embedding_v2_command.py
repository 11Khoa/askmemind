from types import SimpleNamespace

import pytest

from app.commands import embedding_v2


class FakeSession:
    def __init__(
        self,
        chunks: list[SimpleNamespace] | None = None,
        scalar_results: list[int] | None = None,
    ) -> None:
        self.chunks = chunks or []
        self.scalar_results = iter(scalar_results or [])
        self.committed = False

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def scalars(self, statement: object) -> list[SimpleNamespace]:
        return self.chunks

    def scalar(self, statement: object) -> int:
        return next(self.scalar_results)

    def commit(self) -> None:
        self.committed = True


class FakeEmbeddingService:
    embedding_provider = "nvidia"
    embedding_model = "nvidia/nemotron-3-embed-1b"
    embedding_dimensions = 2048

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.embedding_dimensions for _text in texts]


def test_backfill_writes_v2_embeddings_and_metadata(monkeypatch) -> None:
    chunks = [
        SimpleNamespace(content="first"),
        SimpleNamespace(content="second"),
    ]
    session = FakeSession(chunks=chunks)
    monkeypatch.setattr(embedding_v2, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        embedding_v2,
        "get_embedding_service",
        lambda: FakeEmbeddingService(),
    )

    exit_code = embedding_v2.backfill(batch_size=2, limit=2)

    assert exit_code == 0
    assert session.committed is True
    assert all(len(chunk.embedding_v2) == 2048 for chunk in chunks)
    assert all(chunk.embedding_v2_provider == "nvidia" for chunk in chunks)
    assert all(
        chunk.embedding_v2_model == "nvidia/nemotron-3-embed-1b"
        for chunk in chunks
    )
    assert all(chunk.embedding_v2_dimensions == 2048 for chunk in chunks)


def test_backfill_rejects_unexpected_vector_dimensions(monkeypatch) -> None:
    chunk = SimpleNamespace(content="first")
    session = FakeSession(chunks=[chunk])
    embedding_service = FakeEmbeddingService()
    embedding_service.embed_passages = lambda texts: [[0.0] * 1024]

    monkeypatch.setattr(embedding_v2, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        embedding_v2,
        "get_embedding_service",
        lambda: embedding_service,
    )

    with pytest.raises(RuntimeError, match="unexpected vector dimension"):
        embedding_v2.backfill(batch_size=1, limit=1)

    assert session.committed is False


@pytest.mark.parametrize(
    ("scalar_results", "expected_exit_code"),
    [
        ([10, 0, 0], 0),
        ([10, 2, 0], 1),
        ([10, 0, 1], 1),
    ],
)
def test_verify_requires_complete_valid_coverage(
    monkeypatch,
    scalar_results: list[int],
    expected_exit_code: int,
) -> None:
    session = FakeSession(scalar_results=scalar_results)
    monkeypatch.setattr(embedding_v2, "SessionLocal", lambda: session)

    assert embedding_v2.verify() == expected_exit_code
