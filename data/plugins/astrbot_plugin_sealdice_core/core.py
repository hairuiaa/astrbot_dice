from __future__ import annotations

import hashlib
import json
import math
import random
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .command_router import CommandRouter
from .feature_matrix import find_feature_docs, format_feature_matrix

COC_DEFAULTS = {
    "str": 50,
    "con": 50,
    "siz": 50,
    "dex": 50,
    "app": 50,
    "int": 50,
    "pow": 50,
    "edu": 50,
    "hpmax": 10,
    "hp": 10,
    "san": 60,
    "理智": 60,
    "生命值上限": 10,
    "生命值": 10,
    "敏捷": 50,
}

DND_DEFAULTS = {
    "str": 10,
    "dex": 10,
    "con": 10,
    "int": 10,
    "wis": 10,
    "cha": 10,
    "hpmax": 10,
    "hp": 10,
    "ac": 10,
    "dc": 10,
    "pp": 10,
}

ATTR_ALIASES = {
    "hp": "hp",
    "生命": "生命值",
    "生命值": "生命值",
    "hpmax": "hpmax",
    "生命值上限": "生命值上限",
    "san": "san",
    "理智": "理智",
    "dex": "dex",
    "敏捷": "敏捷",
    "ac": "ac",
    "dc": "dc",
    "pp": "pp",
}

SN_TEMPLATES = {
    "coc": "{$t玩家_RAW} SAN{理智} HP{生命值}/{生命值上限} DEX{敏捷}",
    "cocL": "{$t玩家_RAW} san{理智} hp{生命值}/{生命值上限} dex{敏捷}",
    "dnd": "{$t玩家_RAW} HP{hp}/{hpmax} AC{ac} DC{dc} PP{pp}",
}

TEMP_INSANITY = [
    "失忆",
    "假性残疾",
    "暴力倾向",
    "偏执",
    "人际依赖",
    "昏厥",
    "逃避行为",
    "歇斯底里",
    "恐惧",
    "狂躁",
]

INDEFINITE_INSANITY = [
    "焦虑症",
    "恐惧症",
    "强迫症",
    "妄想症",
    "创伤后应激障碍",
    "人格解离",
    "进食障碍",
    "睡眠障碍",
    "成瘾",
    "抑郁",
]

DEFAULT_DECKS = {
    "dnd": [
        "一瓶写着旧标签的治疗药水",
        "一枚刻着徽记的银币",
        "一封没有署名的短笺",
        "一把磨损严重的匕首",
        "一块带血的绷带",
    ],
    "coc": [
        "一张折过三次的车票",
        "一本边角潮湿的笔记",
        "一枚黄铜钥匙",
        "一张被撕掉半边的照片",
        "一只空药瓶",
    ],
}

CN_SURNAMES = ["赵", "钱", "孙", "李", "周", "吴", "郑", "王", "林", "许"]
CN_GIVEN = ["明", "然", "一", "宁", "秋", "远", "岚", "青", "白", "南"]
DND_NAMES = [
    "Aelar",
    "Bran",
    "Cora",
    "Dain",
    "Elaith",
    "Garrick",
    "Mira",
    "Nyx",
    "Tarin",
    "Vera",
]


@dataclass
class CharacterSheet:
    name: str
    rule: str = "coc"
    attrs: dict[str, int] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    spell_slots: dict[str, int] = field(default_factory=dict)
    spell_slots_max: dict[str, int] = field(default_factory=dict)
    buffs: list[str] = field(default_factory=list)
    death_success: int = 0
    death_failure: int = 0


@dataclass
class PlayerState:
    nickname: str = ""
    active: str = "default"
    sheets: dict[str, CharacterSheet] = field(default_factory=dict)
    sn_template: str = ""
    aliases: dict[str, str] = field(default_factory=dict)


@dataclass
class LogEntry:
    name: str
    created_at: float = field(default_factory=time.time)
    active: bool = True
    halted: bool = False
    lines: list[str] = field(default_factory=list)


@dataclass
class GroupState:
    active: bool = True
    rule: str = "coc"
    coc_rule: str = "0"
    players: dict[str, PlayerState] = field(default_factory=dict)
    logs: dict[str, LogEntry] = field(default_factory=dict)
    active_log: str = ""
    initiative: list[dict[str, Any]] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    decks: dict[str, list[str]] = field(default_factory=dict)
    custom_replies_enabled: bool = True
    helpdocs: dict[str, str] = field(default_factory=dict)
    sealpacks: dict[str, dict[str, str]] = field(default_factory=dict)
    teams: dict[str, list[str]] = field(default_factory=dict)
    bans: dict[str, str] = field(default_factory=dict)


@dataclass
class CommandOutcome:
    text: str = ""
    stop: bool = True
    group_card: str | None = None
    report_card_status: bool = False


class DiceError(ValueError):
    pass


class DiceRoller:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def roll_expr(self, expr: str) -> tuple[int, str]:
        parser = _DiceParser(expr, self.rng)
        total, detail = parser.parse()
        return total, detail

    def d100(self) -> int:
        return self.rng.randint(1, 100)

    def d20(self, mode: str = "") -> tuple[int, str]:
        rolls = [self.rng.randint(1, 20)]
        if mode in {"adv", "dis"}:
            rolls.append(self.rng.randint(1, 20))
        if mode == "adv":
            return max(rolls), f"{rolls}取高"
        if mode == "dis":
            return min(rolls), f"{rolls}取低"
        return rolls[0], str(rolls[0])


class _DiceParser:
    def __init__(self, expr: str, rng: random.Random) -> None:
        self.expr = expr.replace("D", "d").replace("％", "%").strip()
        self.rng = rng
        self.tokens = re.findall(r"\d*d(?:\d+|%)|\d+|[()+\-*/]", self.expr)
        self.pos = 0
        if not self.tokens or "".join(self.tokens) != re.sub(r"\s+", "", self.expr):
            raise DiceError("骰点表达式格式不对")

    def parse(self) -> tuple[int, str]:
        value, detail = self._expr()
        if self.pos != len(self.tokens):
            raise DiceError("骰点表达式没有读完")
        return value, detail

    def _expr(self) -> tuple[int, str]:
        value, detail = self._term()
        while self._peek() in {"+", "-"}:
            op = self._take()
            right, right_detail = self._term()
            if op == "+":
                value += right
            else:
                value -= right
            detail = f"{detail}{op}{right_detail}"
        return value, detail

    def _term(self) -> tuple[int, str]:
        value, detail = self._factor()
        while self._peek() in {"*", "/"}:
            op = self._take()
            right, right_detail = self._factor()
            if op == "*":
                value *= right
            else:
                if right == 0:
                    raise DiceError("除数不能为 0")
                value = math.floor(value / right)
            detail = f"{detail}{op}{right_detail}"
        return value, detail

    def _factor(self) -> tuple[int, str]:
        token = self._take()
        if token == "(":
            value, detail = self._expr()
            if self._take() != ")":
                raise DiceError("缺少右括号")
            return value, f"({detail})"
        if token == "-":
            value, detail = self._factor()
            return -value, f"-{detail}"
        if "d" in token:
            count_text, sides_text = token.split("d", 1)
            count = int(count_text) if count_text else 1
            sides = 100 if sides_text == "%" else int(sides_text)
            if count < 1 or count > 200 or sides < 2 or sides > 100000:
                raise DiceError("骰子数量或面数超出范围")
            rolls = [self.rng.randint(1, sides) for _ in range(count)]
            return sum(rolls), f"{token}{rolls}"
        if token.isdigit():
            return int(token), token
        raise DiceError("骰点表达式格式不对")

    def _peek(self) -> str | None:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def _take(self) -> str:
        if self.pos >= len(self.tokens):
            raise DiceError("表达式提前结束")
        token = self.tokens[self.pos]
        self.pos += 1
        return token


