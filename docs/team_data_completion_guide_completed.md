## 9 个低置信战斗标签（已补充）

角色基础属性、命途和定位已经可用，以下标签仅保留能够由角色技能、行迹或角色定位直接支持的机制。星魂限定机制原则上不作为基础标签；若某标签来自星魂，会在依据中单独注明。

> 编号校正：目录版本 `4.4.51` 中 `1306` 为量子·同谐“花火”，
> `1501` 为火·欢愉“火花”。两者是独立角色，不能互换 ID。

```json
[
  {
    "character_id": "1501",
    "name": "火花",
    "battle_tags": [
      "enhanced_basic",
      "skill_point",
      "random",
      "multi_hit",
      "blast"
    ],
    "source": "docs/hsr_nanoka_characters/characters/1501_火花.md",
    "source_basis": "4.4.51 角色档案显示火花为火属性欢愉输出；战技开启强化普攻与随机互动陷阱，终结技和欢愉技包含多段随机伤害，技能同时具有战技点恢复与爆点抵扣机制。"
  },
  {
    "character_id": "1203",
    "name": "罗刹",
    "battle_tags": [
      "healing",
      "auto_heal",
      "attack_triggered_healing",
      "cleanse",
      "buff_dispel"
    ],
    "source": "https://wiki.biligame.com/sr/罗刹",
    "source_basis": "角色页说明战技可主动治疗，并会在队友低生命时自动触发；结界可在队友攻击敌人后回复生命，同时角色具有效果解除与敌方增益解除能力。"
  },
  {
    "character_id": "1107",
    "name": "克拉拉",
    "battle_tags": [
      "follow_up",
      "counter",
      "damage_reduction",
      "aggro_increase",
      "crowd_control_resistance"
    ],
    "source": "https://wiki.biligame.com/sr/克拉拉",
    "source_basis": "角色页将反击、追加攻击、自身减伤、受击概率提升和控制抵抗列为主要机制，并说明克拉拉受击时由史瓦罗发动反击。"
  },
  {
    "character_id": "1004",
    "name": "瓦尔特",
    "battle_tags": [
      "debuff",
      "action_delay",
      "slow",
      "vulnerability"
    ],
    "source": "https://wiki.biligame.com/sr/瓦尔特",
    "source_basis": "角色页将行动延后、减速和易伤列为主要机制，并说明战技与终结技能够减缓敌方行动。"
  },
  {
    "character_id": "1312",
    "name": "米沙",
    "battle_tags": [
      "debuff",
      "freeze",
      "skill_point_scaling",
      "multi_hit"
    ],
    "source": "https://wiki.biligame.com/sr/米沙",
    "source_basis": "角色页说明终结技能够冻结敌人；我方消耗战技点后，米沙终结技的攻击段数会增加，因此属于战技点联动的多段控制输出。"
  },
  {
    "character_id": "1215",
    "name": "寒鸦",
    "battle_tags": [
      "skill_point",
      "damage_buff",
      "attack_buff",
      "speed_buff"
    ],
    "source": "https://wiki.biligame.com/sr/寒鸦",
    "source_basis": "角色页说明寒鸦可恢复战技点，并提高指定队友的速度与攻击力；其 TAG 同时包含增伤。"
  },
  {
    "character_id": "1202",
    "name": "停云",
    "battle_tags": [
      "energy_restore",
      "attack_buff",
      "damage_buff",
      "additional_damage"
    ],
    "source": "https://wiki.biligame.com/sr/停云",
    "source_basis": "角色页说明战技能强化队友攻击并产生额外伤害，终结技可直接为指定队友恢复能量并提高其造成的伤害。"
  },
  {
    "character_id": "1201",
    "name": "青雀",
    "battle_tags": [
      "skill_point",
      "enhanced_basic",
      "random",
      "blast"
    ],
    "source": "https://wiki.biligame.com/sr/青雀",
    "source_basis": "角色页说明青雀通过随机抽取琼玉牌形成四张同色，随后获得能够攻击多个敌人的强化普攻；其循环与战技点消耗紧密相关。"
  },
  {
    "character_id": "1008",
    "name": "阿兰",
    "battle_tags": [
      "hp_consumption",
      "low_hp_scaling",
      "self_healing",
      "damage_reduction"
    ],
    "source": "https://wiki.biligame.com/sr/阿兰",
    "source_basis": "角色页将消耗生命值、自身伤害提升、自身治疗和伤害抵抗列为主要机制；其战技以生命值代替战技点作为代价。"
  }
]
```

### 标签语义说明

