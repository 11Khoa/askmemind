import csv
import json

import pytest

from evaluation.evaluators.retrieval_evaluator import RetrievalEvaluationResult
from evaluation.run_evaluation import (
    calculate_retrieval_summary,
    write_benchmark_csv,
    write_csv_report,
    write_json_report,
)


def make_result() -> RetrievalEvaluationResult:
    return RetrievalEvaluationResult(
        test_id="case_001",
        question_language="en",
        hit=True,
        expected_pages=[1, 2],
        retrieved_pages=[1, 3],
        matched_pages=[1],
        best_rank=1,
        mrr=1.0,
        recall_at_k=0.5,
        precision_at_k=0.5,
        latency_ms=12.5,
        retrieved_chunk_count=2,
    )


def test_calculate_retrieval_summary_averages_metrics() -> None:
    summary = calculate_retrieval_summary(results=[make_result()])

    assert summary.total == 1
    assert summary.hit_rate == 1.0
    assert summary.mean_mrr == 1.0
    assert summary.mean_recall_at_k == 0.5
    assert summary.mean_precision_at_k == 0.5
    assert summary.mean_latency_ms == 12.5
    assert summary.mean_chunk_count == 2.0


def test_report_writers_include_advanced_metrics(tmp_path) -> None:
    result = make_result()
    json_path = tmp_path / "method.json"
    csv_path = tmp_path / "method.csv"
    benchmark_path = tmp_path / "benchmark.csv"

    write_json_report(
        path=json_path,
        dataset_path=tmp_path / "dataset.json",
        top_k=5,
        results=[result],
        answer_results=[],
    )
    write_csv_report(
        path=csv_path,
        results=[result],
        answer_results=[],
    )
    write_benchmark_csv(
        path=benchmark_path,
        top_k=5,
        benchmark_results={"hybrid": [result]},
        benchmark_answer_results={"hybrid": []},
    )

    json_report = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_report["recall_at_k"] == 0.5
    assert json_report["precision_at_k"] == 0.5
    assert json_report["mean_latency_ms"] == 12.5
    assert json_report["answer_success_rate"] is None

    with csv_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["recall_at_k"] == "0.5"
    assert rows[0]["answer_passed"] == ""

    with benchmark_path.open(encoding="utf-8", newline="") as file:
        benchmark_rows = list(csv.DictReader(file))
    assert benchmark_rows[0]["method"] == "hybrid"
    assert float(benchmark_rows[0]["mean_latency_ms"]) == pytest.approx(12.5)
