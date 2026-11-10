"""Durable worker integration. ASGI handlers never perform collection/generation.

Factories are injectable. No DB session survives any await/external call. The
worker process uses one bounded job/check at a time; PostgreSQL fences multiple
worker processes using leases, locks and unique active-monitor jobs.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import time

from sqlalchemy import select, text

from app.models import DiscoveryRun, SourceMonitor, AcademicItem, Source
from app.repositories import runtime as db
from app.repositories.discovery import (
    snapshot_from_item,
    upsert_item_entity,
    save_suggestions,
    update_run,
)
from app.schemas.discovery import (
    SuggestionInput,
    EvidenceInput,
    RunUpdate,
    DiscoveryCreate,
)
from app.services.source_monitor import GitHubContextMonitor
from app.services.source_collectors import SourceFailure

_SAFE_WARNINGS = {
    "insufficient_context",
    "context_window_limited",
    "candidate_budget_reached",
    "invalid_candidate",
    "source_unavailable",
    "search_timeout",
    "explanation_unavailable",
    "explanation_invalid",
    "explanation_timeout",
    "explanation_budget_reached",
}


class Runtime:
    def __init__(
        self,
        session_factory,
        *,
        search_factory=None,
        explainer_factory=None,
        source_monitor=None,
        settings=None,
    ):
        from app.core.config import settings as defaults

        self.settings = settings or defaults
        self.sessions = session_factory
        self.search_factory = search_factory or self._default_search
        self.explainer_factory = explainer_factory or self._default_explainer
        self.source_monitor = source_monitor or GitHubContextMonitor()
        self._provider_loaded = False
        self._provider = None
        self._sdk_client = None

    def _default_search(self):
        from app.services.discovery_search import DiscoverySearch, SearchBudget

        return DiscoverySearch(
            budget=SearchBudget(
                top_k=self.settings.DISCOVERY_TOP_K,
                max_queries=2,
                per_query=12,
                max_candidates=24,
                total_seconds=25,
                request_seconds=8,
            )
        )

    def _default_explainer(self):
        from app.services.discovery_explanations import DiscoveryExplainer

        timeout_seconds = min(20, self.settings.LLM_TIMEOUT_SECONDS)
        if self.settings.DISCOVERY_LLM_ENABLED and not self._provider_loaded:
            self._provider_loaded = True
            from app.services.llm import require_provider, LLMConfig

            try:
                config = LLMConfig(
                    provider=self.settings.LLM_PROVIDER,
                    model=self.settings.LLM_MODEL,
                    api_key=self.settings.GEMINI_API_KEY,
                    max_retries=0,
                    timeout_seconds=timeout_seconds,
                    max_output_tokens=min(1024, self.settings.LLM_MAX_OUTPUT_TOKENS),
                )
                overrides = (
                    {"client_factory": self._client_factory}
                    if config.provider == "gemini"
                    else {}
                )
                self._provider = require_provider(config, **overrides)
            except Exception:
                pass  # explicit fallback warning comes from explainer
        return DiscoveryExplainer(
            provider=self._provider, timeout_seconds=timeout_seconds, max_calls=3
        )

    def _client_factory(self, *, api_key):
        self._sdk_client = _gemini_client(api_key=api_key)
        return self._sdk_client

    async def aclose(self):
        client = self._sdk_client
        if client is None:
            return
        self._sdk_client = None
        try:
            close = getattr(getattr(client, "aio", None), "aclose", None)
            if close is not None:
                await close()
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                close()

    @contextmanager
    def tx(self):
        with self.sessions() as session, session.begin():
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            session.execute(text("SET LOCAL statement_timeout = '5s'"))
            yield session

    async def tick(self):
        with self.tx() as session:
            db.recover_expired(session)
            lease = db.claim_run(session)
        if lease:
            await self.process(lease)
            return True
        with self.tx() as session:
            lease = db.claim_monitor(
                session, lease_seconds=int(self.settings.MONITOR_FETCH_SECONDS) + 5
            )
        if lease:
            await self.check(lease)
            return True
        return False

    async def check(self, lease):
        deadline = time.monotonic() + self.settings.MONITOR_FETCH_SECONDS
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.source_monitor.check,
                    lease.repo_url,
                    state=lease.state,
                    deadline=deadline,
                ),
                timeout=self.settings.MONITOR_FETCH_SECONDS + 1,
            )
            with self.tx() as session:
                db.record_observation(
                    session,
                    lease,
                    result,
                    deadline_seconds=self.settings.DISCOVERY_DEADLINE_SECONDS,
                )
        except Exception as exc:
            with self.tx() as session:
                db.record_failure(
                    session,
                    lease,
                    "timeout"
                    if isinstance(exc, (TimeoutError, asyncio.TimeoutError))
                    else getattr(exc, "code", "source_unavailable"),
                    retry_after=getattr(exc, "retry_after", None),
                )

    def _claimed(self, session, lease):
        run = session.scalar(
            select(DiscoveryRun)
            .where(DiscoveryRun.id == lease.run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            run is None
            or run.status != "running"
            or run.claim_token != lease.token
            or run.deadline_at <= db.now()
        ):
            raise db.Conflict("Expired run claim")
        return run

    async def process(self, lease):
        remaining = (lease.deadline_at - datetime.now(timezone.utc)).total_seconds()
        deadline = time.monotonic() + max(0, remaining)
        warnings = []
        try:
            async with asyncio.timeout(max(0, remaining)):
                result = await asyncio.to_thread(
                    self.source_monitor.check,
                    lease.repo_url,
                    state=lease.state,
                    deadline=min(
                        deadline, time.monotonic() + self.settings.MONITOR_FETCH_SECONDS
                    ),
                )
                with self.tx() as session:
                    item_id, monitor_id = db.record_observation(
                        session,
                        lease,
                        result,
                        deadline_seconds=self.settings.DISCOVERY_DEADLINE_SECONDS,
                    )
                    run = self._claimed(session, lease)
                    project = upsert_item_entity(session, item_id, "project")
                    run.project_id = project.id
                    item = session.get(AcademicItem, item_id, populate_existing=True)
                    project_snapshot = snapshot_from_item(item, "github")
                    run.context_hash = project_snapshot.content_hash
                    topics = tuple((item.metadata_ or {}).get("topics") or [])[:20]
                # A factory per run enforces provider budgets across candidates.
                search = self.search_factory()
                search_result = await search.search(
                    project_snapshot, topics=topics, deadline=deadline
                )
                warnings.extend(
                    w for w in search_result.warnings if w in _SAFE_WARNINGS
                )
                if "insufficient_context" in warnings:
                    self._finish(lease, [], warnings, "insufficient_context")
                    return
                if search_result.failed:
                    self._finish(
                        lease,
                        [],
                        warnings,
                        "timeout"
                        if "search_timeout" in warnings
                        else "source_unavailable",
                    )
                    return
                candidates = list(search_result.candidates)[
                    : self.settings.DISCOVERY_TOP_K
                ]
                if not candidates:
                    self._finish(lease, [], warnings, None)
                    return
                with self.tx() as session:
                    self._claimed(session, lease)
                    ids = db.persist_items(session, [c.item for c in candidates])
                    rows = session.execute(
                        select(AcademicItem, Source.provider)
                        .join(Source)
                        .where(AcademicItem.id.in_(ids.values()))
                    ).all()
                    snapshots = {
                        item.external_id: snapshot_from_item(item, provider)
                        for item, provider in rows
                    }
                explainer = self.explainer_factory()
                proposals = []
                for candidate in candidates:
                    if time.monotonic() >= deadline:
                        raise TimeoutError()
                    snapshot = snapshots[candidate.item.external_id]
                    try:
                        explanation = await explainer.explain(
                            project_snapshot, snapshot, candidate, deadline=deadline
                        )
                        if explanation.warning in _SAFE_WARNINGS:
                            warnings.append(explanation.warning)
                        proposals.append(
                            SuggestionInput(
                                article_item_id=snapshot.origin_item_id,
                                justification=explanation.justification,
                                score=explanation.score,
                                evidences=tuple(
                                    EvidenceInput.model_validate(e)
                                    for e in explanation.evidences
                                ),
                            )
                        )
                    except _candidate_rejected_type():
                        continue
                    except ValueError:
                        warnings.append("invalid_candidate")
                self._finish(
                    lease,
                    proposals,
                    warnings,
                    "invalid_evidence"
                    if not proposals and "invalid_candidate" in warnings
                    else None,
                )
        except (TimeoutError, asyncio.TimeoutError):
            self._fail(lease, "timeout", warnings)
        except ValueError:
            self._fail(lease, "invalid_evidence", warnings)
        except SourceFailure as exc:
            self._fail(lease, exc.code, warnings)
        except Exception:
            self._fail(lease, "internal_error", warnings)

    def _finish(self, lease, proposals, warnings, error):
        # Monitor -> run -> ordered source items. No I/O inside the transaction.
        with self.tx() as session:
            m = session.scalar(
                select(SourceMonitor)
                .where(SourceMonitor.id == lease.monitor_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            run = self._claimed(session, lease)
            if m is None:
                raise db.Conflict("Monitor removed")
            if proposals:
                save_suggestions(session, run.id, proposals)
            unique = list(dict.fromkeys(warnings))
            if error:
                update_run(
                    session, run.id, RunUpdate(status="failed", error_code=error)
                )
            elif unique:
                update_run(
                    session,
                    run.id,
                    RunUpdate(status="partial", error_code="analysis_warning"),
                )
            else:
                update_run(session, run.id, RunUpdate(status="completed"))
            run.warnings = unique
            run.claim_token = None
            run.lease_expires_at = None
            if run.status in ("completed", "partial"):
                # Only a successful analysis of the currently observed context clears stale.
                if m.current_hash == run.context_hash:
                    m.analyzed_hash = run.context_hash
            # A change during an active analysis may have coalesced its auto request.
            if (
                m.enabled
                and m.reanalyze_on_change
                and m.current_hash != m.analyzed_hash
                and m.current_hash != run.context_hash
            ):
                db.submit(
                    session,
                    DiscoveryCreate(repo_url=m.repo_url),
                    deadline_seconds=self.settings.DISCOVERY_DEADLINE_SECONDS,
                    monitor=m,
                )

    def _fail(self, lease, code, warnings):
        code = (
            code
            if code
            in {
                "timeout",
                "source_unavailable",
                "invalid_evidence",
                "insufficient_context",
            }
            else "internal_error"
        )
        with self.tx() as session:
            # First release any still-owned fetch lease. Failed analysis never changes analyzed_hash.
            db.record_failure(session, lease, code)
            run = session.scalar(
                select(DiscoveryRun)
                .where(DiscoveryRun.id == lease.run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if run and run.status == "running" and run.claim_token == lease.token:
                if run.deadline_at <= db.now():
                    from app.repositories.discovery import expire_run

                    expire_run(session, run.id)
                else:
                    update_run(
                        session, run.id, RunUpdate(status="failed", error_code=code)
                    )
                run.warnings = list(dict.fromkeys(warnings))
                run.claim_token = None
                run.lease_expires_at = None


def _candidate_rejected_type():
    from app.services.discovery_explanations import CandidateRejected

    return CandidateRejected


def _gemini_client(*, api_key):
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1)
        ),
    )
