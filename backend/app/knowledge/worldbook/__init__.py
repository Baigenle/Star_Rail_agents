"""Worldbook 主动注入层（star-rail-worldbook-design.md 落地）。

- loader.py：解析 entries/*.md（格式 v1.1）
- engine.py：DMAE 激活状态机（PG 持久化，按 conversation_id 隔离）
- injector.py：组装注入块（常驻 + 激活条目，2500 字预算）
"""
