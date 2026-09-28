import argparse
from collections.abc import Sequence

from sqlalchemy import func, or_, select

from app.core.config import settings
from app.core.dependencies import get_embedding_service
from app.database import SessionLocal
from app.models.chunk import Chunk


def backfill(batch_size: int, limit: int | None) -> int:
    embedding_service = get_embedding_service()
    processed = 0

    while limit is None or processed < limit:
        current_batch_size = (
            min(batch_size, limit - processed)
            if limit is not None
            else batch_size
        )

        with SessionLocal() as db:
            chunks = list(
                db.scalars(
                    select(Chunk)
                    .where(Chunk.embedding_v2.is_(None))
                    .order_by(Chunk.id)
                    .limit(current_batch_size)
                )
            )
            if not chunks:
                break

            embeddings = embedding_service.embed_passages(
                texts=[chunk.content for chunk in chunks],
            )
            if len(embeddings) != len(chunks):
                raise RuntimeError(
                    "Embedding provider returned an unexpected batch size"
                )

            if any(
                len(embedding) != embedding_service.embedding_dimensions
                for embedding in embeddings
            ):
                raise RuntimeError(
                    "Embedding provider returned an unexpected vector dimension"
                )

            for chunk, embedding in zip(chunks, embeddings, strict=True):
                chunk.embedding_v2 = embedding
                chunk.embedding_v2_provider = (
                    embedding_service.embedding_provider
                )
                chunk.embedding_v2_model = embedding_service.embedding_model
                chunk.embedding_v2_dimensions = (
                    embedding_service.embedding_dimensions
                )

            db.commit()
            processed += len(chunks)
            print(f"Backfilled {processed} chunks", flush=True)

    print(f"Backfill stopped after {processed} chunks")
    return 0


def verify() -> int:
    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(Chunk)) or 0
        missing = (
            db.scalar(
                select(func.count())
                .select_from(Chunk)
                .where(Chunk.embedding_v2.is_(None))
            )
            or 0
        )
        invalid = (
            db.scalar(
                select(func.count())
                .select_from(Chunk)
                .where(
                    Chunk.embedding_v2.is_not(None),
                    or_(
                        func.vector_dims(Chunk.embedding_v2)
                        != settings.embedding_dimensions,
                        Chunk.embedding_v2_dimensions.is_(None),
                        Chunk.embedding_v2_dimensions
                        != settings.embedding_dimensions,
                        Chunk.embedding_v2_provider.is_(None),
                        Chunk.embedding_v2_provider
                        != settings.embedding_provider,
                        Chunk.embedding_v2_model.is_(None),
                        Chunk.embedding_v2_model != settings.embedding_model,
                    ),
                )
            )
            or 0
        )

    complete = missing == 0 and invalid == 0
    coverage = 100.0 if total == 0 else ((total - missing) / total) * 100
    print(
        f"Embedding v2 coverage: {total - missing}/{total} "
        f"({coverage:.2f}%), invalid={invalid}"
    )
    return 0 if complete else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage embedding v2 rollout")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backfill_parser = subparsers.add_parser("backfill")
    backfill_parser.add_argument("--batch-size", type=int, default=32)
    backfill_parser.add_argument("--limit", type=int)

    subparsers.add_parser("verify")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "backfill":
        if args.batch_size < 1:
            raise ValueError("batch-size must be at least 1")
        if args.limit is not None and args.limit < 1:
            raise ValueError("limit must be at least 1")
        return backfill(batch_size=args.batch_size, limit=args.limit)

    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
