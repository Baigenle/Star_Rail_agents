"""Worldbook 条目加载器（格式 v1.1，修正 Cyrene 的两个坑）。

1. 标题行即触发词——不会出现"无触发词死知识"
2. 元数据块显式终结：元数据只在标题后的连续 `- ` 行中解析，遇到正文行即止
   （此后正文可随便用列表）——修复"正文以 `- ` 开头被当元数据吞掉"的 bug

校验（设计 §5.3）：每条必须有【事实】；触发词 ≥2 字；跨条目重复触发词告警去重。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

ENTRIES_DIR = Path(__file__).resolve().parent / "entries"


@dataclass(frozen=True)
class WorldbookEntry:
    entry_id: str  # f"{文件名}:{标题}"（标题变更即重置状态，可接受）
    title: str
    keywords: tuple[str, ...]
    permanent: bool
    intrinsic: float  # 内在价值：越高忘得越慢
    priority: float  # 激活分相同时的排序 tiebreaker
    link_triggers: tuple[str, ...]
    content: str  # 【事实】起的完整正文（含【写法】【口径】）


def _split_list(raw: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,，/]", raw) if item.strip()]


def _parse_file(path: Path) -> list[WorldbookEntry]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header_indices = [
        index for index, line in enumerate(lines) if line.strip().startswith("## ")
    ]
    entries: list[WorldbookEntry] = []
    for position, start in enumerate(header_indices):
        end = header_indices[position + 1] if position + 1 < len(header_indices) else len(lines)
        title = lines[start][3:].strip()
        keywords: list[str] = [title]
        permanent = False
        intrinsic = 70.0
        priority = 100.0
        link_triggers: list[str] = []
        index = start + 1
        # 元数据区：标题后连续的 "- key: value" 行；首个非元数据行即正文开始（格式 v1.1 规则 2）
        while index < end:
            stripped = lines[index].strip()
            if not stripped.startswith("- "):
                break
            key, _, value = stripped[2:].partition(":")
            key = key.strip()
            value = value.strip()
            if key == "触发词":
                keywords.extend(_split_list(value))
            elif key == "常驻":
                permanent = value == "是"
            elif key == "内在价值":
                try:
                    intrinsic = float(value)
                except ValueError:
                    pass
            elif key == "优先级":
                try:
                    priority = float(value)
                except ValueError:
                    pass
            elif key == "连带触发词":
                if value and value != "无":
                    link_triggers = _split_list(value)
            index += 1
        content = "\n".join(lines[index:end]).strip()
        if not content:
            logger.warning("Worldbook 条目无正文，跳过：%s / %s", path.stem, title)
            continue
        entries.append(
            WorldbookEntry(
                entry_id=f"{path.stem}:{title}",
                title=title,
                keywords=tuple(dict.fromkeys(k for k in keywords if len(k) >= 2)),
                permanent=permanent,
                intrinsic=max(intrinsic, 10.0),
                priority=priority,
                link_triggers=tuple(link_triggers),
                content=content,
            )
        )
    return entries


def load_entries(directory: Path | None = None) -> list[WorldbookEntry]:
    directory = directory or ENTRIES_DIR
    entries: list[WorldbookEntry] = []
    full_set_owners: dict[frozenset, str] = {}
    for path in sorted(directory.glob("*.md")):
        file_entries = _parse_file(path)
        for entry in file_entries:
            if "【事实】" not in entry.content:
                logger.warning("Worldbook 条目缺少【事实】：%s", entry.entry_id)
                continue
            # 去重按"完整触发词集合"判定（设计 §5.3 的本意是防整组重复的复制粘贴条目）；
            # 部分共享关键词是正常的（如"模拟宇宙"同属项目组与世界观条目），保留不剥
            key_set = frozenset(entry.keywords)
            owner = full_set_owners.get(key_set)
            if owner:
                logger.warning(
                    "触发词集合与 %s 完全重复，跳过 %s", owner, entry.entry_id
                )
                continue
            full_set_owners[key_set] = entry.entry_id
            entries.append(entry)
    return entries
