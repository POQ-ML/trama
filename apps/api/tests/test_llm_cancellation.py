"""No network: real adapter wrapped around a waiting fake SDK call."""
import asyncio
from types import SimpleNamespace

import pytest

from app.services.llm import LLMError, LLMErrorCategory, LLMRequest
from app.services.llm.gemini import GeminiLLMProvider


def adapter(timeout=30):
    entered = asyncio.Event()
    calls = []

    async def generate_content(**kwargs):
        calls.append(kwargs)
        entered.set()
        await asyncio.Event().wait()

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(
        generate_content=generate_content)))
    provider = GeminiLLMProvider(
        api_key="synthetic", timeout_seconds=timeout, max_retries=0,
        client_factory=lambda **kwargs: client,
    )
    return provider, entered, calls


def test_outer_deadline_is_timeout_instead_of_unknown_provider_error():
    async def scenario():
        provider, _, calls = adapter()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(provider.generate(LLMRequest(user_input="synthetic")), 0.01)
        assert len(calls) == 1

    asyncio.run(scenario())


def test_external_cancellation_propagates_without_retry():
    async def scenario():
        provider, entered, calls = adapter()
        task = asyncio.create_task(provider.generate(LLMRequest(user_input="synthetic")))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled() and len(calls) == 1

    asyncio.run(scenario())


def test_provider_timeout_still_normalized_without_retry():
    async def scenario():
        provider, _, calls = adapter(timeout=0.01)
        with pytest.raises(LLMError) as error:
            await provider.generate(LLMRequest(user_input="synthetic"))
        assert error.value.category == LLMErrorCategory.TIMEOUT
        assert error.value.retry_count == 0 and len(calls) == 1

    asyncio.run(scenario())


def test_explainer_outer_deadline_yields_timeout_fallback():
    from datetime import datetime, timezone
    from uuid import UUID

    from app.services.discovery_evidence import SourceSnapshot
    from app.services.discovery_explanations import DiscoveryExplainer
    from app.services.discovery_search import rank_candidate
    from test_discovery_search import article_item, project_snapshot

    async def scenario():
        provider, _, calls = adapter()
        project = project_snapshot()
        item = article_item()
        candidate = rank_candidate(project, item)
        article = SourceSnapshot(
            UUID(int=2), "article", {"title": item.title, "description": item.description},
            "https://openalex.org/W123", item.content_hash, datetime.now(timezone.utc),
        )
        result = await DiscoveryExplainer(provider, timeout_seconds=0.01).explain(
            project, article, candidate,
        )
        assert result.warning == "explanation_timeout"
        assert len(calls) == 1 and len(result.evidences) == 2

    asyncio.run(scenario())
