import json
import re
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Any

import yaml

from app.schemas.catalog import (
    CharacterDetail,
    CharacterSummary,
    EntityRecommendation,
    KnowledgeEntityDetail,
    KnowledgeEntitySummary,
    LightconeDetail,
    LightconeLevelStats,
    LightconeMaterial,
    RelicDetail,
    ItemDetail,
    RelatedItem,
    NamedDescription,
    RelatedEntity,
)


RARITY_ORDER = {"Normal": 1, "NotNormal": 2, "Rare": 3, "VeryRare": 4, "SuperRare": 5}
SKILL_ICONS = {
    "普攻": "Normal",
    "战技": "BP",
    "终结技": "Ultra",
    "天赋": "Passive",
    "秘技": "Maze",
    "欢愉技": "Elation",
}
ITEM_OVERRIDES = {
    "110507": {
        "item_name": "阳雷的遥想",
        "item_desc": "行迹升级的高阶素材。",
    },
    "110508": {
        "item_name": "灭流绝溢的缄默",
        "item_desc": "行迹升级的高阶素材。",
    },
}
CHARACTER_WEEKLY_MATERIALS = {
    "1002": "110501",
    "1003": "110501",
    "1321": "110508",
    "1406": "110507",
    "1408": "110507",
    "1410": "110507",
    "1412": "110507",
    "1413": "110507",
    "1415": "110508",
    "1501": "110508",
    "1502": "110508",
    "1504": "110508",
    "1505": "110508",
    "1506": "110508",
}
MATERIAL_TYPE_ORDER = {
    "CommonMonsterDrop": 0,
    "TracePath": 1,
    "AvatarRank": 2,
    "WeeklyMonsterDrop": 3,
}
ENTITY_CONFIG = {
    "lightcones": ("lightcone", "lightcones", "光锥"),
    "relics": ("relic", "relics", "遗器"),
    "monsters": ("monster", "monsters", "敌对生物"),
}


