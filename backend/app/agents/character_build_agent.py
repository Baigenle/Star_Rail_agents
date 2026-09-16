import re
from pathlib import Path

from app.agents.base import AgentContext, BaseAgent
from app.agents.rag_agent import RAGAgent
from app.schemas.planning import CharacterPlanInput
from app.schemas.progression import SkillRange
from app.services.catalog_service import CatalogService
from app.services.planning_service import PlanningService


class CharacterBuildAgent(BaseAgent):
    name = "character_build_agent"
    description = "结合用户练度计算角色材料与已验证构筑建议"

    def __init__(self, docs_root: Path, rag_agent: RAGAgent) -> None:
        self.catalog = CatalogService(docs_root)
        self.planning = PlanningService(docs_root)
        self.rag_agent = rag_agent

    async def run(self, context: AgentContext):
        character = self._character(context.message)
        if character is None:
            fallback = await self.rag_agent.run(context)
            return fallback.model_copy(update={"agent": self.name})

        progress_by_id = {
            item["character_id"]: item
            for item in context.entities.get("character_progress", [])
        }
        progress = progress_by_id.get(character.id, {})
        from_level = int(progress.get("current_level", 1))
        to_level = int(progress.get("target_level", 80))
        tracks = self.planning.progression.track_definitions(character.id)
        current_skills = progress.get("current_skills", {})
        target_skills = progress.get("target_skills", {})
        skill_ranges = {
            key: SkillRange(
                from_level=int(current_skills.get(key, 1)),
                to_level=int(target_skills.get(key, definition["max_level"])),
            )
            for key, definition in tracks.items()
        }
        result = self.planning.calculate(
            [
                CharacterPlanInput(
                    character_id=character.id,
                    from_level=from_level,
                    to_level=to_level,
                    skill_ranges=skill_ranges,
                )
            ]
        )
        response = result.response
        recommendation = result.recommendations.get(character.id)
        citation = next(
            (
                item
                for item in response.citations
                if item.document_id == character.id
            ),
            None,
        )
        citation_id = citation.id if citation else "C1"

        def names(items: list[dict]) -> str:
            return "、".join(str(item.get("name") or "未命名") for item in items)

        lightcones = names(recommendation.lightcones) if recommendation else ""
        tunnel_relics = names(recommendation.tunnel_relics) if recommendation else ""
        planar_relics = names(recommendation.planar_relics) if recommendation else ""
        skill_priority = (
            " → ".join(recommendation.skill_priority) if recommendation else ""
        )
        plan_intro = (
            f"当前没有保存{character.name}的练度，先按 Lv.1→Lv.80 估算。"
            if not progress
            else f"按你保存的练度，从 Lv.{from_level} 规划到 Lv.{to_level}。"
        )
        sections = [
            f"{character.name}养成方案：{plan_intro} [{citation_id}]",
            (
                f"技能清单（档案顺序）：{skill_priority or '现有资料不足'}；"
                f"现有资料未给出可信优先级，不把该顺序当作强度排名。 "
                f"[{citation_id}]"
            ),
            f"光锥推荐：{lightcones or '现有资料不足'} [{citation_id}]",
            f"隧洞遗器：{tunnel_relics or '现有资料不足'} [{citation_id}]",
            f"位面饰品：{planar_relics or '现有资料不足'} [{citation_id}]",
            (
                f"晋阶与技能目标共涉及 {len(result.materials)} 类材料；"
                "进入养成规划页可以调整等级和每项技能的 From/To。 "
                f"[{citation_id}]"
            ),
        ]
        return response.model_copy(
            update={
                "agent": self.name,
                "answer": "\n".join(sections),
            }
        )

    def _character(self, message: str):
        normalized = self._normalize(message)
        matches = [
            item
            for item in self.catalog.list_characters()
            if self._normalize(item.name) in normalized
        ]
        if not matches:
            return None
        selected = max(matches, key=lambda item: len(self._normalize(item.name)))
        return self.catalog.get_character(selected.id)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", value).lower()
