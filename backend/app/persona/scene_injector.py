"""场景语气注入器：按用户输入匹配场景，输出该轮的语气注入段。"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.persona import SCENES_DIR, MATCH_THRESHOLD  # re-export 常量

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Scene:
    scene_id: str  # 文件名（稳定标识，如 lose_streak）
    name: str  # 中文标题（进 prompt 展示用）
    keywords: tuple[str, ...]
    serious: bool
    corpus: tuple[str, ...]
    body: str


FALLBACK_SCENE = "daily_chat"


@lru_cache(maxsize=1)
def load_scenes() -> dict[str, Scene]:
    scenes: dict[str, Scene] = {}
    for path in sorted(SCENES_DIR.glob("*.md")):
        scene = _parse(path)
        if scene is not None:
            scenes[path.stem] = scene
    if not scenes:
        logger.warning("场景库为空：%s", SCENES_DIR)
    return scenes


def _parse(path: Path) -> Scene | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("# "):
        return None
    name = lines[0][2:].strip()
    keywords: list[str] = []
    corpus: list[str] = []
    serious = False
    body_start = len(lines)
    for index in range(1, len(lines)):
        line = lines[index].strip()
        if not line:
            continue
        if line.startswith("- 触发语料:"):
            keywords = [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
        elif line.startswith("- 正经模式:"):
            serious = line.split(":", 1)[1].strip() == "是"
        elif line.startswith("- 代表语料:"):
            corpus = [item.strip() for item in line.split(":", 1)[1].split("/") if item.strip()]
        else:
            body_start = index
            break
    body = "\n".join(lines[body_start:]).strip()
    if not body:
        return None
    return Scene(
        scene_id=path.stem,
        name=name,
        keywords=tuple(keywords),
        serious=serious,
        corpus=tuple(corpus),
        body=body,
    )


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_match(query: str, candidates: list[Scene]) -> Scene | None:
    scored: list[tuple[int, int, Scene]] = []
    for scene in candidates:
        hits = sum(1 for keyword in scene.keywords if keyword in query)
        if hits:
            # 平局时正经场景优先（受挫语境下"先站队"比"嘴硬"安全）
            scored.append((hits, 1 if scene.serious else 0, scene))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored[0][2]


def match_scene(query: str, embedder=None) -> Scene | None:
    scenes = load_scenes()
    candidates = [scene for name, scene in scenes.items() if name != FALLBACK_SCENE]
    if not candidates:
        return None
    if embedder is not None:
        corpus_lines = [line for scene in candidates for line in scene.corpus]
        if corpus_lines:
            try:
                vectors = embedder.embed_documents([query, *corpus_lines])
                query_vector = vectors[0]
                best: Scene | None = None
                best_score = 0.0
                cursor = 1
                for scene in candidates:
                    if not scene.corpus:
                        continue
                    score = max(
                        _cosine(query_vector, vectors[cursor + offset])
                        for offset in range(len(scene.corpus))
                    )
                    if score > best_score:
                        best, best_score = scene, score
                    cursor += len(scene.corpus)
                if best is not None and best_score >= MATCH_THRESHOLD:
                    return best
                return None
            except Exception:  # noqa: BLE001 —— embedding 服务不可用 → 关键词降级
                logger.warning("场景向量匹配失败，降级关键词匹配")
    return _keyword_match(query, candidates)


def build_scene_injection(query: str, embedder=None) -> str:
    scene = match_scene(query, embedder)
    if scene is None:
        return ""  # 未命中场景：只依赖 system 静态段的通用语气规则（规格 Q6）
    return f"[当前场景：{scene.name}]\n{scene.body}"
