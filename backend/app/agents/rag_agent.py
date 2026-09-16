import asyncio
import json
import re
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, BaseAgent
from app.llm.base import LLMMessage, LLMProvider
from app.rag.milvus_store import MilvusKnowledgeStore
from app.schemas.ai_response import (
    AIResponse,
    Citation,
    Claim,
    FilteringReport,
    QueryStep,
    ValidationReport,
)
from app.services.story_text_cleaner import clean_story_content
from app.services.story_chunk_resolver import StoryChunkResolver
from app.agents.structured_character_agent import StructuredCharacterAgent


class DraftClaim(BaseModel):
    statement: str = Field(min_length=1, max_length=1500)
    confidence: float = Field(default=0.7, ge=0, le=1)
    citation_ids: list[str] = Field(default_factory=list)
    claim_type: Literal["fact", "interpretation"] = "fact"
    evidence_quotes: list[str] = Field(default_factory=list, max_length=4)


class GroundedDraft(BaseModel):
    answer: str = ""
    claims: list[DraftClaim] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = """你是《崩坏：星穹铁道》知识库检索子 Agent，只负责生成中性、结构化、可验证的事实结果，不扮演任何角色。
只能根据给出的证据回答，不得使用证据之外的游戏事实，不得猜测版本数据。
把回答拆成可独立验证的主张，每条主张必须引用一个或多个证据编号。
answer 是交给主 Agent 的中性事实摘要，并在对应事实后写出 [C1] 形式的引用。
claims 必须使用中性事实表述，不要加入吐槽或人格化修辞。
只回答用户所问范围。普通事实查询最多生成 3 条主张，不主动扩展技能、星魂、配队或养成建议。
不得把数值解释成“较高、较低、输出型”等证据没有直接说明的定性结论。
若证据不足，明确说明知识库没有足够信息，不要补全答案。
只输出 JSON，不要 Markdown：
{{"answer":"... [C1]","claims":[{{"statement":"...","confidence":0.0,"citation_ids":["C1"],"claim_type":"fact","evidence_quotes":[]}}],"warnings":[]}}
"""


