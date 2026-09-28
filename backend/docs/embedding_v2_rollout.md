# Embedding v2 rollout

This runbook migrates `chunks.embedding` from the retired 1024-dimensional
model to `nvidia/nemotron-3-embed-1b` at 2048 dimensions without deleting
legacy vectors during rollout.

## Preconditions

- Back up PostgreSQL and confirm the restore procedure.
- Keep `EMBEDDING_V2_ENABLED=False`.
- Deploy the application and migration from the same release.
- Run only one backfill worker unless row-claiming is added later.

## 1. Expand the schema

Apply the additive migration:

```bash
docker compose run --rm backend alembic upgrade d7e9f1a2b3c4
```

The migration adds nullable `embedding_v2*` columns. It does not alter or
clear the legacy `embedding*` columns, so the schema remains backward
compatible.

Deploy the new application with:

```dotenv
EMBEDDING_MODEL=nvidia/nemotron-3-embed-1b
EMBEDDING_DIMENSIONS=2048
EMBEDDING_V2_ENABLED=False
```

While the flag is false, retrieval uses PostgreSQL full-text search. New
document processing writes 2048-dimensional vectors to the v2 columns.

## 2. Backfill existing chunks

Start with a small canary:

```bash
docker compose run --rm backend \
  python -m app.commands.embedding_v2 backfill --batch-size 8 --limit 32
```

Continue without a limit after checking logs and NVIDIA usage:

```bash
docker compose run --rm backend \
  python -m app.commands.embedding_v2 backfill --batch-size 32
```

The command selects only rows where `embedding_v2 IS NULL` and commits each
batch. It is safe to stop and resume. A failed provider response does not
commit the current batch.

## 3. Verify coverage

```bash
docker compose run --rm backend python -m app.commands.embedding_v2 verify
```

Exit code 0 means every chunk has a v2 vector and its dimensions, provider,
and model match the active configuration. Any missing or invalid row returns
exit code 1. Do not enable v2 retrieval until this command succeeds.

Run retrieval evaluation and compare it with the saved baseline before
switching traffic.

## 4. Switch and monitor

Set the flag and redeploy:

```dotenv
EMBEDDING_V2_ENABLED=True
```

With `HYBRID_SEARCH_ENABLED=False`, retrieval uses vector v2. With both
flags enabled, retrieval uses hybrid vector v2 plus full-text search.

Monitor API errors, empty retrieval results, answer quality, latency, and
NVIDIA rate limits. To roll back retrieval immediately, set
`EMBEDDING_V2_ENABLED=False` and redeploy. No database downgrade is required.

## 5. Contract in a later release

Keep the legacy columns for an agreed stabilization window. After production
verification and backup retention are complete:

1. Remove legacy-column compatibility from application code.
2. Generate a new Alembic revision specifically for the contract release.
3. Drop `embedding`, `embedding_provider`, `embedding_model`, and
   `embedding_dimensions`.
4. Rename the `embedding_v2*` columns to the canonical `embedding*` names.
5. Deploy the matching application code and rerun tests and evaluation.

The contract migration is intentionally absent from the current Alembic
chain. Adding it now would make a normal `alembic upgrade head` delete the
rollback path before the new model has been proven in production.
