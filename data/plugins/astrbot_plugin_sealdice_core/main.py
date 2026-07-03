from __future__ import annotations

from pathlib import Path

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .core import CommandOutcome, SeaDiceService
from .go_bridge import BridgeMessage, SeaDiceHTTPBridge
from .platform_actions import AstrBotPlatformActions


class Main(star.Star):
    def __init__(self, context: star.Context, config: dict | None = None) -> None:
        super().__init__(context, config=config)
        self.config = config or {}
        state_path = Path(get_astrbot_plugin_data_path()) / "sealdice_core" / "state.json"
        self.service = SeaDiceService(state_path, config=dict(self.config))
        self.platform_actions = AstrBotPlatformActions()
        self.bridge = self._build_bridge()

    @filter.command("sealhelp")
    async def sealhelp(self, event: AstrMessageEvent):
        """Show SeaDice-style dice command help."""
        yield event.plain_result(self.service.help_text())

    @filter.command("sealdice")
    async def sealdice(self, event: AstrMessageEvent):
        """Show SeaDice plugin status."""
        route = self.config.get("route", "python")
        yield event.plain_result(f"海豹骰核心复刻已加载。当前路线：{route}。骰子指令使用 . 或 。 前缀。")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        """Handle SeaDice-compatible dot commands without touching slash commands."""
        text = event.get_message_str() or ""
        if self.bridge and text.strip().startswith((".", "。")):
            reply = await self._handle_by_bridge(event, text)
            event.stop_event()
            call_llm = getattr(event, "should_call_llm", None)
            if callable(call_llm):
                call_llm(False)
            if reply:
                yield event.plain_result(reply)
            return

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
        call_llm = getattr(event, "should_call_llm", None)
        if callable(call_llm):
            call_llm(False)
        if reply:
            yield event.plain_result(reply)

    def _build_bridge(self) -> SeaDiceHTTPBridge | None:
        route = str(self.config.get("route", "python")).lower()
        if route != "go_bridge":
            return None
        return SeaDiceHTTPBridge(
            str(self.config.get("go_bridge_url", "http://127.0.0.1:3211")),
            password=str(self.config.get("go_bridge_password", "")),
        )

    async def _handle_by_bridge(self, event: AstrMessageEvent, text: str) -> str:
        if self.bridge is None:
            return ""
        messages = await self.bridge.execute(
            BridgeMessage(
                content=text,
                message_type="group" if event.get_group_id() else "private",
                group_id=event.get_group_id() or event.get_session_id() or "private",
                user_id=event.get_sender_id() or "unknown",
                sender_name=event.get_sender_name() or "",
            ),
        )
        return "\n".join(message for message in messages if message)

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
        ok, reason = await self.platform_actions.try_set_group_card(
            event,
            outcome.group_card,
        )
        if outcome.report_card_status:
            status = "已尝试更新群名片。" if ok else f"未能自动改群名片：{reason}"
            reply = f"{reply}\n{status}"
        return reply
