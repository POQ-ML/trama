"""Métricas puras de avaliação — sem ML, sem chamada real a modelos."""
from __future__ import annotations


def exact_match(expected: str, actual: str) -> float:
    """1.0 se strings normalizadas são iguais, senão 0.0."""
    return 1.0 if expected.strip().lower() == actual.strip().lower() else 0.0


def coverage_ratio(expected_items: list[str], actual_items: list[str]) -> float:
    """Fração de `expected_items` presente em `actual_items` (0.0 vazio)."""
    if not expected_items:
        return 0.0
    expected = {e.strip().lower() for e in expected_items}
    actual = {a.strip().lower() for a in actual_items}
    return len(expected & actual) / len(expected)
