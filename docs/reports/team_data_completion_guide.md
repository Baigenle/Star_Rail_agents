# 配队与构筑数据补充说明

## 73 条“无法映射”是什么

- 52 条属于角色别名或不完整名称：开拓者各命途未指定穹/星，以及“仙舟三月七”。
- 21 条属于队伍槽位：任意主 C、任意辅助、辅助位、拉条辅助、双 C、核心辅助、光环/负面辅助等。

槽位不是角色，不应填写虚假的角色 ID。系统后续应把它们规范化为 `dps`、`sub_dps`、`support`、`sustain` 及机制约束。开拓者若来源没有指定穹/星，也应保留为“对应命途开拓者”，在推荐时根据用户角色池动态替换。

如需人工指定，请提供：

```json
{
  "source_file": "原配队文件名.md",
  "raw_name": "原文名称",
  "mapping_type": "character | role_slot",
  "character_id": "仅 character 时填写",
  "role": "仅 role_slot 时填写",
  "mechanic_tags": ["可选机制标签"],
  "note": "判断依据"
}
```

## 9 个低置信战斗标签

角色基础属性、命途和定位已经可用，缺的是能支持配队评分的机制标签：

- 1501 火花
- 1203 罗刹
- 1107 克拉拉
- 1004 瓦尔特
- 1312 米沙
- 1215 寒鸦
- 1202 停云
- 1201 青雀
- 1008 阿兰

每名角色补充 2–6 个可靠机制标签即可，例如：`follow_up`、`summon`、`break`、`super_break`、`dot`、`debuff`、`defense_reduction`、`resistance_reduction`、`action_advance`、`energy_restore`、`skill_point`、`healing`、`shield`。请同时给出来源段落，避免只凭印象写标签。

## 3 名构筑资料不完整

- 1509 吉尔伽美什
- 1508 远坂凛
- 1301 加拉赫

每名角色至少需要：

```json
{
  "character_id": "1509",
  "recommended_lightcones": [{"name": "光锥名", "priority": 1, "reason": "理由"}],
  "tunnel_relics": [{"name": "四件套名", "priority": 1, "reason": "理由"}],
  "planar_relics": [{"name": "两件套名", "priority": 1, "reason": "理由"}],
  "source": "资料来源"
}
```

没有可靠资料时可以继续留空；系统会在 Filtering 中明确提示，不会挪用其他角色的构筑。
