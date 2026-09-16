"""分层记忆层（规格 §8）：L0/L1 玩家画像、L1.5 事实缓存、L2 情景记忆。

设计对齐 WORLDBOOK_DESIGN_ADAPTED.md / 工作簿 Q6 决议：
- 存储用现有 PostgreSQL + SQLAlchemy（不用 SQLite）；Repository 接口保持可换。
- L0/L1 以 JSONB 存储整份画像（结构由 memory.schemas 的 pydantic 模型校验）。
- L2 embedding 存 JSONB 数组，检索时内存算余弦（个人量级 <1 万条）。
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy import JSON

from app.db.session import Base
from app.models.user import utc_now


class PlayerProfile(Base):
    """L0（永久画像）+ L1（近期状态），每用户一行；结构见 memory.schemas。"""

    __tablename__ = "player_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    l0: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    l1: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class WorldbookStateRow(Base):
    """Worldbook 激活状态：按 (conversation_id, entry_id) 隔离与持久化。"""

    __tablename__ = "worldbook_states"
    __table_args__ = (
        UniqueConstraint("conversation_id", "entry_id", name="uq_worldbook_states_conv_entry"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    entry_id: Mapped[str] = mapped_column(String(160))
    activation: Mapped[float] = mapped_column(default=0.0)
    user_silence: Mapped[int] = mapped_column(Integer, default=0)
    model_silence: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class L15Fact(Base):
    """L1.5 游戏事实缓存：按 user_id + fact_key 唯一（档案/材料查询顺手写入）。"""

    __tablename__ = "l15_facts"
    __table_args__ = (UniqueConstraint("user_id", "fact_key"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    fact_key: Mapped[str] = mapped_column(String(64))
    fact_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class L2MemoryRow(Base):
    """L2 情景记忆：一次有记忆点的对话/事件，embedding 供语义召回。"""

    __tablename__ = "l2_memories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    trigger_text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
