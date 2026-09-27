import argparse
import csv
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from app.core.dependencies import get_llm_service, get_retrieval_service
from app.database import SessionLocal
from app.repositories.document_repository import DocumentRepository
from app.services.context_builder_service import ContextBuilderService
from app.services.retrieval_service import RetrievalService, RetrievedChunk
from app.services.reranking_service import RerankingService
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
REPORTS_DIR = Path("evaluation/reports")
BENCHMARK_PATH = REPORTS_DIR / "benchmark.md"
BENCHMARK_CSV_PATH = REPORTS_DIR / "benchmark.csv"
TOP_K = 5
RUN_ANSWER_EVALUATION = False
RERANKER_CANDIDATE_K = 20
RETRIEVAL_METHODS = ("vector", "fts_search", "hybrid", "hybrid_reranked")


@dataclass(frozen=True)
class RetrievalSummary:
    total: int
    hit_count: int
    hit_rate: float
    mean_mrr: float
    mean_recall_at_k: float
    mean_precision_at_k: float
    mean_latency_ms: float
    mean_chunk_count: float


def retrieve_chunks_by_method(
    retrieval_service: RetrievalService,
    reranking_service: RerankingService,
    method: str,
    query: str,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    top_k: int,
) -> list[RetrievedChunk]:
    if method == "vector":
        return retrieval_service.vector_search(
            query=query,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )

    if method == "fts_search":
        return retrieval_service.fts_search(
            query=query,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )

    if method == "hybrid":
        return retrieval_service.hybrid_search(
            query=query,
            user_id=user_id,
            document_id=document_id,
            top_k=top_k,
        )

    if method == "hybrid_reranked":
        candidates = retrieval_service.hybrid_search(
            query=query,
            user_id=user_id,
            document_id=document_id,
            top_k=max(top_k, RERANKER_CANDIDATE_K),
        )
        return reranking_service.rerank(
            query=query,
            retrieved_chunks=candidates,
            top_k=top_k,
        )

    raise ValueError(f"Unsupported retrieval method: {method}")


