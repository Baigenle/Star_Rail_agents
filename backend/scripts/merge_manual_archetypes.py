"""合并人工修订的体系分类到 character_archetypes.json。

保留文件中已有的 LLM 结果；对其余角色按领域知识写入分类，
确定性字段（80 级面板、机制标签）仍从原始数据提取。
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DOCS = Path("../docs").resolve()
PROFILES = DOCS / "team_knowledge" / "official_combat_profiles.json"
MD_DIR = DOCS / "hsr_nanoka_characters" / "characters"
OUT = DOCS / "team_knowledge" / "character_archetypes.json"

LEVEL80_TABLE = re.compile(
    r"###\s*80\s*级基础属性估算\s*\n+\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|\n"
    r"\|[-:|]+\|\n"
    r"\|\s*(?P<hp>[\d.]+)\s*\|\s*(?P<atk>[\d.]+)\s*\|\s*(?P<def>[\d.]+)"
    r"\s*\|\s*(?P<speed>[\d.]+)\s*\|\s*(?P<taunt>[\d.]+)\s*\|"
)

# 体系词表与 team_archetype_service.CORE_ENGINE_TAGS 对齐：
# 超击破 / 持续伤害 / 追加攻击 / 召唤 / 记忆忆灵 / 黄泉充能 / 暴击直伤
# 增益辅助 / 生存辅助 / 减抗辅助
# (primary_stat, archetypes, sp_profile, core_mechanic)
CLASSIFICATION = {
    "1001": ("defense", ["生存辅助"], "neutral", "提供单体护盾与冻结反制，护盾量吃防御力。"),
    "1002": ("attack", ["暴击直伤"], "neutral", "巡猎单体风伤，终结技降风抗。"),
    "1003": ("attack", ["追加攻击", "暴击直伤"], "neutral", "弱点击破后触发追击，战技群攻带灼烧。"),
    "1004": ("attack", ["减抗辅助"], "hungry", "禁锢减速推条，持续施加负面效果为黄泉充能。"),
    "1005": ("attack", ["持续伤害"], "hungry", "DoT 体系引爆器：终结技引爆全部持续伤害并追加雷伤。"),
    "1006": ("attack", ["减抗辅助"], "neutral", "植入弱点、降防降抗，破盾后减免全抗。"),
    "1008": ("attack", ["暴击直伤"], "neutral", "低血量增伤的雷伤输出，自带战技治疗。"),
    "1009": ("attack", ["增益辅助"], "positive", "叠加攻击力与全队速度加成，终结技回能。"),
    "1013": ("attack", ["追加攻击", "暴击直伤"], "neutral", "转圈圈追击收割残局，击破触发额外追击。"),
    "1014": ("attack", ["暴击直伤"], "neutral", "风伤爆发输出，普攻回能支撑高频终结技。"),
    "1015": ("attack", ["追加攻击", "暴击直伤"], "hungry", "充能箭雨追击主C，高频消耗战技点。"),
    "1101": ("attack", ["增益辅助"], "hungry", "战技拉条并提升暴击伤害，是暴击主C的经典引擎。"),
    "1102": ("attack", ["暴击直伤"], "hungry", "量子巡猎，击杀再现提供额外行动。"),
    "1103": ("attack", ["持续伤害", "暴击直伤"], "hungry", "智识雷伤并施加感电持续伤害。"),
    "1104": ("defense", ["生存辅助"], "positive", "全队大盾抵挡爆发，护盾量吃防御力。"),
    "1105": ("hp", ["生存辅助"], "positive", "单体急救与持续回复，治疗量吃生命上限。"),
    "1106": ("attack", ["减抗辅助"], "positive", "终结技大范围减防，是减防体系的核心辅助。"),
    "1107": ("attack", ["追加攻击", "暴击直伤"], "neutral", "受击反制追击体系主C，自带减伤与嘲讽。"),
    "1108": ("attack", ["持续伤害"], "hungry", "风化叠层施加者，为 DoT 体系铺伤。"),
    "1109": ("attack", ["持续伤害", "暴击直伤"], "hungry", "灼烧火伤输出，强化战技消耗战技点。"),
    "1110": ("hp", ["生存辅助"], "positive", "量子治疗并附加强化，治疗量吃生命上限。"),
    "1111": ("attack", ["持续伤害"], "hungry", "拳击灼烧 DoT 副C，需要近身叠层。"),
    "1112": ("attack", ["追加攻击"], "hungry", "账账追击主C，负债标记易伤放大全队追击。"),
    "1201": ("attack", ["暴击直伤"], "positive", "筛点强化普攻的群攻智识，最产战技点的输出。"),
    "1202": ("attack", ["增益辅助"], "positive", "攻击加成与能量充电双引擎，终结技附雷。"),
    "1203": ("attack", ["生存辅助"], "positive", "被动自动治疗加净化驱散，治疗量吃攻击力。"),
    "1204": ("attack", ["召唤", "追加攻击"], "hungry", "神君召唤体系主C，多段追加攻击输出。"),
    "1205": ("hp", ["暴击直伤", "追加攻击"], "positive", "生命消耗转输出的追击主C，强化普攻产点。"),
    "1206": ("attack", ["暴击直伤", "超击破"], "hungry", "物理巡猎，降防与击破拉条服务速攻。"),
    "1207": ("attack", ["增益辅助"], "hungry", "攻击与暴击加成辅助，需要配速控制 buff 覆盖。"),
    "1208": ("hp", ["生存辅助"], "neutral", "伤害分摊与暴击率光环，提供队伍生存兜底。"),
    "1209": ("attack", ["暴击直伤", "追加攻击"], "hungry", "高暴击巡猎，受增益时触发追加攻击。"),
    "1210": ("attack", ["持续伤害"], "hungry", "火化 DoT 施加者，终结技引爆灼烧。"),
    "1211": ("hp", ["生存辅助"], "positive", "群体治疗加复生庇佑，治疗量吃生命上限。"),
    "1212": ("attack", ["暴击直伤"], "hungry", "镜魄强化态自拉条暴击输出，经典 hypercarry。"),
    "1213": ("attack", ["暴击直伤"], "hungry", "消耗战技点强化攻击的龙形态输出。"),
    "1214": ("attack", ["追加攻击", "超击破"], "neutral", "击破转追击的量子输出，吃击破特攻。"),
    "1215": ("attack", ["增益辅助"], "positive", "产战技点并提升速度与攻击，适配耗点主C。"),
    "1217": ("hp", ["生存辅助", "增益辅助"], "positive", "治疗回能净化三合一，治疗量吃生命上限。"),
    "1218": ("attack", ["持续伤害", "减抗辅助"], "hungry", "灼烧蔓延与减防，黄泉充能高频部件。"),
    "1220": ("attack", ["追加攻击"], "neutral", "全队攻击次数充能的追击主C，队内引擎核心。"),
    "1221": ("attack", ["暴击直伤", "追加攻击"], "neutral", "受击反制格挡反击的暴击输出。"),
    "1222": ("attack", ["生存辅助", "追加攻击"], "positive", "击破拉条的丰饶生存，自带追击输出。"),
    "1223": ("attack", ["追加攻击"], "neutral", "标记敌人的巡猎追击副C。"),
    "1224": ("attack", ["超击破"], "positive", "提供护盾与击破增益，辅助单体击破输出。"),
    "1225": ("attack", ["超击破", "减抗辅助"], "hungry", "超击破引擎：附加弱点与外韧削减，开启全队超击破。"),
    "1301": ("attack", ["生存辅助", "超击破"], "positive", "击破加成的丰饶生存，攻击回血产点。"),
    "1302": ("attack", ["暴击直伤"], "hungry", "终结技群爆的智识输出，依赖能量循环。"),
    "1303": ("attack", ["超击破", "增益辅助"], "neutral", "击破效率与减抗核心，延长弱击破窗口。"),
    "1304": ("defense", ["生存辅助", "追加攻击"], "positive", "防御转护盾与追击的生存位，盾量吃防御。"),
    "1305": ("attack", ["追加攻击"], "neutral", "追击输出并施加易伤，被追击目标增伤。"),
    "1306": ("attack", ["增益辅助"], "positive", "战技点引擎：产点同时拉条与提升暴击伤害。"),
    "1307": ("attack", ["持续伤害", "减抗辅助"], "hungry", "奥迹叠层 DoT 核心，依赖多种 debuff 叠加。"),
    "1308": ("attack", ["黄泉充能"], "hungry", "施加 debuff 充能终结技的减抗输出。"),
    "1309": ("attack", ["增益辅助"], "neutral", "全队拉条与追击暴伤加成，协奏期强化追击队。"),
    "1310": ("attack", ["超击破"], "hungry", "击破转攻击的超击破主C，终结技进入强化态。"),
    "1312": ("attack", ["暴击直伤"], "neutral", "冻结控场的多段群攻输出。"),
    "1313": ("attack", ["增益辅助"], "hungry", "召唤物与忆灵拉条引擎，提升暴伤并回能。"),
    "1314": ("attack", ["追加攻击", "暴击直伤"], "neutral", "古董收租追击的智识群攻。"),
    "1315": ("attack", ["超击破"], "hungry", "击破特攻转攻击的巡猎，盗贼决斗拉条。"),
    "1317": ("attack", ["超击破"], "hungry", "智识击破输出，强化普攻清杂并减抗。"),
    "1321": ("attack", ["超击破", "减抗辅助"], "neutral", "侵染减抗与追击的击破辅助。"),
    "1401": ("attack", ["暴击直伤"], "hungry", "魔灵紫叠层群攻主C，终结技自拉条再爆发。"),
    "1402": ("attack", ["召唤", "记忆忆灵"], "hungry", "忆灵召唤主C，能量循环支撑高频行动。"),
    "1403": ("hp", ["增益辅助", "追加攻击"], "neutral", "生命_scale的减抗辅助，全队受击触发追击。"),
    "1404": ("hp", ["暴击直伤"], "neutral", "生命消耗换输出的毁灭主C，自动拉条。"),
    "1405": ("attack", ["暴击直伤", "减抗辅助"], "hungry", "植入弱点与质性揭露的智识，debuff 高频施加。"),
    "1406": ("attack", ["追加攻击", "减抗辅助"], "neutral", "记录伤害转追击的虚无辅助。"),
    "1407": ("hp", ["记忆忆灵", "暴击直伤"], "hungry", "死龙忆灵体系核心，生命缩放并减全抗。"),
    "1408": ("attack", ["暴击直伤"], "hungry", "命运塑造形态的暴击主C，终结技变身自拉条。"),
    "1409": ("hp", ["记忆忆灵", "生存辅助"], "positive", "忆灵治疗体系：治疗与忆灵行动双引擎。"),
    "1410": ("attack", ["持续伤害", "减抗辅助"], "hungry", "多重 DoT 与减防，效果命中转伤害。"),
    "1412": ("attack", ["增益辅助"], "hungry", "爵位增益引擎：提升战技伤害并拉条。"),
    "1413": ("attack", ["记忆忆灵", "暴击直伤"], "hungry", "忆灵冰伤输出，暴击体系配合忆灵行动。"),
    "1414": ("defense", ["生存辅助", "追加攻击"], "positive", "防御护盾与追击兼具的存护生存。"),
    "1415": ("attack", ["记忆忆灵", "暴击直伤"], "neutral", "忆灵体系输出，暴击配合召唤行动。"),
    # 自建角色：按命途、标签与欢愉/巡猎/智识特性推断
    "1501": ("attack", ["暴击直伤"], "positive", "强化普攻多段扩散的欢愉输出，产战技点。"),
    "1502": ("attack", ["暴击直伤", "减抗辅助"], "neutral", "欢愉输出附带减抗。"),
    "1504": ("attack", ["追加攻击", "暴击直伤"], "hungry", "巡猎追击输出并削减防御。"),
    "1505": ("attack", ["追加攻击", "暴击直伤"], "neutral", "欢愉追击暴击输出。"),
    "1506": ("attack", ["暴击直伤", "增益辅助"], "neutral", "拉条与暴击兼具的欢愉输出。"),
    "1507": ("attack", ["追加攻击", "减抗辅助"], "neutral", "虚无减防追击副C。"),
    "1508": ("attack", ["追加攻击", "暴击直伤"], "hungry", "智识追击暴击输出。"),
    "1509": ("attack", ["追加攻击", "减抗辅助"], "neutral", "毁灭追击输出并削减防御。"),
    "1510": ("attack", ["超击破", "暴击直伤"], "neutral", "智识减抗与击破兼具的群攻输出。"),
}


def level80_stats(character_id: str, name: str) -> dict | None:
    md_path = MD_DIR / f"{character_id}_{name}.md"
    if not md_path.exists():
        return None
    match = LEVEL80_TABLE.search(md_path.read_text(encoding="utf-8"))
    if not match:
        return None
    return {
        "hp": float(match.group("hp")),
        "attack": float(match.group("atk")),
        "defense": float(match.group("def")),
        "speed": float(match.group("speed")),
    }


def main() -> None:
    existing_doc = json.loads(OUT.read_text(encoding="utf-8"))
    existing = existing_doc.get("characters", {})
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))["characters"]

    missing = [
        (cid, profile)
        for cid, profile in profiles.items()
        if cid not in existing
    ]
    filled = 0
    for cid, profile in missing:
        spec = CLASSIFICATION.get(cid)
        if spec is None:
            print(f"!! 缺少分类：{cid} {profile.get('name')}")
            continue
        primary_stat, archetypes, sp_profile, core_mechanic = spec
        tags = list(profile.get("mechanic_tags") or [])
        existing[cid] = {
            "name": profile.get("name"),
            "path": profile.get("path"),
            "element": profile.get("element"),
            "roles": profile.get("roles"),
            "mechanic_tags": tags,
            "level80_stats": level80_stats(cid, str(profile.get("name"))),
            "primary_stat": primary_stat,
            "archetypes": archetypes,
            "engine_tags": tags[:6],
            "sp_profile": sp_profile,
            "core_mechanic": core_mechanic,
            "model": "manual_review",
        }
        filled += 1

    counts = {"llm": 0, "manual": 0, "rule": 0}
    for item in existing.values():
        model = str(item.get("model") or "")
        if model == "manual_review":
            counts["manual"] += 1
        elif model == "rule_fallback":
            counts["rule"] += 1
        else:
            counts["llm"] += 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(existing),
        "llm_classified": counts["llm"],
        "manual_review": counts["manual"],
        "rule_fallback": counts["rule"],
        "missing_markdown": [
            item.get("name")
            for item in existing.values()
            if item.get("level80_stats") is None
        ],
        "primary_stat_distribution": _count(existing, "primary_stat"),
        "sp_profile_distribution": _count(existing, "sp_profile"),
        "archetype_distribution": _count_archetypes(existing),
    }
    dataset = {
        "version": "4.4",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scoring_note": "体系感知配队算法的唯一角色体系数据源；允许人工修订。",
        "characters": existing,
        "report": report,
    }
    OUT.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DOCS / "team_knowledge" / "archetype_alignment_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"补齐 {filled} 个，总数 {len(existing)}；来源：LLM {counts['llm']} / 人工 {counts['manual']} / 规则 {counts['rule']}")


def _count(records: dict, field: str) -> dict:
    counter: dict[str, int] = {}
    for item in records.values():
        key = str(item.get(field))
        counter[key] = counter.get(key, 0) + 1
    return counter


def _count_archetypes(records: dict) -> dict:
    counter: dict[str, int] = {}
    for item in records.values():
        for archetype in item.get("archetypes", []):
            counter[archetype] = counter.get(archetype, 0) + 1
    return dict(sorted(counter.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    main()
