"""社区示例内容填充 + 创作管线 E2E 验证。

以真实用户身份走完整四阶段创作管线（显式字段，不依赖 LLM 抽取），
自查后提交、管理员审核上架，同时验证创作→审核→社区全链路。
"""


import os

import httpx

API = "http://localhost:8000/api/v1"

client = httpx.Client(timeout=120)


def admin_credentials() -> dict[str, str]:
    """从进程环境读取本地管理员凭据，禁止把真实账号写进源码。"""
    account = os.getenv("STAR_RAIL_ADMIN_ACCOUNT", "").strip()
    password = os.getenv("STAR_RAIL_ADMIN_PASSWORD", "")
    if not account or not password:
        raise SystemExit(
            "请先设置 STAR_RAIL_ADMIN_ACCOUNT 和 STAR_RAIL_ADMIN_PASSWORD。"
        )
    return {"account": account, "password": password}


def login() -> dict:
    token = client.post(
        f"{API}/auth/login", json=admin_credentials()
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_character(headers: dict, spec: dict) -> str:
    char_id = client.post(
        f"{API}/custom-characters", headers=headers, json={"name": spec["name"]}
    ).json()["id"]
    session_id = client.post(
        f"{API}/custom-characters/{char_id}/sessions", headers=headers
    ).json()["id"]

    stages = [
        {
            "message": "确认基础身份",
            "fields": {
                "name": spec["name"],
                "rarity": spec["rarity"],
                "element": spec["element"],
                "path": spec["path"],
                "summary": spec["summary"],
            },
        },
        {
            "message": "确认战斗定位",
            "fields": {
                "roles": spec["roles"],
                "core_mechanics": spec["core_mechanics"],
                "mechanic_tags": spec["mechanic_tags"],
            },
        },
        {
            "message": "确认数值与技能",
            "fields": {"base_stats": spec["base_stats"], "skills": spec["skills"]},
        },
        {
            "message": "确认故事与星魂",
            "fields": {
                "special_skills": spec.get("special_skills", {}),
                "story": spec["story"],
                "eidolons": spec["eidolons"],
            },
        },
    ]
    for stage_index, stage_fields in enumerate(stages, start=1):
        message = client.post(
            f"{API}/custom-character-sessions/{session_id}/messages",
            headers=headers,
            json=stage_fields,
        )
        assert message.status_code == 200, (
            f"{spec['name']} 阶段{stage_index} 提交失败: {message.text[:150]}"
        )
        confirm = client.post(
            f"{API}/custom-character-sessions/{session_id}/confirm-stage",
            headers=headers,
        )
        assert confirm.status_code == 200, (
            f"{spec['name']} 阶段{stage_index} 确认失败: {confirm.text[:150]}"
        )
        print(f"  {spec['name']} 阶段{stage_index} ✓")
    return char_id


def review_and_submit(headers: dict, char_id: str, name: str) -> dict:
    review = client.post(
        f"{API}/custom-characters/{char_id}/self-review", headers=headers
    ).json()
    print(
        f"  {name} 自查: 总分{review['overall_score']} "
        f"({review['verdict']}) 硬伤{review['must_fix_count']}项"
    )
    submit = client.post(
        f"{API}/custom-characters/{char_id}/submit", headers=headers
    )
    assert submit.status_code == 200, f"{name} 提交失败: {submit.text[:150]}"
    version_id = submit.json().get("current_draft_version_id") or submit.json().get(
        "id"
    )
    return {"char_id": char_id, "version_id": version_id, "name": name}


CHARACTERS = [
    {
        "name": "霜序",
        "rarity": 5,
        "element": "冰",
        "path": "记忆",
        "summary": "巡回剧团的傀儡师，以忆灵「霜偶」为舞台搭档，为忆灵体系提供护盾与减速控制的辅助位。",
        "roles": ["辅助", "生存"],
        "core_mechanics": "战技为忆灵「霜偶」与我方全体施加【霜幕】护盾；【霜幕】存在时敌方全体速度降低；天赋：忆灵行动时为生命值最低的队友回复少量生命并延长【霜幕】1回合；终结技刷新护盾并冻结敌方全体1回合",
        "mechanic_tags": ["护盾", "忆灵", "控制", "减速", "治疗"],
        "base_stats": {
            "hp": 1180,
            "attack": 480,
            "defence": 520,
            "speed": 98,
            "taunt": 100,
            "energy": 130,
        },
        "skills": {
            "basic": "对指定敌方单体造成冰属性伤害。",
            "skill": "召唤忆灵「霜偶」，为我方全体施加相当于霜序生命上限12%的【霜幕】护盾，持续2回合。",
            "ultimate": "刷新所有【霜幕】护盾，冻结敌方全体1回合，并使敌方全体速度降低15%，持续2回合。",
            "talent": "忆灵「霜偶」行动后，为生命值百分比最低的我方目标回复相当于霜序生命上限5%的生命，并延长【霜幕】持续时间1回合。",
            "technique": "施展傀儡戏开场，使下一次战斗开始时立即召唤「霜偶」并为全队施加【霜幕】。",
        },
        "special_skills": {
            "memosprite_skill": "【霜偶】对敌方全体造成冰属性伤害，并刷新我方全体的【霜幕】护盾。",
            "memosprite_talent": "【霜偶】行动时，使我方全体速度提高8%，持续1回合。",
        },
        "story": "霜序出身于流浪剧团，靠一手傀儡戏走遍星海。当剧团因事故离散后，她将搭档「霜偶」的记忆缝进忆灵，继续把演出带到没有掌声的角落。加入列车后，她把护幕织进每一场战斗，让队友知道：幕布落下之前，没有人会独自面对观众。",
        "eidolons": [
            "【霜幕】护盾量提高20%。",
            "忆灵「霜偶」行动时额外回复5点能量。",
            "终结技等级+2。",
            "敌方全体处于减速状态时，霜序造成的伤害提高18%。",
            "战技等级+2。",
            "【霜幕】被击破时立即重新施加一次50%护盾量的护盾。",
        ],
    },
    {
        "name": "铁岸",
        "rarity": 4,
        "element": "物理",
        "path": "存护",
        "summary": "旧星港的码头监工，把每一次受击都变成反击的号角，为追击体系提供护盾与额外出手。",
        "roles": ["生存", "副C"],
        "core_mechanics": "战技为全队施加【号角】护盾并嘲讽敌方；我方受到攻击时铁岸立即发动追加攻击反击（每回合最多3次）；天赋：追加攻击命中后为全队恢复少量生命；终结技格挡所有伤害并在结束时发动一次大范围反冲",
        "mechanic_tags": ["护盾", "追加攻击", "反击", "嘲讽"],
        "base_stats": {
            "hp": 1300,
            "attack": 560,
            "defence": 560,
            "speed": 96,
            "taunt": 125,
            "energy": 120,
        },
        "skills": {
            "basic": "对指定敌方单体造成物理属性伤害。",
            "skill": "为我方全体施加相当于铁岸防御力180%的【号角】护盾，并嘲讽敌方全体，持续1回合。",
            "ultimate": "进入【终末号角】状态，期间免疫伤害，结束时对敌方全体造成大量物理属性伤害。",
            "talent": "我方目标受到敌方攻击后，铁岸立即对该攻击者发动追加攻击，造成物理属性伤害，该效果每回合最多触发3次；追加攻击命中后为全队回复少量生命。",
            "technique": "吹响号角，使下一次战斗开始时立即获得【号角】护盾并嘲讽敌方。",
        },
        "story": "铁岸在旧星港当了二十年监工，最擅长的就是在风暴里把货柜钉死。退休那天他说：防护从来不是躲在盾后面，而是让每一次撞击都成为还手的鼓点。如今的他把号角带上了列车，为每一次队友遇袭敲响反击。",
        "eidolons": [
            "【号角】护盾量提高15%。",
            "追加攻击的反击次数上限提升至4次。",
            "战技等级+2。",
            "受到攻击时额外恢复5点能量。",
            "天赋等级+2。",
            "反击命中后使目标防御力降低12%，持续2回合。",
        ],
    },
    {
        "name": "绯灯",
        "rarity": 5,
        "element": "火",
        "path": "欢愉",
        "summary": "嘉年华的提灯小丑，以笑点点燃欢愉时刻的火属性输出，与欢愉体系共享笑点资源。",
        "roles": ["主C"],
        "core_mechanics": "战技命中产生【笑点】；【笑点】达到阈值时进入【嘉年华】状态：强化战技变为范围提灯旋舞，伤害随【笑点】层数提高；终结技消耗全部【笑点】对敌方全体释放漫天灯火，每层造成一段火属性欢愉伤害",
        "mechanic_tags": ["欢愉", "多段攻击", "扩散"],
        "base_stats": {
            "hp": 1050,
            "attack": 640,
            "defence": 420,
            "speed": 104,
            "taunt": 100,
            "energy": 140,
        },
        "skills": {
            "basic": "对指定敌方单体造成火属性伤害。",
            "skill": "对指定敌方单体及其相邻目标造成火属性伤害，并获得2点【笑点】。",
            "ultimate": "消耗全部【笑点】，对敌方全体释放漫天灯火，每层【笑点】造成一段火属性欢愉伤害。",
            "talent": "【笑点】达到6层时进入【嘉年华】：战技强化为提灯旋舞，对敌方全体造成火属性伤害，伤害随【笑点】超出6层的部分提高。",
            "technique": "提灯开场，吸引全场敌人注视，使下一次战斗开始时获得3点【笑点】。",
        },
        "story": "没有人知道绯灯的灯芯是从哪场嘉年华捡来的。她只在人群笑得最大声的时候出现，灯火转一圈，烦恼就烧掉一层。她加入列车的理由写在灯罩内侧：把还没笑够的人，一个不落地找到。",
        "eidolons": [
            "【笑点】上限提高4层。",
            "战技额外获得1点【笑点】。",
            "终结技等级+2。",
            "【嘉年华】状态下速度提高12%。",
            "天赋等级+2。",
            "终结技每段灯火有概率使目标灼烧。",
        ],
    },
]


def main() -> None:
    headers = login()
    submissions = []
    for spec in CHARACTERS:
        print(f"创建 {spec['name']}……")
        char_id = create_character(headers, spec)
        submissions.append(review_and_submit(headers, char_id, spec["name"]))

    print("\n管理员审核上架：")
    for item in submissions:
        approve = client.post(
            f"{API}/admin/reviews/{item['version_id']}",
            headers=headers,
            json={"action": "approve", "reason": "社区示例内容入库"},
        )
        print(f"  {item['name']}: 审核 {approve.status_code}")

    community = client.get(f"{API}/community/characters").json()
    community_list = (
        community.get("items") or community if isinstance(community, list) else []
    )
    names = [
        item.get("name")
        for item in community_list
        if isinstance(item, dict)
    ][:8]
    print("\n社区角色库当前内容:", names)


if __name__ == "__main__":
    main()
