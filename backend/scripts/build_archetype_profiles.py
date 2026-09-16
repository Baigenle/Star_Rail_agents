"""构建角色体系（archetype）档案。

为每名角色生成体系感知配队算法所需的结构化数据：
- 确定性部分：从角色 markdown 解析 80 级面板与技能文本中的缩放线索；
- LLM 部分：由推理模型标注主缩放属性、体系归属、引擎标签与战技点画像；
- 无可用模型时回退到关键词规则，保证脚本在任何环境都能产出数据。

输出 docs/team_knowledge/character_archetypes.json（数据文件，可人工修订），
并附带 docs/team_knowledge/archetype_alignment_report.json 对齐报告。
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.llm.base import LLMMessage  # noqa: E402
from app.llm.providers import create_llm_provider  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_ROOT = Path(settings.docs_root) if settings.docs_root else (
    BACKEND_ROOT.parent / "docs"
)
CHARACTER_MD_DIRNAME = "hsr_nanoka_characters/characters"
LEVEL80_TABLE = re.compile(
    r"###\s*80\s*级基础属性估算\s*\n+\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\n"
    r"\|[-:|]+\|\n"
    r"\|\s*(?P<hp>[\d.]+)\s*\|\s*(?P<atk>[\d.]+)\s*\|\s*(?P<def>[\d.]+)"
    r"\s*\|\s*(?P<speed>[\d.]+)\s*\|\s*(?P<taunt>[\d.]+)\s*\|"
)
SKILL_SECTION = re.compile(
    r"##\s*技能\s*(?P<body>.*?)(?:\n##\s|\Z)", re.DOTALL
)
STAT_KEYWORDS = {
    "hp": ("生命上限", "最大生命", "生命值消耗", "当前生命"),
    "defense": ("防御力", "防御"),
    "attack": ("攻击力", "攻击"),
}
ARCHETYPE_TAG_RULES = {
    "超击破": ("击破",),
    "持续伤害": ("持续伤害",),
    "追加攻击": ("追加攻击", "反击"),
    "召唤": ("召唤",),
    "记忆忆灵": ("忆灵",),
    "暴击直伤": ("暴击",),
}
SP_PROFILE_RULES = {
    "positive": ("战技点", "恢复战技点", "强化普攻"),
    "hungry": ("消耗战技点", "战技点消耗"),
}
PRIMARY_STAT_FALLBACK = {
    # 生命/防御缩放的代表性角色：技能文本关键词之外的第二道保险。
    "刃": "hp",
    "遐蝶": "hp",
    "白厄": "hp",
    "风堇": "hp",
    "砂金": "defense",
    "丹恒·腾荒": "defense",
}

SYSTEM_PROMPT = """你是星穹铁道战斗体系标注器。根据角色的命途、属性、定位、机制标签、
80 级面板和技能文本，输出严格的 JSON（不要 Markdown）：
{
 "primary_stat": "attack|hp|defense",
 "archetypes": ["从这些体系中选择1-2个：暴击直伤、超击破、持续伤害、追加攻击、召唤、记忆忆灵、黄泉充能、增益辅助、生存辅助、减抗辅助"],
 "engine_tags": ["该角色为体系提供的引擎能力，如：引爆DoT、超击破转化、拉条、产战技点、充能"],
 "sp_profile": "positive|neutral|hungry",
 "core_mechanic": "一句话概括该角色的资源循环（不超过40字）"
}
判定规则：
1. primary_stat 看技能伤害公式引用的属性：写"生命上限"→hp，"防御力"→defense，否则 attack。
2. sp_profile：多数回合普攻且产点→positive；每回合战技且耗点→hungry；其余 neutral。
3. 辅助/生存角色 primary_stat 一般为 attack，但体系与 engine_tags 必须准确。
4. 输出仅 JSON。"""


def parse_character_markdown(md_path: Path) -> dict | None:
    text = md_path.read_text(encoding="utf-8")
    match = LEVEL80_TABLE.search(text)
    stats = None
    if match:
        stats = {
            "hp": float(match.group("hp")),
            "attack": float(match.group("atk")),
            "defense": float(match.group("def")),
            "speed": float(match.group("speed")),
        }
    skill_match = SKILL_SECTION.search(text)
    skill_text = re.sub(r"\s+", " ", skill_match.group("body"))[:3000] if skill_match else ""
    name_match = re.search(r'^# (.+)$', text, re.MULTILINE)
    return {
        "name": name_match.group(1).strip() if name_match else md_path.stem,
        "stats": stats,
        "skill_text": skill_text,
    }


def detect_primary_stat(name: str, stats: dict | None, skill_text: str) -> str:
    for stat, keywords in STAT_KEYWORDS.items():
        if stat == "hp" and any(k in skill_text for k in keywords) and "生命上限的" in skill_text:
            return "hp"
        if stat == "defense" and any(f"{k}的" in skill_text or f"{k}伤害" in skill_text for k in keywords):
            return "defense"
    if "生命上限" in skill_text:
        return "hp"
    if name in PRIMARY_STAT_FALLBACK:
        return PRIMARY_STAT_FALLBACK[name]
    return "attack"


def detect_archetypes(tags: list[str]) -> list[str]:
    archetypes: list[str] = []
    for archetype, keywords in ARCHETYPE_TAG_RULES.items():
        if any(keyword in tags for keyword in keywords):
            archetypes.append(archetype)
    if not archetypes:
        archetypes.append("暴击直伤")
    return archetypes


def detect_sp_profile(tags: list[str]) -> str:
    for profile, keywords in SP_PROFILE_RULES.items():
        if any(keyword in " ".join(tags) for keyword in keywords):
            return profile
    return "neutral"


def rule_based_profile(name: str, tags: list[str], parsed: dict) -> dict:
    return {
        "primary_stat": detect_primary_stat(name, parsed.get("stats"), parsed.get("skill_text", "")),
        "archetypes": detect_archetypes(tags),
        "engine_tags": list(tags)[:6],
        "sp_profile": detect_sp_profile(tags),
        "core_mechanic": "由标签规则推断，建议人工修订。",
        "model": "rule_fallback",
    }


async def llm_profile(llm, name: str, path_name: str, element: str, roles: list[str],
                      tags: list[str], parsed: dict) -> dict | None:
    payload = {
        "name": name,
        "path": path_name,
        "element": element,
        "roles": roles,
        "mechanic_tags": tags,
        "level80_stats": parsed.get("stats"),
        "skill_text_excerpt": parsed.get("skill_text", "")[:1800],
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            raw = await llm.complete([
                LLMMessage(role="system", content=SYSTEM_PROMPT),
                LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
            ])
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("response did not contain JSON")
            data = json.loads(raw[start:end + 1])
            if data.get("primary_stat") not in {"attack", "hp", "defense"}:
                raise ValueError("invalid primary_stat")
            if data.get("sp_profile") not in {"positive", "neutral", "hungry"}:
                data["sp_profile"] = "neutral"
            data["archetypes"] = [str(item) for item in (data.get("archetypes") or [])][:3]
            data["engine_tags"] = [str(item) for item in (data.get("engine_tags") or [])][:6]
            data["core_mechanic"] = str(data.get("core_mechanic") or "")[:60]
            data["model"] = llm.name
            return data
        except Exception as exc:  # noqa: BLE001 - 限流或格式抖动时退避重试
            last_error = exc
            await asyncio.sleep(2 * (attempt + 1))
    print(f"  {name} LLM 标注失败（{type(last_error).__name__}），回退规则。", flush=True)
    return None


async def run(docs_root: Path, use_llm: bool, limit: int | None) -> dict:
    profiles_path = docs_root / "team_knowledge" / "official_combat_profiles.json"
    raw_profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    profiles = (
        raw_profiles["characters"]
        if isinstance(raw_profiles, dict) and "characters" in raw_profiles
        else raw_profiles
    )
    if isinstance(profiles, dict):
        profiles = list(profiles.values())
    md_dir = docs_root / CHARACTER_MD_DIRNAME
    llm = create_llm_provider(settings, workload="reasoning") if use_llm else None

    records: dict[str, dict] = {}
    llm_hits = 0
    targets = profiles if limit is None else profiles[:limit]

    # 断点续跑：跳过上一轮已由 LLM 标注过的角色，避免重复消耗 token。
    existing_path = docs_root / "team_knowledge" / "character_archetypes.json"
    if existing_path.exists():
        existing = json.loads(existing_path.read_text(encoding="utf-8")).get(
            "characters", {}
        )
        for character_id, item in existing.items():
            if item.get("model") and item.get("model") != "rule_fallback":
                records[str(character_id)] = item
        if records:
            print(f"断点续跑：已恢复 {len(records)} 个 LLM 结果。", flush=True)

    concurrency = 4
    llm_done = len(records)

    async def classify(profile: dict) -> tuple[str, str, dict, dict, list[str], dict | None]:
        character_id = str(profile.get("character_id") or "")
        name = str(profile.get("name") or "")
        md_path = md_dir / f"{character_id}_{name}.md"
        parsed = (
            parse_character_markdown(md_path)
            if md_path.exists()
            else {"name": name, "stats": None, "skill_text": ""}
        )
        tags = list(profile.get("mechanic_tags") or [])
        data = None
        if llm:
            data = await llm_profile(
                llm, name,
                str(profile.get("path") or ""),
                str(profile.get("element") or ""),
                list(profile.get("roles") or []),
                tags, parsed,
            )
        return character_id, name, parsed, profile, tags, data

    pending = [p for p in targets if str(p.get("character_id") or "") not in records]
    for chunk_start in range(0, len(pending), concurrency):
        chunk = pending[chunk_start : chunk_start + concurrency]
        results = await asyncio.gather(*(classify(profile) for profile in chunk))
        for character_id, name, parsed, profile, tags, data in results:
            if data is None:
                data = rule_based_profile(name, tags, parsed)
            else:
                llm_hits += 1
            records[character_id] = {
                "name": name,
                "path": profile.get("path"),
                "element": profile.get("element"),
                "roles": profile.get("roles"),
                "mechanic_tags": tags,
                "level80_stats": parsed.get("stats"),
                **data,
            }
            print(
                f"[{len(records)}/{len(targets)}] {name} -> "
                f"{data.get('archetypes')} (model={data.get('model')})",
                flush=True,
            )
        # 增量落盘：中断后已有部分结果可查，不丢整批进度。
        if len(records) - llm_done >= concurrency:
            llm_done = len(records)
            _write_dataset(docs_root, records, llm_hits)

    dataset = build_dataset(records, llm_hits)
    write_dataset(docs_root, dataset)
    return dataset


def build_dataset(records: dict, llm_hits: int) -> dict:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(records),
        "llm_classified": llm_hits,
        "rule_fallback": len(records) - llm_hits,
        "missing_markdown": [
            record["name"]
            for record in records.values()
            if record["level80_stats"] is None
        ],
        "primary_stat_distribution": _count_by(records, "primary_stat"),
        "sp_profile_distribution": _count_by(records, "sp_profile"),
        "archetype_distribution": _count_archetypes(records),
    }
    return {
        "version": "4.4",
        "generated_at": report["generated_at"],
        "scoring_note": "体系感知配队算法的唯一角色体系数据源；允许人工修订。",
        "characters": records,
        "report": report,
    }


def write_dataset(docs_root: Path, dataset: dict) -> None:
    out_dir = docs_root / "team_knowledge"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "character_archetypes.json").write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "archetype_alignment_report.json").write_text(
        json.dumps(dataset["report"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_dataset(docs_root: Path, records: dict, llm_hits: int) -> None:
    write_dataset(docs_root, build_dataset(records, llm_hits))


def _count_by(records: dict, field: str) -> dict:
    counter: dict[str, int] = {}
    for record in records.values():
        key = str(record.get(field))
        counter[key] = counter.get(key, 0) + 1
    return counter


def _count_archetypes(records: dict) -> dict:
    counter: dict[str, int] = {}
    for record in records.values():
        for archetype in record.get("archetypes", []):
            counter[archetype] = counter.get(archetype, 0) + 1
    return dict(sorted(counter.items(), key=lambda kv: -kv[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-root", type=Path, default=DEFAULT_DOCS_ROOT)
    parser.add_argument("--no-llm", action="store_true", help="跳过 LLM，仅规则推断")
    parser.add_argument("--limit", type=int, default=None, help="仅处理前 N 个角色（调试）")
    args = parser.parse_args()

    dataset = asyncio.run(run(args.docs_root, use_llm=not args.no_llm, limit=args.limit))
    print(json.dumps(dataset["report"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
