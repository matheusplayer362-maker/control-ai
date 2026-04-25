from __future__ import annotations

import logging
import re
from typing import Any

LOGGER = logging.getLogger(__name__)


class ActionRunner:
    """Executes bounded local actions derived from user intent."""

    def __init__(self) -> None:
        self.pattern_script = re.compile(r"^/run\s+(.+)$", re.IGNORECASE)

    def maybe_execute(self, text: str) -> dict[str, Any] | None:
        match = self.pattern_script.match(text.strip())
        if not match:
            return None

        command = match.group(1)
        if any(token in command for token in ["rm ", "del ", "format", "shutdown", "reboot"]):
            return {
                "ok": False,
                "message": "Comando bloqueado por seguranca.",
            }

        LOGGER.info("Script request captured: %s", command)
        return {
            "ok": True,
            "message": (
                "Solicitacao de execucao recebida. Por seguranca, confirme no terminal do backend "
                "antes de executar comandos reais."
            ),
            "command": command,
        }
