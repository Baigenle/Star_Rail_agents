"""记忆层存储抽象 + PostgreSQL 默认实现。

规格 §8.3 要求存储可整体替换；本实现刻意用"查询后合并"而不是 PG 方言的
ON CONFLICT——同一个仓库类要在测试的内存 SQLite 上跑（tests 现行模式），
可移植性优先，个人量级下性能无差异。"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.memory.schemas import L0Profile, L15Fact, L1Profile, L2Memory
from app.models.memory import L15Fact as L15FactRow
from app.models.memory import L2MemoryRow
from app.models.memory import PlayerProfile


def _now() -> int:
    return int(time.time())


class MemoryRepository(ABC):
    @abstractmethod
    def get_l0(self, user_id: str) -> L0Profile: ...

    @abstractmethod
    def save_l0(self, user_id: str, profile: L0Profile) -> None: ...

    @abstractmethod
    def get_l1(self, user_id: str) -> L1Profile: ...

    @abstractmethod
    def save_l1(self, user_id: str, profile: L1Profile) -> None: ...

    @abstractmethod
    def upsert_fact(self, user_id: str, fact: L15Fact) -> None: ...

    @abstractmethod
    def get_facts(self, user_id: str) -> list[L15Fact]: ...

    @abstractmethod
    def add_l2(self, memory: L2Memory) -> str: ...

    @abstractmethod
    def all_active_l2(self, user_id: str) -> list[L2Memory]: ...

    @abstractmethod
    def update_l2_stats(self, memory_id: str) -> None: ...

    @abstractmethod
    def mark_superseded(self, memory_id: str) -> None: ...


def _row_to_l2(row: L2MemoryRow) -> L2Memory:
    return L2Memory(
        id=row.id,
        content=row.content,
        trigger_text=row.trigger_text or "",
        embedding=list(row.embedding) if row.embedding else None,
        created_at=int(row.created_at.timestamp()) if row.created_at else 0,
        last_accessed_at=int(row.last_accessed_at.timestamp()) if row.last_accessed_at else 0,
        access_count=row.access_count or 0,
        status=row.status or "active",
    )


class PgMemoryRepository(MemoryRepository):
    """默认实现：现有 SessionLocal（同步会话，与仓库既有 DB 访问模式一致）。"""

    def __init__(self, session_factory: Any = None, session: Any = None) -> None:
        self._session_factory = session_factory or SessionLocal
        self._bound_session = session

    @contextmanager
    def _session(self):
        """请求内复用外层 Session；独立任务仍由仓库自行创建和关闭 Session。"""
        if self._bound_session is not None:
            yield self._bound_session
            return
        with self._session_factory() as session:
            yield session

    def _persist(self, session) -> None:
        # 绑定 Session 的事务由 API 外层统一提交，避免一次请求被切成多个事务。
        if self._bound_session is not None:
            session.flush()
        else:
            session.commit()

    # -- L0/L1 ---------------------------------------------------------
    def _load_profile_row(self, session, user_id: str) -> PlayerProfile | None:
        return session.get(PlayerProfile, user_id)

    def get_l0(self, user_id: str) -> L0Profile:
        with self._session() as session:
            row = self._load_profile_row(session, user_id)
            return L0Profile.model_validate(row.l0 or {}) if row else L0Profile()

    def save_l0(self, user_id: str, profile: L0Profile) -> None:
        profile.updated_at = _now()
        with self._session() as session:
            row = self._load_profile_row(session, user_id)
            if row is None:
                row = PlayerProfile(user_id=user_id, l0={}, l1={})
                session.add(row)
            row.l0 = profile.model_dump()
            self._persist(session)

    def get_l1(self, user_id: str) -> L1Profile:
        with self._session() as session:
            row = self._load_profile_row(session, user_id)
            return L1Profile.model_validate(row.l1 or {}) if row else L1Profile()

    def save_l1(self, user_id: str, profile: L1Profile) -> None:
        profile.updated_at = _now()
        with self._session() as session:
            row = self._load_profile_row(session, user_id)
            if row is None:
                row = PlayerProfile(user_id=user_id, l0={}, l1={})
                session.add(row)
            row.l1 = profile.model_dump()
            self._persist(session)

    # -- L1.5 ----------------------------------------------------------
    def upsert_fact(self, user_id: str, fact: L15Fact) -> None:
        fact.updated_at = _now()  # 时间戳由仓库统一盖章，调用方传入值无效
        with self._session() as session:
            row = session.scalar(
                select(L15FactRow).where(
                    L15FactRow.user_id == user_id,
                    L15FactRow.fact_key == fact.fact_key,
                )
            )
            if row is None:
                row = L15FactRow(user_id=user_id, fact_key=fact.fact_key, fact_value="")
                session.add(row)
            row.fact_value = fact.fact_value
            self._persist(session)

    def get_facts(self, user_id: str) -> list[L15Fact]:
        with self._session() as session:
            rows = session.scalars(
                select(L15FactRow)
                .where(L15FactRow.user_id == user_id)
                .order_by(L15FactRow.updated_at.desc())
            ).all()
            return [
                L15Fact(
                    fact_key=row.fact_key,
                    fact_value=row.fact_value,
                    updated_at=int(row.updated_at.timestamp()) if row.updated_at else 0,
                )
                for row in rows
            ]

    # -- L2 ------------------------------------------------------------
    def add_l2(self, memory: L2Memory) -> str:
        memory_id = memory.id or f"l2-{_now()}-{id(memory):x}"
        with self._session() as session:
            session.add(
                L2MemoryRow(
                    id=memory_id,
                    user_id=memory.user_id,
                    content=memory.content,
                    trigger_text=memory.trigger_text,
                    embedding=memory.embedding,
                    access_count=memory.access_count,
                    status=memory.status,
                )
            )
            self._persist(session)
        return memory_id

    def all_active_l2(self, user_id: str) -> list[L2Memory]:
        with self._session() as session:
            rows = session.scalars(
                select(L2MemoryRow).where(
                    L2MemoryRow.user_id == user_id,
                    L2MemoryRow.status == "active",
                )
            ).all()
            return [_row_to_l2(row) for row in rows]

    def update_l2_stats(self, memory_id: str) -> None:
        with self._session() as session:
            row = session.get(L2MemoryRow, memory_id)
            if row is not None:
                row.access_count = (row.access_count or 0) + 1
                self._persist(session)

    def mark_superseded(self, memory_id: str) -> None:
        with self._session() as session:
            row = session.get(L2MemoryRow, memory_id)
            if row is not None:
                row.status = "superseded"
                self._persist(session)