- `action_advance`：使我方单位行动提前。
- `skill_point`：直接恢复、扩大战技点上限，或以战技点为核心循环资源。
- `skill_point_scaling`：自身效果会随队伍消耗战技点而增强，但不等同于直接恢复战技点。
- `auto_heal`：满足生命阈值等条件后自动治疗。
- `attack_triggered_healing`：队友攻击特定敌人后触发治疗。
- `cleanse`：解除我方负面效果。
- `buff_dispel`：解除敌方增益效果。
- `counter`：受击后反击；反击在游戏机制中属于追加攻击的一种。
- `aggro_increase`：提高自身被敌方选中的概率。
- `action_delay`：直接推迟敌方行动，不等同于单纯降低速度。
- `vulnerability`：提高敌方受到的伤害。
- `enhanced_basic`：通过特定资源或状态获得强化普攻。
- `blast`：攻击主目标及相邻目标。
- `hp_consumption`：主动消耗自身生命值施放技能。
- `low_hp_scaling`：生命值越低或低于阈值时获得更高收益。

## 1 名构筑资料不完整（已补充）

以下优先级不是绝对强弱排序，而是按“通用辅助 → 专项击破 → 低成本替代”整理；实际选择需要结合队伍类型、敌人弱点和已有装备。

```json
{
  "character_id": "1301",
  "recommended_lightcones": [
    {
      "name": "等价交换",
      "priority": 1,
      "reason": "通用辅助首选。加拉赫终结技后能够行动提前，可更频繁触发光锥的队友回能效果，适合依赖终结技循环的队伍。"
    },
    {
      "name": "唯有香如故",
      "priority": 2,
      "reason": "高成本击破向选择，提供大量击破特攻，并在施放攻击型终结技后给敌方施加易伤；同时契合加拉赫将击破特攻转化为治疗量的行迹。"
    },
    {
      "name": "何物为真",
      "priority": 3,
      "reason": "可获取的击破向选择，提高击破特攻，并通过普攻恢复自身生命；适合超击破队或需要兼顾生存的配置。"
    },
    {
      "name": "蕃息",
      "priority": 4,
      "reason": "低成本产点方案。加拉赫通常以普攻为主，普攻后的行动提前可以增加行动次数与战技点产出，但三星光锥基础属性较低。"
    }
  ],
  "tunnel_relics": [
    {
      "name": "烈阳惊雷的女武神",
      "priority": 1,
      "reason": "当前通用辅助方案，可提供速度并为暴击队提供全队暴击伤害增益；在击破队中也能利用速度收益加快循环。"
    },
    {
      "name": "荡除蠹灾的铁骑",
      "priority": 2,
      "reason": "超击破专项方案。当队伍能够提供超击破时，可显著提高加拉赫自身的击破与超击破伤害；普通队伍不建议优先。"
    },
    {
      "name": "流星追迹的怪盗",
      "priority": 3,
      "reason": "击破向过渡方案，提供击破特攻，并能在击破敌人时补充能量，适合缺少更优四件套时使用。"
    }
  ],
  "planar_relics": [
    {
      "name": "劫火莲灯铸炼宫",
      "priority": 1,
      "reason": "火属性击破队优先，提供常驻速度，并在攻击具有火弱点的敌人后获得大量击破特攻。"
    },
    {
      "name": "盗贼公国塔利亚",
      "priority": 2,
      "reason": "通用击破替代，不依赖敌人火弱点；需要达到较高速度阈值才能完整获得击破特攻加成。"
    },
    {
      "name": "折断的龙骨",
      "priority": 3,
      "reason": "暴击队辅助方案。加拉赫较容易堆叠效果抵抗，达到条件后可提高全队暴击伤害。"
    },
    {
      "name": "沉陆海域露莎卡",
      "priority": 4,
      "reason": "单核攻击力输出队方案，提供能量恢复效率并提高一号位队友攻击力，有助于加拉赫终结技循环。"
    }
  ],
  "source": "Prydwen Gallagher Best Build Guide（2026-05-31 更新）：https://www.prydwen.gg/star-rail/characters/gallagher ；崩坏：星穹铁道 BWIKI 加拉赫攻略（2025-12-10 更新）：https://wiki.biligame.com/sr/加拉赫/攻略"
}
```

### 加拉赫主副词条补充

- 躯干：治疗量加成。
- 脚部：速度。
- 位面球：生命值百分比或防御力百分比。
- 连结绳：能量恢复效率。
- 副词条：速度 > 击破特攻（通常不必超过 150%）> 效果抵抗 > 生命值百分比 / 防御力百分比。

没有可靠资料时可以继续留空；系统会在 Filtering 中明确提示，不会挪用其他角色的构筑。
