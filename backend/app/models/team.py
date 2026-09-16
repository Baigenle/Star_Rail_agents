"""用户保存队伍及其有序成员的数据模型。"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.user import utc_now


class UserTeam(Base):
    __tablename__ = "user_teams"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    members: Mapped[list["UserTeamMember"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
        order_by="UserTeamMember.position",
    )


class UserTeamMember(Base):
    __tablename__ = "user_team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "position"),
        UniqueConstraint("team_id", "character_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    team_id: Mapped[str] = mapped_column(
        ForeignKey("user_teams.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[str] = mapped_column(String(16), index=True)
    position: Mapped[int] = mapped_column(Integer)
    team: Mapped[UserTeam] = relationship(back_populates="members")
