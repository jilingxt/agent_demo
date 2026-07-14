from __future__ import annotations

from pathlib import Path

import pytest

from tests.v058_case_helpers import (
    assert_expected_outcome,
    discover_v058_cases,
    replay_v058_case,
)


CASES = discover_v058_cases()


def test_v058_corpus_contains_exactly_ten_cases() -> None:
    assert len(CASES) == 10


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_v058_case_matches_golden_contract(case_dir: Path) -> None:
    result = replay_v058_case(case_dir)
    assert_expected_outcome(case_dir, result)
