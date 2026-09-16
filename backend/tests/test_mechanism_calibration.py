"""机制知识分校准测试：官方存储队必须高于其扰动版。

这组测试是配队评分质量的"考卷"：
- 体系完全体 > 引擎件被替换为体系外角色的扰动版
- 刚需满足 > 刚需未满足
任一失败都说明知识分规则被改坏。
"""

from pathlib import Path


from app.services.team_simulation_service import TeamSimulationService

DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"


def _score(member_ids: list[str]) -> float:
    service = TeamSimulationService(
        DOCS_ROOT,
        archetype_service=__import__(
            "app.services.team_archetype_service",
            fromlist=["TeamArchetypeService"],
        ).TeamArchetypeService(DOCS_ROOT),
    )
    result = service.evaluate(
        member_ids,
        structural_score=80.0,
    )
    return result.final_score


def _knowledge(member_ids: list[str]) -> tuple[float, list[str]]:
    service = TeamSimulationService(
        DOCS_ROOT,
        archetype_service=__import__(
            "app.services.team_archetype_service",
            fromlist=["TeamArchetypeService"],
        ).TeamArchetypeService(DOCS_ROOT),
    )
    result = service.evaluate(
        member_ids,
        structural_score=80.0,
    )
    return result.knowledge_score, result.knowledge_notes


def test_firefly_stored_team_beats_off_engine_swap() -> None:
    """流萤超击破完全体 > 忘归人被替换为体系外角色（彦卿）。"""
    stored = ["1310", "1303", "1301", "1225"]
    perturbed = ["1310", "1303", "1301", "1209"]
    assert _score(stored) > _score(perturbed)


def test_hyacine_satisfies_castorice_hard_need() -> None:
    """遐蝶：风堇（大额高频治疗+忆灵）> 玲可（小额低频）。"""
    good = ["1407", "1409", "1403", "1313"]
    weak = ["1407", "1110", "1403", "1313"]
    assert _score(good) > _score(weak)
    knowledge, notes = _knowledge(weak)
    assert knowledge < 60.0  # 硬需求未满足被扣到基线以下区间；软需求部分回血
    assert any("硬需求未满足" in note for note in notes)


def test_dot_team_rejects_crit_buffers() -> None:
    """DoT 体系不吃双爆：双爆拐换入应显著降分。"""
    good = ["1005", "1307", "1410", "1217"]
    crit_buffered = ["1005", "1307", "1101", "1217"]  # 布洛妮娅（双爆拐）换入
    assert _score(good) > _score(crit_buffered)


def test_acheron_requires_debuff_appliers() -> None:
    """黄泉：负面施加位 > 同谐增益位（椒丘/佩拉 > 花火）。"""
    good = ["1308", "1218", "1106", "1301"]
    weak = ["1308", "1306", "1309", "1301"]
    assert _score(good) > _score(weak)


def test_knowledge_score_within_bounds() -> None:
    knowledge, _ = _knowledge(["1310", "1303", "1301", "1225"])
    assert 0.0 <= knowledge <= 100.0
