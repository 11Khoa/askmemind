import json
import uuid
from pathlib import Path
from typing import Any

from app.core.dependencies import get_llm_service, get_retrieval_service
from app.database import SessionLocal
from app.repositories.document_repository import DocumentRepository
from app.services.context_builder_service import ContextBuilderService
from evaluation.evaluators.retrieval_evaluator import (
    RetrievalEvaluator,
    RetrievalEvaluationResult,
)
from evaluation.evaluators.citation_evaluator import (
    CitationEvaluator,
    CitationEvaluationResult,
    CitationIntegrityEvaluationResult,
)
from evaluation.evaluators.answer_evaluator import (
    AnswerEvaluator,
    AnswerEvaluationResult,
)

DATASET_PATH = Path("evaluation/datasets/rag_eval.json")
REPORT_PATH = Path("evaluation/reports/baseline.json")
BENCHMARK_PATH = Path("evaluation/reports/benchmark.md")
TOP_K = 5
RUN_ANSWER_EVALUATION = False


def main() -> None:
    dataset = load_dataset(path=DATASET_PATH)

    db = SessionLocal()

    try:
        document_repository = DocumentRepository(db=db)
        retrieval_service = get_retrieval_service(db=db)
        llm_service = get_llm_service() if RUN_ANSWER_EVALUATION else None
        retrieval_evaluator = RetrievalEvaluator()
        context_builder_service = ContextBuilderService()
        citation_evaluator = CitationEvaluator()
        answer_evaluator = AnswerEvaluator() if RUN_ANSWER_EVALUATION else None

        results: list[RetrievalEvaluationResult] = []
        citation_results: list[CitationEvaluationResult] = []
        citation_integrity_results: list[CitationIntegrityEvaluationResult] = []
        answer_results: list[AnswerEvaluationResult] = []

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

            build_context = context_builder_service.build_context(
                retrieved_chunks=retrieval_chunks,
            )

            result = retrieval_evaluator.evaluate(
                test_id=test_case["id"],
                question_language=test_case["question_language"],
                expected_pages=test_case["expected_pages"],
                retrieved_chunks=retrieval_chunks,
            )

            citation_result = citation_evaluator.evaluate(
                test_id=test_case["id"],
                question_language=test_case["question_language"],
                expected_pages=test_case["expected_pages"],
                citations=build_context.citations,
            )

            citation_integrity_result = citation_evaluator.evaluate_integrity(
                test_id=test_case["id"],
                question_language=test_case["question_language"],
                retrieved_chunks=retrieval_chunks,
                citations=build_context.citations,
            )

            results.append(result)
            print_result(result=result)

            citation_results.append(citation_result)
            print_citation_result(result=citation_result)

            citation_integrity_results.append(citation_integrity_result)
            print_citation_integrity_result(result=citation_integrity_result)

            if RUN_ANSWER_EVALUATION:
                assert llm_service is not None
                assert answer_evaluator is not None
                
                answer = llm_service.generate_answer(
                    question=test_case["question"],
                    context=build_context.context,
                )

                answer_result = answer_evaluator.evaluate(
                    test_id=test_case["id"],
                    question_language=test_case["question_language"],
                    answer=answer,
                    expected_keywords=test_case["expected_answer_keywords"],
                    citation_count=len(build_context.citations),
                )
                answer_results.append(answer_result)
                if not answer_result.passed:
                    print(f"Answer: {answer}")
                print(
                    f"[ANSWER {'PASS' if answer_result.passed else 'FAIL'}] "
                    f"{answer_result.test_id} "
                    f"keyword_recall={answer_result.keyword_recall:.2f} "
                    f"has_citations={answer_result.has_citations} "
                    f"missing_keywords={answer_result.missing_keywords}"
                )

        print_summary(results=results)
        print_citation_summary(results=citation_results)
        print_citation_integrity_summary(results=citation_integrity_results)
        if RUN_ANSWER_EVALUATION:
            print_answer_summary(results=answer_results)

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
            retrieval_results=results,
            citation_results=citation_results,
            citation_integrity_results=citation_integrity_results,
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


def print_citation_result(result: CitationEvaluationResult) -> None:
    status = "PASS" if result.hit else "FAIL"

    print(
        f"[CITATION {status}] {result.test_id} "
        f"expected={result.expected_pages} "
        f"cited={result.cited_pages} "
        f"best_rank={result.best_rank} "
        f"mrr={result.mrr:.2f}"
    )


def print_citation_integrity_result(
    result: CitationIntegrityEvaluationResult,
) -> None:
    status = "PASS" if result.passed else "FAIL"

    print(
        f"[CITATION INTEGRITY {status}] {result.test_id} "
        f"retrieved_chunks={result.retrieved_chunk_count} "
        f"citations={result.citation_count} "
        f"errors={len(result.errors)}"
    )

    for error in result.errors:
        print(f" - {error}")


def calculate_summary(
    results: list[RetrievalEvaluationResult] | list[CitationEvaluationResult],
) -> tuple[int, int, float, float]:
    total = len(results)
    hit_count = sum(1 for result in results if result.hit)
    hit_rate = 0.0 if total == 0 else hit_count / total
    mean_mrr = 0.0 if total == 0 else sum(
        result.mrr for result in results) / total

    return total, hit_count, hit_rate, mean_mrr


def print_summary(results: list[RetrievalEvaluationResult]) -> None:
    if not results:
        print("No evaluation results.")
        return

    total, _, hit_rate, mean_mrr = calculate_summary(results=results)

    print()
    print("Retrieval Summary")
    print(f"Total: {total}")
    print(f"Hit rate: {hit_rate:.2%}")
    print(f"MRR: {mean_mrr:.2f}")


