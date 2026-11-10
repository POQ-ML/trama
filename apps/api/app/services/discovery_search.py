"""Bounded, injectable OpenAlex retrieval and conservative lexical screening.

Scores are inspectable heuristics, NOT measured probabilities of usefulness.
At least two substantive terms must occur in literal windows on BOTH sides;
at least one must also be a discriminating cue in the project's lead context,
not just a structural/multiuse term such as graph/network. Obvious negated
clauses do not supply positive cues. Tags alone cannot qualify an article. This intentionally abstains
on sparse, multilingual or vocabulary-mismatched projects. Source text is data.
No ORM, persistence, model configuration or free-form LLM retrieval is involved.

deadline is absolute time.monotonic(). Calls are sequential. On a timeout we
stop: a cancelled to_thread cannot kill an already-running urllib request. The
default adapter has a process-wide two-request gate, zero retries, one page and
socket timeout; it never starts a replacement request after that timeout.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from itertools import islice
import math
import re
import threading
import time
import unicodedata
from typing import Protocol, Sequence

from app.services.discovery_evidence import EvidenceSelection, SourceSnapshot
from app.services.ingestion.models import NormalisedItem

_HTTP_SLOTS = threading.BoundedSemaphore(2)
_WORD = re.compile(r"[^\W\d_][\w-]{2,40}", re.UNICODE)
_STOP = set("""the and for with from this that have has are was were will would could
into your you our their they its using used use uses based about more also can
uma umas uns para com por dos das que como este esta esse essa pelo pela nao
ser sao tem uma sobre mais seu sua seus suas projeto projetos project projects
repository repositories repo github readme install installation getting started
dependency dependencies requirements setup quickstart
python javascript typescript java code software application applications app
data dados system systems sistema development framework library libraries
example examples test tests testing documentation license open source build
tool tools research study studies results result analysis approach proposed
web website api fastapi react nextjs docker service services backend frontend
method methods model models implementation implement learning machine
http https www org github openalex instructions instruction ignore previous
prompt prompts assistant system user developer return output response please
introduction abstract paper article trabalho artigo artigos pesquisa estudo
through between these those such than then which when where while not all
one two each other only both new different presents present provides provide
analysis analise avaliacao evaluation performance efficient efficientes
state art best leading cutting edge innovative innovation powerful seamless
revolutionary advanced world class high quality easy simple fast
""".split())
_ALIASES = {
    "graphs": "graph", "grafos": "graph", "grafo": "graph",
    "networks": "network", "redes": "network", "rede": "network",
    "neural": "neural", "neurais": "neural", "neuronais": "neural",
    "embeddings": "embedding", "representations": "representation",
    "recommendations": "recommendation", "recomendacao": "recommendation",
    "recommender": "recommendation", "recommendation": "recommendation",
    "retrieval": "retrieval", "recuperacao": "retrieval",
    "semantic": "semantic", "semantica": "semantic", "semantico": "semantic",
    "documents": "document", "documentos": "document",
    "classificacao": "classification", "classifications": "classification",
    "images": "image", "imagens": "image", "imagem": "image",
    "knowledge": "knowledge", "conhecimento": "knowledge",
    "scientific": "scientific", "cientifico": "scientific",
    "citations": "citation", "citacoes": "citation",
}
# General structural vocabulary crosses unrelated disciplines. It can support
# ranking AFTER an intent cue qualifies, never establish utility by itself.
# This is a versioned heuristic, not a taxonomy or fixture-specific topic ban.
_BROAD_SIGNALS = set("""graph network route path directed weighted exact neural
scientific document image semantic knowledge context information digital
computer computational technology technologies algorithm algorithms general
learning machine visual visualization monitoring engine goal correct minimum
academic academics educational education student students university universities
agent agents agentic platform platforms fragmented relevant relevance relation
relations relationship relationships intelligent intelligence artificial
""".split())


def _canonical(word: str) -> str:
    word = "".join(c for c in unicodedata.normalize("NFKD", word.casefold()) if not unicodedata.combining(c))
    return _ALIASES.get(word, word)


def _masked(text: str) -> str:
    """Keep character offsets while excluding links, code and obvious directives.

    This is noise reduction, not an assertion that arbitrary prose is safe or
    meaningful. The explainer never accepts executable instructions from prose.
    """
    text = text[:20_000]
    text = re.sub(r"```[\s\S]*?(?:```|$)|https?://\S+", lambda m: " " * len(m[0]), text)
    text = re.sub(r"(?im)^.*(?:ignore (?:all|previous)|system prompt|ignore instru|api[_ -]?key|bearer ).*$", lambda m: " " * len(m[0]), text)
    # Conservative explicit negation scope; unsupported syntax can still require
    # abstention/human review. Never use an exclusion as an affirmative match.
    text = re.sub(r"(?i)\b(?:no|not|without|never|sem|não|nao)\b[^.;\n]*", lambda m: " " * len(m[0]), text)
    return text.replace("-", " ").replace("–", " ")


_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s*(.*?)\s*#*\s*$")
_RST_UNDERLINE = re.compile(r"^\s{0,3}([=\-~^\"`:+*#_])\1{2,}\s*$")
_BOILERPLATE_HEADING = re.compile(
    r"^(?:install(?:ation|ing)?|getting started|quick ?start|quickstart|"
    r"requirements?|dependencies|setup|build|building)(?:\b.*)?$",
    re.I,
)
_BOILERPLATE_LINE = re.compile(
    r"^\s*(?:(?:[$>]\s*)?(?:pip|pip3|npm|yarn|pnpm|conda|poetry|uv)\s+(?:install|add)\b|"
    r"(?:requirements|environment|dependencies)\.(?:txt|ya?ml)|"
    r"install(?:ation)?\s+(?:instructions|steps)|add the dependency)\b",
    re.I,
)


def _purpose_mask(text: str) -> str:
    """Mask generic setup sections while preserving original character offsets."""
    masked = list(_masked(text))
    if len(masked) < len(text):
        masked.extend(" " for _ in range(len(text) - len(masked)))
    lines = text.splitlines(keepends=True)
    offsets = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    active = None
    index = 0
    while index < len(lines):
        line = lines[index]
        body = line.rstrip("\r\n")
        heading = _HEADING.match(body)
        rst_heading = (
            index + 1 < len(lines)
            and body.strip()
            and _RST_UNDERLINE.fullmatch(lines[index + 1].strip())
        )
        skip = False
        if heading or rst_heading:
            # A new RST section always starts a new scope. For Markdown, a
            # same-level or higher heading closes the active section.
            if rst_heading:
                active = None
            elif active and active[0] == "markdown" and len(heading.group(1)) <= active[1]:
                active = None
            elif active and active[0] == "rst":
                active = None
            label = heading.group(2).strip() if heading else body.strip()
            level = len(heading.group(1)) if heading else None
            if _BOILERPLATE_HEADING.fullmatch(label):
                active = ("markdown", level) if heading else ("rst", None)
                skip = True
                if rst_heading:
                    underline_offset = offsets[index + 1]
                    underline_end = underline_offset + len(lines[index + 1])
                    for cursor in range(underline_offset, underline_end):
                        if masked[cursor] not in "\r\n":
                            masked[cursor] = " "
            elif active:
                skip = True
        elif active:
            skip = True
        elif _BOILERPLATE_LINE.match(body):
            skip = True
        if skip:
            start = offsets[index]
            for cursor in range(start, start + len(line)):
                if masked[cursor] not in "\r\n":
                    masked[cursor] = " "
        index += 1
    return "".join(masked)


def _intent_context(fields: dict[str, str]) -> str:
    description = _purpose_mask(fields.get("description", ""))
    readme_masked = _purpose_mask(fields.get("metadata.readme", "")[:20_000])
    readme = " ".join(line.strip() for line in readme_masked.splitlines() if line.strip())
    if len(readme) > 2_000:
        readme = readme[:2_000].rsplit(" ", 1)[0]
    description_cues = tokens(description) - _BROAD_SIGNALS
    readme_cues = tokens(readme) - _BROAD_SIGNALS
    # Use the short description when it has concrete cues; otherwise consult
    # only a compact, boilerplate-filtered README lead (<=2k chars), not the
    # vocabulary of the entire documentation. Selections still slice originals.
    if len(readme_cues) >= 2 and len(readme_cues) > len(description_cues):
        return readme
    return description if description.strip() else readme


def _word_window(text: str, hit_start: int, hit_end: int, limit: int = 900) -> tuple[int, int]:
    start = max(0, hit_start - min(300, limit // 3))
    end = min(len(text), start + limit)
    if start > 0:
        while start < hit_start and not text[start - 1].isspace():
            start += 1
    if end < len(text):
        while end > hit_end and not text[end - 1].isspace():
            end -= 1
    if end <= hit_end:
        while end < len(text) and not text[end].isspace():
            end += 1
    return start, end


def _sentence_window(text: str, hit_start: int, hit_end: int) -> tuple[int, int]:
    """Heuristic sentence boundary; punctuation in URLs/decimals can confuse it."""
    left = max(text.rfind(mark, 0, hit_start) for mark in (".", "!", "?", "\n")) + 1
    while left < hit_start and text[left].isspace():
        left += 1
    right_candidates = [position for mark in (".", "!", "?", "\n")
                        if (position := text.find(mark, hit_end)) != -1]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    while right < len(text) and text[right] in "\"'”’)]}":
        right += 1
    while right > left and text[right - 1].isspace():
        right -= 1
    return left, right


def tokens(text: str) -> set[str]:
    return {w for m in _WORD.finditer(_masked(text)) if (w := _canonical(m[0])) not in _STOP and len(w) >= 3}


@dataclass(frozen=True)
class SearchBudget:
    max_queries: int = 3
    per_query: int = 12
    max_candidates: int = 30
    top_k: int = 5
    request_seconds: float = 8.0
    total_seconds: float = 30.0

    def __post_init__(self):
        for name, maximum in (("max_queries", 3), ("per_query", 20), ("max_candidates", 60), ("top_k", 10)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"Invalid search budget: {name}")
        for name, maximum in (("request_seconds", 15), ("total_seconds", 60)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= maximum:
                raise ValueError(f"Invalid search budget: {name}")


class ArticleSearcher(Protocol):
    async def search(self, query: str, *, limit: int, timeout: float) -> Sequence[NormalisedItem]: ...


class OpenAlexSearch:
    """Existing connector adapter. Inject an ArticleSearcher to avoid all network."""

    async def search(self, query: str, *, limit: int, timeout: float) -> Sequence[NormalisedItem]:
        def fetch():
            if not _HTTP_SLOTS.acquire(blocking=False):
                raise RuntimeError("OpenAlex request capacity reached")
            try:
                from app.services.ingestion.openalex import OpenAlexConnector
                connector = OpenAlexConnector(query=query, per_page=limit, max_pages=1, timeout=timeout, max_retries=0)
                return list(islice(connector.fetch(), limit))
            finally:
                _HTTP_SLOTS.release()
        return await asyncio.to_thread(fetch)


@dataclass(frozen=True)
class RankedCandidate:
    item: NormalisedItem
    score: float
    matched_terms: tuple[str, ...]
    repo_selection: EvidenceSelection
    article_selection: EvidenceSelection
    repo_content_hash: str
    context_anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchResult:
    candidates: tuple[RankedCandidate, ...]
    queries: tuple[str, ...]
    warnings: tuple[str, ...]
    failed: bool


def _project_fields(project: SourceSnapshot) -> dict[str, str]:
    if project.side != "repo":
        raise ValueError("Search requires a trusted repository snapshot")
    return {name: text for name in ("description", "metadata.readme")
            if isinstance(text := project.fields.get(name), str) and 0 < len(text) <= 100_000 and text.strip()}


def _terms(fields: dict[str, str], topics: Sequence[str]) -> list[str]:
    weights: Counter = Counter()
    for name, text in fields.items():
        # Document frequency caps repeated SEO/injection words; no frequency boost.
        for term in tokens(_purpose_mask(text)):
            weights[term] += 3 if name == "description" else 1
    # Tags guide queries only when the context independently contains their terms.
    context_terms = set(weights)
    for topic in topics[:20]:
        if isinstance(topic, str):
            for term in tokens(topic) & context_terms:
                weights[term] += 2
    anchors = tokens(_intent_context(fields)) - _BROAD_SIGNALS
    # Put task/object cues before broad descriptors. A query budget must not be
    # consumed by academic/agent/platform when actual intent is available.
    return sorted(weights, key=lambda term: (term not in anchors, -weights[term], term))[:24]


def _window(field: str, text: str, terms: set[str]) -> EvidenceSelection | None:
    masked = _purpose_mask(text)
    hits = [m for m in _WORD.finditer(masked) if _canonical(m[0]) in terms]
    best = None
    best_count = 0
    # Prefer complete sentences. Overlong sentences fall back to whole-word
    # windows. The selection remains an exact slice of the original field.
    for hit in hits[:64]:
        start, end = _sentence_window(text, hit.start(), hit.end())
        if end - start > 900:
            start, end = _word_window(text, hit.start(), hit.end())
        count = len(tokens(text[start:end]) & terms)
        if count > best_count:
            best_count = count
            best = EvidenceSelection(field, start, end, text[start:end])
    return best


def rank_candidate(project: SourceSnapshot, item: NormalisedItem) -> RankedCandidate | None:
    """Require concrete overlapping context, never just OpenAlex topic scores."""
    if (item.item_type != "article" or item.source_key != "openalex"
        or not isinstance(item.external_id, str) or not re.fullmatch(r"W[0-9]+", item.external_id)
        or not isinstance(item.title, str) or not item.title.strip()
        or len(item.title) > 100_000
        or item.description is not None and not isinstance(item.description, str)
        or isinstance(item.description, str) and len(item.description) > 100_000
        or not isinstance(item.metadata, dict)
        or not isinstance(item.content_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", item.content_hash)):
        return None
    repo_fields = _project_fields(project)
    article_fields = {"title": item.title, "description": item.description or ""}
    repo_terms = set().union(*(tokens(_purpose_mask(t)) for t in repo_fields.values()))
    article_terms = set().union(*(tokens(t) for t in article_fields.values()))
    common = repo_terms & article_terms
    if len(common) < 2:
        return None
    # A title/stack name and incidental README paragraph are not project intent.
    intent_cues = tokens(_intent_context(repo_fields)) - _BROAD_SIGNALS
    if not common & intent_cues:
        return None
    best = None
    for repo_field, repo_text in repo_fields.items():
        repo = _window(repo_field, repo_text, common)
        if repo is None:
            continue
        supported = tokens(repo.excerpt) & common
        for article_field, article_text in article_fields.items():
            article = _window(article_field, article_text, supported)
            if article is None:
                continue
            matched = supported & tokens(article.excerpt)
            anchors = matched & intent_cues
            if len(matched) < 2 or not anchors:
                continue
            # Bound explanation/structured-output size independently of README
            # vocabulary; always retain the discriminating intent cues first.
            anchor_terms = tuple(sorted(anchors)[:4])
            selected = tuple(dict.fromkeys((*anchor_terms, *sorted(matched))))[:8]
            # Jaccard-like local coverage plus capped overlap and title support.
            title_support = len(matched & tokens(item.title)) / len(matched)
            score = round(min(1.0, .15 * min(len(matched), 4) + .25 * title_support + .15 * len(matched) / max(1, len(tokens(repo.excerpt)))), 4)
            candidate = RankedCandidate(item, score, tuple(sorted(selected)), repo, article, project.content_hash, anchor_terms)
            # If both evidence fields support the same substantive anchor set
            # equally, prefer the abstract sentence that can explain a method;
            # title remains the fallback whenever its score/support is better
            # or the description fails the existing term+anchor gate.
            prefer_article_description = (
                best is not None
                and candidate.score == best.score
                and candidate.article_selection.field == "description"
                and best.article_selection.field == "title"
            )
            if best is None or candidate.score > best.score or prefer_article_description:
                best = candidate
    return best


class DiscoverySearch:
    def __init__(self, searcher: ArticleSearcher | None = None, budget: SearchBudget | None = None):
        self.searcher = searcher if searcher is not None else OpenAlexSearch()
        self.budget = budget or SearchBudget()

    async def search(self, project: SourceSnapshot, *, topics: Sequence[str] = (), deadline: float | None = None) -> SearchResult:
        budget = self.budget
        end = time.monotonic() + budget.total_seconds
        if deadline is not None:
            if not math.isfinite(deadline):
                raise ValueError("deadline must be finite monotonic time")
            end = min(end, deadline)
        if end <= time.monotonic():
            return SearchResult((), (), ("search_timeout",), True)
        terms = _terms(_project_fields(project), topics)
        fields = _project_fields(project)
        anchors = tokens(_intent_context(fields)) - _BROAD_SIGNALS
        if len(terms) < 2 or not anchors:
            return SearchResult((), (), ("insufficient_context",), False)
        # Rotate small groups rather than issue near-identical broad searches.
        ordered_anchors = [term for term in terms if term in anchors]
        plans = []
        for i in range(budget.max_queries):
            # Every query retains a task cue, even when rotating supporting words.
            task = ordered_anchors[(i*2) % len(ordered_anchors):][:2]
            supporting = terms[i*3:i*3+4]
            query = " ".join(dict.fromkeys((*task, *supporting)))
            if query and query not in plans:
                plans.append(query)
        planned = plans
        queries = []
        warnings = ["context_window_limited"] if any(len(text) > 20_000 for text in _project_fields(project).values()) else []
        candidates: list[RankedCandidate] = []
        seen_ids, seen_dois = set(), set()
        success = 0
        accepted_count = 0
        for query in planned:
            remaining = end - time.monotonic()
            if remaining <= 0:
                warnings.append("search_timeout")
                break
            queries.append(query)
            timeout = min(budget.request_seconds, remaining)
            try:
                items = await asyncio.wait_for(self.searcher.search(query, limit=budget.per_query, timeout=timeout), timeout=timeout)
            except (TimeoutError, asyncio.TimeoutError):
                warnings.append("search_timeout")
                break  # Never launch a new thread after a timed-out request.
            except Exception:
                warnings.append("source_unavailable")
                continue
            if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
                warnings.append("invalid_candidate")
                continue
            success += 1
            for item in islice(items, budget.per_query):
                if time.monotonic() >= end:
                    warnings.append("search_timeout")
                    break
                if not isinstance(item, NormalisedItem):
                    warnings.append("invalid_candidate")
                    continue
                doi = str(item.metadata.get("doi") or "").casefold().removeprefix("https://doi.org/").strip()
                if item.external_id in seen_ids or doi and doi in seen_dois:
                    continue
                seen_ids.add(item.external_id)
                if doi:
                    seen_dois.add(doi)
                accepted_count += 1
                ranked = rank_candidate(project, item)
                if ranked is not None:
                    candidates.append(ranked)
                if accepted_count >= budget.max_candidates:
                    break
            if accepted_count >= budget.max_candidates:
                warnings.append("candidate_budget_reached")
                break
            if "search_timeout" in warnings:
                break
        candidates.sort(key=lambda c: (-c.score, c.item.external_id))
        return SearchResult(tuple(candidates[:budget.top_k]), tuple(queries), tuple(dict.fromkeys(warnings)), bool(warnings) and success == 0)
