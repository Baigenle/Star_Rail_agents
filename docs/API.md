# 业务接口说明

完整交互式文档启动后见 `http://localhost:8000/docs`。除公开目录、匿名聊天和社区已发布内容外，用户数据接口均要求 `Authorization: Bearer <token>`。

## 1. 核心接口

| 领域 | 方法与路径 | 作用 |
|---|---|---|
| 聊天 | `POST /api/v1/chat/messages` | 黑塔主 Agent 统一入口；支持 `conversation_id` |
| 会话 | `GET /api/v1/chat/conversations` | 当前用户会话列表 |
| 会话 | `GET /api/v1/chat/conversations/{id}/messages` | 恢复会话消息 |
| 记忆 | `GET/POST /api/v1/profile/memories` | 查看或确认长期记忆 |
| 记忆 | `PATCH/DELETE /api/v1/profile/memories/{id}` | 修改、停用或删除记忆 |
| 配队 | `POST /api/v1/teams/recommendations` | 理论队与角色池可用队 |
| 队伍 | `GET/POST /api/v1/profile/teams` | 常用队伍 |
| 队伍 | `PATCH/DELETE /api/v1/profile/teams/{id}` | 改名或删除常用队伍 |
| 养成 | `POST /api/v1/planning/progression/calculate` | 多角色材料合并与构筑 |
| 养成 | `GET/POST /api/v1/profile/progression-plans` | 保存养成方案 |
| 养成 | `PATCH /api/v1/profile/progression-plans/{id}` | 优先级和状态 |
| 每周 | `POST /api/v1/planning/weekly/generate` | 按养成方案、体力预算和周本次数生成本周任务（滚动窗口：以生成当天为起点覆盖未来 7 天，响应含 statistics 方案进度统计） |
| 每周 | `GET /api/v1/profile/weekly-plans/current` | 当前滚动窗口计划（含统计：刚需完成度、隧洞推荐单列、按方案分组） |
| 每周 | `PATCH /api/v1/profile/weekly-plans/{id}/tasks/{task_id}` | 更新完成状态 |
| 每日 | `GET /api/v1/planning/daily?date=YYYY-MM-DD` | 查看计划窗口内指定日期的体力安排：240 点上限、按优先级排程、周本置顶；`date` 可省略（默认今天） |
| 每日 | `PATCH /api/v1/planning/daily/{date}/{task_id}` | 勾选/取消某日任务的完成，从当日 240 点账本核销并同步周进度；侵蚀隧洞为推荐项（`is_required=false`），不计入方案完成度 |
| 养成 | `DELETE /api/v1/profile/progression-plans/{id}` | 删除用户自己的养成方案 |

## 2. 聊天示例

```json
POST /api/v1/chat/messages
{
  "message": "阮·梅突破和行迹需要什么材料？",
  "conversation_id": null
}
```

响应除 `answer` 外始终包含：

```json
{
  "agent": "herta_main_agent",
  "protocol": "claim-citation-validation-filtering",
  "claims": [],
  "citations": [],
  "validation": {},
  "filtering": {},
  "query_steps": [],
  "conversation_id": "uuid-or-null",
  "memory_suggestions": []
}
```

`memory_suggestions` 只是候选；只有用户再调用 `POST /profile/memories` 才会持久化。

## 3. 多角色养成示例

```json
POST /api/v1/planning/progression/calculate
{
  "characters": [
    {
      "character_id": "1303",
      "from_level": 60,
      "to_level": 80,
      "skill_ranges": {
        "basic": {"from_level": 1, "to_level": 6},
        "skill": {"from_level": 6, "to_level": 10}
      }
    }
  ]
}
```

## 4. 常见错误码

| 状态码 | 含义 |
|---|---|
| `401` | 未登录、令牌缺失或失效 |
| `403` | 非管理员访问审核接口 |
| `404` | 资源不存在，或资源不属于当前用户 |
| `409` | 用户名/邮箱或业务唯一项冲突 |
| `422` | 角色未拥有、非法等级区间、重复角色或非法枚举 |
| `503` | 依赖服务暂不可用；不会生成无证据游戏事实 |
