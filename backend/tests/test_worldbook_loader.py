"""Worldbook 加载器测试：24 条全量、格式校验、常驻标记、触发词去重。"""

from __future__ import annotations

from app.knowledge.worldbook.loader import load_entries


def test_loads_all_seed_entries():
    entries = load_entries()
    assert len(entries) == 24
    # 全部带【事实】正文
    assert all("【事实】" in entry.content for entry in entries)
    # 全部有触发词（含标题即触发词）
    assert all(entry.keywords for entry in entries)


def test_permanent_flags():
    entries = {entry.title: entry for entry in load_entries()}
    permanent_titles = {title for title, entry in entries.items() if entry.permanent}
    assert "黑塔 = 大黑塔 = 黑塔女士 = 你" in permanent_titles
    assert "用户与称呼" in permanent_titles
    assert "星穹列车组" in permanent_titles
    # 命途速查：用户拍板为非常驻
    assert entries["命途与星神速查（18 对应）"].permanent is False


def test_entry_ids_namespaced_by_file():
    entries = {entry.entry_id: entry for entry in load_entries()}
    assert "10_herta:黑塔的人偶与本体" in entries
    assert "20_world:翁法罗斯与黄金裔" in entries


def test_shared_keywords_allowed_full_sets_deduped():
    """部分共享关键词合法（一词激活多相关条目）；整组重复的条目才被剔除。"""
    entries = load_entries()
    sets = [frozenset(entry.keywords) for entry in entries]
    assert len(sets) == len(set(sets))  # 无整组重复
    # "模拟宇宙"同时属于项目组与世界观两条（设计修正：不再剥共享词）
    owners = [entry.entry_id for entry in entries if "模拟宇宙" in entry.keywords]
    assert len(owners) >= 2
    # 每条仍有触发词
    assert all(entry.keywords for entry in entries)


def test_herta_entry_content_layers():
    entries = {entry.title: entry for entry in load_entries()}
    content = entries["黑塔的人偶与本体"].content
    assert "【事实】" in content and "【写法】" in content and "【口径】" in content
    assert "勉强七分相似" in content  # 原文引用保真
