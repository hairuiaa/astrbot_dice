from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureItem:
    category: str
    commands: tuple[str, ...]
    status: str
    route: str
    notes: str


FEATURE_MATRIX: tuple[FeatureItem, ...] = (
    FeatureItem(
        "内置指令",
        ("bot", "set", "nn", "pc", "st", "r", "ra", "userid", "botlist"),
        "python-ready",
        "Python",
        "第一阶段已覆盖核心骰点、开关、人物卡和规则切换，本阶段补齐身份查询。",
    ),
    FeatureItem(
        "COC7",
        ("coc", "setcoc", "ra", "rc", "sc", "en", "ti", "li", "cst"),
        "python-ready",
        "Python",
        "覆盖人物生成、检定、SAN、成长、疯狂表和规则参数记录。",
    ),
    FeatureItem(
        "DND5E",
        ("dnd", "dndx", "ri", "init", "dst", "ss", "cast", "longrest", "ds"),
        "python-ready",
        "Python",
        "覆盖人物生成、先攻、属性、法术位、施法、长休和死亡豁免。",
    ),
    FeatureItem(
        "日志",
        ("log", "stat", "ob", "sn"),
        "python-ready",
        "Python",
        "保留群内文本和骰点回复，支持导出最近记录和群名片预览。",
    ),
    FeatureItem(
        "牌堆",
        ("draw", "deck"),
        "compat-ready",
        "Python",
        "内置轻量牌堆和群内自定义牌堆，后续可导入 SeaDice 牌堆资源。",
    ),
    FeatureItem(
        "自定义回复",
        ("reply", "alias", "&", "a"),
        "compat-ready",
        "Python",
        "支持别名快捷指令和开关状态，复杂回复规则进入兼容层。",
    ),
    FeatureItem(
        "故事工具",
        ("name", "namednd", "who", "cnmods", "modu", "魔都"),
        "compat-ready",
        "Python",
        "提供随机姓名、排序和模组检索占位，资源可由兼容层扩展。",
    ),
    FeatureItem(
        "娱乐工具",
        ("jrrp", "gugu", "ping", "text", "rsr", "ek", "dx", "w", "jsr"),
        "partial",
        "Python",
        "先提供 jrrp、gugu、ping 和入口提示，复杂生成器保留验收点。",
    ),
    FeatureItem(
        "骰主和黑名单",
        ("master", "black", "ban", "dismiss"),
        "compat-ready",
        "AstrBot",
        "骰主权限交给 AstrBot 管理，群内黑名单落本插件状态。",
    ),
    FeatureItem(
        "helpdoc",
        ("help", "find", "helpdoc"),
        "compat-ready",
        "Python",
        "内置功能矩阵查询和群内帮助文档存储。",
    ),
    FeatureItem(
        "JS 扩展",
        ("ext", "js"),
        "spike",
        "Compat",
        "当前记录启停和资源状态，不执行任意 JS。新扩展推荐 AstrBot 插件。",
    ),
    FeatureItem(
        ".sealpack",
        ("sealpack",),
        "spike",
        "Compat",
        "记录导入包路径和状态，为后续解析 SeaDice 扩展包留接口。",
    ),
    FeatureItem(
        "Go 核心桥接",
        ("sd-api/dice/exec", "sd-api/dice/recentMessage"),
        "spike",
        "Go Bridge",
        "已封装 HTTP 客户端，需独立进程提供 SeaDice UI endpoint。",
    ),
)


def format_feature_matrix(filter_text: str = "") -> str:
    items = _filter_items(filter_text)
    if not items:
        return "没有匹配的 SeaDice 功能项。"
    lines = ["SeaDice 第二阶段验收矩阵："]
    for item in items:
        commands = " ".join(f".{command}" for command in item.commands[:10])
        lines.append(f"{item.category}: {item.status} [{item.route}]")
        lines.append(f"指令: {commands}")
        lines.append(f"说明: {item.notes}")
    return "\n".join(lines)


def find_feature_docs(query: str) -> str:
    text = query.strip().lower()
    if not text:
        return format_feature_matrix()
    items = _filter_items(text)
    if not items:
        return f"没有找到与 {query} 相关的 SeaDice 功能项。"
    lines = [f"与 {query} 相关的功能项："]
    for item in items:
        lines.append(f"{item.category}: {item.status} [{item.route}]")
        lines.append(item.notes)
    return "\n".join(lines)


def _filter_items(filter_text: str) -> list[FeatureItem]:
    text = filter_text.strip().lower()
    if not text:
        return list(FEATURE_MATRIX)
    result = []
    for item in FEATURE_MATRIX:
        haystack = " ".join(
            (
                item.category,
                " ".join(item.commands),
                item.status,
                item.route,
                item.notes,
            ),
        ).lower()
        if text in haystack:
            result.append(item)
    return result