class SeaDiceService:
    def __init__(
        self,
        state_path: str | Path | None = None,
        rng: random.Random | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.state_path = Path(state_path) if state_path else None
        self.roller = DiceRoller(rng)
        self.config = config or {}
        self.router = CommandRouter()
        self.groups: dict[str, GroupState] = {}
        self._current_context: dict[str, str] = {}
        self._register_handlers()
        self._load()

    def handle(
        self,
        text: str,
        *,
        group_id: str,
        user_id: str,
        sender_name: str = "",
    ) -> CommandOutcome | None:
        raw = text.strip()
        if not raw.startswith((".", "。")):
            self.record_plain(raw, group_id=group_id, user_id=user_id, sender_name=sender_name)
            return None
        body = raw[1:].strip()
        if not body:
            return None
        group = self._group(group_id)
        player = self._player(group, user_id, sender_name)
        cmd, rest = self._parse_command_body(body)
        if cmd not in {"bot", "sealhelp", "help"} and not group.active:
            return CommandOutcome("骰子当前关闭。使用 .bot on 开启。")

        if user_id in group.bans and cmd not in {"help", "sealhelp", "bot"}:
            return CommandOutcome("该用户在本群黑名单中。")

        handler = self.router.get(cmd)
        if not handler:
            return None
        self._current_context = {
            "group_id": group_id,
            "user_id": user_id,
            "sender_name": sender_name,
            "raw": raw,
        }
        try:
            outcome = handler(cmd, rest, group, player, user_id)
        finally:
            self._current_context = {}
        if outcome and outcome.text:
            self._record(group, user_id, sender_name, raw, outcome.text)
        self._save()
        return outcome

    def record_plain(
        self,
        text: str,
        *,
        group_id: str,
        user_id: str,
        sender_name: str = "",
    ) -> None:
        if not text:
            return
        group = self._group(group_id)
        if group.active_log and group.active_log in group.logs:
            log = group.logs[group.active_log]
            if log.active and not log.halted:
                who = sender_name or user_id
                log.lines.append(f"{who}: {text}")
                self._save()

    def _parse_command_body(self, body: str) -> tuple[str, str]:
        first, rest = self._split_first(body)
        exact = first.lower()
        if self.router.get(exact):
            return exact, rest
        matched = self.router.match_prefix(body)
        if matched:
            cmd, rest_text, _ = matched
            return cmd, rest_text
        return exact, rest

    def _register_handlers(self) -> None:
        self.router.register(("bot",), self._cmd_bot)
        self.router.register(("set",), self._cmd_set)
        self.router.register(("setcoc",), self._cmd_setcoc)
        self.router.register(("nn",), self._cmd_nn)
        self.router.register(("pc", "ch", "char", "character", "角色"), self._cmd_pc)
        self.router.register(("st", "cst", "dst"), self._cmd_st)
        self.router.register(("coc",), self._cmd_coc)
        self.router.register(("dnd", "dndx"), self._cmd_dnd)
        self.router.register(
            ("r", "rd", "roll", "rh", "rhd", "rdh", "rx", "rxh", "rhx"),
            self._cmd_roll,
        )
        self.router.register(
            (
                "ra",
                "rc",
                "rah",
                "rch",
                "cra",
                "crc",
                "crah",
                "crch",
                "rav",
                "rcv",
            ),
            self._cmd_check,
        )
        self.router.register(("sc",), self._cmd_san)
        self.router.register(("en",), self._cmd_en)
        self.router.register(("ti",), self._cmd_ti)
        self.router.register(("li",), self._cmd_li)
        self.router.register(("ri",), self._cmd_ri)
        self.router.register(("init",), self._cmd_init)
        self.router.register(("buff",), self._cmd_buff)
        self.router.register(("dbuff",), self._cmd_dbuff)
        self.router.register(("spellslots", "ss", "dss", "法术位"), self._cmd_spellslots)
        self.router.register(("cast", "dcast"), self._cmd_cast)
        self.router.register(("长休", "longrest", "dlongrest"), self._cmd_longrest)
        self.router.register(("ds", "死亡豁免"), self._cmd_death_save)
        self.router.register(("log",), self._cmd_log)
        self.router.register(("stat", "hiy"), self._cmd_stat)
        self.router.register(("sn",), self._cmd_sn)
        self.router.register(("ob",), self._cmd_ob)
        self.router.register(("sealhelp", "help"), self._cmd_help)
        self.router.register(("find", "查询", "査詢"), self._cmd_find)
        self.router.register(("helpdoc",), self._cmd_helpdoc)
        self.router.register(("ext",), self._cmd_ext)
        self.router.register(("js",), self._cmd_js)
        self.router.register(("sealpack",), self._cmd_sealpack)
        self.router.register(("matrix",), self._cmd_matrix)
        self.router.register(("draw", "deck"), self._cmd_deck)
        self.router.register(("alias",), self._cmd_alias)
        self.router.register(("&", "a"), self._cmd_alias_exec)
        self.router.register(("reply",), self._cmd_reply)
        self.router.register(("jrrp",), self._cmd_jrrp)
        self.router.register(("gugu", "咕咕"), self._cmd_gugu)
        self.router.register(("ping",), self._cmd_ping)
        self.router.register(("who",), self._cmd_who)
        self.router.register(("name", "namednd"), self._cmd_name)
        self.router.register(("cnmods", "modu", "魔都"), self._cmd_modu)
        self.router.register(("userid",), self._cmd_userid)
        self.router.register(("botlist",), self._cmd_botlist)
        self.router.register(("dismiss",), self._cmd_dismiss)
        self.router.register(("master",), self._cmd_master)
        self.router.register(("black", "ban"), self._cmd_ban)
        self.router.register(("team",), self._cmd_team)
        self.router.register(
            ("text", "rsr", "ek", "ekgen", "dx", "dxh", "w", "ww", "wh", "wwh", "jsr", "drl", "drlh", "check", "send", "welcome"),
            self._cmd_compat_placeholder,
        )

    def help_text(self) -> str:
        return (
            "海豹骰核心指令：\n"
            ".bot on/off/about\n"
            ".set coc/dnd/info/clr\n"
            ".nn 昵称 .pc new/load/save/list/del/tag\n"
            ".st hp=10 hp-1 .cst .dst\n"
            ".r 1d100 .ra 侦查 .rc 侦查 .sc 1/1d6\n"
            ".coc .en 侦查 .ti .li\n"
            ".dnd .dndx .ri .init .ss .cast .longrest .ds\n"
            ".log new/on/off/end/list/get/del/stat/export\n"
            ".draw 牌堆 .deck list/add/show/del\n"
            ".alias 名称 .指令 .&名称 .jrrp .who .name\n"
            ".find 关键词 .helpdoc list/add/get/del .matrix\n"
            ".ext .js .sealpack .black .team\n"
            ".sn coc/cocL/dnd/none/off/expr ..."
        )

    def _cmd_help(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        return CommandOutcome(self.help_text())

    def _cmd_bot(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action = rest.strip().lower()
        if action in {"on", "开启"}:
            group.active = True
            return CommandOutcome("骰子已开启。")
        if action in {"off", "关闭"}:
            group.active = False
            return CommandOutcome("骰子已关闭。")
        if action in {"about", "info", ""}:
            status = "开启" if group.active else "关闭"
            return CommandOutcome(f"海豹骰核心复刻 for AstrBot。当前状态：{status}。")
        if action in {"bye", "quit"}:
            group.active = False
            return CommandOutcome("骰子已关闭。")
        return CommandOutcome("用法：.bot on/off/about")

    def _cmd_set(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        arg = rest.strip().lower()
        if arg in {"coc", "coc7"}:
            group.rule = "coc"
            self._sheet(group, player, "coc")
            return CommandOutcome("当前规则已切换为 COC7。", group_card=self._render_sn(player))
        if arg in {"dnd", "dnd5e", "5e"}:
            group.rule = "dnd"
            self._sheet(group, player, "dnd")
            return CommandOutcome("当前规则已切换为 DND5e。", group_card=self._render_sn(player))
        if arg in {"info", ""}:
            return CommandOutcome(f"当前规则：{group.rule}\nCOC 房规：{group.coc_rule}")
        if arg in {"clr", "clear"}:
            group.rule = "coc"
            return CommandOutcome("群规则已重置为 COC7。")
        return CommandOutcome("用法：.set coc/dnd/info/clr")

    def _cmd_setcoc(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        value = rest.strip() or "0"
        group.coc_rule = value
        group.rule = "coc"
        self._sheet(group, player, "coc")
        return CommandOutcome(f"COC 房规已设置为 {value}。")

    def _cmd_nn(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        name = rest.strip()
        if not name:
            return CommandOutcome(f"当前昵称：{player.nickname or '未设置'}")
        player.nickname = name
        return CommandOutcome(f"昵称已设为 {name}。", group_card=self._render_sn(player))

    def _cmd_pc(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action, arg = self._split_first(rest.strip())
        action = action.lower()
        if action in {"", "show"}:
            sheet = self._sheet(group, player)
            return CommandOutcome(self._format_sheet(sheet))
        if action == "new":
            name = arg.strip() or f"{group.rule}-card"
            player.sheets[name] = self._new_sheet(name, group.rule)
            player.active = name
            return CommandOutcome(f"已新建并绑定人物卡：{name}", group_card=self._render_sn(player))
        if action in {"list", "ls"}:
            if not player.sheets:
                return CommandOutcome("当前没有人物卡。")
            items = [f"* {name}" if name == player.active else f"  {name}" for name in player.sheets]
            return CommandOutcome("人物卡列表：\n" + "\n".join(items))
        if action in {"load", "save", "tag"}:
            name = arg.strip()
            if not name:
                return CommandOutcome(f"用法：.pc {action} 名称")
            if action == "load":
                if name not in player.sheets:
                    player.sheets[name] = self._new_sheet(name, group.rule)
                player.active = name
                return CommandOutcome(f"已载入人物卡：{name}", group_card=self._render_sn(player))
            if action == "save":
                sheet = self._sheet(group, player)
                if name != sheet.name:
                    player.sheets[name] = CharacterSheet(name=name, rule=sheet.rule, attrs=dict(sheet.attrs))
                    player.active = name
                return CommandOutcome(f"人物卡已保存为：{name}")
            sheet = self._sheet(group, player)
            if name not in sheet.tags:
                sheet.tags.append(name)
            return CommandOutcome(f"已给人物卡添加标签：{name}")
        if action in {"rename"}:
            old = player.active
            new = arg.strip()
            if not new:
                return CommandOutcome("用法：.pc rename 新名称")
            sheet = self._sheet(group, player)
            sheet.name = new
            player.sheets[new] = sheet
            if old != new:
                player.sheets.pop(old, None)
            player.active = new
            return CommandOutcome(f"人物卡已改名为：{new}", group_card=self._render_sn(player))
        if action in {"del", "rm"}:
            name = arg.strip() or player.active
            if name in player.sheets:
                player.sheets.pop(name)
                player.active = next(iter(player.sheets), "default")
                return CommandOutcome(f"已删除人物卡：{name}", group_card=self._render_sn(player))
            return CommandOutcome(f"没有找到人物卡：{name}")
        if action.lower() == "untagall":
            self._sheet(group, player).tags.clear()
            return CommandOutcome("已清空人物卡标签。")
        return CommandOutcome("用法：.pc new/load/save/list/rename/del/tag/untagAll")

    def _cmd_st(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        if cmd == "cst":
            self._sheet(group, player, "coc")
        elif cmd == "dst":
            self._sheet(group, player, "dnd")
        sheet = self._sheet(group, player)
        if not rest.strip():
            return CommandOutcome(self._format_sheet(sheet))
        changes = []
        for item in re.split(r"[\s,，]+", rest.strip()):
            if not item:
                continue
            parsed = self._parse_attr_change(item)
            if not parsed:
                return CommandOutcome(f"无法识别属性改动：{item}")
            key, op, value_text = parsed
            key = self._attr_key(key.strip(), sheet)
            try:
                value, _ = self.roller.roll_expr(value_text)
            except DiceError as exc:
                return CommandOutcome(f"属性表达式错误：{item}，{exc}")
            old = int(sheet.attrs.get(key, 0))
            if op in {"=", ":", "："}:
                new = value
            elif op == "+":
                new = old + value
            else:
                new = old - value
            sheet.attrs[key] = new
            self._sync_coc_aliases(sheet, key, new)
            changes.append(f"{key}:{old}->{new}")
        return CommandOutcome("属性已更新：" + "，".join(changes), group_card=self._render_sn(player))

    def _cmd_coc(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        name = rest.strip() or "coc-card"
        attrs = {
            "str": self._sum_rolls(3, 6) * 5,
            "con": self._sum_rolls(3, 6) * 5,
            "siz": (self._sum_rolls(2, 6) + 6) * 5,
            "dex": self._sum_rolls(3, 6) * 5,
            "app": self._sum_rolls(3, 6) * 5,
            "int": (self._sum_rolls(2, 6) + 6) * 5,
            "pow": self._sum_rolls(3, 6) * 5,
            "edu": (self._sum_rolls(2, 6) + 6) * 5,
        }
        hpmax = max(1, (attrs["con"] + attrs["siz"]) // 10)
        attrs.update({"hpmax": hpmax, "hp": hpmax, "san": attrs["pow"]})
        sheet = CharacterSheet(name=name, rule="coc", attrs=attrs)
        self._sync_all_coc_aliases(sheet)
        player.sheets[name] = sheet
        player.active = name
        return CommandOutcome("COC 人物卡已生成：\n" + self._format_sheet(sheet), group_card=self._render_sn(player))

    def _cmd_dnd(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        name = rest.strip() or "dnd-card"
        attrs = {}
        for attr in ("str", "dex", "con", "int", "wis", "cha"):
            rolls = sorted([self.roller.rng.randint(1, 6) for _ in range(4)])
            attrs[attr] = sum(rolls[1:])
        attrs["hpmax"] = 10 + self._ability_mod(attrs["con"])
        attrs["hp"] = attrs["hpmax"]
        attrs["ac"] = 10 + self._ability_mod(attrs["dex"])
        attrs["dc"] = 8
        attrs["pp"] = 10 + self._ability_mod(attrs["wis"])
        sheet = CharacterSheet(name=name, rule="dnd", attrs=attrs)
        player.sheets[name] = sheet
        player.active = name
        return CommandOutcome("DND 人物卡已生成：\n" + self._format_sheet(sheet), group_card=self._render_sn(player))

    def _cmd_roll(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        hidden = "h" in cmd
        repeat = 1
        expr = rest.strip() or "1d100"
        if cmd.startswith("rx") or cmd.endswith("x"):
            first, remain = self._split_first(expr)
            if first.isdigit():
                repeat = max(1, min(20, int(first)))
                expr = remain.strip() or "1d100"
        lines = []
        for _ in range(repeat):
            try:
                total, detail = self.roller.roll_expr(expr)
            except DiceError as e:
                return CommandOutcome(str(e))
            lines.append(f"{expr} = {total} ({detail})")
        prefix = "暗骰 " if hidden else ""
        return CommandOutcome(prefix + "\n".join(lines))

    def _cmd_check(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        hidden = cmd.endswith("h")
        sheet = self._sheet(group, player)
        target_name, value = self._parse_check_target(rest.strip(), sheet)
        if sheet.rule == "dnd" or cmd.startswith("d"):
            roll, detail = self.roller.d20()
            mod = self._ability_mod(value) if value > 9 else value
            total = roll + mod
            prefix = "暗骰 " if hidden else ""
            return CommandOutcome(f"{prefix}{target_name} 检定：d20({detail})+{mod} = {total}")
        roll = self.roller.d100()
        level = self._coc_level(roll, value)
        prefix = "暗骰 " if hidden else ""
        return CommandOutcome(f"{prefix}{target_name} 检定：D100={roll}/{value}，{level}")

    def _cmd_san(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        sheet = self._sheet(group, player, "coc")
        dice_expr, success_expr, fail_expr, target = self._parse_san_args(
            rest.strip(),
            sheet,
        )
        roll = self.roller.d100()
        roll_detail = str(roll)
        if dice_expr.lower() not in {"d100", "1d100"}:
            try:
                roll, roll_detail = self.roller.roll_expr(dice_expr)
            except DiceError as exc:
                return CommandOutcome(f"SAN Check 判定表达式错误：{exc}")
        ok = roll <= target
        loss_expr = success_expr if ok else fail_expr
        try:
            loss_total, loss_detail = self.roller.roll_expr(loss_expr)
        except DiceError as exc:
            return CommandOutcome(f"SAN Check 损失表达式错误：{exc}")
        old = int(sheet.attrs.get("san", sheet.attrs.get("理智", 0)))
        new = max(0, old - loss_total)
        sheet.attrs["san"] = new
        sheet.attrs["理智"] = new
        result = "成功" if ok else "失败"
        return CommandOutcome(
            f"SAN Check：{dice_expr}={roll}/{target} ({roll_detail})，{result}，损失 {loss_total} ({loss_detail})，SAN {old}->{new}",
            group_card=self._render_sn(player),
        )

    def _cmd_en(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        sheet = self._sheet(group, player, "coc")
        key = rest.strip()
        if not key:
            return CommandOutcome("用法：.en 技能名")
        key, explicit_value = self._split_name_value(key)
        key = self._attr_key(key, sheet)
        old = explicit_value if explicit_value is not None else int(sheet.attrs.get(key, 0))
        roll = self.roller.d100()
        if roll > old:
            inc, detail = self.roller.roll_expr("1d10")
            sheet.attrs[key] = old + inc
            return CommandOutcome(f"{key} 成长：D100={roll}>{old}，+{inc} ({detail})，{old}->{old + inc}", group_card=self._render_sn(player))
        return CommandOutcome(f"{key} 成长：D100={roll}<={old}，没有成长。")

    def _cmd_ti(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        idx = self.roller.rng.randint(1, len(TEMP_INSANITY))
        return CommandOutcome(f"临时疯狂 {idx}：{TEMP_INSANITY[idx - 1]}")

    def _cmd_li(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        idx = self.roller.rng.randint(1, len(INDEFINITE_INSANITY))
        return CommandOutcome(f"总结性疯狂 {idx}：{INDEFINITE_INSANITY[idx - 1]}")

    def _cmd_ri(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        sheet = self._sheet(group, player, "dnd")
        dex = int(sheet.attrs.get("dex", 10))
        mod = self._ability_mod(dex)
        roll, detail = self.roller.d20()
        total = roll + mod
        name = player.nickname or sheet.name
        group.initiative = [i for i in group.initiative if i.get("user_id") != user_id]
        group.initiative.append({"user_id": user_id, "name": name, "value": total})
        group.initiative.sort(key=lambda x: int(x["value"]), reverse=True)
        return CommandOutcome(f"{name} 先攻：d20({detail})+{mod} = {total}\n" + self._format_init(group))

    def _cmd_init(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action, arg = self._split_first(rest.strip())
        if action.lower() in {"clr", "clear"}:
            group.initiative.clear()
            return CommandOutcome("先攻列表已清空。")
        if action.lower() in {"del", "rm"}:
            name = arg.strip()
            group.initiative = [i for i in group.initiative if i.get("name") != name]
            return CommandOutcome(self._format_init(group))
        if action and arg.strip().lstrip("-").isdigit():
            group.initiative.append({"user_id": "", "name": action, "value": int(arg.strip())})
            group.initiative.sort(key=lambda x: int(x["value"]), reverse=True)
        return CommandOutcome(self._format_init(group))

    def _cmd_buff(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        sheet = self._sheet(group, player, "dnd")
        buff = rest.strip()
        if not buff:
            return CommandOutcome("当前 Buff：" + ("，".join(sheet.buffs) if sheet.buffs else "无"))
        if buff not in sheet.buffs:
            sheet.buffs.append(buff)
        return CommandOutcome(f"已添加 Buff：{buff}")

    def _cmd_dbuff(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        sheet = self._sheet(group, player, "dnd")
        buff = rest.strip()
        if not buff:
            sheet.buffs.clear()
            return CommandOutcome("已清空 Buff。")
        if buff in sheet.buffs:
            sheet.buffs.remove(buff)
        return CommandOutcome(f"已移除 Buff：{buff}")

    def _cmd_spellslots(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        sheet = self._sheet(group, player, "dnd")
        if not rest.strip():
            return CommandOutcome("法术位：" + self._format_slots(sheet))
        for item in re.split(r"[\s,，]+", rest.strip()):
            m = re.fullmatch(r"(\d+)(?:环|级)?[=:：](\d+)(?:/(\d+))?", item)
            if not m:
                return CommandOutcome("用法：.ss 1=4 2=3 或 .ss 1=2/4")
            level, current, maximum = m.groups()
            sheet.spell_slots[level] = int(current)
            sheet.spell_slots_max[level] = int(maximum or current)
        return CommandOutcome("法术位已更新：" + self._format_slots(sheet), group_card=self._render_sn(player))

    def _cmd_cast(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        sheet = self._sheet(group, player, "dnd")
        level = re.sub(r"\D", "", rest.strip()) or "1"
        old = int(sheet.spell_slots.get(level, 0))
        if old <= 0:
            return CommandOutcome(f"{level} 环法术位不足。")
        sheet.spell_slots[level] = old - 1
        return CommandOutcome(f"消耗 {level} 环法术位：{old}->{old - 1}", group_card=self._render_sn(player))

    def _cmd_longrest(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        sheet = self._sheet(group, player, "dnd")
        old_hp = int(sheet.attrs.get("hp", 0))
        sheet.attrs["hp"] = int(sheet.attrs.get("hpmax", old_hp))
        sheet.spell_slots = dict(sheet.spell_slots_max)
        sheet.death_success = 0
        sheet.death_failure = 0
        return CommandOutcome(f"长休完成，HP {old_hp}->{sheet.attrs['hp']}，法术位已恢复。", group_card=self._render_sn(player))

    def _cmd_death_save(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        sheet = self._sheet(group, player, "dnd")
        roll, detail = self.roller.d20()
        if roll == 20:
            sheet.attrs["hp"] = 1
            sheet.death_success = 0
            sheet.death_failure = 0
            return CommandOutcome(f"死亡豁免：d20({detail})，大成功，HP 恢复到 1。", group_card=self._render_sn(player))
        if roll == 1:
            sheet.death_failure += 2
            result = "大失败，失败+2"
        elif roll >= 10:
            sheet.death_success += 1
            result = "成功+1"
        else:
            sheet.death_failure += 1
            result = "失败+1"
        return CommandOutcome(f"死亡豁免：d20({detail})，{result}。成功{sheet.death_success}/失败{sheet.death_failure}")

    def _cmd_log(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action, arg = self._split_first(rest.strip())
        action = action.lower() or "list"
        if action == "new":
            name = arg.strip() or time.strftime("log-%Y%m%d-%H%M%S")
            group.logs[name] = LogEntry(name=name)
            group.active_log = name
            return CommandOutcome(f"日志已创建并开启：{name}")
        if action == "on":
            name = arg.strip() or group.active_log
            if not name or name not in group.logs:
                return CommandOutcome("没有可开启的日志。")
            group.active_log = name
            group.logs[name].active = True
            group.logs[name].halted = False
            return CommandOutcome(f"日志已开启：{name}")
        if action in {"off", "halt"}:
            if group.active_log and group.active_log in group.logs:
                group.logs[group.active_log].halted = True
                return CommandOutcome(f"日志已暂停：{group.active_log}")
            return CommandOutcome("当前没有活动日志。")
        if action == "end":
            if group.active_log and group.active_log in group.logs:
                name = group.active_log
                group.logs[name].active = False
                group.logs[name].halted = True
                group.active_log = ""
                return CommandOutcome(f"日志已结束：{name}")
            return CommandOutcome("当前没有活动日志。")
        if action == "list":
            if not group.logs:
                return CommandOutcome("当前没有日志。")
            lines = [f"* {n}" if n == group.active_log else f"  {n}" for n in group.logs]
            return CommandOutcome("日志列表：\n" + "\n".join(lines))
        if action in {"get", "export"}:
            name = arg.strip() or group.active_log
            if not name or name not in group.logs:
                return CommandOutcome("没有找到日志。")
            log = group.logs[name]
            body = "\n".join(log.lines[-80:]) or "日志为空。"
            return CommandOutcome(f"日志 {name}：\n{body}")
        if action in {"del", "rm"}:
            name = arg.strip()
            if name in group.logs:
                group.logs.pop(name)
                if group.active_log == name:
                    group.active_log = ""
                return CommandOutcome(f"日志已删除：{name}")
            return CommandOutcome("没有找到日志。")
        if action == "stat":
            return self._cmd_stat(cmd, "log", group, player, user_id)
        return CommandOutcome("用法：.log new/on/off/end/halt/list/get/del/stat/export")

    def _cmd_stat(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        if rest.strip().startswith("log") or cmd == "stat":
            total = sum(len(log.lines) for log in group.logs.values())
            return CommandOutcome(f"日志数量：{len(group.logs)}，记录行数：{total}")
        return CommandOutcome("用法：.stat log")

    def _cmd_sn(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        arg = rest.strip()
        low = arg.lower()
        if low in {"off", "none", "关闭"}:
            player.sn_template = ""
            return CommandOutcome("自动群名片已关闭。", group_card="", report_card_status=True)
        if arg in SN_TEMPLATES:
            player.sn_template = SN_TEMPLATES[arg]
        elif low.startswith("expr "):
            player.sn_template = arg[5:].strip()
        elif arg:
            return CommandOutcome("用法：.sn coc/cocL/dnd/none/off/expr 模板")
        card = self._render_sn(player)
        if not card:
            return CommandOutcome("当前没有群名片模板。")
        return CommandOutcome(f"群名片模板已设置。\n名片预览：{card}", group_card=card, report_card_status=True)

    def _cmd_ob(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        return CommandOutcome("OB 记录已保留为日志兼容项。当前版本可使用 .log 记录观战文本。")

    def _cmd_ext(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        enabled = self._config_bool("enable_legacy_js_compat", True)
        status = "开启" if enabled else "关闭"
        return CommandOutcome(
            "COC7 和 DND5e 已内置启用。\n"
            f"海豹 JS 兼容层：{status}\n"
            "新扩展建议使用 AstrBot 插件体系。",
        )

    def _cmd_find(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        query = rest.strip()
        docs = []
        if query:
            q = query.lower()
            for key, text in group.helpdocs.items():
                if q in key.lower() or q in text.lower():
                    docs.append(f"{key}: {text}")
        matrix = find_feature_docs(query)
        if docs:
            return CommandOutcome(matrix + "\n群内 helpdoc：\n" + "\n".join(docs))
        return CommandOutcome(matrix)

    def _cmd_helpdoc(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action, arg = self._split_first(rest.strip())
        action = action.lower() or "list"
        if action in {"list", "ls"}:
            if not group.helpdocs:
                return CommandOutcome("当前没有群内 helpdoc。")
            return CommandOutcome("群内 helpdoc：\n" + "\n".join(sorted(group.helpdocs)))
        if action in {"get", "show"}:
            key = arg.strip()
            if not key or key not in group.helpdocs:
                return CommandOutcome("没有找到对应 helpdoc。")
            return CommandOutcome(f"{key}:\n{group.helpdocs[key]}")
        if action == "add":
            key, text = self._split_first(arg)
            if not key or not text:
                return CommandOutcome("用法：.helpdoc add 名称 内容")
            group.helpdocs[key] = text.strip()
            return CommandOutcome(f"helpdoc 已保存：{key}")
        if action in {"del", "rm"}:
            key = arg.strip()
            if group.helpdocs.pop(key, None) is None:
                return CommandOutcome("没有找到对应 helpdoc。")
            return CommandOutcome(f"helpdoc 已删除：{key}")
        return CommandOutcome("用法：.helpdoc list/get/add/del")

    def _cmd_js(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action = rest.strip().lower() or "status"
        enabled = self._config_bool("enable_legacy_js_compat", True)
        if action in {"status", "info"}:
            state = "开启" if enabled else "关闭"
            return CommandOutcome(f"海豹 JS 兼容层：{state}。当前不执行任意 JS。")
        if action in {"list", "ls"}:
            packs = ", ".join(sorted(group.sealpacks)) or "无"
            return CommandOutcome(f"已记录扩展包：{packs}")
        if action in {"reload", "on", "off"}:
            return CommandOutcome("JS 扩展启停交给兼容层记录，新扩展请使用 AstrBot 插件。")
        return CommandOutcome("用法：.js status/list/reload")

    def _cmd_sealpack(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action, arg = self._split_first(rest.strip())
        action = action.lower() or "list"
        if action in {"list", "ls", "status"}:
            if not group.sealpacks:
                return CommandOutcome("当前没有记录 sealpack。")
            lines = [f"{name}: {meta.get('state', 'imported')} {meta.get('path', '')}" for name, meta in group.sealpacks.items()]
            return CommandOutcome("sealpack 记录：\n" + "\n".join(lines))
        if action in {"import", "add"}:
            path = Path(arg.strip())
            if not path.name:
                return CommandOutcome("用法：.sealpack import 文件.sealpack")
            if path.suffix.lower() != ".sealpack":
                return CommandOutcome("只能记录 .sealpack 文件。")
            group.sealpacks[path.name] = {"path": str(path), "state": "imported"}
            return CommandOutcome(f"sealpack 已记录：{path.name}")
        if action in {"del", "rm"}:
            name = arg.strip()
            if group.sealpacks.pop(name, None) is None:
                return CommandOutcome("没有找到对应 sealpack。")
            return CommandOutcome(f"sealpack 已删除：{name}")
        return CommandOutcome("用法：.sealpack list/import/del")

    def _cmd_matrix(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        return CommandOutcome(format_feature_matrix(rest.strip()))

    def _cmd_deck(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        if cmd == "draw":
            deck_name = rest.strip() or "coc"
            return self._draw_from_deck(deck_name, group)
        action, arg = self._split_first(rest.strip())
        action = action.lower() or "list"
        if action in {"list", "ls"}:
            names = sorted(set(DEFAULT_DECKS) | set(group.decks))
            return CommandOutcome("牌堆列表：" + (" ".join(names) if names else "无"))
        if action == "draw":
            return self._draw_from_deck(arg.strip() or "coc", group)
        if action in {"show", "get"}:
            name = arg.strip()
            cards = self._deck_cards(name, group)
            if not cards:
                return CommandOutcome("没有找到牌堆。")
            return CommandOutcome(f"{name}：\n" + "\n".join(cards[:30]))
        if action == "add":
            name, cards_text = self._split_first(arg)
            cards = [card.strip() for card in re.split(r"[|｜]", cards_text) if card.strip()]
            if not name or not cards:
                return CommandOutcome("用法：.deck add 名称 卡1|卡2|卡3")
            group.decks[name] = cards
            return CommandOutcome(f"牌堆已保存：{name}，共 {len(cards)} 张。")
        if action in {"del", "rm"}:
            name = arg.strip()
            if group.decks.pop(name, None) is None:
                return CommandOutcome("没有找到自定义牌堆。")
            return CommandOutcome(f"牌堆已删除：{name}")
        return CommandOutcome("用法：.deck list/draw/show/add/del")

    def _cmd_alias(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action, arg = self._split_first(rest.strip())
        if not action or action.lower() in {"list", "ls"}:
            items = []
            items.extend(f"{name} -> {target}" for name, target in sorted(group.aliases.items()))
            items.extend(f"{name} -> {target}" for name, target in sorted(player.aliases.items()))
            return CommandOutcome("快捷指令：\n" + ("\n".join(items) if items else "无"))
        if action.lower() in {"del", "rm"}:
            name = arg.strip()
            removed = player.aliases.pop(name, None)
            removed = group.aliases.pop(name, None) if removed is None else removed
            if removed is None:
                return CommandOutcome("没有找到快捷指令。")
            return CommandOutcome(f"快捷指令已删除：{name}")
        global_alias = action == "--global"
        if global_alias:
            name, target = self._split_first(arg)
        else:
            name, target = action, arg
        if not name or not target:
            return CommandOutcome("用法：.alias 名称 .指令 或 .alias --global 名称 .指令")
        if not target.startswith((".", "。")):
            target = "." + target
        if global_alias:
            group.aliases[name] = target
        else:
            player.aliases[name] = target
        return CommandOutcome(f"快捷指令已保存：{name} -> {target}")

    def _cmd_alias_exec(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        name, extra = self._split_first(rest.strip())
        if not name:
            return CommandOutcome("用法：.&名称 或 .a 名称")
        target = player.aliases.get(name) or group.aliases.get(name)
        if not target:
            return CommandOutcome(f"未设置快捷指令：{name}")
        if extra:
            target = target + " " + extra
        if target.strip() == self._current_context.get("raw", "").strip():
            return CommandOutcome("快捷指令循环调用已停止。")
        outcome = self.handle(
            target,
            group_id=self._current_context.get("group_id", "private"),
            user_id=user_id,
            sender_name=self._current_context.get("sender_name", ""),
        )
        if outcome is None:
            return CommandOutcome(f"快捷指令没有产生回复：{name}")
        return CommandOutcome(f"快捷指令 {name}：\n{outcome.text}", group_card=outcome.group_card, report_card_status=outcome.report_card_status)

    def _cmd_reply(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action = rest.strip().lower() or "status"
        if action in {"on", "enable"}:
            group.custom_replies_enabled = True
            return CommandOutcome("自定义回复兼容层已开启。")
        if action in {"off", "disable"}:
            group.custom_replies_enabled = False
            return CommandOutcome("自定义回复兼容层已关闭。")
        state = "开启" if group.custom_replies_enabled else "关闭"
        return CommandOutcome(f"自定义回复兼容层：{state}。复杂回复规则将进入兼容层。")

    def _cmd_jrrp(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        today = time.strftime("%Y-%m-%d")
        digest = hashlib.sha256(f"{today}:{user_id}".encode()).hexdigest()
        value = int(digest[:8], 16) % 100 + 1
        name = player.nickname or user_id
        return CommandOutcome(f"{name} 今日人品：{value}")

    def _cmd_gugu(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        target = rest.strip() or player.nickname or user_id
        return CommandOutcome(f"{target} 咕咕了一下。")

    def _cmd_ping(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        return CommandOutcome("pong")

    def _cmd_who(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        names = [part.strip() for part in re.split(r"[\s,，]+", rest.strip()) if part.strip()]
        if not names:
            names = [p.nickname or uid for uid, p in group.players.items()]
        if not names:
            return CommandOutcome("当前没有可随机的对象。")
        self.roller.rng.shuffle(names)
        return CommandOutcome("随机顺序：\n" + "\n".join(f"{i + 1}. {name}" for i, name in enumerate(names)))

    def _cmd_name(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        parts = rest.split()
        count = 1
        style = "dnd" if cmd == "namednd" else "cn"
        for part in parts:
            if part.isdigit():
                count = max(1, min(10, int(part)))
            else:
                style = part.lower()
        names = []
        for _ in range(count):
            if style in {"dnd", "fantasy"}:
                names.append(self.roller.rng.choice(DND_NAMES))
            else:
                names.append(self.roller.rng.choice(CN_SURNAMES) + self.roller.rng.choice(CN_GIVEN))
        return CommandOutcome("随机姓名：\n" + "\n".join(names))

    def _cmd_modu(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        keyword = rest.strip() or "随机"
        return CommandOutcome(f"模组工具已接入兼容层。当前查询关键词：{keyword}")

    def _cmd_userid(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        group_id = self._current_context.get("group_id", "private")
        return CommandOutcome(f"用户 ID：{user_id}\n群 ID：{group_id}")

    def _cmd_botlist(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        state = "开启" if group.active else "关闭"
        route = self.config.get("route", "python")
        return CommandOutcome(f"当前群骰子：{state}\n运行路线：{route}")

    def _cmd_dismiss(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        group.active = False
        return CommandOutcome("骰子已在当前会话关闭。")

    def _cmd_master(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        return CommandOutcome("骰主权限由 AstrBot 管理员体系承接。插件内保留 SeaDice master 指令入口。")

    def _cmd_ban(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action, arg = self._split_first(rest.strip())
        action = action.lower() or "list"
        if action in {"list", "ls"}:
            if not group.bans:
                return CommandOutcome("当前群黑名单为空。")
            lines = [f"{uid}: {reason}" for uid, reason in sorted(group.bans.items())]
            return CommandOutcome("当前群黑名单：\n" + "\n".join(lines))
        if action in {"add", "on"}:
            target, reason = self._split_first(arg)
            if not target:
                return CommandOutcome("用法：.ban add 用户ID 原因")
            group.bans[target] = reason.strip() or "未填写原因"
            return CommandOutcome(f"已加入黑名单：{target}")
        if action in {"del", "rm", "off"}:
            target = arg.strip()
            if group.bans.pop(target, None) is None:
                return CommandOutcome("没有找到黑名单记录。")
            return CommandOutcome(f"已移出黑名单：{target}")
        return CommandOutcome("用法：.ban list/add/del")

    def _cmd_team(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        action, arg = self._split_first(rest.strip())
        action = action.lower() or "list"
        if action in {"list", "ls"}:
            if not group.teams:
                return CommandOutcome("当前没有队伍。")
            lines = [f"{name}: {' '.join(members)}" for name, members in group.teams.items()]
            return CommandOutcome("队伍列表：\n" + "\n".join(lines))
        if action == "add":
            name, members_text = self._split_first(arg)
            members = [item for item in re.split(r"[\s,，]+", members_text) if item]
            if not name:
                return CommandOutcome("用法：.team add 队伍名 成员1 成员2")
            if not members:
                members = [player.nickname or user_id]
            group.teams.setdefault(name, [])
            for member in members:
                if member not in group.teams[name]:
                    group.teams[name].append(member)
            return CommandOutcome(f"队伍已更新：{name}")
        if action in {"del", "rm"}:
            name = arg.strip()
            if group.teams.pop(name, None) is None:
                return CommandOutcome("没有找到队伍。")
            return CommandOutcome(f"队伍已删除：{name}")
        if action in {"clear", "clr"}:
            group.teams.clear()
            return CommandOutcome("队伍已清空。")
        return CommandOutcome("用法：.team list/add/del/clear")

    def _cmd_compat_placeholder(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        if not self._config_bool("reply_to_unknown_compat_command", True):
            return CommandOutcome("")
        return CommandOutcome(f".{cmd} 已登记为 SeaDice 兼容项，完整行为将在后续模块补齐。")

    def _draw_from_deck(self, deck_name: str, group: GroupState) -> CommandOutcome:
        cards = self._deck_cards(deck_name, group)
        if not cards:
            return CommandOutcome(f"没有找到牌堆：{deck_name}")
        card = self.roller.rng.choice(cards)
        return CommandOutcome(f"{deck_name} 抽牌：{card}")

    def _deck_cards(self, deck_name: str, group: GroupState) -> list[str]:
        name = deck_name.strip() or "coc"
        if name in group.decks:
            return group.decks[name]
        return DEFAULT_DECKS.get(name, [])

    def _config_bool(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "开启"}
        return bool(value)

    def _group(self, group_id: str) -> GroupState:
        gid = group_id or "private"
        if gid not in self.groups:
            self.groups[gid] = GroupState()
        return self.groups[gid]

    def _player(self, group: GroupState, user_id: str, sender_name: str) -> PlayerState:
        uid = user_id or "unknown"
        if uid not in group.players:
            group.players[uid] = PlayerState(nickname=sender_name or uid)
        elif sender_name and not group.players[uid].nickname:
            group.players[uid].nickname = sender_name
        return group.players[uid]

    def _sheet(self, group: GroupState, player: PlayerState, rule: str | None = None) -> CharacterSheet:
        wanted_rule = rule or group.rule
        if player.active not in player.sheets:
            player.sheets[player.active] = self._new_sheet(player.active, wanted_rule)
        sheet = player.sheets[player.active]
        if rule and sheet.rule != rule:
            sheet = self._new_sheet(player.active, rule)
            player.sheets[player.active] = sheet
        return sheet

    def _new_sheet(self, name: str, rule: str) -> CharacterSheet:
        if rule == "dnd":
            return CharacterSheet(name=name, rule="dnd", attrs=dict(DND_DEFAULTS))
        sheet = CharacterSheet(name=name, rule="coc", attrs=dict(COC_DEFAULTS))
        self._sync_all_coc_aliases(sheet)
        return sheet

    def _attr_key(self, key: str, sheet: CharacterSheet) -> str:
        normalized = key.strip()
        alias = ATTR_ALIASES.get(normalized.lower()) or ATTR_ALIASES.get(normalized)
        if alias:
            return alias
        for existing in sheet.attrs:
            if existing.lower() == normalized.lower():
                return existing
        return normalized

    def _parse_check_target(self, rest: str, sheet: CharacterSheet) -> tuple[str, int]:
        if not rest:
            return "检定", 50
        if rest.lstrip("-").isdigit():
            return "检定", int(rest)
        parts = rest.split()
        if len(parts) >= 2 and parts[-1].lstrip("-").isdigit():
            return " ".join(parts[:-1]), int(parts[-1])
        name, explicit_value = self._split_name_value(rest)
        key = self._attr_key(name, sheet)
        value = explicit_value
        if value is None:
            value = int(sheet.attrs.get(key, 50 if sheet.rule == "coc" else 10))
        return name, value

    def _parse_attr_change(self, item: str) -> tuple[str, str, str] | None:
        with_op = re.fullmatch(r"([^=+\-:：]+)([=+\-:：])(.+)", item)
        if with_op:
            key, op, value_text = with_op.groups()
            return key, op, value_text
        compact = re.fullmatch(r"(.+?)(-?\d.*|[dD]\d.*)", item)
        if compact:
            key, value_text = compact.groups()
            return key, "=", value_text
        return None

    def _split_name_value(self, text: str) -> tuple[str, int | None]:
        stripped = text.strip()
        if re.fullmatch(r"\d*[dD]\d+.*", stripped):
            return text, None
        compact = re.fullmatch(r"(.+?)(-?\d+)", stripped)
        if not compact:
            return text, None
        name, value = compact.groups()
        if not name:
            return text, None
        return name, int(value)

    def _parse_san_args(self, text: str, sheet: CharacterSheet) -> tuple[str, str, str, int]:
        target = int(sheet.attrs.get("san", sheet.attrs.get("理智", 0)))
        parts = text.split()
        if not parts:
            return "d100", "0", "1d6", target

        first = parts[0].strip(",，")
        if "/" in first:
            success_expr, fail_expr = self._split_san_loss(first)
            if len(parts) > 1 and parts[1].lstrip("-").isdigit():
                target = int(parts[1])
            return "d100", success_expr, fail_expr, target

        if len(parts) == 1:
            return "d100", "0", first, target

        dice_expr = first
        loss_token = parts[1].strip(",，")
        if "/" in loss_token:
            success_expr, fail_expr = self._split_san_loss(loss_token)
        else:
            success_expr, fail_expr = "0", loss_token
        if len(parts) > 2 and parts[2].lstrip("-").isdigit():
            target = int(parts[2])
        return dice_expr, success_expr, fail_expr, target

    def _split_san_loss(self, text: str) -> tuple[str, str]:
        success_expr, fail_expr = text.split("/", 1)
        return success_expr.strip() or "0", fail_expr.strip() or "0"

    def _coc_level(self, roll: int, target: int) -> str:
        if roll == 1:
            return "大成功"
        if roll >= 96 and (target < 50 or roll == 100):
            return "大失败"
        if roll <= target // 5:
            return "极难成功"
        if roll <= target // 2:
            return "困难成功"
        if roll <= target:
            return "成功"
        return "失败"

    def _render_sn(self, player: PlayerState) -> str | None:
        if not player.sn_template:
            return None
        sheet = player.sheets.get(player.active)
        if not sheet:
            return None
        text = player.sn_template.replace("{$t玩家_RAW}", player.nickname or sheet.name)
        values = dict(sheet.attrs)
        values.setdefault("name", sheet.name)
        for key, value in values.items():
            text = text.replace("{" + key + "}", str(value))
        return text

    def _record(self, group: GroupState, user_id: str, sender_name: str, raw: str, response: str) -> None:
        if not group.active_log or group.active_log not in group.logs:
            return
        log = group.logs[group.active_log]
        if not log.active or log.halted:
            return
        who = sender_name or user_id
        log.lines.append(f"{who}: {raw}")
        log.lines.append(f"骰子: {response}")

    def _format_sheet(self, sheet: CharacterSheet) -> str:
        attrs = " ".join(f"{k}={v}" for k, v in sheet.attrs.items() if not self._is_duplicate_coc_key(sheet, k))
        return f"{sheet.name} [{sheet.rule}] {attrs}".strip()

    def _format_init(self, group: GroupState) -> str:
        if not group.initiative:
            return "先攻列表为空。"
        return "先攻列表：\n" + "\n".join(f"{i + 1}. {row['name']} {row['value']}" for i, row in enumerate(group.initiative))

    def _format_slots(self, sheet: CharacterSheet) -> str:
        if not sheet.spell_slots:
            return "无"
        return " ".join(f"{k}环 {sheet.spell_slots.get(k, 0)}/{sheet.spell_slots_max.get(k, sheet.spell_slots.get(k, 0))}" for k in sorted(sheet.spell_slots, key=int))

    def _sum_rolls(self, count: int, sides: int) -> int:
        return sum(self.roller.rng.randint(1, sides) for _ in range(count))

    def _ability_mod(self, score: int) -> int:
        return math.floor((score - 10) / 2)

    def _sync_coc_aliases(self, sheet: CharacterSheet, key: str, value: int) -> None:
        pairs = {
            "hp": "生命值",
            "生命值": "hp",
            "hpmax": "生命值上限",
            "生命值上限": "hpmax",
            "san": "理智",
            "理智": "san",
            "dex": "敏捷",
            "敏捷": "dex",
        }
        if sheet.rule == "coc" and key in pairs:
            sheet.attrs[pairs[key]] = value

    def _sync_all_coc_aliases(self, sheet: CharacterSheet) -> None:
        for key in list(sheet.attrs):
            self._sync_coc_aliases(sheet, key, sheet.attrs[key])

    def _is_duplicate_coc_key(self, sheet: CharacterSheet, key: str) -> bool:
        return sheet.rule == "coc" and key in {"生命值", "生命值上限", "理智", "敏捷"}

    def _split_first(self, text: str) -> tuple[str, str]:
        text = text.strip()
        if not text:
            return "", ""
        parts = text.split(maxsplit=1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

    def _load(self) -> None:
        if not self.state_path or not self.state_path.exists():
            return
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.groups = {}
        for gid, group_data in data.get("groups", {}).items():
            group = GroupState(
                active=group_data.get("active", True),
                rule=group_data.get("rule", "coc"),
                coc_rule=group_data.get("coc_rule", "0"),
                active_log=group_data.get("active_log", ""),
                initiative=group_data.get("initiative", []),
                aliases=group_data.get("aliases", {}),
                decks=group_data.get("decks", {}),
                custom_replies_enabled=group_data.get("custom_replies_enabled", True),
                helpdocs=group_data.get("helpdocs", {}),
                sealpacks=group_data.get("sealpacks", {}),
                teams=group_data.get("teams", {}),
                bans=group_data.get("bans", {}),
            )
            for uid, player_data in group_data.get("players", {}).items():
                player = PlayerState(
                    nickname=player_data.get("nickname", ""),
                    active=player_data.get("active", "default"),
                    sn_template=player_data.get("sn_template", ""),
                    aliases=player_data.get("aliases", {}),
                )
                for name, sheet_data in player_data.get("sheets", {}).items():
                    player.sheets[name] = CharacterSheet(**sheet_data)
                group.players[uid] = player
            for name, log_data in group_data.get("logs", {}).items():
                group.logs[name] = LogEntry(**log_data)
            self.groups[gid] = group

    def _save(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"groups": {}}
        for gid, group in self.groups.items():
            group_dict = asdict(group)
            payload["groups"][gid] = group_dict
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
