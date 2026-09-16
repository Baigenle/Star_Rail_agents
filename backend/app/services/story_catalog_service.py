from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from app.services.story_text_cleaner import clean_story_content, speaking_characters


class StoryCatalogService:
    def __init__(self, story_root: Path) -> None:
        self.story_root = story_root
        self._missions = self._load("trailblaze_missions.jsonl")
        self._scenes = self._load("trailblaze_story_chunks.jsonl")
        self._mission_by_id = {
            str(item["mission_id"]): item for item in self._missions
        }
        scenes_by_mission: dict[str, list[dict]] = defaultdict(list)
        for scene in self._scenes:
            scenes_by_mission[str(scene["mission_id"])].append(scene)
        self._scenes_by_mission = {
            mission_id: sorted(
                scenes, key=lambda item: int(item.get("chunk_order") or 0)
            )
            for mission_id, scenes in scenes_by_mission.items()
        }
        self._characters_by_mission = {
            mission_id: self._mission_characters(scenes)
            for mission_id, scenes in self._scenes_by_mission.items()
        }

    def _load(self, name: str) -> list[dict]:
        path = self.story_root / name
        if not path.exists():
            return []
        rows: list[dict] = []
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def list(
        self,
        *,
        q: str = "",
        version: str = "",
        world: str = "",
        mission_type: str = "",
        series: str = "",
        character: str = "",
    ) -> dict:
        query = q.strip().casefold()

        def matches(item: dict) -> bool:
            if version and str(item.get("version", "")) != version:
                return False
            if world and str(item.get("world", "")) != world:
                return False
            if mission_type and str(item.get("mission_type", "")) != mission_type:
                return False
            if series and str(item.get("series_name", "")) != series:
                return False
            mission_id = str(item.get("mission_id") or "")
            characters = self._characters_by_mission.get(mission_id, [])
            if character and character not in characters:
                return False
            searchable = " ".join(
                [
                    str(item.get("mission_name", "")),
                    str(item.get("summary", "")),
                    str(item.get("story_text", "")),
                    str(item.get("series_name", "")),
                    " ".join(characters),
                ]
            ).casefold()
            return not query or query in searchable

        items = []
        for item in self._missions:
            if not matches(item):
                continue
            summary = self._summary(item)
            mission_scenes = self._scenes_by_mission.get(summary["mission_id"], [])
            summary["scene_count"] = len(mission_scenes)
            if character:
                matching_scenes = [
                    scene
                    for scene in mission_scenes
                    if character
                    in speaking_characters(
                        scene.get("characters") or [],
                        str(scene.get("content") or ""),
                    )
                ]
                summary.update(
                    {
                        "matched_character": character,
                        "matched_scene_count": len(matching_scenes),
                        "first_matching_chunk_id": (
                            str(matching_scenes[0].get("chunk_id") or "")
                            if matching_scenes
                            else None
                        ),
                    }
                )
            items.append(summary)
        items.sort(
            key=lambda item: (
                self._version_key(item["version"]),
                item["mission_order"],
            ),
            reverse=True,
        )
        return {
            "items": items,
            "total": len(items),
            "filters": {
                "versions": self._unique("version", version_sort=True),
                "worlds": self._unique("world"),
                "mission_types": self._unique("mission_type"),
                "series": self._unique("series_name"),
            },
        }

    def detail(self, mission_id: str) -> dict | None:
        mission = self._mission_by_id.get(mission_id)
        if mission is None:
            return None
        return {
            **self._summary(mission),
            "story_text": clean_story_content(str(mission.get("story_text") or "")),
            "source_url": str(mission.get("source_url") or ""),
            "previous_mission": mission.get("previous_mission"),
            "next_mission": mission.get("next_mission"),
            "scenes": [
                self._scene_summary(scene)
                for scene in self._scenes_by_mission.get(mission_id, [])
            ],
        }

    def scene(self, mission_id: str, chunk_id: str) -> dict | None:
        scenes = self._scenes_by_mission.get(mission_id, [])
        for index, item in enumerate(scenes):
            if str(item.get("chunk_id")) != chunk_id:
                continue
            return {
                **self._scene_summary(item),
                "mission_id": mission_id,
                "mission_name": str(item.get("mission_name") or ""),
                "content": clean_story_content(str(item.get("content") or "")),
                "source_url": str(item.get("source_url") or ""),
                "previous_chunk_id": (
                    str(scenes[index - 1]["chunk_id"]) if index else None
                ),
                "next_chunk_id": (
                    str(scenes[index + 1]["chunk_id"])
                    if index + 1 < len(scenes)
                    else None
                ),
            }
        return None

    def _summary(self, item: dict) -> dict:
        summary = str(item.get("summary") or "").strip()
        if not summary:
            summary = str(item.get("story_text") or "").strip().replace("\n", " ")
        summary = summary[:240] + ("…" if len(summary) > 240 else "")
        return {
            "mission_id": str(item.get("mission_id") or ""),
            "mission_name": str(item.get("mission_name") or "未命名任务"),
            "mission_type": str(item.get("mission_type") or ""),
            "version": str(item.get("version") or ""),
            "world": str(item.get("world") or ""),
            "series_name": str(item.get("series_name") or ""),
            "mission_order": int(item.get("mission_order") or 0),
            "characters": self._characters_by_mission.get(
                str(item.get("mission_id") or ""), []
            ),
            "summary": summary,
            "scene_count": 0,
            "matched_character": None,
            "matched_scene_count": 0,
            "first_matching_chunk_id": None,
        }

    def _scene_summary(self, item: dict) -> dict:
        return {
            "chunk_id": str(item.get("chunk_id") or ""),
            "chunk_order": int(item.get("chunk_order") or 0),
            "scene_title": str(item.get("scene_title") or "未命名场景"),
            "location": item.get("location"),
            "characters": speaking_characters(
                item.get("characters") or [],
                str(item.get("content") or ""),
            ),
        }

    @staticmethod
    def _mission_characters(scenes: list[dict]) -> list[str]:
        confirmed: list[str] = []
        for scene in scenes:
            for name in speaking_characters(
                scene.get("characters") or [],
                str(scene.get("content") or ""),
            ):
                if name not in confirmed:
                    confirmed.append(name)
        return confirmed

    def _unique(self, key: str, *, version_sort: bool = False) -> list[str]:
        values = {
            str(item.get(key) or "").strip()
            for item in self._missions
            if str(item.get(key) or "").strip()
        }
        return sorted(
            values,
            key=self._version_key if version_sort else None,
            reverse=version_sort,
        )

    @staticmethod
    def _version_key(value: str) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in value.split("."))
        except ValueError:
            return (0,)
