"""Replaceable source polling abstraction; scheduling and state live in PostgreSQL."""

from typing import Protocol
from app.services.source_collectors import (
    CollectionState,
    CollectionResult,
    GitHubRepoCollector,
)


class SourceMonitor(Protocol):
    def check(
        self, repo_url: str, *, state: CollectionState, deadline: float
    ) -> CollectionResult: ...


class GitHubContextMonitor:
    """Covers normalized repo metadata and README, not every commit or code file."""

    def __init__(self, collector: GitHubRepoCollector | None = None):
        self.collector = collector or GitHubRepoCollector()

    def check(
        self, repo_url: str, *, state: CollectionState, deadline: float
    ) -> CollectionResult:
        return self.collector.collect(repo_url, state=state, deadline=deadline)
