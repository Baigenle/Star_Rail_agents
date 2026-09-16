from __future__ import annotations

import re


_MEDIAWIKI_MARKER = re.compile(r"MediaWiki:[A-Za-z][A-Za-z0-9_]*")
_CRAWLER_HEADER = re.compile(
    r"(?m)^【(?:所属版本|世界|系列任务|任务名称|当前场景|当前地点|出场角色|剧情正文|地点)】"
    r"[^\n]*(?:\n|$)"
)
_VECTOR_ENRICHMENT_HEADER = re.compile(
    r"(?m)^(?:角色/条目|章节)：[^\n]*(?:\n|$)"
)


def clean_story_content(content: str) -> str:
    """Remove crawler-only metadata without rewriting the source dialogue."""
    cleaned = _CRAWLER_HEADER.sub("", content)
    cleaned = _VECTOR_ENRICHMENT_HEADER.sub("", cleaned)
    cleaned = _MEDIAWIKI_MARKER.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def speaking_characters(candidates: list[object], content: str) -> list[str]:
    """Keep only candidates that have an actual dialogue line in the scene."""
    cleaned = clean_story_content(content)
    confirmed: list[str] = []
    for raw_name in candidates:
        name = str(raw_name).strip()
        if not name or name.casefold() == "mediawiki":
            continue
        speaker = re.compile(rf"(?m)^\s*{re.escape(name)}\s*[:：]")
        if speaker.search(cleaned) and name not in confirmed:
            confirmed.append(name)
    return confirmed
