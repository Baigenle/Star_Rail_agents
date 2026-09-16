# 星穹列车智库系统验收报告

验收日期：2026-07-30  
验收环境：Windows、Docker Engine 29.5.3、Python 3.12.13、
Docker Node.js 22、Chrome 150

## 1. 验收结论

本轮对毕业设计主要业务链路、部署链路和权限边界进行了自动化与真实运行验收。

- 后端 96 项测试全部通过。
- Ruff 静态检查通过，Python 已安装依赖无冲突。
- Vue TypeScript 类型检查和生产构建通过。
- 7 个 Docker 服务正常运行；PostgreSQL、Milvus、BGE 和 backend 均为 healthy。
- 13 个主要页面通过 Chrome 真实渲染；匿名访问受保护页面会跳转登录。
- BGE-M3、Reranker、Milvus 与 RAG 索引完成一次容器内只读联调。
- 黑塔主 Agent 完成一次真实问答，返回 1 条 Claim、5 条 Citation，
  `partially_verified` 验证状态并通过 Filtering。
- 36640 个图片资源通过清单校验。

因此，当前核心毕业设计功能具备可演示、可测试和可复现条件。尚未完成的内容主要是资料型扩展和最终论文交付物，不影响主业务闭环演示。

## 2. 自动化测试

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| Pytest | 通过 | 96 passed |
| Ruff | 通过 | app、tests、scripts 无违规 |
| pip check | 通过 | No broken requirements found |
| Vue type-check | 通过 | `vue-tsc --noEmit` |
| Vue production build | 通过 | 166 modules transformed |
| OpenAPI 契约 | 通过 | 核心路径存在，operationId 唯一 |
| 图片资源清单 | 通过 | 36640 assets verified |
| npm audit | 未执行 | 执行环境禁止向外部镜像站发送依赖元数据 |

新增测试覆盖：

- 注册、邮箱/用户名登录、`/auth/me` 与无效 Token。
- 用户名和邮箱重复、非法用户名、错误密码。
- 密码仅保存 scrypt 哈希，响应不返回密码字段。
- 无 Token 访问审核 API 返回 401。
- 普通用户访问审核 API 返回 403。
- `ADMIN_USERNAMES` 中的注册用户名获得管理员权限。
- 后端镜像包含知识脚本和正确 `PYTHONPATH`。
- Compose 不再提供隐式默认管理员，并支持前端端口覆盖。
- 核心毕业设计 API 不会在 Router 重构时被意外移除。

## 3. Docker 与 API 验收

运行服务：

| 服务 | 结果 | 端口 |
| --- | --- | --- |
| frontend | 运行 | 8030 |
| backend | healthy | 8000 |
| bge-model-service | healthy | 8001 |
| postgres | healthy | 5432 |
| milvus-standalone | healthy | 19531 |
| etcd | healthy | 容器内部 |
| minio | healthy | 容器内部 |

以下公开接口均返回 200：

- `/api/v1/health`
- `/openapi.json`
- `/api/v1/catalog/characters`
- `/api/v1/catalog/lightcones`
- `/api/v1/catalog/relics`
- `/api/v1/catalog/items`
- `/api/v1/stories`
- `/api/v1/activities`
- `/api/v1/community/characters`
- 前端 `/`

以下受保护接口在无 Token 时均返回 401：

- `/api/v1/auth/me`
- `/api/v1/profile/memories`
- `/api/v1/admin/reviews`
- `/api/v1/admin/activity-guide-reviews`

最近容器日志未发现 5xx、Traceback、Exception 或应用 ERROR。

## 4. 浏览器验收

Chrome 无头真实渲染通过 13 个入口：

- `/`
- `/characters`
- `/lightcones`
- `/relics`
- `/items`
- `/stories`
- `/activities`
- `/community/characters`
- `/login`
- `/teams`
- `/planning`
- `/weekly-plan`
- `/creator`

公开页面均渲染出对应档案标题。匿名访问配队、养成、每周规划和创作工坊时，均渲染登录页面，说明路由保护生效。

可复现命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\browser_acceptance.ps1
```

## 5. 功能覆盖状态

| 功能 | 状态 | 验收证据 |
| --- | --- | --- |
| 黑塔主 Agent 与 Router | 已完成 | 意图测试、真实问答、协议断言 |
| RAG 问答 | 已完成 | Loader、Chunk、检索、重排、幻觉回归测试 |
| 角色/光锥/遗器/物品 | 已完成 | API 测试、浏览器渲染、图片校验 |
| 角色池与喜欢角色 | 已完成 | 用户隔离、批量导入、收藏测试 |
| 官方智能配队 | 已完成 | 评分、限制、替代队、保存队伍测试 |
| 养成规划 | 已完成 | 标准/记忆/欢愉规则、多角色材料隔离测试 |
| 每周规划 | 已完成 | 周本优先、预算、任务状态与删除测试 |
| 长期记忆 | 已完成 | 确认、启停、修改、删除与跨用户隔离测试 |
| 剧情解析与阅读 | 已完成 | 筛选、场景定位、角色关系证据测试 |
| 4.4 活动与投稿 | 已完成 | 详情、投稿、审核、下架和恢复测试 |
| 自定义角色 | 已完成 | 四阶段、会话恢复、配队和版本测试 |
| 社区审核 | 已完成 | 管理员权限、AI 辅助报告、治理操作测试 |
| 后台聊天任务与 SSE | 已完成 | 状态、恢复、去重和事件流测试 |

## 6. 本轮发现并修复的问题

1. Milvus 暂时不可达时，FastAPI 启动会整体失败。现在聊天任务恢复可降级跳过，健康检查和非 AI 页面仍能启动。
2. Compose 曾在未配置时默认把特定用户名视为管理员。现在默认没有管理员，必须显式配置。
3. 前端审核页只检查登录。现在增加管理员路由守卫，后端继续做最终 403 校验。
4. 后端镜像未包含数据脚本，随后又发现脚本缺少 `/app` 模块路径。现在镜像包含 scripts 并设置 `PYTHONPATH=/app`。
5. 默认 8080 落入本机 WSL 保留端口范围。现在前端端口可配置，默认改为 8030。
6. 仅 GPU Compose 不利于无显卡复现。现在提供 `docker-compose.cpu.yml` 覆盖配置。
7. BGE 文档仍引用旧 collection 名称。现在统一为 `star_rail_knowledge_bge_m3_v2`。

## 7. 已知限制与剩余工作

数据限制：

- 1771 个行迹节点缺少名称、前置关系、解锁条件和逐节点材料。
- 地图、宝箱、锚点、谜题和导航坐标库尚未建立。
- 通用 Boss/副本攻略不足，可靠活动攻略主要是 4.4。
- 部分往期活动缺少精确时间、奖励和前置任务。
- 副本开放星期与确定掉落数量不完整。

工程限制：

- `pymilvus 2.5.2` 会输出 `pkg_resources` 弃用警告，目前不影响功能，后续升级 Milvus 客户端时应消除。
- Python 顶层依赖已固定版本，但尚未生成完整的传递依赖 lock 文件。
- npm 在线安全公告审计需在允许向 registry 发送依赖元数据的环境中补跑。
- 尚缺完整的前端组件级/E2E 测试、持续集成、性能基准与异常监控。
- Git 仓库仍需整理正式提交历史，并准备 GitHub Release 图片资源包。
- 论文、开题报告、答辩 PPT 和演示视频尚未制作。