def print_citation_summary(results: list[CitationEvaluationResult]) -> None:
    total, _, hit_rate, mean_mrr = calculate_summary(results=results)

    print()
    print("Citation Summary")
    print(f"Total: {total}")
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


def print_citation_integrity_summary(
    results: list[CitationIntegrityEvaluationResult],
) -> None:
    if not results:
        print("No citation integrity results.")
        return

    total, _, pass_rate = calculate_integrity_summary(results=results)

    print()
    print("Citation Integrity Summary")
    print(f"Total: {total}")
    print(f"Pass rate: {pass_rate:.2%}")


def print_answer_summary(results: list[AnswerEvaluationResult]) -> None:
    if not results:
        print("No answer evaluation results.")
        return

    total = len(results)
    pass_count = sum(1 for result in results if result.passed)
    pass_rate = pass_count / total
    mean_keyword_recall = (
        sum(result.keyword_recall for result in results) / total
    )
    print()
    print("Answer Summary")
    print(f"Total: {total}")
    print(f"Pass rate: {pass_rate:.2%}")
    print(f"Keyword recall: {mean_keyword_recall:.2f}")


def write_markdown_report(
    path: Path,
    dataset_path: Path,
    top_k: int,
    retrieval_results: list[RetrievalEvaluationResult],
    citation_results: list[CitationEvaluationResult],
    citation_integrity_results: list[CitationIntegrityEvaluationResult],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    retrieval_total, _, retrieval_hit_rate, retrieval_mrr = (
        calculate_summary(results=retrieval_results)
    )

    citation_total, _, citation_hit_rate, citation_mrr = (
        calculate_summary(results=citation_results)
    )

    integrity_total, _, integrity_pass_rate = (
        calculate_integrity_summary(results=citation_integrity_results)
    )

    lines = [
        "# RAG Benchmark",
        "",
        f"- Dataset: `{dataset_path}`",
        f"- Top K: `{top_k}`",
        "",
        "## Summary",
        "",
        "| Metric | Total | Pass/Hit Rate | MRR |",
        "|---|---:|---:|---:|",
        f"| Retrieval | {retrieval_total} | {retrieval_hit_rate:.2%} | {retrieval_mrr:.2f} |",
        f"| Citation Relevance | {citation_total} | {citation_hit_rate:.2%} | {citation_mrr:.2f} |",
        f"| Citation Integrity | {integrity_total} | {integrity_pass_rate:.2%} | - |",
        "",
    ]

    lines.extend(
        build_language_summary_lines(
            title="Retrieval By Question Language",
            results=retrieval_results,
        )
    )

    lines.extend(
        build_language_summary_lines(
            title="Citation By Question Language",
            results=citation_results,
        )
    )

    lines.extend(
        [
            "## Retrieval Results",
            "",
            "| Test ID | Language | Status | Expected Pages | Retrieved Pages | Matched Pages | Best Rank | MRR |",
            "|---|---|---|---|---|---|---:|---:|",
        ]
    )

    for result in retrieval_results:
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

    lines.extend(
        [
            "## Citation Results",
            "",
            "| Test ID | Language | Status | Expected Pages | Cited Pages | Matched Pages | Best Rank | MRR |",
            "|---|---|---|---|---|---|---:|---:|",
        ]
    )
    for result in citation_results:
        status = "PASS" if result.hit else "FAIL"
        lines.append(
            "| "
            f"{result.test_id} | "
            f"{result.question_language} | "
            f"{status} | "
            f"{format_pages(result.expected_pages)} | "
            f"{format_pages(result.cited_pages)} | "
            f"{format_pages(result.matched_pages)} | "
            f"{format_optional_rank(result.best_rank)} | "
            f"{result.mrr:.2f} |"
        )

    lines.append("")

    lines.extend(
        [
            "## Citation Integrity Results",
            "",
            "| Test ID | Language | Status | Retrieved Chunks | Citations | Errors |",
            "|---|---|---|---:|---:|---|",
        ]
    )

    for result in citation_integrity_results:
        status = "PASS" if result.passed else "FAIL"
        errors = format_errors(result.errors)

        lines.append(
            "| "
            f"{result.test_id} | "
            f"{result.question_language} | "
            f"{status} | "
            f"{result.retrieved_chunk_count} | "
            f"{result.citation_count} | "
            f"{errors} |"
        )

    lines.append("")

    with path.open("w", encoding="utf-8") as file:
        file.write("\n".join(lines))

    print(f"Wrote Markdown report to {path}")


def calculate_integrity_summary(
    results: list[CitationIntegrityEvaluationResult],
) -> tuple[int, int, float]:
    total = len(results)
    pass_count = sum(1 for result in results if result.passed)
    pass_rate = 0.0 if total == 0 else pass_count / total

    return total, pass_count, pass_rate


def format_pages(pages: list[int | None]) -> str:
    if not pages:
        return "-"

    return "[" + ", ".join(str(page) for page in pages) + "]"


def format_optional_rank(rank: int | None) -> str:
    if rank is None:
        return "-"

    return str(rank)


def format_errors(errors: list[str]) -> str:
    if not errors:
        return "-"

    return "<br>".join(errors)


def build_language_summary_lines(
    title: str,
    results: list[RetrievalEvaluationResult] | list[CitationEvaluationResult],
) -> list[str]:
    grouped_results: dict[str, list[RetrievalEvaluationResult] | list[CitationEvaluationResult]] = {}

    for result in results:
        grouped_results.setdefault(result.question_language, []).append(result)

    lines = [
        f"## {title}",
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
