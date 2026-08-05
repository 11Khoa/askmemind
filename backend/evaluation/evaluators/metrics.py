def find_best_rank(
    expected_pages: list[int],
    actual_pages: list[int | None],
) -> int | None:
    for index, page in enumerate(actual_pages, start=1):
        if page in expected_pages:
            return index

    return None


def calculate_mrr(best_rank: int | None) -> float:
    if best_rank is None:
        return 0.0

    return 1 / best_rank
