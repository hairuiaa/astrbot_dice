from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import CommandOutcome, GroupState, PlayerState


CommandHandler = Callable[
    [str, str, "GroupState", "PlayerState", str],
    "CommandOutcome",
]


class CommandRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(
        self,
        aliases: Iterable[str],
        handler: CommandHandler,
    ) -> None:
        for alias in aliases:
            key = alias.strip().lower()
            if key:
                self._handlers[key] = handler

    def get(self, command: str) -> CommandHandler | None:
        return self._handlers.get(command.strip().lower())

    def match_prefix(self, text: str) -> tuple[str, str, bool] | None:
        lowered = text.strip().lower()
        for alias in sorted(self._handlers, key=len, reverse=True):
            if not lowered.startswith(alias):
                continue
            rest = text.strip()[len(alias) :]
            has_space = bool(rest[:1] and rest[0].isspace())
            return alias, rest.strip(), has_space
        return None

    def aliases(self) -> list[str]:
        return sorted(self._handlers)
