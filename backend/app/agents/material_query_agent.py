import re
from pathlib import Path

from app.agents.base import AgentContext, BaseAgent
from app.agents.rag_agent import RAGAgent
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)
from app.services.catalog_service import CatalogService
from app.services.progression_service import ProgressionService


class MaterialQueryAgent(BaseAgent):
    name = "material_query_agent"
    description = "优先读取结构化角色、光锥、遗器与物品档案的材料查询 Agent"

    def __init__(self, docs_root: Path, rag_agent: RAGAgent) -> None:
        self.catalog = CatalogService(docs_root)
        self.progression = ProgressionService(docs_root)
        self.rag_agent = rag_agent

    async def run(self, context: AgentContext) -> AIResponse:
        character = self._character(context.message)
        if character:
            return self._character_materials(character, context.message)
        lightcone = self._lightcone(context.message)
        if lightcone:
            return self._lightcone_materials(lightcone)
        relic = self._relic(context.message)
        if relic:
            return self._relic_source(relic)
        item = self._item(context.message)
        if item:
            return self._item_source(item)

        fallback = await self.rag_agent.run(context)
        return fallback.model_copy(
            update={
                "agent": self.name,
                "query_steps": [
                    QueryStep(
                        id="structured_material_lookup",
                        name="结构化材料查询",
                        status="fallback",
                        detail="未识别到唯一实体，已转交 RAG 补充检索。",
                        duration_ms=0,
                    ),
                    *fallback.query_steps,
                ],
            }
        )

    def _character_materials(self, character, question: str) -> AIResponse:
        material_types = {
            "CommonMonsterDrop",
            "AvatarRank",
            "TracePath",
            "WeeklyMonsterDrop",
        }
        materials = [
            item
            for item in character.related_items
            if item.type in material_types or item.id in {"2", "241"}
        ]
        existing_ids = {item.id for item in materials}
        for item_id in self.progression.bindings().get(character.id, {}).values():
            if item_id in existing_ids:
                continue
            item = self.catalog.get_item(item_id)
            if item is not None:
                materials.append(item)
                existing_ids.add(item_id)
        citations = [
            Citation(
                id=f"C{index}",
                title=item.name,
                source=character.source_url,
                excerpt=f"{character.name}关联材料：{item.name}；类别：{item.type}。",
                document_id=item.id,
                entity_url=f"/items/{item.id}",
                image_url=item.image_url,
            )
            for index, item in enumerate(materials, start=1)
        ]
        claims = [
            Claim(
                statement=f"{character.name}的已对齐材料包括：{item.name}。",
                confidence=0.98,
                citation_ids=[f"C{index}"],
            )
            for index, item in enumerate(materials, start=1)
        ]
        answer = "；".join(
            f"{item.name} [C{index}]"
            for index, item in enumerate(materials, start=1)
        )
        warnings = []
        if any(keyword in question for keyword in ("开放时间", "星期几", "周几")):
            warnings.append("当前结构化材料档案缺少可靠副本开放时间，未生成时间结论。")
        return AIResponse(
            agent=self.name,
            answer=f"{character.name}的结构化材料档案如下：{answer}。",
            claims=claims,
            citations=citations,
            validation=ValidationReport(
                status="verified" if claims else "unverified",
                method="structured_character_material_binding",
                evidence_count=len(citations),
                notes=["材料 ID 已通过角色关联档案映射到物品库。"],
            ),
            filtering=FilteringReport(
                passed=bool(claims),
                removed_claims=0,
                rules=["只返回结构化角色关联材料。", "没有开放时间数据时不推测。"],
                warnings=warnings,
            ),
            query_steps=[
                QueryStep(
                    id="structured_material_lookup",
                    name="结构化材料查询 Agent",
                    status="completed" if claims else "fallback",
                    detail=f"命中角色 {character.name}，返回 {len(claims)} 项已对齐材料。",
                    duration_ms=0,
                )
            ],
        )

    def _lightcone_materials(self, lightcone) -> AIResponse:
        totals: dict[str, dict] = {}
        for materials in lightcone.promotion_materials.values():
            for material in materials:
                item = totals.setdefault(
                    material.id,
                    {
                        "name": material.name,
                        "quantity": 0,
                        "image_url": material.image_url,
                    },
                )
                item["quantity"] += material.quantity
        citations = [
            Citation(
                id=f"C{index}",
                title=item["name"],
                source=lightcone.source_url or f"docs/lightcones/{lightcone.id}",
                excerpt=f"{lightcone.name}晋阶材料汇总：{item['name']} ×{item['quantity']}。",
                document_id=item_id,
                entity_url=f"/items/{item_id}",
                image_url=item["image_url"],
            )
            for index, (item_id, item) in enumerate(totals.items(), start=1)
        ]
        claims = [
            Claim(
                statement=citation.excerpt,
                confidence=0.98,
                citation_ids=[citation.id],
            )
            for citation in citations
        ]
        return self._structured_response(
            title=f"{lightcone.name}晋阶材料",
            claims=claims,
            citations=citations,
        )

    def _relic_source(self, relic) -> AIResponse:
        citation = Citation(
            id="C1",
            title=relic.name,
            source=relic.source_url or f"docs/relics/{relic.id}",
            excerpt=relic.acquisition or "当前遗器档案未记录可靠获取来源。",
            document_id=relic.id,
            entity_url=f"/relics/{relic.id}",
            image_url=relic.image_url,
        )
        has_source = bool(relic.acquisition)
        return AIResponse(
            agent=self.name,
            answer=(
                f"{relic.name}的获取来源：{relic.acquisition} [C1]"
                if has_source
                else f"{relic.name}档案目前没有可靠获取来源记录。"
            ),
            claims=(
                [
                    Claim(
                        statement=f"{relic.name}可从{relic.acquisition}获取。",
                        confidence=0.9,
                        citation_ids=["C1"],
                    )
                ]
                if has_source
                else []
            ),
            citations=[citation],
            validation=ValidationReport(
                status="verified" if has_source else "unverified",
                method="structured_relic_acquisition",
                evidence_count=1 if has_source else 0,
                notes=["优先使用遗器结构化获取来源字段。"],
            ),
            filtering=FilteringReport(
                passed=has_source,
                removed_claims=0,
                rules=["不根据遗器名称猜测掉落副本。"],
                warnings=[] if has_source else ["缺少获取来源。"],
            ),
            query_steps=[
                QueryStep(
                    id="structured_material_lookup",
                    name="结构化遗器来源查询",
                    status="completed" if has_source else "fallback",
                    detail=f"已检查遗器 {relic.name} 的获取来源字段。",
                    duration_ms=0,
                )
            ],
        )

    def _item_source(self, item) -> AIResponse:
        sources = "；".join(item.sources)
        citation = Citation(
            id="C1",
            title=item.name,
            source=item.source_url or f"docs/items/{item.id}",
            excerpt=sources or item.description or "当前物品档案没有可靠掉落来源。",
            document_id=item.id,
            entity_url=f"/items/{item.id}",
            image_url=item.image_url,
        )
        has_source = bool(item.sources)
        return AIResponse(
            agent=self.name,
            answer=(
                f"{item.name}的已记录来源：{sources} [C1]"
                if has_source
                else f"{item.name}当前没有可靠掉落来源记录。"
            ),
            claims=(
                [
                    Claim(
                        statement=f"{item.name}的来源包括：{sources}。",
                        confidence=0.95,
                        citation_ids=["C1"],
                    )
                ]
                if has_source
                else []
            ),
            citations=[citation],
            validation=ValidationReport(
                status="verified" if has_source else "unverified",
                method="structured_item_sources",
                evidence_count=1 if has_source else 0,
                notes=["来源直接读取物品结构化档案。"],
            ),
            filtering=FilteringReport(
                passed=has_source,
                removed_claims=0,
                rules=["没有来源字段时不补全掉落位置。"],
                warnings=[] if has_source else ["缺少物品来源数据。"],
            ),
            query_steps=[
                QueryStep(
                    id="structured_material_lookup",
                    name="结构化物品来源查询",
                    status="completed" if has_source else "fallback",
                    detail=f"已检查物品 {item.name} 的来源字段。",
                    duration_ms=0,
                )
            ],
        )

    def _structured_response(
        self, *, title: str, claims: list[Claim], citations: list[Citation]
    ) -> AIResponse:
        return AIResponse(
            agent=self.name,
            answer="；".join(
                f"{claim.statement} [{claim.citation_ids[0]}]" for claim in claims
            ),
            claims=claims,
            citations=citations,
            validation=ValidationReport(
                status="verified" if claims else "unverified",
                method="structured_catalog_lookup",
                evidence_count=len(citations),
                notes=[f"{title}已通过结构化档案核对。"],
            ),
            filtering=FilteringReport(
                passed=bool(claims),
                removed_claims=0,
                rules=["只保留能映射到物品库的材料。"],
            ),
            query_steps=[
                QueryStep(
                    id="structured_material_lookup",
                    name="结构化材料查询 Agent",
                    status="completed" if claims else "fallback",
                    detail=f"{title}命中 {len(claims)} 项记录。",
                    duration_ms=0,
                )
            ],
        )

    def _character(self, question: str):
        return self._match(
            question,
            self.catalog.list_characters(),
            self.catalog.get_character,
        )

    def _lightcone(self, question: str):
        if "光锥" not in question:
            return None
        return self._match(
            question,
            self.catalog.list_entities("lightcones"),
            self.catalog.get_lightcone,
        )

    def _relic(self, question: str):
        if "遗器" not in question and "饰品" not in question:
            return None
        return self._match(
            question,
            self.catalog.list_entities("relics"),
            self.catalog.get_relic,
        )

    def _item(self, question: str):
        return self._match(
            question,
            self.catalog.list_items(limit=2000),
            self.catalog.get_item,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", value).lower()

    @classmethod
    def _match(cls, question: str, entries, getter):
        normalized = cls._normalize(question)
        matches = [
            entry
            for entry in entries
            if cls._normalize(entry.name) in normalized
        ]
        if not matches:
            return None
        selected = max(matches, key=lambda item: len(cls._normalize(item.name)))
        return getter(selected.id)
