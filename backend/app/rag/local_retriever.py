import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+")
NORMALIZE_PATTERN = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]+")


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    path: Path
    metadata: dict[str, Any]
    content: str

    @property
    def title(self) -> str:
        return str(self.metadata.get("title", self.path.stem))


@dataclass(frozen=True, slots=True)
class SearchResult:
    document: MarkdownDocument
    score: float
    snippet: str
    matched_terms: tuple[str, ...]


REQUIRED_METADATA = (
    "title",
    "character_id",
    "data_version",
    "source_page",
    "generated_at",
    "document_type",
)


def document_quality_issues(document: MarkdownDocument) -> list[str]:
    issues = [f"missing_metadata:{field}" for field in REQUIRED_METADATA if not document.metadata.get(field)]
    title = document.title
    if len(title) > 40 or "\n" in title or "'enhance':" in title:
        issues.append("malformed_title")
    if not document.path.name.startswith(str(document.metadata.get("character_id", ""))):
        issues.append("character_id_filename_mismatch")
    for section in ("## 基本资料", "## 技能"):
        if section not in document.content:
            issues.append(f"missing_section:{section.removeprefix('## ')}")
    return issues


def load_character_documents(directory: Path) -> list[MarkdownDocument]:
    documents: list[MarkdownDocument] = []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        match = FRONTMATTER_PATTERN.match(raw)
        if not match:
            continue
        metadata = yaml.safe_load(match.group(1)) or {}
        content = raw[match.end() :].strip()
        documents.append(MarkdownDocument(path=path, metadata=metadata, content=content))
    return documents


def _query_terms(query: str) -> list[str]:
    terms: set[str] = set()
    for token in TOKEN_PATTERN.findall(query.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            max_size = min(6, len(token))
            for size in range(2, max_size + 1):
                terms.update(token[index : index + size] for index in range(len(token) - size + 1))
        elif len(token) >= 2:
            terms.add(token)
    return sorted(terms, key=lambda item: (-len(item), item))


def _normalize(value: str) -> str:
    """Make common display punctuation irrelevant to character-name matching."""
    return NORMALIZE_PATTERN.sub("", value).lower()


def _snippet(content: str, matched_terms: list[str], radius: int = 90) -> str:
    flattened = re.sub(r"\s+", " ", content)
    positions = [flattened.lower().find(term) for term in matched_terms]
    positions = [position for position in positions if position >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - radius)
    end = min(len(flattened), center + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(flattened) else ""
    return f"{prefix}{flattened[start:end].strip()}{suffix}"


def search_documents(
    documents: list[MarkdownDocument], query: str, limit: int = 3
) -> list[SearchResult]:
    terms = _query_terms(_normalize(query))
    results: list[SearchResult] = []
    normalized_query = _normalize(query)

    for document in documents:
        if document_quality_issues(document):
            continue
        title = _normalize(document.title)
        searchable = _normalize(f"{document.title}\n{document.content}")
        matched = [term for term in terms if term in searchable]
        if not matched:
            continue

        score = 0.0
        if title and title in normalized_query:
            score += 500.0
        for term in matched:
            frequency = min(searchable.count(term), 8)
            score += frequency * math.pow(len(term), 1.35)
            if term in title:
                score += 10.0 * len(term)

        results.append(
            SearchResult(
                document=document,
                score=score,
                snippet=_snippet(document.content, matched),
                matched_terms=tuple(matched[:8]),
            )
        )

    return sorted(results, key=lambda result: (-result.score, result.document.title))[:limit]