def main(
    dataset_path: Path = DATASET_PATH,
    reports_dir: Path = REPORTS_DIR,
    top_k: int = TOP_K,
    methods: tuple[str, ...] = RETRIEVAL_METHODS,
    run_answer_evaluation: bool = RUN_ANSWER_EVALUATION,
) -> None:
    dataset = load_dataset(path=dataset_path)

    db = SessionLocal()
    try:
        document_repository = DocumentRepository(db=db)
        retrieval_service = get_retrieval_service(db=db)
        reranking_service = RerankingService()
        llm_service = get_llm_service() if run_answer_evaluation else None
        retrieval_evaluator = RetrievalEvaluator()
        context_builder_service = ContextBuilderService()
        citation_evaluator = CitationEvaluator()
        answer_evaluator = AnswerEvaluator() if run_answer_evaluation else None

        benchmark_results: dict[str, list[RetrievalEvaluationResult]] = {}
        benchmark_answer_results: dict[str, list[AnswerEvaluationResult]] = {}
        for method in methods:
            print()
            print(f"=== Benchmark: {method} ===")
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

                retrieval_started_at = perf_counter()
                retrieval_chunks = retrieve_chunks_by_method(
                    retrieval_service=retrieval_service,
                    reranking_service=reranking_service,
                    method=method,
                    query=test_case["question"],
                    user_id=user_id,
                    document_id=document.id,
                    top_k=top_k,
                )
                retrieval_latency_ms = (
                    perf_counter() - retrieval_started_at
                ) * 1000

                build_context = context_builder_service.build_context(
                    retrieved_chunks=retrieval_chunks,
                )

                result = retrieval_evaluator.evaluate(
                    test_id=test_case["id"],
                    question_language=test_case["question_language"],
                    expected_pages=test_case["expected_pages"],
                    retrieved_chunks=retrieval_chunks,
                    latency_ms=retrieval_latency_ms,
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

                if run_answer_evaluation:
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
            if run_answer_evaluation:
                print_answer_summary(results=answer_results)

            write_json_report(
                path=reports_dir / f"{method}.json",
                dataset_path=dataset_path,
                top_k=top_k,
                results=results,
                answer_results=answer_results,
            )
            write_csv_report(
                path=reports_dir / f"{method}.csv",
                results=results,
                answer_results=answer_results,
            )
            write_markdown_report(
                path=reports_dir / f"{method}.md",
                dataset_path=dataset_path,
                top_k=top_k,
                retrieval_results=results,
                citation_results=citation_results,
                citation_integrity_results=citation_integrity_results,
            )
            benchmark_results[method] = results
            benchmark_answer_results[method] = answer_results

        write_benchmark_comparison(
            path=reports_dir / BENCHMARK_PATH.name,
            top_k=top_k,
            benchmark_results=benchmark_results,
            benchmark_answer_results=benchmark_answer_results,
        )
        write_benchmark_csv(
            path=reports_dir / BENCHMARK_CSV_PATH.name,
            top_k=top_k,
            benchmark_results=benchmark_results,
            benchmark_answer_results=benchmark_answer_results,
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


def calculate_retrieval_summary(
    results: list[RetrievalEvaluationResult],
) -> RetrievalSummary:
    total = len(results)
    if total == 0:
        return RetrievalSummary(
            total=0,
            hit_count=0,
            hit_rate=0.0,
            mean_mrr=0.0,
            mean_recall_at_k=0.0,
            mean_precision_at_k=0.0,
            mean_latency_ms=0.0,
            mean_chunk_count=0.0,
        )

    hit_count = sum(1 for result in results if result.hit)
    return RetrievalSummary(
        total=total,
        hit_count=hit_count,
        hit_rate=hit_count / total,
        mean_mrr=sum(result.mrr for result in results) / total,
        mean_recall_at_k=(
            sum(result.recall_at_k for result in results) / total
        ),
        mean_precision_at_k=(
            sum(result.precision_at_k for result in results) / total
        ),
        mean_latency_ms=(
            sum(result.latency_ms for result in results) / total
        ),
        mean_chunk_count=(
            sum(result.retrieved_chunk_count for result in results) / total
        ),
    )

def print_summary(results: list[RetrievalEvaluationResult]) -> None:
    if not results:
        print("No evaluation results.")
        return

    summary = calculate_retrieval_summary(results=results)

    print()
    print("Retrieval Summary")
    print(f"Total: {summary.total}")
    print(f"Hit rate: {summary.hit_rate:.2%}")
    print(f"MRR: {summary.mean_mrr:.2f}")
    print(f"Recall@K: {summary.mean_recall_at_k:.2%}")
    print(f"Precision@K: {summary.mean_precision_at_k:.2%}")
    print(f"Mean latency: {summary.mean_latency_ms:.2f} ms")
    print(f"Mean retrieved chunks: {summary.mean_chunk_count:.2f}")


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
    answer_results: list[AnswerEvaluationResult],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    summary = calculate_retrieval_summary(results=results)
    answer_success_rate = (
        None if not answer_results
        else sum(result.passed for result in answer_results) / len(answer_results)
    )

    report = {
        "dataset": str(dataset_path),
        "top_k": top_k,
        "total": summary.total,
        "hit_count": summary.hit_count,
        "hit_rate": summary.hit_rate,
        "mrr": summary.mean_mrr,
        "recall_at_k": summary.mean_recall_at_k,
        "precision_at_k": summary.mean_precision_at_k,
        "mean_latency_ms": summary.mean_latency_ms,
        "mean_retrieved_chunk_count": summary.mean_chunk_count,
        "answer_success_rate": answer_success_rate,
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
                "recall_at_k": result.recall_at_k,
                "precision_at_k": result.precision_at_k,
                "latency_ms": result.latency_ms,
                "retrieved_chunk_count": result.retrieved_chunk_count,
            }
            for result in results
        ],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print(f"Wrote JSON report to {path}")



def write_csv_report(
    path: Path,
    results: list[RetrievalEvaluationResult],
    answer_results: list[AnswerEvaluationResult],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    answers_by_test_id = {
        result.test_id: result for result in answer_results
    }
    fieldnames = [
        "test_id",
        "question_language",
        "hit",
        "expected_pages",
        "retrieved_pages",
        "matched_pages",
        "best_rank",
        "mrr",
        "recall_at_k",
        "precision_at_k",
        "latency_ms",
        "retrieved_chunk_count",
        "answer_passed",
    ]

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            answer_result = answers_by_test_id.get(result.test_id)
            writer.writerow(
                {
                    "test_id": result.test_id,
                    "question_language": result.question_language,
                    "hit": result.hit,
                    "expected_pages": json.dumps(result.expected_pages),
                    "retrieved_pages": json.dumps(result.retrieved_pages),
                    "matched_pages": json.dumps(result.matched_pages),
                    "best_rank": result.best_rank,
                    "mrr": result.mrr,
                    "recall_at_k": result.recall_at_k,
                    "precision_at_k": result.precision_at_k,
                    "latency_ms": result.latency_ms,
                    "retrieved_chunk_count": result.retrieved_chunk_count,
                    "answer_passed": (
                        "" if answer_result is None else answer_result.passed
                    ),
                }
            )

    print(f"Wrote CSV report to {path}")
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

    retrieval_summary = calculate_retrieval_summary(results=retrieval_results)

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
        "| Metric | Total | Pass/Hit Rate | MRR | Recall@K | Precision@K | Mean Latency |",
        "|---|---:|---:|---:|---:|---:|---:|",
        "| Retrieval "
        f"| {retrieval_summary.total} | {retrieval_summary.hit_rate:.2%} "
        f"| {retrieval_summary.mean_mrr:.2f} | {retrieval_summary.mean_recall_at_k:.2%} "
        f"| {retrieval_summary.mean_precision_at_k:.2%} | {retrieval_summary.mean_latency_ms:.2f} ms |",
        f"| Citation Relevance | {citation_total} | {citation_hit_rate:.2%} | {citation_mrr:.2f} | - | - | - |",
        f"| Citation Integrity | {integrity_total} | {integrity_pass_rate:.2%} | - | - | - | - |",
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
            "| Test ID | Language | Status | Expected Pages | Retrieved Pages | Matched Pages | Best Rank | MRR | Recall@K | Precision@K | Latency | Chunks |",
            "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|",
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
            f"{result.mrr:.2f} | "
            f"{result.recall_at_k:.2%} | "
            f"{result.precision_at_k:.2%} | "
            f"{result.latency_ms:.2f} ms | "
            f"{result.retrieved_chunk_count} |"
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


def write_benchmark_comparison(
    path: Path,
    top_k: int,
    benchmark_results: dict[str, list[RetrievalEvaluationResult]],
    benchmark_answer_results: dict[str, list[AnswerEvaluationResult]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Benchmark Comparison",
        "",
        f"| Method | Total | Hit@{top_k} | MRR | Recall@{top_k} | Precision@{top_k} | Mean Latency | Mean Chunks | Answer Success |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, results in benchmark_results.items():
        summary = calculate_retrieval_summary(results=results)
        answer_results = benchmark_answer_results.get(method, [])
        answer_success = (
            "-"
            if not answer_results
            else f"{sum(result.passed for result in answer_results) / len(answer_results):.2%}"
        )
        lines.append(
            f"| {method} | {summary.total} | {summary.hit_rate:.2%} "
            f"| {summary.mean_mrr:.2f} | {summary.mean_recall_at_k:.2%} "
            f"| {summary.mean_precision_at_k:.2%} | {summary.mean_latency_ms:.2f} ms "
            f"| {summary.mean_chunk_count:.2f} | {answer_success} |"
        )

    lines.append("")
    with path.open("w", encoding="utf-8") as file:
        file.write("\n".join(lines))

    print(f"Wrote benchmark comparison to {path}")



def write_benchmark_csv(
    path: Path,
    top_k: int,
    benchmark_results: dict[str, list[RetrievalEvaluationResult]],
    benchmark_answer_results: dict[str, list[AnswerEvaluationResult]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "method",
        "top_k",
        "total",
        "hit_rate",
        "mrr",
        "recall_at_k",
        "precision_at_k",
        "mean_latency_ms",
        "mean_retrieved_chunk_count",
        "answer_success_rate",
    ]

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for method, results in benchmark_results.items():
            summary = calculate_retrieval_summary(results=results)
            answer_results = benchmark_answer_results.get(method, [])
            answer_success_rate = (
                ""
                if not answer_results
                else sum(result.passed for result in answer_results)
                / len(answer_results)
            )
            writer.writerow(
                {
                    "method": method,
                    "top_k": top_k,
                    "total": summary.total,
                    "hit_rate": summary.hit_rate,
                    "mrr": summary.mean_mrr,
                    "recall_at_k": summary.mean_recall_at_k,
                    "precision_at_k": summary.mean_precision_at_k,
                    "mean_latency_ms": summary.mean_latency_ms,
                    "mean_retrieved_chunk_count": summary.mean_chunk_count,
                    "answer_success_rate": answer_success_rate,
                }
            )

    print(f"Wrote benchmark CSV to {path}")
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
    grouped_results: dict[str, list[RetrievalEvaluationResult]
                          | list[CitationEvaluationResult]] = {}

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


def positive_int(value: str) -> int:
    parsed_value = int(value)
    if parsed_value < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed_value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate and compare AskMeMind retrieval methods.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DATASET_PATH,
        help="Path to the evaluation dataset.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=REPORTS_DIR,
        help="Directory for JSON, CSV, and Markdown reports.",
    )
    parser.add_argument(
        "--top-k",
        type=positive_int,
        default=TOP_K,
        help="Number of final chunks to evaluate.",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=RETRIEVAL_METHODS,
        default=list(RETRIEVAL_METHODS),
        help="Retrieval methods to compare.",
    )
    parser.add_argument(
        "--with-answers",
        action="store_true",
        help="Call the LLM and include answer success metrics.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    main(
        dataset_path=arguments.dataset,
        reports_dir=arguments.reports_dir,
        top_k=arguments.top_k,
        methods=tuple(arguments.methods),
        run_answer_evaluation=arguments.with_answers,
    )
