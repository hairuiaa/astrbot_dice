from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class AstrBotPlatformActions:
    async def try_set_group_card(
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
                await bot.set_group_card(
                    group_id=group_value,
                    user_id=user_value,
                    card=card,
                )
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
