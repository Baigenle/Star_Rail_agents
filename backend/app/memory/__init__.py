"""分层记忆层：存储抽象与实现（Phase 2）。

- schemas.py：L0/L1/L2 数据结构（pydantic 校验，规格 §8.2）
- repository.py：MemoryRepository 抽象 + PostgreSQL 默认实现（可整体替换）

对接约定（工作簿 Q6 / 可行性报告 §2.3）：
- L0/L1 由 MemoryJudge 自动写入（低风险字段）
- L2 走用户确认流（沿用现有 memory_suggestions 前端确认的哲学）
- 轮次计数存 L1.round_count（DB 持久化，重启不丢）
"""
