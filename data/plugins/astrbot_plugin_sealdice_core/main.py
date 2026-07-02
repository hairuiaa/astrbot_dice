from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .core import CommandOutcome, SeaDiceService


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        state_path = Path(get_astrbot_plugin_data_path()) / "sealdice_core" / "state.json"
        self.service = SeaDiceService(state_path)

    @filter.command("sealhelp")
    async def sealhelp(self, event: AstrMessageEvent):
        """Show SeaDice-style dice command help."""
        yield event.plain_result(self.service.help_text())

    @filter.command("sealdice")
    async def sealdice(self, event: AstrMessageEvent):
        """Show SeaDice plugin status."""
        yield event.plain_result("海豹骰核心复刻已加载。骰子指令使用 . 或 。 前缀。")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        """Handle SeaDice-compatible dot commands without touching slash commands."""
        text = event.get_message_str() or ""
        outcome = self.service.handle(
            text,
            group_id=event.get_group_id() or event.get_session_id() or "private",
            user_id=event.get_sender_id() or "unknown",
            sender_name=event.get_sender_name() or "",
        )
        if outcome is None:
            return
        reply = await self._decorate_group_card_status(event, outcome)
        event.stop_event()
        if reply:
            yield event.plain_result(reply)

    async def _decorate_group_card_status(
        self,
        event: AstrMessageEvent,
        outcome: CommandOutcome,
    ) -> str:
        reply = outcome.text
        if outcome.group_card is None:
            return reply
        if not outcome.group_card:
            return reply
        ok, reason = await self._try_set_group_card(event, outcome.group_card)
        if outcome.report_card_status:
            status = "已尝试更新群名片。" if ok else f"未能自动改群名片：{reason}"
            reply = f"{reply}\n{status}"
        return reply

    async def _try_set_group_card(
        self,
        event: AstrMessageEvent,
        card: str,
    ) -> tuple[bool, str]:
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        if not group_id:
            return False, "当前消息不是群聊"
        if not user_id:
            return False, "没有拿到发送者 ID"

        bot = getattr(event, "bot", None)
        if bot is None:
            return False, "当前适配器没有暴露 OneBot 客户端"

        try:
            group_value: int | str = int(group_id) if str(group_id).isdigit() else group_id
            user_value: int | str = int(user_id) if str(user_id).isdigit() else user_id
            if hasattr(bot, "set_group_card"):
                await bot.set_group_card(group_id=group_value, user_id=user_value, card=card)
                return True, ""
            call_action: Any = getattr(bot, "call_action", None)
            if callable(call_action):
                await call_action(
                    "set_group_card",
                    group_id=group_value,
                    user_id=user_value,
                    card=card,
                )
                return True, ""
        except Exception as exc:
            logger.warning("SeaDice group card update failed: %s", exc)
            return False, str(exc)
        return False, "当前 OneBot 客户端不支持 set_group_card"
