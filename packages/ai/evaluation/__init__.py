"""Evaluation — métricas puras, sem chamada real a modelos."""
from __future__ import annotations

from .metrics import coverage_ratio, exact_match

__all__ = ["coverage_ratio", "exact_match"]