class CatalogService:
    def __init__(self, docs_root: Path) -> None:
        self.docs_root = docs_root.resolve()

    @lru_cache(maxsize=1)
    def _character_index(self) -> dict[str, Any]:
        path = self.docs_root / "hsr_nanoka_characters" / "manifest.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @lru_cache(maxsize=1)
    def _character_overrides(self) -> dict[str, dict[str, Any]]:
        path = self.docs_root / "character_catalog_overrides.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    @lru_cache(maxsize=1)
    def _items(self) -> dict[str, dict[str, Any]]:
        path = self.docs_root / "hsr_nanoka_items" / "hsr_items.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @lru_cache(maxsize=1)
    def _character_skill_supplements(self) -> dict[str, Any]:
        path = self.docs_root / "character_skill_supplements.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    @lru_cache(maxsize=8)
    def _entity_index(self, kind: str) -> dict[str, Any]:
        dataset, _, _ = ENTITY_CONFIG[kind]
        return json.loads((self.docs_root / dataset / "manifest.json").read_text(encoding="utf-8"))

    @lru_cache(maxsize=1)
    def _alignment_report(self) -> dict[str, Any]:
        path = self.docs_root / "normalized_supplements" / "alignment_report.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"aligned": []}

    @lru_cache(maxsize=4096)
    def _asset_manifest(self, kind: str, entry_id: str) -> dict[str, Any]:
        path = self.docs_root / "data" / "assets" / kind / entry_id / "manifest.json"
        if kind == "relics" and not path.is_file():
            path = self.docs_root / "data" / "assets" / kind / f"relic_{entry_id}" / "manifest.json"
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def list_characters(
        self,
        search: str = "",
        element: str = "",
        path: str = "",
        rarity: int | None = None,
    ) -> list[CharacterSummary]:
        query = self._normalize_character_search(search)
        result: list[CharacterSummary] = []
        for entry in self._character_index().get("characters", []):
            entry_id = str(entry["character_id"])
            override = self._character_overrides().get(entry_id, {})
            if entry.get("error") and not override:
                continue
            name = str(override.get("name") or entry.get("name") or "").strip()
            if not name or len(name) > 24 or any(token in name for token in ("{", "}", "'")):
                continue
            entry_element = str(override.get("element") or entry.get("element") or "未知")
            entry_path = str(override.get("path") or entry.get("path") or "未知")
            entry_rarity = int(override.get("rarity") or entry.get("rarity") or 0)
            if query and query not in self._normalize_character_search(name):
                continue
            if element and entry_element != element:
                continue
            if path and entry_path != path:
                continue
            if rarity is not None and entry_rarity != rarity:
                continue
            assets = self._asset_manifest("characters", entry_id)
            result.append(
                CharacterSummary(
                    id=entry_id,
                    name=name,
                    rarity=entry_rarity,
                    path=entry_path,
                    element=entry_element,
                    image_url=self._find_asset(
                        assets, rf"/avatarroundicon/{re.escape(entry_id)}\.webp$"
                    )
                    or self._find_asset(assets, rf"/avatardrawcard/{re.escape(entry_id)}\.webp$"),
                )
            )
        return sorted(result, key=lambda item: (-item.rarity, -int(item.id)))

    def get_character(self, character_id: str) -> CharacterDetail | None:
        summary = next(
            (item for item in self.list_characters() if item.id == character_id), None
        )
        if summary is None:
            return None
        index_entry = next(
            item
            for item in self._character_index()["characters"]
            if str(item.get("character_id")) == character_id
        )
        markdown_path = self._character_markdown_path(character_id, index_entry)
        text = markdown_path.read_text(encoding="utf-8")
        assets = self._asset_manifest("characters", character_id)
        basic = self._two_column_table(self._section(text, "基本资料"))
        supplement = self._character_supplement(character_id)
        supplement_body = str(supplement.get("body") or "")
        skills = self._named_entries(text, "技能", assets, character_id, skills=True)
        skills.extend(self._memory_skills(character_id, assets))
        eidolons = self._supplement_eidolons(supplement_body, assets, character_id)
        if len(eidolons) != 6:
            eidolons = self._named_entries(text, "星魂", assets, character_id)
        return CharacterDetail(
            **summary.model_dump(),
            description=self._plain_section(self._section(text, "角色简介")),
            energy=basic.get("终结技能量"),
            stats=self._level_80_stats(text),
            skills=skills,
            eidolons=eidolons,
            related_items=self._related_items(assets, character_id),
            recommended_lightcones=self._recommendations(
                supplement.get("metadata", {}).get("recommended_lightcones", []), "lightcones"
            ),
            recommended_relics=self._recommendations(
                supplement.get("metadata", {}).get("recommended_relics", []), "relics"
            ),
            story=self._section(supplement_body, "角色故事"),
            community_source_url=str(
                supplement.get("metadata", {}).get("source_page") or ""
            ) or None,
            portrait_url=self._find_asset(
                assets, rf"/avatardrawcard/{re.escape(character_id)}\.webp$"
            ),
            element_icon_url=self._find_asset(assets, r"/element/[^/]+\.webp$"),
            path_icon_url=self._find_asset(assets, r"/pathicon/[^/]+\.webp$"),
            source_url=str(assets.get("source_page") or index_entry.get("source_page") or ""),
            data_version=str(self._character_index().get("data_version") or "") or None,
        )

    def _character_markdown_path(
        self, character_id: str, index_entry: dict[str, Any]
    ) -> Path:
        directory = self.docs_root / "hsr_nanoka_characters" / "characters"
        filename = str(index_entry.get("filename") or "")
        candidate = directory / filename if filename else None
        if candidate and candidate.is_file():
            return candidate
        recovered = sorted(directory.glob(f"{character_id}_*.md"))
        if not recovered:
            raise FileNotFoundError(f"character_markdown_missing:{character_id}")
        return recovered[0]

    @staticmethod
    def _normalize_character_search(value: str) -> str:
        return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", value).lower()

    @lru_cache(maxsize=256)
    def _character_supplement(self, character_id: str) -> dict[str, Any]:
        directory = self.docs_root / "normalized_supplements" / "characters"
        paths = sorted(directory.glob(f"{character_id}_*.md"))
        if not paths:
            return {}
        raw = paths[0].read_text(encoding="utf-8")
        match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", raw, re.S)
        if not match:
            return {}
        metadata = yaml.safe_load(match.group(1)) or {}
        return {"metadata": metadata, "body": match.group(2).strip()}

    def _recommendations(
        self, entries: list[dict[str, Any]], asset_kind: str
    ) -> list[EntityRecommendation]:
        result: list[EntityRecommendation] = []
        for entry in entries:
            entry_id = str(entry.get("id") or "")
            if not entry_id:
                continue
            manifest = self._asset_manifest(asset_kind, entry_id)
            if asset_kind == "lightcones":
                image_url = self._local_asset("lightcones", entry_id, f"{entry_id}.webp") or self._find_asset(
                    manifest, rf"/lightconemaxfigures/{re.escape(entry_id)}\.webp$"
                ) or self._find_asset(manifest, r"/(?:1|2)\.webp$")
                image_status = "official" if image_url else "category_placeholder"
                image_url = image_url or "/api/v1/assets/placeholders/lightcone.svg"
            else:
                image_url, image_status = self._entity_art("relics", entry_id)
                piece_count = self._relic_info(entry_id)["piece_count"]
                set_type = "cavern" if piece_count == 4 else "planar"
            result.append(
                EntityRecommendation(
                    id=entry_id,
                    name=str(entry.get("name") or entry_id),
                    kind=str(entry.get("kind") or asset_kind.rstrip("s")),
                    image_url=image_url,
                    image_status=image_status,
                    set_type=(
                        set_type
                        if asset_kind == "relics"
                        else str(entry.get("set_type") or "") or None
                    ),
                    piece_count=(
                        piece_count
                        if asset_kind == "relics"
                        else int(entry.get("piece_count") or 0) or None
                    ),
                )
            )
        return result

    def list_items(self, search: str = "", limit: int = 100) -> list[RelatedItem]:
        query = search.strip().lower()
        result: list[RelatedItem] = []
        for item_id, entry in self._items().items():
            name = str(ITEM_OVERRIDES.get(item_id, {}).get("item_name") or entry.get("item_name") or "")
            if not name or name == "..." or not entry.get("is_visible", True):
                continue
            if query and query not in name.lower():
                continue
            result.append(self._related_item(item_id, entry))
        result.sort(key=lambda item: (-RARITY_ORDER.get(item.rarity, 0), item.name))
        return result[:limit]

    def get_item(self, item_id: str) -> ItemDetail | None:
        entry = self._items().get(item_id)
        if entry is None:
            return None
        base = self._related_item(item_id, entry)
        sources = [
            str(item.get("desc"))
            for item in entry.get("item_comefrom", [])
            if item.get("desc")
        ]
        manifest = self._asset_manifest("items", item_id)
        return ItemDetail(
            **base.model_dump(),
            background=self._clean_html(str(entry.get("item_bg_desc") or "")),
            sources=sources,
            pile_limit=entry.get("pile_limit"),
            source_url=str(manifest.get("visited_url") or manifest.get("source_page") or "") or None,
            related_entities=self._item_related_characters(item_id),
        )

    def list_entities(self, kind: str) -> list[KnowledgeEntitySummary]:
        if kind == "items":
            return [
                KnowledgeEntitySummary(
                    id=item.id,
                    name=item.name,
                    kind="items",
                    subtitle=item.type,
                    image_url=item.image_url,
                    image_status="official" if "placeholders" not in (item.image_url or "") else "category_placeholder",
                    rarity=RARITY_ORDER.get(item.rarity, 0),
                )
                for item in self.list_items(limit=2000)
            ]
        if kind not in ENTITY_CONFIG:
            return []
        _, asset_kind, label = ENTITY_CONFIG[kind]
        result: list[KnowledgeEntitySummary] = []
        for entry in self._entity_index(kind).get("entries", []):
            if entry.get("status") not in (None, "complete") or entry.get("error"):
                continue
            entry_id, name = str(entry.get("id") or ""), str(entry.get("name") or "").strip()
            if not entry_id or not name:
                continue
            image_url, image_status = self._entity_art(kind, entry_id)
            rarity = None
            path_name = None
            if kind == "lightcones":
                markdown = self.docs_root / "lightcone" / "lightcones" / str(entry["filename"])
                basic = self._two_column_table(self._section(markdown.read_text(encoding="utf-8"), "基本资料"))
                rarity_match = re.search(r"\d+", basic.get("稀有度", ""))
                rarity = int(rarity_match.group()) if rarity_match else None
                path_name = basic.get("命途")
            set_type = None
            piece_count = None
            if kind == "relics":
                markdown = self.docs_root / "relic" / "relics" / str(entry["filename"])
                piece_count = self._relic_piece_count(markdown.read_text(encoding="utf-8"))
                set_type = "cavern" if piece_count == 4 else "planar"
            result.append(
                KnowledgeEntitySummary(
                    id=entry_id,
                    name=name,
                    kind=kind,
                    subtitle=label,
                    image_url=image_url,
                    image_status=image_status,
                    rarity=rarity,
                    path=path_name,
                    set_type=set_type,
                    piece_count=piece_count,
                )
            )
        if kind in {"lightcones", "items"}:
            result.sort(key=lambda item: (-(item.rarity or 0), item.path or "", -int(item.id)))
        return result

    def get_lightcone(self, entry_id: str) -> LightconeDetail | None:
        base = self.get_entity("lightcones", entry_id)
        if not base:
            return None
        index_entry = next(
            item for item in self._entity_index("lightcones")["entries"] if str(item.get("id")) == entry_id
        )
        path = self.docs_root / "lightcone" / "lightcones" / str(index_entry["filename"])
        text = path.read_text(encoding="utf-8")
        supplement = self._lightcone_supplement(entry_id)
        supplement_body = str(supplement.get("body") or "")
        effect_name, effects = self._superimposition_data(text, supplement_body)
        data = base.model_dump()
        data.update(
            description=self._lightcone_summary(text),
            lore_description=self._lightcone_lore(supplement_body),
            effect_name=effect_name,
            superimposition_effects=effects,
            level_stats=self._lightcone_level_stats(text),
            promotion_materials=self._lightcone_materials(text),
            sections=[],
            related_entities=[item for item in base.related_entities if item.kind == "characters"],
        )
        return LightconeDetail(**data)

    def get_relic(self, entry_id: str) -> RelicDetail | None:
        base = self.get_entity("relics", entry_id)
        if not base:
            return None
        supplement = self._relic_supplement(entry_id)
        body = str(supplement.get("body") or "")
        metadata = supplement.get("metadata", {})
        effects_section = self._section(body, "套装效果")
        effects = [
            NamedDescription(name=name, description=description.strip())
            for name, description in re.findall(r"^(二件套|四件套)[：:](.+)$", effects_section, re.M)
        ]
        pieces = self._relic_pieces(entry_id, base.name, body)
        acquisition_match = re.search(r"^获取途径：(.+)$", body, re.M)
        data = base.model_dump()
        data.update(
            description="\n".join(f"{item.name}：{item.description}" for item in effects) or base.description,
            sections=[],
            set_type=str(base.set_type or metadata.get("set_type") or "planar"),
            piece_count=int(base.piece_count or metadata.get("piece_count") or len(pieces)),
            acquisition=acquisition_match.group(1).strip() if acquisition_match else "",
            set_effects=effects,
            pieces=pieces,
            community_source_url=str(metadata.get("source_page") or "") or None,
        )
        return RelicDetail(**data)

    @lru_cache(maxsize=128)
    def _relic_supplement(self, entry_id: str) -> dict[str, Any]:
        paths = sorted((self.docs_root / "normalized_supplements" / "relics").glob(f"{entry_id}_*.md"))
        if not paths:
            return {}
        raw = paths[0].read_text(encoding="utf-8")
        match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", raw, re.S)
        return {"metadata": yaml.safe_load(match.group(1)) or {}, "body": match.group(2)} if match else {}

    @lru_cache(maxsize=128)
    def _relic_info(self, entry_id: str) -> dict[str, Any]:
        entry = next(
            (
                item
                for item in self._entity_index("relics").get("entries", [])
                if str(item.get("id")) == entry_id
            ),
            None,
        )
        if entry is None:
            return {"piece_count": 0, "set_type": ""}
        path = self.docs_root / "relic" / "relics" / str(entry["filename"])
        piece_count = self._relic_piece_count(path.read_text(encoding="utf-8"))
        return {
            "piece_count": piece_count,
            "set_type": "cavern" if piece_count == 4 else "planar",
        }

    def _relic_pieces(self, entry_id: str, set_name: str, text: str) -> list[NamedDescription]:
        slots = ("头部", "手部", "躯干", "脚部", "位面球", "连结绳")
        slot_pattern = "|".join(slots)
        pieces: list[NamedDescription] = []
        for match in re.finditer(
            rf"^({slot_pattern})：([^\n]+)\n描述：([^\n]*)\n来历\s*\n(.*?)(?=^(?:{slot_pattern})：|^{re.escape(set_name)}\s*$|\Z)",
            text,
            re.M | re.S,
        ):
            slot, name, description, lore = (item.strip() for item in match.groups())
            index = slots.index(slot) + 1
            pieces.append(
                NamedDescription(
                    name=name,
                    type=slot,
                    description=(description + "\n\n" + lore).strip(),
                    image_url=self._relic_asset_url(entry_id, index),
                )
            )
        return sorted(pieces, key=lambda item: slots.index(item.type or slots[0]))

    @staticmethod
    def _relic_piece_count(text: str) -> int:
        section = CatalogService._section(text, "其他结构化资料")
        return len(re.findall(r"^####\s+\d+\s*$", section, re.M))

    @lru_cache(maxsize=256)
    def _lightcone_supplement(self, entry_id: str) -> dict[str, Any]:
        paths = sorted((self.docs_root / "normalized_supplements" / "lightcones").glob(f"{entry_id}_*.md"))
        if not paths:
            return {}
        raw = paths[0].read_text(encoding="utf-8")
        match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", raw, re.S)
        return {"metadata": yaml.safe_load(match.group(1)) or {}, "body": match.group(2)} if match else {}

    def _lightcone_summary(self, text: str) -> str:
        basic = self._two_column_table(self._section(text, "基本资料"))
        return " · ".join(f"{key}：{value}" for key, value in basic.items())

    @staticmethod
    def _lightcone_lore(body: str) -> str:
        match = re.search(r"^光锥描述\s*$\n(.*?)(?=^成长数值\s*$|^光锥信息\s*$|\Z)", body, re.M | re.S)
        return match.group(1).strip() if match else ""

    def _superimposition_data(self, text: str, supplement_body: str) -> tuple[str, list[str]]:
        original = self._section(text, "叠影效果")
        name = self._two_column_table(original).get("名称", "叠影效果")
        supplement_match = re.search(
            r"^技能\s*$\n([^\n]+)\n(.*?)(?=^光锥描述\s*$|^成长数值\s*$|\Z)",
            supplement_body,
            re.M | re.S,
        )
        template = supplement_match.group(2).strip() if supplement_match else self._plain_section(original)
        if supplement_match:
            name = supplement_match.group(1).strip()
        value_groups = [group.split("/") for group in re.findall(r"【([^】]+)】", template)]
        effects: list[str] = []
        for index in range(5):
            cursor = 0
            def replace(_: re.Match[str]) -> str:
                nonlocal cursor
                values = value_groups[cursor]
                cursor += 1
                return values[index] if index < len(values) else values[-1]
            effects.append(re.sub(r"【[^】]+】", replace, template))
        return name, effects

    def _lightcone_level_stats(self, text: str) -> list[LightconeLevelStats]:
        stages: list[dict[str, float]] = []
        section_text = self._section(text, "等级与晋阶属性")
        for match in re.finditer(r"^###\s+等级与晋阶属性\s+\d+\s*$\n(.*?)(?=^###\s+等级与晋阶属性|\Z)", section_text, re.M | re.S):
            table = self._two_column_table(match.group(1))
            try:
                stages.append({
                    "max": float(table["max level"]),
                    "hp": float(table["base hp"]),
                    "hp_add": float(table["base hp add"]),
                    "attack": float(table["base attack"]),
                    "attack_add": float(table["base attack add"]),
                    "defence": float(table["base defence"]),
                    "defence_add": float(table["base defence add"]),
                })
            except (KeyError, ValueError):
                continue
        result: list[LightconeLevelStats] = []
        for level in range(1, 81):
            stage_index = 0 if level < 20 else min(6, level // 10 - 1)
            stage = stages[min(stage_index, len(stages) - 1)] if stages else None
            if not stage:
                break
            result.append(LightconeLevelStats(
                level=level,
                hp=int(stage["hp"] + stage["hp_add"] * (level - 1)),
                attack=int(stage["attack"] + stage["attack_add"] * (level - 1)),
                defence=int(stage["defence"] + stage["defence_add"] * (level - 1)),
            ))
        return result

    def _lightcone_materials(self, text: str) -> dict[int, list[LightconeMaterial]]:
        section_text = self._section(text, "等级与晋阶属性")
        cumulative: dict[str, int] = {}
        result: dict[int, list[LightconeMaterial]] = {1: []}
        for match in re.finditer(r"^###\s+等级与晋阶属性\s+\d+\s*$\n(.*?)(?=^###\s+等级与晋阶属性|\Z)", section_text, re.M | re.S):
            block = match.group(1)
            table = self._two_column_table(block)
            try:
                unlock_level = int(table["max level"])
            except (KeyError, ValueError):
                continue
            consumption_match = re.search(r"^####\s+晋阶消耗\s*$\n(.*?)(?=^#{1,4}\s+|\Z)", block, re.M | re.S)
            consumption = consumption_match.group(1) if consumption_match else ""
            for item_id, quantity in re.findall(r"\|\s*(\d+)\s*\|\s*(\d+)\s*\|", consumption):
                cumulative[item_id] = cumulative.get(item_id, 0) + int(quantity)
            if consumption:
                materials: list[LightconeMaterial] = []
                for item_id, quantity in cumulative.items():
                    item = self._items().get(item_id)
                    if not item:
                        continue
                    base = self._related_item(item_id, item)
                    materials.append(LightconeMaterial(**base.model_dump(), quantity=quantity))
                result[unlock_level] = materials
        return result

    def get_entity(self, kind: str, entry_id: str) -> KnowledgeEntityDetail | None:
        if kind == "items":
            item = self.get_item(entry_id)
            if not item:
                return None
            return KnowledgeEntityDetail(
                id=item.id,
                name=item.name,
                kind="items",
                subtitle=item.type,
                image_url=item.image_url,
                image_status="official" if "placeholders" not in (item.image_url or "") else "category_placeholder",
                description=item.description,
                sections=[
                    NamedDescription(name="背景描述", description=item.background),
                    NamedDescription(name="获取来源", description="\n".join(item.sources)),
                ],
                related_entities=self._item_related_characters(entry_id),
                source_url=item.source_url,
                data_version=str(self._character_index().get("data_version") or "") or None,
            )
        summary = next((item for item in self.list_entities(kind) if item.id == entry_id), None)
        if not summary:
            return None
        dataset, directory, _ = ENTITY_CONFIG[kind]
        index_entry = next(
            item for item in self._entity_index(kind)["entries"] if str(item.get("id")) == entry_id
        )
        path = self.docs_root / dataset / directory / str(index_entry["filename"])
        text = path.read_text(encoding="utf-8")
        description = self._entity_description(kind, text)
        return KnowledgeEntityDetail(
            **summary.model_dump(),
            description=description,
            sections=self._entity_sections(kind, text),
            related_entities=self._entity_relations(kind, entry_id, text),
            source_url=str(index_entry.get("source_page") or "") or None,
            data_version=str(self._entity_index(kind).get("data_version") or "") or None,
        )

    def _entity_art(self, kind: str, entry_id: str) -> tuple[str, str]:
        if kind == "lightcones":
            manifest = self._asset_manifest("lightcones", entry_id)
            image = self._local_asset("lightcones", entry_id, f"{entry_id}.webp") or self._find_asset(manifest, rf"/lightconemaxfigures/{re.escape(entry_id)}\.webp$") or self._find_asset(manifest, r"/2\.webp$")
            return (image or "/api/v1/assets/placeholders/lightcone.svg", "official" if image else "category_placeholder")
        if kind == "relics":
            image = self._relic_asset_url(entry_id)
            return (image or "/api/v1/assets/placeholders/relic.svg", "official" if image else "category_placeholder")
        image = self._monster_asset_url(entry_id)
        return (image or "/api/v1/assets/placeholders/monster.svg", "official" if image else "category_placeholder")

    def _relic_asset_url(self, entry_id: str, piece_index: int | None = None) -> str | None:
        root = self.docs_root / "data" / "assets" / "relics" / f"relic_{entry_id}" / "webp"
        candidates = [root / f"IconRelic_{entry_id}_{piece_index}.webp"] if piece_index else sorted(root.glob(f"IconRelic_{entry_id}_*.webp"))
        path = next((item for item in candidates if item.is_file()), None)
        return f"/api/v1/assets/relics/relic_{entry_id}/webp/{path.name}" if path else None

    @lru_cache(maxsize=1)
    def _monster_images_by_name(self) -> dict[str, str]:
        root = self.docs_root / "data" / "assets" / "manifest"
        entries = {str(item.get("id")): str(item.get("name") or "") for item in self._entity_index("monsters").get("entries", [])}
        result: dict[str, str] = {}
        for path in root.glob("Monster_*.webp"):
            match = re.fullmatch(r"Monster_(\d+)\.webp", path.name)
            if match and entries.get(match.group(1)):
                result.setdefault(entries[match.group(1)], path.name)
        return result

    def _monster_asset_url(self, entry_id: str) -> str | None:
        root = self.docs_root / "data" / "assets" / "manifest"
        direct = root / f"Monster_{entry_id}.webp"
        if direct.is_file():
            return f"/api/v1/assets/manifest/{direct.name}"
        entry = next((item for item in self._entity_index("monsters").get("entries", []) if str(item.get("id")) == entry_id), None)
        filename = self._monster_images_by_name().get(str(entry.get("name") or "")) if entry else None
        return f"/api/v1/assets/manifest/{filename}" if filename else None

    def _entity_description(self, kind: str, text: str) -> str:
        if kind == "monsters":
            return self._plain_section(self._section(text, "敌对物种介绍"))
        if kind == "relics":
            return self._markdown_plain(self._section(text, "套装效果"))[:1200]
        basic = self._two_column_table(self._section(text, "基本资料"))
        return " · ".join(f"{key}：{value}" for key, value in basic.items())

    def _entity_sections(self, kind: str, text: str) -> list[NamedDescription]:
        wanted = {
            "lightcones": ("基本资料", "叠影效果", "晋阶材料 ID 汇总"),
            "relics": ("套装效果", "其他结构化资料"),
            "monsters": ("敌对物种介绍", "掉落物", "其他结构化资料"),
        }[kind]
        return [
            NamedDescription(name=name, description=self._markdown_plain(value)[:6000])
            for name in wanted
            if (value := self._section(text, name))
        ]

    def _entity_relations(self, kind: str, entry_id: str, text: str) -> list[RelatedEntity]:
        related: list[RelatedEntity] = []
        if kind in {"lightcones", "relics"}:
            field = "recommended_lightcones" if kind == "lightcones" else "recommended_relics"
            for row in self._alignment_report().get("aligned", []):
                if row.get("kind") != "character" or not any(str(x.get("id")) == entry_id for x in row.get(field, [])):
                    continue
                character_id = str(row.get("canonical_id"))
                character = next((x for x in self.list_characters() if x.id == character_id), None)
                if character:
                    related.append(RelatedEntity(**character.model_dump(), kind="characters", subtitle=f"{character.element} · {character.path}"))
        item_ids = list(dict.fromkeys(re.findall(r"\|\s*(\d{1,9})\s*\|", text)))
        for item_id in item_ids:
            item = self._items().get(item_id)
            if not item or str(item.get("item_name") or "") in {"", "..."}:
                continue
            base = self._related_item(item_id, item)
            related.append(RelatedEntity(id=base.id, name=base.name, kind="items", subtitle=base.type, image_url=base.image_url, image_status="official" if "placeholders" not in (base.image_url or "") else "category_placeholder"))
            if len(related) >= 24:
                break
        return related

    def _item_related_characters(self, item_id: str) -> list[RelatedEntity]:
        related: list[RelatedEntity] = []
        for character in self.list_characters():
            assets = self._asset_manifest("characters", character.id)
            if item_id in self._related_item_ids(assets, character.id):
                related.append(RelatedEntity(**character.model_dump(), kind="characters", subtitle=f"{character.element} · {character.path}"))
        return related

    def _related_item_ids(self, assets: dict[str, Any], character_id: str) -> list[str]:
        seen: set[str] = set()
        for asset in assets.get("assets", []):
            match = re.search(r"/itemfigures/(\d+)\.webp$", str(asset.get("url") or ""), re.I)
            if not match:
                continue
            item_id = match.group(1)
            entry = self._items().get(item_id)
            if (
                item_id in seen
                or not entry
                or entry.get("item_main_type") != "Material"
                or not entry.get("is_visible", True)
            ):
                continue
            seen.add(item_id)

        # A page may lazy-load only one tier of a three-item material family.
        # Complete common-drop and trace families by their canonical item_group.
        for item_id in tuple(seen):
            entry = self._items().get(item_id, {})
            if entry.get("item_sub_type") not in {"CommonMonsterDrop", "TracePath"}:
                continue
            group = entry.get("item_group")
            for sibling_id, sibling in self._items().items():
                if (
                    sibling.get("item_group") == group
                    and sibling.get("item_sub_type") == entry.get("item_sub_type")
                    and sibling.get("is_visible", True)
                    and str(sibling.get("item_name") or "") not in {"", "..."}
                ):
                    seen.add(sibling_id)

        # Every character consumes Tracks of Destiny and one boss material from
        # Echo of War. Newer pages omit the latter from their initial asset set.
        seen.add("241")
        weekly_id = CHARACTER_WEEKLY_MATERIALS.get(character_id)
        if weekly_id:
            seen.add(weekly_id)

        def sort_key(item_id: str) -> tuple[int, int, int]:
            entry = self._items().get(item_id, {})
            subtype = str(entry.get("item_sub_type") or "")
            weekly_track = 1 if item_id == "241" else 0
            return (
                MATERIAL_TYPE_ORDER.get(subtype, 9),
                weekly_track,
                RARITY_ORDER.get(str(entry.get("rarity") or ""), 0),
            )

        return sorted(seen, key=sort_key)

    def _related_items(
        self, assets: dict[str, Any], character_id: str
    ) -> list[RelatedItem]:
        return [
            self._related_item(item_id, self._items()[item_id])
            for item_id in self._related_item_ids(assets, character_id)
        ][:9]

    def _related_item(self, item_id: str, entry: dict[str, Any]) -> RelatedItem:
        override = ITEM_OVERRIDES.get(item_id, {})
        return RelatedItem(
            id=item_id,
            name=str(override.get("item_name") or entry.get("item_name") or item_id),
            rarity=str(entry.get("rarity") or "Normal"),
            type=str(entry.get("item_sub_type") or entry.get("item_main_type") or "Item"),
            description=self._clean_html(
                str(override.get("item_desc") or entry.get("item_desc") or "")
            ),
            image_url=self._item_image_url(item_id, entry),
        )

    def _item_image_url(self, item_id: str, entry: dict[str, Any]) -> str:
        fields = (
            "item_figure_icon_path",
            "item_icon_path",
            "item_currency_icon_path",
            "item_avatar_icon_path",
        )
        seen: set[str] = set()
        for field in fields:
            resource_id = Path(str(entry.get(field) or "")).stem
            if not resource_id or resource_id in seen:
                continue
            seen.add(resource_id)
            image = self._local_asset("items", item_id, f"{resource_id}.webp")
            if image:
                return image
            shared = self._item_resource_index().get(resource_id)
            if shared:
                return shared
        return "/api/v1/assets/placeholders/item.svg"

    @lru_cache(maxsize=1)
    def _item_resource_index(self) -> dict[str, str]:
        root = self.docs_root / "data" / "assets" / "items"
        index: dict[str, str] = {}
        for path in root.glob("*/raw/*.webp"):
            owner_id = path.parent.parent.name
            index.setdefault(
                path.stem,
                f"/api/v1/assets/items/{owner_id}/raw/{path.name}",
            )
        return index

    def _memory_skills(
        self, character_id: str, assets: dict[str, Any]
    ) -> list[NamedDescription]:
        character = (
            self._character_skill_supplements()
            .get("characters", {})
            .get(character_id, {})
        )
        result: list[NamedDescription] = []
        for entry in character.get("skills", []):
            entry_type = str(entry.get("type") or "")
            suffix = "ServantPassive" if entry_type == "忆灵天赋" else r"Servant(?:\d+)?"
            icon_url = self._find_asset(
                assets,
                rf"/SkillIcon_1{re.escape(character_id)}_{suffix}\.webp$",
            )
            result.append(
                NamedDescription(
                    name=str(entry.get("name") or "忆灵技能"),
                    description=self._clean_game_tokens(
                        str(entry.get("description") or "")
                    ),
                    type=entry_type or "忆灵技能",
                    image_url=icon_url,
                )
            )
        return result

    def _supplement_eidolons(
        self, body: str, assets: dict[str, Any], character_id: str
    ) -> list[NamedDescription]:
        content = self._section(body, "角色星魂")
        entries: list[NamedDescription] = []
        pattern = re.compile(
            r"^[【\[]([1-6])[】\]]\s*(.+?)\s*$\n(.*?)(?=^[【\[](?:[1-6])[】\]]|\Z)",
            re.M | re.S,
        )
        for match in pattern.finditer(content):
            index = int(match.group(1))
            description = self._plain_section(match.group(3))
            if not description:
                continue
            entries.append(
                NamedDescription(
                    name=match.group(2).strip(),
                    description=self._clean_game_tokens(description),
                    type="星魂",
                    image_url=self._find_asset(
                        assets,
                        rf"/{re.escape(character_id)}_Rank_{index}\.webp$",
                    ),
                )
            )
        return entries

    def _named_entries(
        self,
        text: str,
        section_name: str,
        assets: dict[str, Any],
        character_id: str,
        skills: bool = False,
    ) -> list[NamedDescription]:
        section = self._section(text, section_name)
        entries: list[NamedDescription] = []
        for index, match in enumerate(
            re.finditer(r"^###\s+(.+?)\s*\n(.*?)(?=^###\s+|\Z)", section, re.M | re.S),
            start=1,
        ):
            title, body = match.group(1).strip(), match.group(2).strip()
            description = self._plain_section(body)
            if not description or title.startswith("行迹 point"):
                continue
            entry_type = None
            icon_url = None
            if skills:
                type_match = re.search(r"（(.+?)）", title)
                entry_type = type_match.group(1) if type_match else None
                if entry_type == "MazeNormal":
                    continue
                title = re.sub(r"（[^（）]+）\s*$", "", title).strip()
                icon_key = SKILL_ICONS.get(entry_type or "")
                if icon_key:
                    icon_url = self._find_asset(
                        assets,
                        rf"/SkillIcon_{re.escape(character_id)}_{icon_key}\.webp$",
                    )
            else:
                icon_url = self._find_asset(
                    assets, rf"/{re.escape(character_id)}_Rank_{index}\.webp$"
                )
            entries.append(
                NamedDescription(
                    name=title,
                    description=self._clean_game_tokens(description),
                    type=entry_type,
                    image_url=icon_url,
                )
            )
        return entries

    @staticmethod
    def _section(text: str, name: str) -> str:
        match = re.search(rf"^##\s+{re.escape(name)}\s*$\n(.*?)(?=^##\s+|\Z)", text, re.M | re.S)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _plain_section(text: str) -> str:
        lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if lines:
                    break
                continue
            if stripped.startswith(("|", ">", "- **", "- `")):
                break
            lines.append(stripped)
        return "\n".join(lines)

    @staticmethod
    def _two_column_table(text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in text.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == 2 and cells[0] not in {"字段", "---"} and not cells[0].startswith("---"):
                result[cells[0]] = cells[1]
        return result

    @staticmethod
    def _level_80_stats(text: str) -> dict[str, str]:
        match = re.search(
            r"###\s+80 级基础属性估算\s*\n\s*\|([^\n]+)\|\s*\n\s*\|[-:|\s]+\|\s*\n\s*\|([^\n]+)\|",
            text,
        )
        if not match:
            return {}
        headers = [item.strip() for item in match.group(1).split("|")]
        values = [item.strip() for item in match.group(2).split("|")]
        return dict(zip(headers, values, strict=False))

    @staticmethod
    def _find_asset(manifest: dict[str, Any], pattern: str) -> str | None:
        for asset in manifest.get("assets", []):
            if re.search(pattern, str(asset.get("url") or ""), re.I):
                public_url = str(asset.get("public_url") or "")
                return f"/api/v1{public_url}" if public_url.startswith("/assets/") else public_url
        return None

    def _local_asset(self, kind: str, entry_id: str, filename: str) -> str | None:
        path = self.docs_root / "data" / "assets" / kind / entry_id / "raw" / filename
        if not path.is_file():
            return None
        return f"/api/v1/assets/{kind}/{entry_id}/raw/{filename}"

    @staticmethod
    def _clean_html(value: str) -> str:
        value = value.replace("\\n", "\n")
        return unescape(re.sub(r"<[^>]+>", "", value)).strip()

    @staticmethod
    def _clean_game_tokens(value: str) -> str:
        value = re.sub(r"#\d+\[[^\]]+\]%?", "相应数值", value)
        value = re.sub(r"\{TextID#[^}]+\}", "待确认条目", value)
        return value.strip()

    @staticmethod
    def _markdown_plain(value: str) -> str:
        lines: list[str] = []
        for line in value.splitlines():
            text = line.strip()
            if not text or text.startswith(("|---", "####")):
                continue
            text = re.sub(r"^#{1,4}\s+", "", text)
            if text.startswith("|"):
                cells = [x.strip() for x in text.strip("|").split("|") if x.strip()]
                text = "：".join(cells)
            text = re.sub(r"[`*_>]", "", text).strip()
            if text:
                lines.append(text)
        return "\n".join(lines)
