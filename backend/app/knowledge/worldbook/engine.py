"""DMAE 激活状态机（Cyrene v4.0 公式的 Python 移植，含适配版 §4 的 Rm clamp 修正）。

每一轮（用户消息 + 上轮回复）调一次 on_turn：
- 用户命中：Ru = Bu × (1 + γ·ln(1 + 用户沉默轮数))——久别重逢增益
- 模型复述：Rm = Bm × e^(−λ·US)，且 clamp Rm ≤ 本轮衰减量（模型话语不能抵消遗忘）
- 双双沉默：D = (α·US² + β·MS²) / √I —— 内在价值高 ⇒ 忘得慢
- 连带触发（One-Shot）：命中条目的连带词只注入、不改状态

状态按 conversation_id 隔离、PG 持久化（重启可恢复）；可移植合并写（SQLite 测试兼容）。"""

from __future__ import annotations

import math
import logging
from contextlib import contextmanager
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.knowledge.worldbook.injector import DmaeParams, EntryState, build_injection
from app.knowledge.worldbook.loader import WorldbookEntry, load_entries
from app.models.memory import WorldbookStateRow

logger = logging.getLogger(__name__)

__all__ = ["DmaeParams", "EntryState", "WorldbookEngine"]


class WorldbookEngine:
    def __init__(
        self,
        session_factory: Any = None,
        session: Any = None,
        params: DmaeParams | None = None,
        entries: list[WorldbookEntry] | None = None,
    ) -> None:
        self.entries = entries if entries is not None else load_entries()
        self.by_id = {entry.entry_id: entry for entry in self.entries}
        self.params = params or DmaeParams()
        self.session_factory = session_factory or SessionLocal
        self._bound_session = session

    @contextmanager
    def _session(self):
        if self._bound_session is not None:
            yield self._bound_session
            return
        with self.session_factory() as session:
            yield session

    # ------------------------------------------------------------------
    def on_turn_and_build(self, conversation_id: str | None, user_text: str, model_text: str = "") -> str:
        """每轮入口：更新状态 → 返回本轮注入块（无内容返回空串）。"""
        if not conversation_id or not self.entries:
            return ""
        states = self._load_states(conversation_id)
        cascade = self._on_turn(states, str(user_text or ""), str(model_text or ""))
        self._save_states(conversation_id, states)
        return build_injection(self.entries, states, cascade, self.params)

    def _on_turn(self, states: dict[str, EntryState], user_text: str, model_text: str) -> set[str]:
        params = self.params
        user_hits: set[str] = set()

        # 常驻条目不进状态机，但其命中可作为级联触发源（如"大黑塔"→人偶/本体条目）
        for entry in self.entries:
            if entry.permanent and entry.link_triggers:
                if any(keyword in user_text for keyword in entry.keywords):
                    user_hits.add(entry.entry_id)

        for entry in self.entries:
            if entry.permanent or not entry.keywords:
                continue
            state = states.setdefault(entry.entry_id, EntryState())
            user_silence_pre = state.user_silence
            model_silence_pre = state.model_silence

            user_hit = any(keyword in user_text for keyword in entry.keywords)
            model_hit = any(keyword in model_text for keyword in entry.keywords)

            if user_hit:
                state.activation = min(
                    params.max_score,
                    state.activation
                    + params.user_base * (1 + params.wake_gamma * math.log(1 + user_silence_pre)),
                )
                state.user_silence = 0
                user_hits.add(entry.entry_id)
            else:
                state.user_silence += 1

            would_decay = (
                params.decay_alpha * user_silence_pre**2
                + params.decay_beta * model_silence_pre**2
            ) / math.sqrt(entry.intrinsic)

            if model_hit and state.activation >= params.threshold:
                rm = params.model_base * math.exp(-params.wake_lambda * state.user_silence)
                state.activation = min(params.max_score, state.activation + min(rm, would_decay))
                state.model_silence = 0
            else:
                state.model_silence += 1

            if not user_hit and not model_hit:
                state.activation = max(0.0, state.activation - would_decay)

        return self._cascade(user_hits)

    def _cascade(self, user_hits: set[str]) -> set[str]:
        cascade: set[str] = set()
        for entry_id in user_hits:
            entry = self.by_id[entry_id]
            if not entry.link_triggers:
                continue
            for other in self.entries:
                if other.entry_id in user_hits or other.permanent:
                    continue
                haystack = " ".join(other.keywords) + " " + other.title
                if any(trigger in haystack for trigger in entry.link_triggers):
                    cascade.add(other.entry_id)
        return cascade

    # ------------------------------------------------------------------
    def _load_states(self, conversation_id: str) -> dict[str, EntryState]:
        with self._session() as session:
            rows = session.scalars(
                select(WorldbookStateRow).where(
                    WorldbookStateRow.conversation_id == conversation_id
                )
            ).all()
            return {
                row.entry_id: EntryState(
                    activation=row.activation,
                    user_silence=row.user_silence,
                    model_silence=row.model_silence,
                )
                for row in rows
            }

    def _save_states(self, conversation_id: str, states: dict[str, EntryState]) -> None:
        with self._session() as session:
            rows = {
                row.entry_id: row
                for row in session.scalars(
                    select(WorldbookStateRow).where(
                        WorldbookStateRow.conversation_id == conversation_id
                    )
                ).all()
            }
            for entry_id, state in states.items():
                row = rows.get(entry_id)
                if row is None:
                    session.add(
                        WorldbookStateRow(
                            conversation_id=conversation_id,
                            entry_id=entry_id,
                            activation=state.activation,
                            user_silence=state.user_silence,
                            model_silence=state.model_silence,
                        )
                    )
                else:
                    row.activation = state.activation
                    row.user_silence = state.user_silence
                    row.model_silence = state.model_silence
            if self._bound_session is not None:
                session.flush()
            else:
                session.commit()
