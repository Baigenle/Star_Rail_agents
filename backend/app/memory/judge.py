"""MemoryJudge（规格 §8.4）：从最近 8 轮对话提取值得长期记住的玩家信息。

触发（问答卷 Q9 定调，拉取式实现）：
- L1.round_count 距上次提取 ≥ 6 轮；或
- 会话闲置 > 30 分钟且有 ≥2 轮未提取的新对话
不实现推式定时器：容器重启丢一次兜底触发无实际损失（记忆晚一轮提取无害）。

写入策略：
- L0/L1 按字段合并：字段为空 → 任何 ≥MIN_CONFIDENCE 的候选可写入；
  已有值 → 仅更高置信度才覆盖（置信度存 profile.field_confidence）
- L2 直接新增（embedding 由注入器补齐；去重在召回侧按内容重合度处理）
- 防护字段（round_count/updated_at/field_confidence/last_judged_round）禁止写入
- 任何异常只记日志，绝不影响主回复（规格禁令）"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from app.llm.base import LLMMessage, LLMProvider
from app.memory.repository import MemoryRepository
from app.memory.schemas import L2Memory

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.6
PROTECTED_FIELDS = {"round_count", "updated_at", "field_confidence", "last_judged_round"}

JUDGE_PROMPT = """你是玩家记忆提取器。从下面的对话里提取值得长期记住的玩家信息，输出严格 JSON 数组。

字段说明（只允许这些 layer/field 组合）：
- L0.main_role：主玩命途/定位（例：「主玩毁灭」）——只有用户明确说出才记
- L0.main_characters：主练角色（例：「流萤、景元」）
- L0.call_name：用户希望被怎么称呼
- L0.skill_note：水平自述（例：「手残党」）——照抄用户自述，不评价
- L0.preferences：交互偏好（例：「别替我排体力」「别玩梗」）
- L0.permanent_note：其他稳定事实
- L1.season_goal：版本目标（例：「深渊满星」）
- L1.current_focus：正在练的/卡关的（例：「卡在忘却之庭第10层」）
- L1.recent_mood：近期情绪基调
- L2（无 field）：一次有记忆点的事件，content 写成一句完整的话

判定标准：只记稳定事实、偏好、目标、有记忆点的事件；一次性闲聊、临时情绪不记；
把握不大时宁可不记。每个候选给 confidence（0-1）和 trigger_text（什么话题该召回）。

