"""记忆层仓库测试：内存 SQLite（仓库实现须 SQLite/PG 双兼容）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 —— 注册全部表
from app.db.session import Base
from app.memory.repository import PgMemoryRepository
from app.memory.schemas import L0Profile, L15Fact, L2Memory


@pytest.fixture()
def repo():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return PgMemoryRepository(factory)


def test_l0_roundtrip_and_default(repo):
    empty = repo.get_l0("user-a")
    assert empty.main_role == ""  # 没有画像时返回空结构，不抛

    repo.save_l0("user-a", L0Profile(main_role="主玩毁灭", main_characters="流萤", preferences="别替我排体力"))
    loaded = repo.get_l0("user-a")
    assert loaded.main_role == "主玩毁灭"
    assert loaded.preferences == "别替我排体力"
    assert loaded.updated_at > 0


def test_l1_round_count_persists(repo):
    profile = repo.get_l1("user-a")
    assert profile.round_count == 0
    profile.round_count = 7
    profile.current_focus = "在练流萤"
    repo.save_l1("user-a", profile)
    assert repo.get_l1("user-a").round_count == 7
    assert repo.get_l1("user-a").current_focus == "在练流萤"


def test_l15_fact_upsert_keeps_single_row(repo):
    before = repo.get_facts("user-a")
    assert before == []
    repo.upsert_fact("user-a", L15Fact(fact_key="last_team", fact_value="流萤队"))
    repo.upsert_fact("user-a", L15Fact(fact_key="last_team", fact_value="流萤超击破队"))
    facts = repo.get_facts("user-a")
    assert len(facts) == 1
    assert facts[0].fact_value == "流萤超击破队"
    assert facts[0].updated_at > 0  # 时间戳由仓库盖章


def test_l2_lifecycle(repo):
    memory_id = repo.add_l2(
        L2Memory(user_id="user-a", content="连歪三次卡池后说想弃游", trigger_text="抽卡 歪了")
    )
    assert memory_id

    active = repo.all_active_l2("user-a")
    assert len(active) == 1
    assert active[0].content.startswith("连歪三次")

    repo.update_l2_stats(memory_id)
    repo.update_l2_stats(memory_id)
    assert repo.all_active_l2("user-a")[0].access_count == 2

    repo.mark_superseded(memory_id)
    assert repo.all_active_l2("user-a") == []

    # 用户隔离：另一用户看不到
    repo.add_l2(L2Memory(user_id="user-b", content="user-b 的记忆"))
    assert len(repo.all_active_l2("user-b")) == 1
    assert len(repo.all_active_l2("user-a")) == 0
