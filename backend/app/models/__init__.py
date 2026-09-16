"""集中导出 SQLAlchemy 模型，供 Alembic 自动发现全部表元数据。"""

from app.models.user import User, UserCharacter, UserCharacterProgress, UserMemory
from app.models.memory import L15Fact, L2MemoryRow, PlayerProfile, WorldbookStateRow
from app.models.custom_character import (
    CustomCharacter,
    CustomCharacterMessage,
    CustomCharacterSession,
    CustomCharacterVersion,
)
from app.models.team import UserTeam, UserTeamMember
from app.models.chat import ChatJob, ChatJobEvent, ChatMessage, Conversation
from app.models.planning import ProgressionPlan, WeeklyPlan
from app.models.activity import ActivityGuide
from app.models.moderation import ModerationAction

__all__ = [
    "User",
    "UserCharacter",
    "UserCharacterProgress",
    "UserMemory",
    "PlayerProfile",
    "L15Fact",
    "L2MemoryRow",
    "WorldbookStateRow",
    "CustomCharacter",
    "CustomCharacterVersion",
    "CustomCharacterSession",
    "CustomCharacterMessage",
    "UserTeam",
    "UserTeamMember",
    "Conversation",
    "ChatMessage",
    "ChatJob",
    "ChatJobEvent",
    "ProgressionPlan",
    "WeeklyPlan",
    "ActivityGuide",
    "ModerationAction",
]
