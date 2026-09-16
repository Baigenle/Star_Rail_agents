import hashlib
import re
from dataclasses import dataclass

from app.rag.knowledge_loader import KnowledgeDocument


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PLACEHOLDER_PATTERN = re.compile(r"#[0-9]+\[[A-Za-z]\]")
EXCLUDED_SECTIONS = {"使用说明", "数据说明", "未展开字段"}


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_id: str
    entry_id: str
    entry_type: str
    title: str
    section: str
    content: str
    content_hash: str
    data_version: str
    source_page: str
    generated_at: str


def _clean_lines(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        if "用于替换技能描述占位符" in line:
            continue
        if PLACEHOLDER_PATTERN.search(line):
            continue
        kept.append(line.rstrip())
    return "\n".join(kept).strip()


def _sections(document: KnowledgeDocument) -> list[tuple[str, str]]:
    current_section = "概览"
    buffer: list[str] = []
    result: list[tuple[str, str]] = []
    skip_section = False

    def flush() -> None:
        if skip_section:
            return
        content = _clean_lines("\n".join(buffer))
        if content:
            result.append((current_section, content))

    for line in document.content.splitlines():
        match = HEADING_PATTERN.match(line)
        if not match:
            if not skip_section:
                buffer.append(line)
            continue
        level = len(match.group(1))
        heading = match.group(2).strip()
        if level >= 3:
            if not skip_section:
                buffer.append(line)
            continue
        flush()
        buffer = []
        current_section = heading
        skip_section = heading in EXCLUDED_SECTIONS
    flush()
    if (
        len(result) > 1
        and result[0][0] == document.title
        and "来源页面" in result[0][1]
    ):
        return result[1:]
    return result


def _windows(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        target_end = min(len(text), start + max_chars)
        end = target_end
        if target_end < len(text):
            candidates = [
                text.rfind("\n\n", start, target_end),
                text.rfind("\n", start, target_end),
                text.rfind("。", start, target_end),
            ]
            boundary = max(candidates)
            if boundary > start + max_chars // 2:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def chunk_document(
    document: KnowledgeDocument, max_chars: int = 900, overlap: int = 120
) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    for section, section_content in _sections(document):
        for index, content in enumerate(_windows(section_content, max_chars, overlap)):
            enriched = f"角色/条目：{document.title}\n章节：{section}\n{content}"
            content_hash = hashlib.sha256(enriched.encode("utf-8")).hexdigest()
            stable_key = f"{document.entry_type}:{document.entry_id}:{section}:{index}:{content_hash}"
            chunk_id = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:40]
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    entry_id=document.entry_id,
                    entry_type=document.entry_type,
                    title=document.title,
                    section=section,
                    content=enriched,
                    content_hash=content_hash,
                    data_version=str(document.metadata.get("data_version", "")),
                    source_page=str(document.metadata.get("source_page", "")),
                    generated_at=str(document.metadata.get("generated_at", "")),
                )
            )
    return chunks


def chunk_documents(documents: list[KnowledgeDocument]) -> list[KnowledgeChunk]:
    return [chunk for document in documents for chunk in chunk_document(document)]
