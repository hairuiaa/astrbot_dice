import random

import pytest

from data.plugins.astrbot_plugin_sealdice_core.core import SeaDiceService
from data.plugins.astrbot_plugin_sealdice_core.main import Main


def run(service: SeaDiceService, text: str, group: str = "g1", user: str = "u1"):
    outcome = service.handle(text, group_id=group, user_id=user, sender_name="调查员")
    assert outcome is not None
    return outcome


def test_dot_prefix_is_handled_and_slash_is_ignored():
    service = SeaDiceService(rng=random.Random(1))

    assert service.handle("/set coc", group_id="g1", user_id="u1") is None
    assert ".set coc" not in run(service, ".set coc").text
    assert run(service, "。r 1d6").text.startswith("1d6 =")


def test_coc_character_check_san_growth_and_sn():
    service = SeaDiceService(rng=random.Random(2))

    assert "COC7" in run(service, ".set coc").text
    assert "昵称已设为" in run(service, ".nn Alice").text
    assert "已新建" in run(service, ".pc new AliceCard").text
    assert "属性已更新" in run(service, ".st 侦查=60 hp=10 san=55").text
    assert "侦查 检定" in run(service, ".ra 侦查").text
    assert "SAN Check" in run(service, ".sc 0/1d3").text
    assert "成长" in run(service, ".en 侦查").text

    sn = run(service, ".sn coc")
    assert "名片预览" in sn.text
    assert sn.group_card is not None
    assert "Alice" in sn.group_card


def test_dnd_character_init_slots_cast_longrest_and_death_save():
    service = SeaDiceService(rng=random.Random(3))

    assert "DND5e" in run(service, ".set dnd").text
    assert "已新建" in run(service, ".pc new Fighter").text
    assert "属性已更新" in run(service, ".dst hp=8 hpmax=12 dex=14").text
    assert "先攻" in run(service, ".ri").text
    assert "法术位已更新" in run(service, ".ss 1=2/4 2=1/2").text
    assert "消耗 1 环法术位" in run(service, ".cast 1").text
    assert "死亡豁免" in run(service, ".ds").text
    assert "长休完成" in run(service, ".longrest").text
    assert "名片预览" in run(service, ".sn dnd").text


def test_log_records_plain_text_and_commands():
    service = SeaDiceService(rng=random.Random(4))

    assert "日志已创建" in run(service, ".log new 第一场").text
    assert service.handle("调查员推开门。", group_id="g1", user_id="u1", sender_name="调查员") is None
    assert "1d6 =" in run(service, ".r 1d6").text
    exported = run(service, ".log get 第一场").text
    assert "调查员推开门。" in exported
    assert ".r 1d6" in exported
    assert "日志已结束" in run(service, ".log end").text


def test_alias_deck_story_and_feature_matrix_commands():
    service = SeaDiceService(rng=random.Random(5))

    assert "快捷指令已保存" in run(service, ".alias toss .r 1d6").text
    assert "1d6 =" in run(service, ".&toss").text
    assert "牌堆已保存" in run(service, ".deck add omens 红牌|蓝牌").text
    assert "omens 抽牌" in run(service, ".draw omens").text
    assert "今日人品" in run(service, ".jrrp").text
    assert "随机顺序" in run(service, ".who Alice Bob").text
    assert "随机姓名" in run(service, ".name 2").text
    assert "SeaDice 第二阶段验收矩阵" in run(service, ".matrix").text
    assert "相关的功能项" in run(service, ".find js").text


def test_sealdice_style_attached_roll_and_san_expressions():
    service = SeaDiceService(rng=random.Random(8))

    assert run(service, ".r1d3").text.startswith("1d3 =")
    assert run(service, ".r1d4").text.startswith("1d4 =")
    assert "侦查 检定" in run(service, ".ra侦查70").text
    assert "/60" in run(service, ".ra60").text
    st_update = run(service, ".st侦查60 hp+1d3").text
    assert "属性已更新" in st_update
    assert "侦查:0->60" in st_update
    assert "昵称已设为 Alice" in run(service, ".nnAlice").text
    assert "已新建" in run(service, ".pcnew Hero").text
    assert "日志已创建" in run(service, ".lognew 第二场").text
    assert "名片预览" in run(service, ".sncoc").text
    assert "SAN Check" in run(service, ".sc1d3").text
    assert "d100=" in run(service, ".sc0/1d3").text
    custom = run(service, ".sc d100 0/1d4 60").text
    assert "d100=" in custom
    assert "/60" in custom


def test_compat_resources_are_persisted(tmp_path):
    state_path = tmp_path / "state.json"
    service = SeaDiceService(state_path, rng=random.Random(6))

    assert "helpdoc 已保存" in run(service, ".helpdoc add sc SAN 检定帮助").text
    assert "牌堆已保存" in run(service, ".deck add clues 线索1|线索2").text
    assert "sealpack 已记录" in run(service, ".sealpack import demo.sealpack").text
    assert "已加入黑名单" in run(service, ".ban add u2 测试").text
    assert "队伍已更新" in run(service, ".team add A队 Alice Bob").text
    assert "COC 房规已设置" in run(service, ".setcoc 2").text

    reloaded = SeaDiceService(state_path, rng=random.Random(7))
    assert "sc:" in run(reloaded, ".helpdoc get sc").text
    assert "clues" in run(reloaded, ".deck list").text
    assert "demo.sealpack" in run(reloaded, ".sealpack list").text
    assert "u2" in run(reloaded, ".ban list").text
    assert "A队" in run(reloaded, ".team list").text
    assert "COC 房规：2" in run(reloaded, ".set info").text


class FakeEvent:
    def __init__(self, text: str) -> None:
        self.text = text
        self.stopped = False
        self.call_llm = True

    def get_message_str(self):
        return self.text

    def get_group_id(self):
        return "g1"

    def get_session_id(self):
        return "s1"

    def get_sender_id(self):
        return "u1"

    def get_sender_name(self):
        return "调查员"

    def stop_event(self):
        self.stopped = True

    def should_call_llm(self, call_llm: bool):
        self.call_llm = call_llm

    def plain_result(self, text: str):
        return text


@pytest.mark.asyncio
async def test_astrbot_event_intercepts_dot_and_leaves_slash(monkeypatch, tmp_path):
    import data.plugins.astrbot_plugin_sealdice_core.main as plugin_main

    monkeypatch.setattr(plugin_main, "get_astrbot_plugin_data_path", lambda: str(tmp_path))
    plugin = Main(context=object(), config={"route": "python"})

    slash = FakeEvent("/set coc")
    slash_outputs = [item async for item in plugin.on_all_message(slash)]
    assert slash_outputs == []
    assert not slash.stopped

    dot = FakeEvent(".r 1d6")
    dot_outputs = [item async for item in plugin.on_all_message(dot)]
    assert len(dot_outputs) == 1
    assert "1d6 =" in dot_outputs[0]
    assert dot.stopped
    assert dot.call_llm is False
