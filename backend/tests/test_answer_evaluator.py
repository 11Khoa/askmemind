from evaluation.evaluators.answer_evaluator import AnswerEvaluator


def test_answer_evaluator_passes_when_answer_has_keywords_and_citations() -> None:
    evaluator = AnswerEvaluator()

    result = evaluator.evaluate(
        test_id="case_001",
        question_language="en",
        answer="A Don maintained by Chainlink nodes and provides computation.",
        expected_keywords=["DON", "Chainlink nodes", "computation"],
        citation_count=2,
    )

    assert result.passed is True
    assert result.keyword_recall == 1.0
    assert result.has_answer is True
    assert result.has_citations is True
    assert result.missing_keywords == []


def test_answer_evaluator_fails_without_citations() -> None:
    evaluator = AnswerEvaluator()

    result = evaluator.evaluate(
        test_id="case_001",
        question_language="en",
        answer="A Don maintained by Chainlink nodes and provides computation.",
        expected_keywords=["DON", "Chainlink nodes", "computation"],
        citation_count=0,
    )

    assert result.passed is False
    assert result.has_citations is False
    assert result.matched_keywords == [
      "DON",
      "Chainlink nodes",
      "computation",
  ]


def test_answer_evaluator_fails_when_keyword_recall_is_too_low() -> None:
    evaluator = AnswerEvaluator()

    expected_keywords = [
      "oracle networks",
      "blockchains",
      "off-chain computation",
      "hybrid smart contracts",
    ]

    result = evaluator.evaluate(
        test_id="case_001",
        question_language="en",
        answer="This discusses DONs.",
        expected_keywords=expected_keywords,
        citation_count=1,
    )

    assert result.passed is False
    assert result.keyword_recall < 0.5
    assert result.missing_keywords == expected_keywords
