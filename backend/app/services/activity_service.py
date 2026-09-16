import json
from pathlib import Path
from typing import Any


class ActivityService:
    DETAIL_VERSION = "4.4"

    def __init__(self, docs_root: Path) -> None:
        source = docs_root / "activity_knowledge" / "activities.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        self.policy = payload.get("policy", {})
        self.activities: list[dict[str, Any]] = payload.get("activities", [])
        self.by_id = {item["id"]: item for item in self.activities}

    def list(self, *, version: str | None = None) -> list[dict[str, Any]]:
        items = self.activities
        if version:
            items = [item for item in items if item.get("version") == version]
        return [self._public(item, include_detail=False) for item in items]

    def get(self, activity_id: str) -> dict[str, Any] | None:
        item = self.by_id.get(activity_id)
        if item is None:
            return None
        return self._public(item, include_detail=True)

    def accepts_guides(self, activity_id: str) -> bool:
        item = self.by_id.get(activity_id)
        return bool(
            item
            and item.get("version") == self.DETAIL_VERSION
            and item.get("community_submission_available")
        )

    def title(self, activity_id: str) -> str:
        return str(self.by_id.get(activity_id, {}).get("title") or activity_id)

    def _public(
        self, item: dict[str, Any], *, include_detail: bool
    ) -> dict[str, Any]:
        is_detailed = (
            item.get("version") == self.DETAIL_VERSION
            and bool(item.get("detail_available"))
        )
        image = dict(item.get("image") or {})
        if image.get("api_path"):
            image["api_path"] = str(image["api_path"]).replace(
                "/api/v1/activities/assets/",
                "/api/v1/activities/assets/",
            )
        return {
            "id": item["id"],
            "title": item.get("title", ""),
            "version": item.get("version", ""),
            "schedule": item.get("schedule", ""),
            "types": item.get("types", []),
            "tags": item.get("tags", []),
            "image": image or None,
            "detail_available": is_detailed,
            "official_guide_available": bool(
                is_detailed and item.get("official_guide_available")
            ),
            "community_submission_available": bool(
                is_detailed and item.get("community_submission_available")
            ),
            "detail": item.get("detail") if include_detail and is_detailed else None,
            "source": item.get("source", {}),
        }