class RAGAgent(BaseAgent):
    name = "rag_agent"
    description = "负责知识检索、引用与事实验证的子 Agent"
    relationship_markers = (
        "人偶",
        "本体",
        "真身",
        "化身",
        "形态",
        "本人",
        "同一",
        "关系",
        "亲属",
        "家人",
        "父亲",
        "母亲",
        "女儿",
        "儿子",
        "姐妹",
        "兄弟",
        "兄妹",
        "姐弟",
        "夫妻",
        "恋人",
        "朋友",
        "同伴",
        "搭档",
        "盟友",
        "导师",
        "学生",
        "师徒",
        "主人",
        "创造",
        "操纵",
        "追随",
        "上司",
        "下属",
        "同事",
        "隶属",
    )

    def __init__(
        self,
        store: MilvusKnowledgeStore,
        llm: LLMProvider | None,
        top_k: int = 5,
        docs_root: Path | None = None,
    ) -> None:
        self.store = store
        self.llm = llm
        self.top_k = top_k
        self.docs_root = docs_root.resolve() if docs_root else None
        self.story_chunk_resolver = (
            StoryChunkResolver(self.docs_root) if self.docs_root else None
        )
        self.structured_character_agent = (
            StructuredCharacterAgent(self.docs_root) if self.docs_root else None
        )

    async def run(self, context: AgentContext) -> AIResponse:
        if (
            self.structured_character_agent
            and self.structured_character_agent.supports(context)
        ):
            return await self.structured_character_agent.run(context)
        query_steps: list[QueryStep] = []
        retrieval_started = perf_counter()
        detailed_answer = (
            context.intent_metadata.get("answer_depth") == "detailed"
        )
        relationship_query = self._is_character_relationship_query(context)
        if relationship_query:
            retrieval_limit = max(self.top_k, 12)
        else:
            retrieval_limit = (
                max(self.top_k, 8) if detailed_answer else self.top_k
            )
        entry_types = self._entry_types(context)
        entry_type_label = ", ".join(
            entry_type or "全部知识类型" for entry_type in entry_types
        )
        await context.emit_event(
            "retrieval.started",
            "正在检索官方知识库",
            agent=self.name,
            detail=f"检索类别：{entry_type_label}。",
            progress={
                "stage": "retrieval",
                "percent": 48,
                "agent": self.name,
            },
        )
        try:
            result_groups = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        self.store.search,
                        context.message,
                        retrieval_limit,
                        entry_type,
                    )
                    for entry_type in entry_types
                )
            )
            candidates = [
                result for group in result_groups for result in group
            ]
            deduplicated: dict[str, dict[str, object]] = {}
            for result in candidates:
                entity = result.get("entity", {})
                chunk_id = str(entity.get("chunk_id") or "")
                current = deduplicated.get(chunk_id)
                score = float(
                    result.get(
                        "model_rerank_score",
                        result.get("vector_score", 0.0),
                    )
                )
                current_score = (
                    float(
                        current.get(
                            "model_rerank_score",
                            current.get("vector_score", 0.0),
                        )
                    )
                    if current
                    else -1.0
                )
                if chunk_id and score > current_score:
                    deduplicated[chunk_id] = result
            ranked_results = sorted(
                deduplicated.values(),
                key=lambda item: float(
                    item.get(
                        "model_rerank_score",
                        item.get("vector_score", 0.0),
                    )
                ),
                reverse=True,
            )
            if relationship_query:
                ranked_results = self._filter_relationship_results(
                    ranked_results,
                    context,
                )
            results = ranked_results[:retrieval_limit]
        except Exception as exc:
            return self._dependency_failure(type(exc).__name__)
        explicit_targets = {
            (
                str(item.get("entity_type") or ""),
                str(item.get("entity_id") or ""),
            )
            for item in context.entities.get(
                "mentioned_catalog_entities", []
            )
            if item.get("entity_type") and item.get("entity_id")
        }
        if context.intent == "knowledge_qa" and explicit_targets:
            entity_results = [
                result
                for result in results
                if (
                    str(result.get("entity", {}).get("entry_type") or ""),
                    str(result.get("entity", {}).get("entry_id") or ""),
                )
                in explicit_targets
            ]
            if entity_results:
                results = entity_results
        else:
            explicit_character_ids = {
                str(item.get("character_id") or "")
                for item in context.entities.get(
                    "mentioned_characters", []
                )
                if item.get("character_id")
            }
            if explicit_character_ids:
                entity_results = [
                    result
                    for result in results
                    if (
                        str(
                            result.get("entity", {}).get("entry_type")
                            or ""
                        )
                        != "hsr_character"
                        or str(
                            result.get("entity", {}).get("entry_id") or ""
                        )
                        in explicit_character_ids
                    )
                ]
                if entity_results:
                    results = entity_results
        if relationship_query and not self._relationship_coverage_complete(
            results,
            context,
        ):
            results = []
        query_steps.append(
            QueryStep(
                id="retrieval",
                name="知识检索与重排",
                status="completed",
                detail=f"BGE-M3 查询 Milvus，并由 BGE Reranker 保留 {len(results)} 条证据。",
                duration_ms=int((perf_counter() - retrieval_started) * 1000),
            )
        )
        await context.emit_event(
            "retrieval.completed",
            "知识检索与重排完成",
            agent=self.name,
            detail=f"已保留 {len(results)} 条候选证据。",
            event_status="completed",
            duration_ms=int((perf_counter() - retrieval_started) * 1000),
            payload={"evidence_count": len(results)},
            progress={
                "stage": "generation",
                "percent": 58,
                "agent": self.name,
            },
        )

        citations = self._citations(results)
        if not citations:
            return self._no_evidence_response(context)

        warnings: list[str] = []
        generation_started = perf_counter()
        if self._is_character_relationship_query(context):
            # 关系问题是封闭题型：目标角色档案里的关系句可以直接确定性抽取，
            # 不把回答质量押在模型对严格主张格式的服从度上。
            draft = self._relationship_draft(context, citations)
            generation_status = "completed"
            generation_detail = "已从目标角色档案确定性抽取关系证据句。"
            # 抽取不足 2 条时让模型补充推断类主张（interpretation 走
            # "据文献可以推断"前缀），引文+推断一起构成完整回答。
            if len(draft.claims) < 2 and self.llm:
                try:
                    llm_draft = await self._generate(context, citations)
                    existing_statements = {
                        claim.statement for claim in draft.claims
                    }
                    for claim in llm_draft.claims:
                        if claim.statement not in existing_statements:
                            draft.claims.append(claim)
                    generation_detail = (
                        f"确定性抽取 {len(draft.claims)} 条关系证据，"
                        f"{self.llm.name} 已补充推断主张。"
                    )
                except Exception:  # noqa: BLE001
                    pass
        elif self.llm:
            try:
                draft = await self._generate(context, citations)
                generation_status = "completed"
                generation_detail = f"{self.llm.name} 已生成结构化主张与中性事实摘要。"
            except Exception as exc:
                warnings.append(f"模型结构化输出失败，已使用证据摘录回退：{type(exc).__name__}")
                draft = self._evidence_fallback(
                    context.message, citations, detailed=detailed_answer
                )
                generation_status = "fallback"
                generation_detail = f"{self.llm.name} 输出不可用，已切换证据摘录模式。"
        else:
            warnings.append("未配置可用的大模型密钥，当前使用证据摘录模式。")
            draft = self._evidence_fallback(
                context.message, citations, detailed=detailed_answer
            )
            generation_status = "fallback"
            generation_detail = "未配置大模型，使用证据摘录模式。"
        query_steps.append(
            QueryStep(
                id="generation",
                name="回答生成",
                status=generation_status,
                detail=generation_detail,
                duration_ms=int((perf_counter() - generation_started) * 1000),
            )
        )

        validation_started = perf_counter()
        claims, removed, filter_warnings = self._filter_claims(draft.claims, citations)
        warnings.extend(draft.warnings)
        warnings.extend(filter_warnings)
        if not claims or (detailed_answer and len(claims) < 3):
            fallback = self._evidence_fallback(
                context.message, citations, detailed=detailed_answer
            )
            claims, fallback_removed, _ = self._filter_claims(fallback.claims, citations)
            removed += fallback_removed
            draft = fallback

        status = "verified" if claims and not filter_warnings else "partially_verified"
        answer = (
            self._claims_answer(claims)
            if context.intent == "story_analysis"
            else self._final_answer(draft.answer, claims, citations)
        )
        query_steps.append(
            QueryStep(
                id="validation",
                name="引用验证与过滤",
                status="completed" if claims else "fallback",
                detail=f"保留 {len(claims)} 条主张，过滤 {removed} 条无效主张。",
                duration_ms=int((perf_counter() - validation_started) * 1000),
            )
        )
        return AIResponse(
            agent=self.name,
            answer=answer,
            claims=claims,
            citations=citations,
            validation=ValidationReport(
                status=status,
                method="bge_m3_retrieval+cross_encoder_rerank+citation_id_validation",
                evidence_count=len(citations),
                notes=[
                    f"检索并重排了知识库证据，保留 {len(claims)} 条有引用主张。",
                    "引用编号、来源地址和证据片段均由后端生成，模型不能自行创建来源。",
                ],
            ),
            filtering=FilteringReport(
                passed=bool(claims),
                removed_claims=removed,
                rules=[
                    "移除没有有效引用编号的主张。",
                    "移除置信度低于 0.35 的主张。",
                    "移除重复主张和证据之外的内容。",
                ],
                warnings=warnings,
            ),
            query_steps=query_steps,
        )

    def _relationship_draft(
        self,
        context: AgentContext,
        citations: list[Citation],
    ) -> GroundedDraft:
        """确定性抽取关系证据：目标角色档案中含关系标记词的完整句。

        每条 statement 都是证据原文的连续句，后续定位校验天然通过。
        """
        expected_ids = {
            str(item.get("character_id") or "")
            for item in self._mentioned_characters(context)
            if item.get("character_id")
        }
        names = [
            str(item.get("name") or "")
            for item in self._mentioned_characters(context)
        ]
        # 档案正文常只用泛名自称（「开拓者」而非全名），名字匹配带上别名。
        alias_names = sorted(
            {
                alias
                for group in self._identity_alias_groups(names)
                for alias in group
            },
            key=len,
            reverse=True,
        )
        alias_groups = self._identity_alias_groups(names)
        # 强标记=直接定义关系的词；弱标记=一般关系词。
        strong_markers = (
            "本尊",
            "真身",
            "本体",
            "人偶",
            "分身",
            "化身",
            "操纵",
            "真正的主人",
            "主人",
            "创造者",
        )
        claims: list[DraftClaim] = []
        seen: set[str] = set()
        for citation in citations:
            is_profile = citation.document_id in expected_ids
            sentences = re.findall(r"[^。！？\n]+[。！？]?", citation.excerpt)
            scored: list[tuple[int, str]] = []
            for sentence in sentences:
                stripped = sentence.strip()
                # 去掉档案块自带的元信息头，避免结论句带着内部字段。
                stripped = re.sub(
                    r"^角色/条目：\S+\s*章节：\S+\s*", "", stripped
                ).strip()
                if not stripped or stripped in seen:
                    continue
                if stripped.startswith("」"):
                    continue  # 断裂的对白引号尾巴，不是可读结论
                has_name = any(
                    alias in stripped for alias in alias_names if alias
                )
                strong = any(
                    marker in stripped for marker in strong_markers
                )
                generic = any(
                    marker in stripped
                    for marker in self.relationship_markers
                )
                if is_profile:
                    score = (3 if strong else 0) + (2 if has_name else 0) + (
                        1 if generic else 0
                    )
                    if score >= 3:
                        scored.append((score, stripped))
                else:
                    # 剧情块：两个目标身份同句出现+关系词，或单身份+强关系词。
                    group_hits = sum(
                        1
                        for group in alias_groups
                        if any(alias in stripped for alias in group)
                    )
                    if (
                        (group_hits >= 2 and generic)
                        or (group_hits >= 1 and strong)
                    ):
                        scored.append((2 + group_hits, stripped))
            scored.sort(key=lambda item: -item[0])
            for _, sentence in scored[:2]:
                if len(claims) >= 5:
                    break
                seen.add(sentence)
                claims.append(
                    DraftClaim(
                        statement=sentence,
                        confidence=0.75,
                        citation_ids=[citation.id],
                        claim_type="fact",
                    )
                )
            if len(claims) >= 5:
                break
        return GroundedDraft(claims=claims)

    async def _generate(
        self, context: AgentContext, citations: list[Citation]
    ) -> GroundedDraft:
        evidence = "\n\n".join(
            f"[{item.id}] 标题：{item.title}\n来源：{item.source}\n证据：{item.excerpt}"
            for item in citations
        )
        detailed_instruction = ""
        if context.intent == "story_analysis":
            detailed_instruction = """
这是剧情解析与世界观问题。先整理文献明确陈述的事实，再回答用户要求的动机、关系、主题或因果解释。
- fact：statement 必须逐字摘录证据中的完整连续句，claim_type 填 fact。
- interpretation：允许根据多段文献作有限解释，但必须填 claim_type=interpretation，
  evidence_quotes 必须列出 1 至 4 段可在所引证据中逐字定位的短句；措辞必须使用
  “据此可理解为/可以推断”，不得把推断冒充官方明示。
- 文献没有建立因果关系、人物关系或时间先后时，明确说明不能确认。
- 共同出场只能证明同场，不能单独证明友好、敌对、亲属或上下级关系。
"""
            if self._is_character_relationship_query(context):
                # 按身份组展示目标角色：家族泛名显示为「开拓者（全系形态）」，
                # 避免把全部变体全名塞进 prompt。
                identity_labels = [
                    (
                        f"{group[0]}（全系形态）"
                        if len(group) > 1
                        else group[0]
                    )
                    for group in self._identity_alias_groups(
                        [
                            item["name"]
                            for item in self._mentioned_characters(context)
                        ]
                    )
                ]
                character_names = "、".join(identity_labels)
                detailed_instruction += f"""
这是一个多角色关系问题，目标角色是：{character_names}。回答采用"证据引文 + 推断措辞 + 不足兜底"三段式：

- 第一段·证据引文：摘录含关系确定词的完整句或对白（如"本尊""人偶""操纵""真正的主人""师徒""故交"），
  逐字引用为证据，并说明出处；不得把对白碎片、叙事片段或相似名称的第三人当作目标角色。
- 第二段·推断措辞：仅依据引文作有限推断，必须用"据此推测，他们可能是「X」关系"，
  禁止使用"确定/就是/一定是"等绝对措辞；推测关系词要与引文中的关系确定词对应。
- 第三段·不足兜底：若证据只说明两人共同出场、或引文无法建立明确关系，则回答
  "在现有剧情资料中，未能判断「{character_names}」之间的关系"，并追加一句
  "需要为你提供这几位角色的角色简介吗？"，不要强行编造关系。
- 结论必须综合覆盖每个目标角色的证据；不得用只提到其中一人的片段代替。
- 证据不足时，禁止用"可以确认共同出场，具体关系无法确认"以外的编造。
"""
            if context.intent_metadata.get("answer_depth") == "detailed":
                detailed_instruction += (
                    "\n用户要求详细回答：按事件或概念逻辑覆盖多个文献片段，"
                    "可生成 3 至 8 条主张，不要压缩成角色简介。"
                )
        elif context.intent_metadata.get("answer_depth") == "detailed":
            detailed_instruction = """
用户要求完整回答。请逐项覆盖问题中明确要求的全部内容，可生成 3 至 8 条主张。
如果询问角色技能，应分别说明知识库能够确认的普攻、战技、终结技、天赋、秘技，
以及该命途确实存在的专属技能；缺少某项资料时明确指出，不要只返回角色简介。
"""
        raw = await self.llm.complete(
            [
                LLMMessage(
                    role="system",
                    content=f"{SYSTEM_PROMPT}{detailed_instruction}",
                ),
                LLMMessage(
                    role="user",
                    content=f"用户问题：{context.message}\n\n可用证据：\n{evidence}",
                ),
            ]
        )
        return GroundedDraft.model_validate_json(self._json_object(raw))

    @staticmethod
    def _json_object(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM response did not contain a JSON object")
        candidate = text[start : end + 1]
        json.loads(candidate)
        return candidate

    def _citations(self, results: list[dict[str, object]]) -> list[Citation]:
        citations: list[Citation] = []
        for index, result in enumerate(results, start=1):
            entity = result["entity"]
            entry_type = str(entity.get("entry_type") or "")
            entry_id = str(entity["entry_id"])
            vector_chunk_id = str(entity["chunk_id"])
            chunk_id = (
                self.story_chunk_resolver.resolve(vector_chunk_id)
                if entry_type == "hsr_story" and self.story_chunk_resolver
                else None
            ) or vector_chunk_id
            raw_content = str(entity["content"])
            if entry_type == "hsr_story":
                raw_content = clean_story_content(raw_content)
            content = re.sub(r"\s+", " ", raw_content).strip()
            excerpt = self._complete_excerpt(content)
            raw_score = result.get("model_rerank_score", result.get("vector_score", 0.0))
            score = max(0.0, min(1.0, float(raw_score)))
            citations.append(
                Citation(
                    id=f"C{index}",
                    title=f"{entity['title']} · {entity['section']}",
                    source=str(entity["source_page"]),
                    excerpt=excerpt,
                    document_id=entry_id,
                    chunk_id=chunk_id,
                    game_version=str(entity.get("data_version") or "") or None,
                    updated_at=str(entity.get("generated_at") or "") or None,
                    relevance_score=score,
                    image_url=self._entity_image(
                        entry_type, entry_id
                    ),
                    entity_url=self._entity_url(entry_type, entry_id, chunk_id),
                )
            )
        return citations

    def _entity_image(self, entry_type: str, entry_id: str) -> str | None:
        if not self.docs_root:
            return None
        kind = {
            "hsr_character": "characters",
            "hsr_lightcone": "lightcones",
            "hsr_relic_set": "relics",
            "hsr_item": "items",
            "hsr_monster": "monsters",
        }.get(entry_type)
        if not kind:
            return None
        fallback = {
            "lightcones": "lightcone.svg",
            "relics": "relic.svg",
            "items": "item.svg",
            "monsters": "monster.svg",
        }.get(kind)
        raw_dir = self.docs_root / "data" / "assets" / kind / entry_id / "raw"
        if kind == "lightcones" and (raw_dir / f"{entry_id}.webp").is_file():
            return f"/api/v1/assets/lightcones/{entry_id}/raw/{entry_id}.webp"
        if kind == "items":
            items_path = self.docs_root / "hsr_nanoka_items" / "hsr_items.json"
            item = json.loads(items_path.read_text(encoding="utf-8")).get(entry_id, {})
            for field in ("item_figure_icon_path", "item_icon_path", "item_currency_icon_path", "item_avatar_icon_path"):
                resource_id = Path(str(item.get(field) or "")).stem
                if resource_id and (raw_dir / f"{resource_id}.webp").is_file():
                    return f"/api/v1/assets/items/{entry_id}/raw/{resource_id}.webp"
                if resource_id:
                    shared = next(
                        (p for p in (self.docs_root / "data" / "assets" / "items").glob(f"*/raw/{resource_id}.webp")),
                        None,
                    )
                    if shared:
                        return f"/api/v1/assets/items/{shared.parent.parent.name}/raw/{shared.name}"
        if kind in {"relics", "monsters"}:
            return f"/api/v1/assets/placeholders/{fallback}"
        path = self.docs_root / "data" / "assets" / kind / entry_id / "manifest.json"
        if not path.is_file():
            return f"/api/v1/assets/placeholders/{fallback}" if fallback else None
        manifest = json.loads(path.read_text(encoding="utf-8"))
        patterns = {
            "characters": [rf"/avatarroundicon/{re.escape(entry_id)}\.webp$", rf"/avatardrawcard/{re.escape(entry_id)}\.webp$"],
            "lightcones": [rf"/lightconemaxfigures/{re.escape(entry_id)}\.webp$", r"/2\.webp$"],
            "items": [rf"/itemfigures/{re.escape(entry_id)}\.webp$"],
            "relics": [r"/InventoryIcon\.webp$"],
            "monsters": [],
        }[kind]
        for pattern in patterns:
            for asset in manifest.get("assets", []):
                if re.search(pattern, str(asset.get("url") or ""), re.I):
                    public_url = str(asset.get("public_url") or "")
                    if public_url.startswith("/assets/"):
                        return f"/api/v1{public_url}"
        return f"/api/v1/assets/placeholders/{fallback}" if fallback else None

    @staticmethod
    def _entity_url(
        entry_type: str, entry_id: str, chunk_id: str | None = None
    ) -> str | None:
        if entry_type == "hsr_story":
            suffix = f"?scene={chunk_id}" if chunk_id else ""
            return f"/stories/{entry_id}{suffix}"
        prefix = {
            "hsr_character": "characters",
            "hsr_lightcone": "lightcones",
            "hsr_relic_set": "relics",
            "hsr_item": "items",
            "hsr_monster": "monsters",
        }.get(entry_type)
        return f"/{prefix}/{entry_id}" if prefix else None

    @staticmethod
    def _complete_excerpt(content: str, limit: int = 1600) -> str:
        # 角色/剧情块普遍超过 600 字，截断会让主张定位失败而被误杀，
        # 因此默认放宽到 1600 并在句界收尾。
        if len(content) <= limit:
            return content
        candidate = content[:limit]
        boundary = max(candidate.rfind("。"), candidate.rfind("！"), candidate.rfind("？"))
        return candidate[: boundary + 1] if boundary >= 80 else f"{candidate[:limit - 1]}…"

    @classmethod
    def _evidence_fallback(
        cls,
        question: str,
        citations: list[Citation],
        *,
        detailed: bool = False,
    ) -> GroundedDraft:
        if detailed:
            claims: list[DraftClaim] = []
            answer_parts: list[str] = []
            for citation in citations:
                content = re.sub(
                    r"^(?:角色|光锥|遗器|物品)/条目：[^。]{0,80}(?:。|\s+)",
                    "",
                    citation.excerpt,
                ).strip()
                sentences = [
                    sentence.strip()
                    for sentence in re.findall(r"[^。！？]+[。！？]", content)
                    if len(sentence.strip()) >= 8
                ]
                if not sentences and len(content) >= 8:
                    sentences = [cls._complete_excerpt(content, 260)]
                for sentence in sentences[:2]:
                    statement = sentence.rstrip("。！？").strip()
                    if not statement:
                        continue
                    claims.append(
                        DraftClaim(
                            statement=statement,
                            confidence=max(
                                0.55, citation.relevance_score or 0.55
                            ),
                            citation_ids=[citation.id],
                        )
                    )
                    answer_parts.append(f"{statement} [{citation.id}]。")
                    if len(claims) >= 8:
                        break
                if len(claims) >= 8:
                    break
            return GroundedDraft(answer="".join(answer_parts), claims=claims)

        primary = citations[0]
        content = re.sub(
            r"^(?:角色|光锥|遗器|物品)/条目：[^。]{0,80}(?:。|\s+)",
            "",
            primary.excerpt,
        ).strip()
        sentences = [
            sentence.strip()
            for sentence in re.findall(r"[^。！？]+[。！？]", content)
            if len(sentence.strip()) >= 8
        ]
        limit = 3 if any(token in question for token in ("故事", "背景", "剧情")) else 2
        selected_sentences = sentences[:limit]
        summary = "".join(selected_sentences)
        if not summary:
            summary = cls._complete_excerpt(content, 260)
        statement = summary.rstrip("。！？")
        cited_answer = (
            "".join(
                f"{sentence.rstrip('。！？')} [{primary.id}]。"
                for sentence in selected_sentences
            )
            if selected_sentences
            else f"{summary} [{primary.id}]"
        )
        return GroundedDraft(
            answer=cited_answer,
            claims=[
                DraftClaim(
                    statement=statement,
                    confidence=max(0.55, primary.relevance_score or 0.55),
                    citation_ids=[primary.id],
                )
            ]
        )

    @staticmethod
    def _filter_claims(
        drafts: list[DraftClaim], citations: list[Citation]
    ) -> tuple[list[Claim], int, list[str]]:
        valid_ids = {citation.id for citation in citations}
        citation_by_id = {citation.id: citation for citation in citations}
        claims: list[Claim] = []
        seen: set[str] = set()
        removed = 0
        ungrounded = 0
        warnings: list[str] = []
        for draft in drafts:
            citation_ids = list(dict.fromkeys(item for item in draft.citation_ids if item in valid_ids))
            normalized = re.sub(
                r"[^\u4e00-\u9fffA-Za-z0-9]+", "", draft.statement
            ).lower()
            if not citation_ids or draft.confidence < 0.35 or normalized in seen:
                removed += 1
                continue
            evidence = "".join(
                re.sub(
                    r"[^\u4e00-\u9fffA-Za-z0-9]+",
                    "",
                    citation_by_id[citation_id].excerpt,
                ).lower()
                for citation_id in citation_ids
            )
            normalized_quotes = [
                re.sub(
                    r"[^\u4e00-\u9fffA-Za-z0-9]+", "", quote
                ).lower()
                for quote in draft.evidence_quotes
                if quote.strip()
            ]
            quotes_grounded = bool(normalized_quotes) and any(
                quote in evidence for quote in normalized_quotes
            )
            statement_grounded = bool(normalized) and normalized in evidence
            if not statement_grounded and draft.claim_type != "interpretation":
                # 子句级兜底：LLM 会轻度转述连接事实，整句定位失败时，
                # 任一足够长的子句命中原文即视为有据（防止长证据被截断误杀）。
                clauses = [
                    re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", clause).lower()
                    for clause in re.split(r"[，；、,]", draft.statement)
                ]
                statement_grounded = any(
                    len(clause) >= 14 and clause in evidence
                    for clause in clauses
                )
            if draft.claim_type == "interpretation":
                grounded = quotes_grounded
            else:
                grounded = statement_grounded
            if not grounded:
                removed += 1
                ungrounded += 1
                continue
            seen.add(normalized)
            claims.append(
                Claim(
                    statement=draft.statement.strip(),
                    confidence=(
                        min(draft.confidence, 0.8)
                        if draft.claim_type == "interpretation"
                        else draft.confidence
                    ),
                    citation_ids=citation_ids,
                    claim_type=draft.claim_type,
                    evidence_quotes=draft.evidence_quotes,
                )
            )
        if removed:
            warnings.append(f"过滤了 {removed} 条无引用、低置信或重复主张。")
        if ungrounded:
            warnings.append(
                f"过滤了 {ungrounded} 条虽带引用但无法在证据原文中定位的主张。"
            )
        return claims, removed, warnings

    @staticmethod
    def _final_answer(answer: str, claims: list[Claim], citations: list[Citation]) -> str:
        valid_ids = {citation.id for citation in citations}
        claim_ids = {citation_id for claim in claims for citation_id in claim.citation_ids}
        safe_sentences: list[str] = []
        normalized_answer = re.sub(
            r"([。！？])\s*((?:\[C\d+\])+)",
            r" \2\1",
            answer.strip(),
        )
        for sentence in re.findall(r"[^。！？\n]+[。！？]?", normalized_answer):
            referenced_ids = set(re.findall(r"\[(C\d+)\]", sentence))
            if referenced_ids and referenced_ids <= valid_ids and referenced_ids & claim_ids:
                safe_sentences.append(sentence.strip())
        if safe_sentences:
            return "".join(safe_sentences)
        if not claims:
            return "现有证据不足，无法形成可靠答案。请把问题描述得更具体。"
        statements = " ".join(
            f"{claim.statement} [{claim.citation_ids[0]}]" for claim in claims
        )
        return statements

    @staticmethod
    def _claims_answer(claims: list[Claim]) -> str:
        if not claims:
            return "现有文献不足以形成可验证的剧情或世界观结论。"
        lines: list[str] = []
        for claim in claims:
            prefix = (
                "据文献可以推断："
                if claim.claim_type == "interpretation"
                else ""
            )
            references = "".join(
                f"[{citation_id}]" for citation_id in claim.citation_ids
            )
            lines.append(f"{prefix}{claim.statement} {references}")
        return "\n".join(lines)

    @staticmethod
    def _entry_type(question: str) -> str | None:
        # Recommendation questions are stored with the character supplement,
        # even when they mention lightcones or relics. Filtering them to the
        # target equipment type would hide the actual recommendation evidence.
        if any(keyword in question for keyword in ("推荐", "搭配", "配装", "构筑")):
            return None
        mappings = (
            (("光锥",), "hsr_lightcone"),
            (("遗器", "套装效果"), "hsr_relic_set"),
            (("敌人", "敌对生物", "怪物", "boss", "Boss"), "hsr_monster"),
            (("物品", "材料", "信用点"), "hsr_item"),
        )
        matches = [
            entry_type
            for keywords, entry_type in mappings
            if any(keyword in question for keyword in keywords)
        ]
        return matches[0] if len(matches) == 1 else None

    @classmethod
    def _entry_types(cls, context: AgentContext) -> list[str | None]:
        if context.intent != "story_analysis":
            explicit_types = [
                str(item.get("entity_type") or "")
                for item in context.entities.get(
                    "mentioned_catalog_entities", []
                )
                if item.get("entity_type")
            ]
            if context.intent == "knowledge_qa" and explicit_types:
                return list(dict.fromkeys(explicit_types))
            return [cls._entry_type(context.message)]
        if cls._is_character_relationship_query(context):
            return ["hsr_character", "hsr_story"]
        question = context.message
        lore_keywords = (
            "世界观",
            "星神",
            "命途",
            "阵营",
            "派系",
            "势力",
            "令使",
            "虚数之树",
            "宇宙结构",
            "琥珀纪",
        )
        story_keywords = (
            "主线",
            "同行",
            "任务",
            "剧情",
            "发生",
            "为什么",
            "关系",
            "时间线",
            "经过",
            "选择",
            "结局",
            "故事",
        )
        wants_lore = any(keyword in question for keyword in lore_keywords)
        wants_story = any(keyword in question for keyword in story_keywords)
        entry_types: list[str | None] = []
        if wants_story or not wants_lore:
            entry_types.append("hsr_story")
        if wants_lore or not wants_story:
            entry_types.append("hsr_lore")
        if (
            context.entities.get("mentioned_characters")
            and any(keyword in question for keyword in ("角色故事", "背景故事"))
        ):
            entry_types.append("hsr_character")
        return list(dict.fromkeys(entry_types))

    @staticmethod
    def _mentioned_characters(
        context: AgentContext,
    ) -> list[dict[str, str]]:
        mentioned: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for raw_item in context.entities.get("mentioned_characters", []):
            character_id = str(raw_item.get("character_id") or "").strip()
            name = str(raw_item.get("name") or "").strip()
            key = (character_id, name)
            if not name or key in seen:
                continue
            seen.add(key)
            mentioned.append(
                {"character_id": character_id, "name": name}
            )
        return mentioned

    @classmethod
    @classmethod
    def _is_character_relationship_query(
        cls,
        context: AgentContext,
    ) -> bool:
        if context.intent != "story_analysis":
            return False
        if len(cls._mentioned_characters(context)) < 2:
            return False
        if context.intent_metadata.get("task_mode") == "character_relationship":
            return True
        # 确定性兜底：路由关键行为不能只依赖意图模型的 task_mode 枚举。
        # 两个已确认角色 + 明显关系词 → 一律按关系问题走档案域检索。
        relationship_keywords = (
            "关系",
            "认识",
            "同一个",
            "同一个人",
            "本尊",
            "真身",
            "什么身份",
            "什么来头",
        )
        return any(
            keyword in context.message for keyword in relationship_keywords
        )

    @staticmethod
    def _non_overlapping_name_matches(
        text: str,
        names: list[str],
    ) -> set[str]:
        occupied: list[tuple[int, int]] = []
        matched: set[str] = set()
        for name in sorted(set(names), key=len, reverse=True):
            for occurrence in re.finditer(re.escape(name), text):
                span = occurrence.span()
                if any(
                    span[0] < end and span[1] > start
                    for start, end in occupied
                ):
                    continue
                occupied.append(span)
                matched.add(name)
                break
        return matched

    @classmethod
    def _story_character_names(
        cls,
        entity: dict[str, object],
        expected_names: list[str],
    ) -> set[str]:
        raw_characters = entity.get("characters")
        if isinstance(raw_characters, list):
            structured_names = {
                str(item).strip()
                for item in raw_characters
                if str(item).strip()
            }
            return {
                name for name in expected_names if name in structured_names
            }

        content = str(entity.get("content") or "")
        header = re.search(r"【出场角色】\s*([^\n]+)", content)
        if header:
            structured_names = {
                item.strip()
                for item in re.split(r"[、,，|/]", header.group(1))
                if item.strip()
            }
            return {
                name for name in expected_names if name in structured_names
            }
        return cls._non_overlapping_name_matches(content, expected_names)

    @classmethod
    def _filter_relationship_results(
        cls,
        results: list[dict[str, object]],
        context: AgentContext,
    ) -> list[dict[str, object]]:
        mentioned = cls._mentioned_characters(context)
        expected_ids = {
            item["character_id"]
            for item in mentioned
            if item["character_id"]
        }
        expected_names = [item["name"] for item in mentioned]
        # 家族变体按身份分组：「开拓者」泛名命中全系变体后，剧情块里
        # 只会出现「开拓者」三个字，按组匹配（组内任一别名命中即算出现）。
        alias_groups = cls._identity_alias_groups(expected_names)
        all_aliases = sorted(
            {alias for group in alias_groups for alias in group},
            key=len,
            reverse=True,
        )
        filtered: list[dict[str, object]] = []
        for result in results:
            entity = result.get("entity", {})
            if not isinstance(entity, dict):
                continue
            entry_type = str(entity.get("entry_type") or "")
            if entry_type == "hsr_character":
                section = str(entity.get("section") or "")
                excluded_sections = (
                    "技能",
                    "星魂",
                    "光锥",
                    "遗器",
                    "晋阶",
                    "材料",
                    "配队",
                    "养成",
                )
                if (
                    str(entity.get("entry_id") or "") in expected_ids
                    and not any(
                        keyword in section
                        for keyword in excluded_sections
                    )
                ):
                    # 角色档案块整段交给模型（简介/角色故事篇幅有限），
                    # 关系结论需要上下文；输出端仍有主张定位器防幻觉。
                    full_content = re.sub(
                        r"\s+", " ", str(entity.get("content") or "")
                    ).strip()
                    if full_content:
                        filtered.append(
                            cls._result_with_content(result, full_content)
                        )
                continue
            if entry_type == "hsr_story":
                matched_names = cls._story_character_names(
                    entity,
                    all_aliases,
                )
                # 关系问题必须让所有目标身份在同一剧情证据中出现，不能拼接各自的无关片段。
                if not all(
                    any(alias in matched_names for alias in group)
                    for group in alias_groups
                ):
                    continue
                excerpt = cls._relationship_evidence_excerpt(
                    clean_story_content(
                        str(entity.get("content") or "")
                    ),
                    all_aliases,
                    require_all_names=False,
                )
                # 逐身份复核：该块必须为每个身份组贡献至少一个命中句。
                if excerpt and all(
                    any(
                        alias in excerpt
                        for alias in group
                    )
                    for group in alias_groups
                ):
                    filtered.append(
                        cls._result_with_content(result, excerpt)
                    )
        return filtered

    @classmethod
    def _identity_alias_groups(cls, names: list[str]) -> list[list[str]]:
        """把提及名按身份分组：家族变体共享一个别名组（泛名+全部全名）。

        「开拓者」命中「开拓者·毁灭（星）」等变体时，剧情块里只会出现
        「开拓者」三个字，分组后任一别名命中即视为该身份出现。
        前缀本身也是被提及角色时（丹恒/丹恒·饮月）各自独立成组。
        """
        mentioned_set = set(names)
        groups: dict[str, list[str]] = {}
        ordered: list[list[str]] = []
        for name in names:
            base = re.split(r"[·（]", name)[0].strip()
            if len(base) >= 2 and base != name and base not in mentioned_set:
                if base not in groups:
                    groups[base] = [base]
                    ordered.append(groups[base])
                if name not in groups[base]:
                    groups[base].append(name)
            else:
                ordered.append([name])
        return ordered

    @classmethod
    def _relationship_evidence_excerpt(
        cls,
        content: str,
        expected_names: list[str],
        *,
        require_all_names: bool = False,
    ) -> str:
        selected: list[str] = []
        # 只把同时包含关系词和目标角色的完整句子交给模型，降低邻近段落造成的关系幻觉。
        for sentence in re.findall(r"[^。！？\n]+[。！？]?", content):
            sentence = sentence.strip()
            if not sentence or not any(
                marker in sentence
                for marker in cls.relationship_markers
            ):
                continue
            if (
                require_all_names
                and not set(expected_names).issubset(
                    cls._non_overlapping_name_matches(
                        sentence,
                        expected_names,
                    )
                )
            ):
                continue
            selected.append(sentence)
            if len(selected) >= 4:
                break
        return "\n".join(selected)

    @staticmethod
    def _result_with_content(
        result: dict[str, object],
        content: str,
    ) -> dict[str, object]:
        copied_result = dict(result)
        raw_entity = result.get("entity", {})
        copied_entity = (
            dict(raw_entity) if isinstance(raw_entity, dict) else {}
        )
        copied_entity["content"] = content
        copied_result["entity"] = copied_entity
        return copied_result

    @classmethod
    def _relationship_coverage_complete(
        cls,
        results: list[dict[str, object]],
        context: AgentContext,
    ) -> bool:
        mentioned = cls._mentioned_characters(context)
        expected_names = [item["name"] for item in mentioned]
        alias_groups = cls._identity_alias_groups(expected_names)
        id_to_name = {
            item["character_id"]: item["name"]
            for item in mentioned
            if item["character_id"]
        }
        covered_ids: set[str] = set()
        covered_names: set[str] = set()
        for result in results:
            entity = result.get("entity", {})
            if not isinstance(entity, dict):
                continue
            if str(entity.get("entry_type") or "") == "hsr_character":
                entry_id = str(entity.get("entry_id") or "")
                covered_ids.add(entry_id)
                if entry_id in id_to_name:
                    covered_names.add(id_to_name[entry_id])
                continue
            matched_names = cls._story_character_names(
                entity,
                sorted(
                    {alias for group in alias_groups for alias in group},
                    key=len,
                    reverse=True,
                ),
            )
            covered_names.update(matched_names)
        # 按身份组判定覆盖：角色档案命中组内任一变体、或剧情块命中
        # 组内任一别名，都算该身份已覆盖。家族泛名不该要求全部变体到场。
        def group_covered(group: list[str]) -> bool:
            if any(alias in covered_names for alias in group):
                return True
            member_ids = {
                character_id
                for character_id, name in id_to_name.items()
                if name in group
            }
            return bool(member_ids & covered_ids)

        return all(group_covered(group) for group in alias_groups)

    def _dependency_failure(self, error_name: str) -> AIResponse:
        return AIResponse(
            agent=self.name,
            answer="知识检索服务暂时不可用，当前无法生成有证据支持的答案。",
            claims=[],
            citations=[],
            validation=ValidationReport(
                status="unverified",
                method="dependency_health_check",
                evidence_count=0,
                notes=["知识检索服务暂时不可用，未生成游戏事实回答。"],
            ),
            filtering=FilteringReport(
                passed=False,
                removed_claims=0,
                rules=["外部依赖不可用时禁止无证据回答。"],
                warnings=[f"检索依赖异常：{error_name}"],
            ),
            query_steps=[
                QueryStep(
                    id="retrieval",
                    name="知识检索与重排",
                    status="failed",
                    detail=f"检索依赖异常：{error_name}",
                )
            ],
        )

    def _no_evidence_response(
        self,
        context: AgentContext | None = None,
    ) -> AIResponse:
        relationship_names = (
            [
                item["name"]
                for item in self._mentioned_characters(context)
            ]
            if context and self._is_character_relationship_query(context)
            else []
        )
        if relationship_names:
            joined_names = "、".join(relationship_names)
            answer = (
                f"在现有剧情资料中，未能判断“{joined_names}”之间的关系。"
                "需要为你提供这几位角色的角色简介吗？"
            )
            notes = [
                f"检索结果没有完整覆盖全部目标角色：{joined_names}，无可靠关系证据。"
            ]
        else:
            answer = "知识库里没有足够证据，请换一个更具体的问题。"
            notes = ["知识库没有检索到足以回答该问题的证据。"]
        return AIResponse(
            agent=self.name,
            answer=answer,
            claims=[],
            citations=[],
            validation=ValidationReport(
                status="unverified",
                method="rag_no_evidence",
                evidence_count=0,
                notes=notes,
            ),
            filtering=FilteringReport(
                passed=False,
                removed_claims=0,
                rules=["没有证据时不输出游戏事实。"],
            ),
            query_steps=[
                QueryStep(
                    id="retrieval",
                    name="知识检索与重排",
                    status="completed",
                    detail="没有检索到可用证据。",
                )
            ],
        )
