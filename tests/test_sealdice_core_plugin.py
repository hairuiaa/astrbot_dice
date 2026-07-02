import random

from data.plugins.astrbot_plugin_sealdice_core.core import SeaDiceService


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
