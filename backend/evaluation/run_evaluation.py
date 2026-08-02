import json
import uuid
from pathlib import Path
from typing import Any

from app.core.dependencies import get_retrieval_service
from app.database import SessionLocal
from app.repositories.document_repository import DocumentRepository
from evaluation.evaluators.retrieval_evaluator import (
    RetrievalEvaluator,
    RetrievalEvaluationResult,
)

DATASET_PATH = Path("evaluation/datasets/rag_eval.json")
REPORT_PATH = Path("evaluation/reports/baseline.json")
BENCHMARK_PATH = Path("evaluation/reports/benchmark.md")
TOP_K = 5


def main() -> None:
    dataset = load_dataset(path=DATASET_PATH)

    db = SessionLocal()

    try:
        document_repository = DocumentRepository(db=db)
        retrieval_service = get_retrieval_service(db=db)
        evaluation = RetrievalEvaluator()

        results: list[RetrievalEvaluationResult] = []
        for test_case in dataset:
            user_id = uuid.UUID(test_case["user_id"])

            document = document_repository.get_user_document_by_original_filename(
                user_id=user_id,
                original_filename=test_case["document_name"],
            )

            if document is None:
                print(
                    f"[MISSING DOCUMENT] "
                    f"user_id={user_id} "
                    f"document={test_case['document_name']}"
                )
                continue

            retrieval_chunks = retrieval_service.retrieve_relevant_chunks(
                query=test_case["question"],
                user_id=user_id,
                document_id=document.id,
                top_k=TOP_K,
            )

            result = evaluation.evaluate(
                test_id=test_case["id"],
                question_language=test_case["question_language"],
                expected_pages=test_case["expected_pages"],
                retrieved_chunks=retrieval_chunks,
            )

            results.append(result)
            print_result(result=result)

        print_summary(results=results)
        write_json_report(
            path=REPORT_PATH,
            dataset_path=DATASET_PATH,
            top_k=TOP_K,
            results=results,
        )
        write_markdown_report(
            path=BENCHMARK_PATH,
            dataset_path=DATASET_PATH,
            top_k=TOP_K,
            results=results,
        )
    finally:
        db.close()


def load_dataset(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def print_result(result: RetrievalEvaluationResult) -> None:
    status = "PASS" if result.hit else "FAIL"

    print(
        f"[{status}] {result.test_id} "
        f"expected={result.expected_pages} "
        f"retrieved={result.retrieved_pages} "
        f"best_rank={result.best_rank} "
        f"mrr={result.mrr:.2f}"
    )


def print_summary(results: list[RetrievalEvaluationResult]) -> None:
    if not results:
        print("No evaluation results.")
        return

    hit_count = sum(1 for result in results if result.hit)
    hit_rate = hit_count / len(results)
    mean_mrr = sum(result.mrr for result in results) / len(results)

    print()
    print("Retrieval Summary")
    print(f"Total: {len(results)}")
    print(f"Hit rate: {hit_rate:.2%}")
    print(f"MRR: {mean_mrr:.2f}")


def write_json_report(
    path: Path,
    dataset_path: Path,
    top_k: int,
    results: list[RetrievalEvaluationResult],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    total = len(results)
    hit_count = sum(1 for result in results if result.hit)
    hit_rate = 0.0 if total == 0 else hit_count / total
    mean_mrr = 0.0 if total == 0 else sum(
        result.mrr for result in results) / total

    report = {
        "dataset": str(dataset_path),
        "top_k": top_k,
        "total": total,
        "hit_count": hit_count,
        "hit_rate": hit_rate,
        "mrr": mean_mrr,
        "results": [
            {
                "test_id": result.test_id,
                "question_language": result.question_language,
                "hit": result.hit,
                "expected_pages": result.expected_pages,
                "retrieved_pages": result.retrieved_pages,
                "matched_pages": result.matched_pages,
                "best_rank": result.best_rank,
                "mrr": result.mrr,
            }
            for result in results
        ],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print(f"Wrote JSON report to {path}")


def write_markdown_report(
    path: Path,
    dataset_path: Path,
    top_k: int,
    results: list[RetrievalEvaluationResult],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    total = len(results)
    hit_count = sum(1 for result in results if result.hit)
    hit_rate = 0.0 if total == 0 else hit_count / total
    mean_mrr = 0.0 if total == 0 else sum(
        result.mrr for result in results) / total

    lines = [
        "# RAG Retrieval Benchmark",
        "",
        f"- Dataset: `{dataset_path}`",
        f"- Top K: `{top_k}`",
        f"- Total: `{total}`",
        f"- Hit Rate: `{hit_rate:.2%}`",
        f"- MRR: `{mean_mrr:.2f}`",
        "",
    ]

    lines.extend(
        build_language_summary_lines(results=results)
    )

    lines.extend(
        [
            "## Results",
            "",
            "| Test ID | Language | Status | Expected Pages | Retrieved Pages | Matched Pages | Best Rank | MRR |",
            "|---|---|---|---|---|---|---:|---:|",
        ]
    )

    for result in results:
        status = "PASS" if result.hit else "FAIL"

        lines.append(
            "| "
            f"{result.test_id} | "
            f"{result.question_language} | "
            f"{status} | "
            f"{format_pages(result.expected_pages)} | "
            f"{format_pages(result.retrieved_pages)} | "
            f"{format_pages(result.matched_pages)} | "
            f"{format_optional_rank(result.best_rank)} | "
            f"{result.mrr:.2f} |"
        )

    lines.append("")

    with path.open("w", encoding="utf-8") as file:
        file.write("\n".join(lines))

    print(f"Wrote Markdown report to {path}")


def format_pages(pages: list[int | None]) -> str:
    if not pages:
        return "-"

    return "[" + ", ".join(str(page) for page in pages) + "]"


def format_optional_rank(rank: int | None) -> str:
    if rank is None:
        return "-"

    return str(rank)


def build_language_summary_lines(
    results: list[RetrievalEvaluationResult],
) -> list[str]:
    grouped_results: dict[str, list[RetrievalEvaluationResult]] = {}

    for result in results:
        grouped_results.setdefault(result.question_language, []).append(result)

    lines = [
        "## By Question Language",
        "",
        "| Language | Total | Hit Rate | MRR |",
        "|---|---:|---:|---:|",
    ]

    for language, language_results in sorted(grouped_results.items()):
        total = len(language_results)
        hit_count = sum(1 for result in language_results if result.hit)
        hit_rate = 0.0 if total == 0 else hit_count / total
        mean_mrr = (
            0.0
            if total == 0
            else sum(result.mrr for result in language_results) / total
        )

        lines.append(
            f"| {language} | {total} | {hit_rate:.2%} | {mean_mrr:.2f} |"
        )

    lines.append("")

    return lines


if __name__ == "__main__":
    main()