输出格式（数组，可为空数组）：
[{"layer":"L0","field":"main_role","content":"主玩毁灭","confidence":0.9,"trigger_text":"命途 主玩"}]
不要输出数组以外的任何文字。"""


class MemoryJudge:
    ROUND_THRESHOLD = 6
    IDLE_GAP_SECONDS = 30 * 60
    CATCH_UP_MIN_ROUNDS = 2

    def __init__(
        self,
        repository: MemoryRepository,
        llm: LLMProvider | None,
        embedder=None,
    ) -> None:
        self.repository = repository
        self.llm = llm
        self.embedder = embedder

    # ------------------------------------------------------------------
    def spawn_if_due(self, user_id: str, *, idle_gap_seconds: float = 0.0) -> asyncio.Task | None:
        """每轮回复后调用；达到触发条件则后台提取，返回任务句柄（否则 None）。"""
        if self.llm is None:
            return None
        l1 = self.repository.get_l1(user_id)
        unjudged = l1.round_count - l1.last_judged_round
        due = (
            unjudged >= self.ROUND_THRESHOLD
            or (
                idle_gap_seconds >= self.IDLE_GAP_SECONDS
                and unjudged >= self.CATCH_UP_MIN_ROUNDS
            )
        )
        if not due:
            return None
        return asyncio.create_task(self._safe_extract(user_id, l1.round_count))

    async def _safe_extract(self, user_id: str, current_round: int) -> None:
        try:
            await self.extract_and_write(user_id, current_round)
        except Exception:  # noqa: BLE001 —— 副作用失败只记日志（规格禁令）
            logger.exception("MemoryJudge 提取失败（user_id=%s）", user_id)

    async def extract_and_write(self, user_id: str, current_round: int, history: list[dict[str, str]] | None = None) -> int:
        """执行一次提取并写入；返回写入候选数（测试用）。"""
        transcript = self._transcript(history) if history else await self._recent_transcript(user_id)
        raw = await self.llm.complete(
            [
                LLMMessage(role="system", content=JUDGE_PROMPT),
                LLMMessage(role="user", content=transcript),
            ]
        )
        candidates = self._parse_candidates(raw)
        written = self._write(user_id, candidates)
        l1 = self.repository.get_l1(user_id)
        l1.last_judged_round = max(l1.last_judged_round, current_round)
        self.repository.save_l1(user_id, l1)
        return written

    # ------------------------------------------------------------------
    @staticmethod
    def _transcript(history: list[dict[str, str]]) -> str:
        """取最近 8 轮（16 条）user/assistant 消息。"""
        pairs = [
            item
            for item in history
            if str(item.get("role")) in {"user", "assistant"} and str(item.get("content") or "").strip()
        ][-16:]
        return "\n".join(
            f"{'用户' if item['role'] == 'user' else '助手'}：{str(item.get('content'))[:200]}"
            for item in pairs
        )

    async def _recent_transcript(self, user_id: str) -> str:
        from sqlalchemy import select

        from app.db.session import SessionLocal
        from app.models.chat import ChatMessage

        def _load() -> list[dict[str, str]]:
            with SessionLocal() as session:
                rows = session.scalars(
                    select(ChatMessage)
                    .join(ChatMessage.conversation)
                    .where(
                        ChatMessage.conversation.has(user_id=user_id)  # type: ignore[attr-defined]
                    )
                    .order_by(ChatMessage.created_at.desc())
                    .limit(16)
                ).all()
                return [
                    {"role": row.role, "content": row.content}
                    for row in reversed(rows)
                ]

        history = await asyncio.to_thread(_load)
        return self._transcript(history)

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_candidates(raw: str) -> list[dict]:
        """容错解析：优先整体解析数组；失败则逐对象打捞（规格 §13.1 截断容错）。"""
        text = str(raw or "").strip()
        start, end = text.find("["), text.rfind("]")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
            except json.JSONDecodeError:
                pass
        salvaged: list[dict] = []
        for match in re.finditer(r"\{[^{}]*\}", text):
            try:
                item = json.loads(match.group(0))
                if isinstance(item, dict):
                    salvaged.append(item)
            except json.JSONDecodeError:
                continue
        return salvaged

    def _write(self, user_id: str, candidates: list[dict]) -> int:
        written = 0
        l0 = self.repository.get_l0(user_id)
        l1 = self.repository.get_l1(user_id)
        for candidate in candidates:
            layer = str(candidate.get("layer") or "")
            field = str(candidate.get("field") or "")
            content = str(candidate.get("content") or "").strip()
            try:
                confidence = float(candidate.get("confidence") or 0.0)
            except (TypeError, ValueError):
                continue
            if not content or confidence < MIN_CONFIDENCE:
                continue
            if layer == "L2":
                self.repository.add_l2(
                    L2Memory(
                        user_id=user_id,
                        content=content,
                        trigger_text=str(candidate.get("trigger_text") or ""),
                    )
                )
                written += 1
                continue
            if layer not in {"L0", "L1"} or field in PROTECTED_FIELDS:
                continue
            target = l0 if layer == "L0" else l1
            if field not in type(target).model_fields:
                continue
            current_conf = target.field_confidence.get(field, 0.0)
            if getattr(target, field) and confidence <= current_conf:
                continue  # 已有值且新候选置信度不高 → 保留现值
            setattr(target, field, content)
            target.field_confidence[field] = confidence
            written += 1
        if written:
            self.repository.save_l0(user_id, l0)
            self.repository.save_l1(user_id, l1)
        return written
