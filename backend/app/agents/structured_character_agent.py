from pathlib import Path

from app.agents.base import AgentContext, BaseAgent
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)
from app.schemas.catalog import CharacterDetail
from app.services.catalog_service import CatalogService


class StructuredCharacterAgent(BaseAgent):
    """直接读取角色结构化档案，避免精确查询被跨领域 RAG 干扰。"""

    name = "structured_character_agent"
    description = "负责角色身份、简介与技能档案的精确结构化查询"

    profile_tokens = (
        "是谁",
        "介绍",
        "简介",
        "什么角色",
        "基本信息",
        "角色信息",
    )
    skill_tokens = (
        "技能",
        "普攻",
        "战技",
        "终结技",
        "天赋",
        "秘技",
        "忆灵技",
        "欢愉技",
    )
    selectable_skill_types = (
        "普攻",
        "战技",
        "终结技",
        "天赋",
        "秘技",
        "忆灵技",
        "忆灵天赋",
        "欢愉技",
    )

    def __init__(self, docs_root: Path) -> None:
        self.catalog = CatalogService(docs_root.resolve())

    def supports(self, context: AgentContext) -> bool:
        return (
            context.intent == "knowledge_qa"
            and self._target_character_id(context) is not None
            and any(
                token in context.message
                for token in self.profile_tokens + self.skill_tokens
            )
        )

    async def run(self, context: AgentContext) -> AIResponse:
        character_id = self._target_character_id(context)
        character = self.catalog.get_character(character_id or "")
        if not character:
            return self._no_record_response()
        if any(token in context.message for token in self.skill_tokens):
            return await self._skill_response(context, character)
        return await self._profile_response(context, character)

    @staticmethod
    def _target_character_id(context: AgentContext) -> str | None:
        mentioned = context.entities.get("mentioned_characters", [])
        if not isinstance(mentioned, list) or len(mentioned) != 1:
            return None
        item = mentioned[0]
        if not isinstance(item, dict):
            return None
        character_id = str(item.get("character_id") or "").strip()
        return character_id or None

    async def _profile_response(
        self,
        context: AgentContext,
        character: CharacterDetail,
    ) -> AIResponse:
        statement = (
            f"{character.name}是{character.rarity}星{character.element}属性"
            f"{character.path}命途角色。{character.description.strip()}"
        )
        await context.emit_event(
            "retrieval.completed",
            "结构化角色档案读取完成",
            agent=self.name,
            detail=f"已读取 {character.name} 的身份与简介。",
            event_status="completed",
            payload={"evidence_count": 1},
            progress={
                "stage": "validation",
                "percent": 68,
                "agent": self.name,
            },
        )
        citation = Citation(
            id="C1",
            title=f"{character.name} · 角色档案",
            source=character.source_url,
            excerpt=statement,
            document_id=character.id,
            game_version=character.data_version,
            relevance_score=1.0,
            image_url=character.image_url,
            entity_url=f"/characters/{character.id}",
        )
        return AIResponse(
            agent=self.name,
            answer=f"{statement} [C1]",
            claims=[
                Claim(
                    statement=statement,
                    confidence=1.0,
                    citation_ids=["C1"],
                )
            ],
            citations=[citation],
            validation=ValidationReport(
                status="verified",
                method="structured_character_profile",
                evidence_count=1,
                notes=["身份、属性、命途和简介直接读取角色档案。"],
            ),
            filtering=FilteringReport(
                passed=True,
                removed_claims=0,
                rules=["仅回答目标角色的身份与简介字段。"],
            ),
            query_steps=[
                QueryStep(
                    id="structured_character_profile",
                    name="结构化角色简介查询",
                    status="completed",
                    detail=(
                        f"读取 {character.name} 的身份、属性、命途与简介，"
                        "跳过跨知识域向量检索。"
                    ),
                )
            ],
        )

    async def _skill_response(
        self,
        context: AgentContext,
        character: CharacterDetail,
    ) -> AIResponse:
        requested_types = {
            skill_type
            for skill_type in self.selectable_skill_types
            if skill_type in context.message
        }
        skills = [
            skill
            for skill in character.skills
            if not requested_types or skill.type in requested_types
        ]
        if not skills:
            return self._no_record_response()
        await context.emit_event(
            "retrieval.started",
            "正在读取结构化角色技能档案",
            agent=self.name,
            detail=f"目标角色：{character.name}。",
            progress={
                "stage": "retrieval",
                "percent": 48,
                "agent": self.name,
            },
        )
        citations: list[Citation] = []
        claims: list[Claim] = []
        lines: list[str] = []
        for index, skill in enumerate(skills, start=1):
            citation_id = f"C{index}"
            skill_type = skill.type or "技能"
            statement = (
                f"【{skill_type}】{skill.name}：{skill.description.strip()}"
            )
            citations.append(
                Citation(
                    id=citation_id,
                    title=f"{character.name} · {skill_type} · {skill.name}",
                    source=character.source_url,
                    excerpt=statement,
                    document_id=character.id,
                    game_version=character.data_version,
                    relevance_score=1.0,
                    image_url=skill.image_url or character.image_url,
                    entity_url=f"/characters/{character.id}",
                )
            )
            claims.append(
                Claim(
                    statement=statement,
                    confidence=1.0,
                    citation_ids=[citation_id],
                )
            )
            lines.append(
                f"- **{skill_type}｜{skill.name}**："
                f"{skill.description.strip()} [{citation_id}]"
            )
        await context.emit_event(
            "retrieval.completed",
            "结构化角色技能档案读取完成",
            agent=self.name,
            detail=f"已读取 {len(skills)} 项技能。",
            event_status="completed",
            payload={"evidence_count": len(citations)},
            progress={
                "stage": "validation",
                "percent": 68,
                "agent": self.name,
            },
        )
        return AIResponse(
            agent=self.name,
            answer=f"{character.name}的技能档案如下：\n\n" + "\n".join(lines),
            claims=claims,
            citations=citations,
            validation=ValidationReport(
                status="verified",
                method="structured_character_skill_catalog",
                evidence_count=len(citations),
                notes=["技能名称、类型与描述直接读取结构化角色档案。"],
            ),
            filtering=FilteringReport(
                passed=True,
                removed_claims=0,
                rules=[
                    "仅保留目标角色的结构化技能字段。",
                    "不向用户暴露内部 ID、能量字段或解析表格。",
                ],
            ),
            query_steps=[
                QueryStep(
                    id="structured_character_skills",
                    name="结构化角色技能查询",
                    status="completed",
                    detail=(
                        f"读取 {character.name} 的 {len(skills)} 项技能，"
                        "跳过跨知识域向量检索。"
                    ),
                )
            ],
        )

    def _no_record_response(self) -> AIResponse:
        return AIResponse(
            agent=self.name,
            answer="角色档案中没有足够的结构化资料回答这个问题。",
            claims=[],
            citations=[],
            validation=ValidationReport(
                status="unverified",
                method="structured_character_catalog",
                evidence_count=0,
                notes=["目标角色或对应技能档案不存在。"],
            ),
            filtering=FilteringReport(
                passed=False,
                removed_claims=0,
                rules=["结构化档案缺失时不补造内容。"],
            ),
            query_steps=[],
        )
