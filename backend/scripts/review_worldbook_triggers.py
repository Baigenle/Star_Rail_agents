"""Worldbook 触发词误命中审查（设计 §4.4）。

用法（backend 目录）：
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe scripts/review_worldbook_triggers.py \
        --corpus ../docs/design/worldbook/corpus_samples.md

输出：每条语料命中的条目（触发词来源标注）；命中 0 条的语料（漏报候选）与
命中 ≥2 条的语料（误报候选）单独汇总，供人工判读后改触发词。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from app.knowledge.worldbook.loader import load_entries


def load_corpus(path: Path) -> list[tuple[int, str]]:
    messages: list[tuple[int, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(\d+)\.\s+(.*)$", raw.strip())
        if match:
            messages.append((int(match.group(1)), match.group(2)))
    return messages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="../docs/design/worldbook/corpus_samples.md")
    args = parser.parse_args()

    entries = load_entries()
    corpus = load_corpus(Path(args.corpus))
    print(f"条目 {len(entries)} 条 | 语料 {len(corpus)} 条\n")

    zero_hits: list[str] = []
    multi_hits: list[str] = []
    for number, text in corpus:
        hits = []
        for entry in entries:
            matched = [k for k in entry.keywords if k in text]
            if matched:
                hits.append((entry.title, matched))
        if not hits:
            zero_hits.append(text)
        elif len(hits) >= 2:
            multi_hits.append(text)
        summary = " | ".join(f"{title}←{matched}" for title, matched in hits)
        print(f"{number:>3}. {text[:28]:<30} → {summary or '（无命中）'}")

    print(f"\n== 无命中（漏报候选，{len(zero_hits)} 条）==")
    for text in zero_hits:
        print(f"  - {text}")
    print(f"\n== 多重命中（误报候选，{len(multi_hits)} 条，需人工判读）==")
    for text in multi_hits:
        print(f"  - {text}")


if __name__ == "__main__":
    main()
