from __future__ import annotations

import json
import math
import random
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


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
    players: dict[str, PlayerState] = field(default_factory=dict)
    logs: dict[str, LogEntry] = field(default_factory=dict)
    active_log: str = ""
    initiative: list[dict[str, Any]] = field(default_factory=list)


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
    ) -> None:
        self.state_path = Path(state_path) if state_path else None
        self.roller = DiceRoller(rng)
        self.groups: dict[str, GroupState] = {}
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
        first, rest = self._split_first(body)
        cmd = first.lower()
        if cmd not in {"bot", "sealhelp", "help"} and not group.active:
            return CommandOutcome("骰子当前关闭。使用 .bot on 开启。")

        handlers = {
            "bot": self._cmd_bot,
            "set": self._cmd_set,
            "nn": self._cmd_nn,
            "pc": self._cmd_pc,
            "ch": self._cmd_pc,
            "char": self._cmd_pc,
            "character": self._cmd_pc,
            "角色": self._cmd_pc,
            "st": self._cmd_st,
            "cst": self._cmd_st,
            "dst": self._cmd_st,
            "coc": self._cmd_coc,
            "dnd": self._cmd_dnd,
            "dndx": self._cmd_dnd,
            "r": self._cmd_roll,
            "rd": self._cmd_roll,
            "roll": self._cmd_roll,
            "rh": self._cmd_roll,
            "rhd": self._cmd_roll,
            "rdh": self._cmd_roll,
            "rx": self._cmd_roll,
            "rxh": self._cmd_roll,
            "rhx": self._cmd_roll,
            "ra": self._cmd_check,
            "rc": self._cmd_check,
            "rah": self._cmd_check,
            "rch": self._cmd_check,
            "cra": self._cmd_check,
            "crc": self._cmd_check,
            "crah": self._cmd_check,
            "crch": self._cmd_check,
            "rav": self._cmd_check,
            "rcv": self._cmd_check,
            "sc": self._cmd_san,
            "en": self._cmd_en,
            "ti": self._cmd_ti,
            "li": self._cmd_li,
            "ri": self._cmd_ri,
            "init": self._cmd_init,
            "buff": self._cmd_buff,
            "dbuff": self._cmd_dbuff,
            "spellslots": self._cmd_spellslots,
            "ss": self._cmd_spellslots,
            "dss": self._cmd_spellslots,
            "法术位": self._cmd_spellslots,
            "cast": self._cmd_cast,
            "dcast": self._cmd_cast,
            "长休": self._cmd_longrest,
            "longrest": self._cmd_longrest,
            "dlongrest": self._cmd_longrest,
            "ds": self._cmd_death_save,
            "死亡豁免": self._cmd_death_save,
            "log": self._cmd_log,
            "stat": self._cmd_stat,
            "sn": self._cmd_sn,
            "ob": self._cmd_ob,
            "sealhelp": self._cmd_help,
            "help": self._cmd_help,
            "ext": self._cmd_ext,
        }
        handler = handlers.get(cmd)
        if not handler:
            return None
        outcome = handler(cmd, rest, group, player, user_id)
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

    def help_text(self) -> str:
        return (
            "海豹骰核心指令：\n"
            ".bot on/off/about\n"
            ".set coc/dnd/info/clr\n"
            ".nn 昵称；.pc new/load/save/list/del/tag\n"
            ".st hp=10 hp-1；.cst；.dst\n"
            ".r 1d100；.ra 侦查；.rc 侦查；.sc 1/1d6\n"
            ".coc；.en 侦查；.ti；.li\n"
            ".dnd；.dndx；.ri；.init；.ss；.cast；.longrest；.ds\n"
            ".log new/on/off/end/list/get/del/stat/export\n"
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
            return CommandOutcome(f"当前规则：{group.rule}")
        if arg in {"clr", "clear"}:
            group.rule = "coc"
            return CommandOutcome("群规则已重置为 COC7。")
        return CommandOutcome("用法：.set coc/dnd/info/clr")

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
            m = re.fullmatch(r"([^=+\-:：]+)([=+\-:：])(-?\d+)", item)
            if not m:
                return CommandOutcome(f"无法识别属性改动：{item}")
            key, op, value_text = m.groups()
            key = self._attr_key(key.strip(), sheet)
            value = int(value_text)
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
        expr = rest.strip() or "0/1d6"
        parts = expr.split()
        loss_expr = parts[0]
        target = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else int(sheet.attrs.get("san", sheet.attrs.get("理智", 0)))
        if "/" not in loss_expr:
            return CommandOutcome("用法：.sc 成功损失/失败损失，例如 .sc 0/1d6")
        success_expr, fail_expr = loss_expr.split("/", 1)
        roll = self.roller.d100()
        ok = roll <= target
        loss_total, loss_detail = self.roller.roll_expr(success_expr if ok else fail_expr)
        old = int(sheet.attrs.get("san", sheet.attrs.get("理智", 0)))
        new = max(0, old - loss_total)
        sheet.attrs["san"] = new
        sheet.attrs["理智"] = new
        result = "成功" if ok else "失败"
        return CommandOutcome(
            f"SAN Check：D100={roll}/{target}，{result}，损失 {loss_total} ({loss_detail})，SAN {old}->{new}",
            group_card=self._render_sn(player),
        )

    def _cmd_en(self, cmd: str, rest: str, group: GroupState, player: PlayerState, user_id: str) -> CommandOutcome:
        sheet = self._sheet(group, player, "coc")
        key = rest.strip()
        if not key:
            return CommandOutcome("用法：.en 技能名")
        key = self._attr_key(key, sheet)
        old = int(sheet.attrs.get(key, 0))
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
        return CommandOutcome("COC7 和 DND5e 已内置启用。")

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
        parts = rest.split()
        if len(parts) >= 2 and parts[-1].lstrip("-").isdigit():
            return " ".join(parts[:-1]), int(parts[-1])
        key = self._attr_key(rest, sheet)
        return rest, int(sheet.attrs.get(key, 50 if sheet.rule == "coc" else 10))

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
                active_log=group_data.get("active_log", ""),
                initiative=group_data.get("initiative", []),
            )
            for uid, player_data in group_data.get("players", {}).items():
                player = PlayerState(
                    nickname=player_data.get("nickname", ""),
                    active=player_data.get("active", "default"),
                    sn_template=player_data.get("sn_template", ""),
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
