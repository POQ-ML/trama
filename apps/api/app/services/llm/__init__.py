"""LLM service package.

Canonical runtime location for the provider abstraction.

Decision (documented here because it affects packaging): ADR-0005 says
``packages/ai`` must isolate the provider behind an interface. ``packages/ai``
is currently pure (zero external deps, see ``packages/ai/README.md``) and —
critically — is NOT copied into the API Docker image
(``apps/api/Dockerfile`` only ``COPY apps/api/``). Creating the runtime
adapter there would leave it unimportable in Docker/pytest
(``pythonpath = .``). The smallest maintainable integration is therefore
``app.services.llm`` (importable, async-ready, covered by existing
``Settings``/logging/pytest conventions). The contracts here are shaped for
a future move to ``packages/ai`` without rewriting consumers once ADR-0002
(monorepo packaging) is decided.
"""

from app.services.llm.base import (
    LLMError,
    LLMErrorCategory,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)
from app.services.llm.config import DEFAULT_MODEL, LLMConfig, create_provider, require_provider
from app.services.llm.fake import FakeLLMProvider
from app.services.llm.gemini import GeminiLLMProvider
from app.services.llm.telemetry import (
    InMemoryTelemetrySink,
    LLMTelemetryRecord,
    LoggingTelemetrySink,
    TelemetrySink,
    observe,
)

__all__ = [
    "DEFAULT_MODEL",
    "FakeLLMProvider",
    "GeminiLLMProvider",
    "InMemoryTelemetrySink",
    "LLMConfig",
    "LLMError",
    "LLMErrorCategory",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "LLMTelemetryRecord",
    "LLMUsage",
    "LoggingTelemetrySink",
    "TelemetrySink",
    "create_provider",
    "observe",
    "require_provider",
]
