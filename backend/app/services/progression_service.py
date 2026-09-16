import json
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.schemas.catalog import RelatedItem
from app.services.catalog_service import CatalogService, RARITY_ORDER


class ProgressionValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProgressionMaterial:
    key: str
    quantity: int
    item: RelatedItem | None


@dataclass(frozen=True, slots=True)
class ProgressionCalculation:
    character_id: str
    archetype: str
    from_level: int
    to_level: int
    skill_ranges: dict[str, tuple[int, int]]
    total_by_key: dict[str, int]
    materials: list[ProgressionMaterial]


class ProgressionService:
    LEVEL_MIN = 1
    LEVEL_MAX = 80

    def __init__(self, docs_root: Path) -> None:
        self.docs_root = docs_root.resolve()
        self.catalog = CatalogService(self.docs_root)

    @lru_cache(maxsize=1)
    def rules(self) -> dict[str, Any]:
        path = self.docs_root / "progression" / "progression_rules.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @lru_cache(maxsize=1)
    def bindings(self) -> dict[str, dict[str, str]]:
        path = self.docs_root / "progression" / "character_material_bindings.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8")).get("characters", {})
        return {}

    def archetype_for(self, character_id: str) -> str:
        character = self.catalog.get_character(character_id)
        if character is None:
            raise ProgressionValidationError("角色不存在")
        return {"欢愉": "elation", "记忆": "remembrance"}.get(
            character.path, "standard"
        )

    def track_definitions(self, character_id: str) -> dict[str, dict[str, Any]]:
        archetype = self.archetype_for(character_id)
        source = self.rules()["archetypes"][archetype]
        result: dict[str, dict[str, Any]] = {}
        for key, definition in source["tracks"].items():
            expanded = dict(definition)
            template = definition.get("template")
            if template:
                expanded["steps"] = source["templates"][template]["steps"]
            result[key] = expanded
        return result

    def calculate(
        self,
        character_id: str,
        *,
        from_level: int,
        to_level: int,
        skill_ranges: dict[str, tuple[int, int]],
    ) -> ProgressionCalculation:
        if not self.LEVEL_MIN <= from_level <= to_level <= self.LEVEL_MAX:
            raise ProgressionValidationError("角色等级范围必须满足 1 ≤ From ≤ To ≤ 80")

        archetype = self.archetype_for(character_id)
        tracks = self.track_definitions(character_id)
        totals: defaultdict[str, int] = defaultdict(int)

        for target, costs in self.rules()["ascension"]["steps"].items():
            gate = int(target)
            if from_level < gate <= to_level:
                self._merge(totals, costs)

        normalized_ranges: dict[str, tuple[int, int]] = {}
        for track, raw_range in skill_ranges.items():
            if track not in tracks:
                raise ProgressionValidationError(f"当前角色不支持技能轨道：{track}")
            start, end = int(raw_range[0]), int(raw_range[1])
            cap = int(tracks[track]["max_level"])
            if not 1 <= start <= end <= cap:
                raise ProgressionValidationError(
                    f"{tracks[track]['label']}等级范围必须满足 1 ≤ From ≤ To ≤ {cap}"
                )
            normalized_ranges[track] = (start, end)
            for target, costs in tracks[track]["steps"].items():
                target_level = int(target)
                if start < target_level <= end:
                    self._merge(totals, costs)

        total_by_key = {key: value for key, value in totals.items() if value}
        materials = [
            ProgressionMaterial(
                key=key,
                quantity=quantity,
                item=self._material_item(character_id, key),
            )
            for key, quantity in total_by_key.items()
        ]
        return ProgressionCalculation(
            character_id=character_id,
            archetype=archetype,
            from_level=from_level,
            to_level=to_level,
            skill_ranges=normalized_ranges,
            total_by_key=total_by_key,
            materials=materials,
        )

    def _material_item(self, character_id: str, key: str) -> RelatedItem | None:
        item_id = self.bindings().get(character_id, {}).get(key)
        if not item_id:
            return None
        item = self.catalog.get_item(item_id)
        if item is None:
            return None
        return RelatedItem(**item.model_dump())

    @staticmethod
    def _merge(target: defaultdict[str, int], costs: dict[str, int]) -> None:
        for key, value in costs.items():
            target[key] += int(value)


def build_material_binding(
    catalog: CatalogService, character_id: str
) -> tuple[dict[str, str], list[str]]:
    detail = catalog.get_character(character_id)
    if detail is None:
        return {}, ["character_missing"]

    by_type: defaultdict[str, list[RelatedItem]] = defaultdict(list)
    for item in detail.related_items:
        by_type[item.type].append(item)
    for items in by_type.values():
        items.sort(key=lambda item: RARITY_ORDER.get(item.rarity, 0))

    binding: dict[str, str] = {"credits": "2", "tracks": "241"}
    missing: list[str] = []
    for prefix, item_type in (
        ("common", "CommonMonsterDrop"),
        ("trace_path", "TracePath"),
    ):
        items = by_type[item_type]
        for index, rarity in enumerate((2, 3, 4)):
            if index < len(items):
                binding[f"{prefix}_{rarity}"] = items[index].id
            else:
                missing.append(f"{prefix}_{rarity}")
    if by_type["AvatarRank"]:
        binding["ascension"] = by_type["AvatarRank"][0].id
    else:
        missing.append("ascension")

    weekly = [item for item in by_type["WeeklyMonsterDrop"] if item.id != "241"]
    if weekly:
        binding["weekly"] = weekly[0].id
    else:
        missing.append("weekly")
    return binding, missing
