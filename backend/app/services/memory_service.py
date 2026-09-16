import re
from typing import Any

from app.schemas.ai_response import FavoriteCharacterSuggestion, MemorySuggestion


class MemoryService:
    """Extract only explicitly stated preferences; never persists them."""

    _patterns = (
        (
            "resource_priority",
            re.compile(r"(?:资源|体力)(?:优先|主要给|先给)\s*([^，。；\n]{1,40})"),
        ),
        (
            "usual_team",
            re.compile(r"(?:我)?常用(?:队伍|配队)(?:是|：|:)?\s*([^。；\n]{2,80})"),
        ),
        (
            "answer_preference",
            re.compile(r"(?:回答|回复)(?:请|要|希望)?\s*([^。；\n]{2,60})"),
        ),
        (
            "playstyle_preference",
            re.compile(r"我(?:更)?(?:喜欢|偏好)(?:的)?玩法\s*([^，。；\n]{2,40})"),
        ),
    )

    @classmethod
    def suggestions(cls, message: str) -> list[MemorySuggestion]:
        suggestions: list[MemorySuggestion] = []
        seen: set[tuple[str, str]] = set()
        seen_content: set[str] = set()
        for memory_type, pattern in cls._patterns:
            match = pattern.search(message)
            if not match:
                continue
            content = match.group(1).strip(" ：:")
            key = (memory_type, content)
            if not content or key in seen or content in seen_content:
                continue
            seen.add(key)
            seen_content.add(content)
            suggestions.append(
                MemorySuggestion(memory_type=memory_type, content=content)
            )
        return suggestions

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", value).lower()

    @classmethod
    def character_mentions(
        cls,
        message: str,
        characters: list[Any],
        *,
        limit: int | None = 8,
    ) -> list[Any]:
        """Return every explicit, non-overlapping catalog-name match."""
        normalized_message = cls._normalize(message)
        matches: list[tuple[int, int, int, str, Any]] = []
        for character in characters:
            character_id = str(
                character.get("id") if isinstance(character, dict) else character.id
            )
            name = str(
                character.get("name") if isinstance(character, dict) else character.name
            )
            normalized_name = cls._normalize(name)
            if not normalized_name:
                continue
            for occurrence in re.finditer(
                re.escape(normalized_name), normalized_message
            ):
                matches.append(
                    (
                        occurrence.start(),
                        occurrence.end(),
                        len(normalized_name),
                        character_id,
                        character,
                    )
                )

        selected_spans: list[tuple[int, int, int, str, Any]] = []
        seen_ids: set[str] = set()
        for match in sorted(
            matches, key=lambda item: (item[0], -item[2], item[3])
        ):
            start, end, _, character_id, _ = match
            if character_id in seen_ids:
                continue
            if any(
                start < selected_end and end > selected_start
                for selected_start, selected_end, *_ in selected_spans
            ):
                continue
            selected_spans.append(match)
            seen_ids.add(character_id)
            if limit is not None and len(selected_spans) >= limit:
                break
        selected = [item[4] for item in selected_spans]

        # 家族泛名扩展：目录里没有叫「开拓者」的角色，只有
        # 「开拓者·毁灭（星）」等变体。消息命中「开拓者」这类前缀
        # （前缀本身不是独立角色）时，把整个家族计入提及。
        # 丹恒、三月七这类前缀自身就是角色，走上面的精确匹配，不扩展。
        standalone_names = {
            cls._normalize(
                str(item.get("name") if isinstance(item, dict) else item.name)
            )
            for item in characters
        }
        covered_spans = [(start, end) for start, end, *_ in selected_spans]
        family_bases: dict[str, list[Any]] = {}
        for item in characters:
            name = str(
                item.get("name") if isinstance(item, dict) else item.name
            )
            base = cls._normalize(re.split(r"[·（]", name)[0])
            if len(base) < 2 or base in standalone_names:
                continue
            if base not in normalized_message:
                continue
            family_bases.setdefault(base, []).append(item)
        for base, members in family_bases.items():
            occurrence = re.search(re.escape(base), normalized_message)
            if not occurrence:
                continue
            if any(
                occurrence.start() < end and occurrence.end() > start
                for start, end in covered_spans
            ):
                continue
            for member in members:
                member_id = str(
                    member.get("id") if isinstance(member, dict) else member.id
                )
                if member_id in seen_ids:
                    continue
                selected.append(member)
                seen_ids.add(member_id)
        if limit is not None:
            selected = selected[:limit]
        return selected

    @classmethod
    def favorite_character_suggestions(
        cls,
        message: str,
        characters: list[Any],
        *,
        owned_character_ids: set[str],
        favorite_character_ids: set[str],
    ) -> list[FavoriteCharacterSuggestion]:
        """Prompt only after the user explicitly expresses a positive preference."""
        if not cls._expresses_favorite_preference(message):
            return []
        selected = []
        for character in cls.character_mentions(
            message, characters, limit=len(characters)
        ):
            character_id = str(
                character.get("id") if isinstance(character, dict) else character.id
            )
            if character_id in favorite_character_ids:
                continue
            name = str(
                character.get("name") if isinstance(character, dict) else character.name
            )
            selected.append((character_id, name))
            if len(selected) == 3:
                break

        return [
            FavoriteCharacterSuggestion(
                character_id=character_id,
                name=name,
                is_owned=character_id in owned_character_ids,
                prompt=(
                    f"你提到了{name}。要把{name}设为喜欢角色吗？"
                    if character_id in owned_character_ids
                    else f"你提到了{name}。要将{name}加入角色池并设为喜欢吗？"
                ),
            )
            for character_id, name in selected
        ]

    @staticmethod
    def _expresses_favorite_preference(message: str) -> bool:
        if re.search(r"(?:不喜欢|不太喜欢|讨厌|排斥)", message):
            return False
        return bool(
            re.search(
                r"(?:我|本人)?(?:最|很|非常|特别|更)?"
                r"(?:喜欢|偏爱|最爱|钟爱|厨|推)"
                r"|(?:设为喜欢|加入喜欢|标为喜欢)",
                message,
            )
        )
