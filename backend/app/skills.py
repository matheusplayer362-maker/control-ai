from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Callable


class SkillRegistry:
    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, Callable[[str], str]] = {}

    def reload(self) -> list[str]:
        self._skills.clear()
        for file in self.skills_dir.glob("*.py"):
            if file.name.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(file.stem, file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            handler = getattr(module, "handle", None)
            if callable(handler):
                self._skills[file.stem] = handler
        return sorted(self._skills.keys())

    def run(self, name: str, text: str) -> str | None:
        handler = self._skills.get(name)
        if handler is None:
            return None
        return str(handler(text))

    def create_skill(self, name: str, instruction: str) -> Path:
        safe_name = "".join(ch for ch in name.lower() if ch.isalnum() or ch == "_")
        path = self.skills_dir / f"{safe_name}.py"
        template = f'''"""Auto-generated skill: {safe_name}"""


def handle(text: str) -> str:
    context = {instruction!r}
    return f"[{safe_name}] {{context}}\\nEntrada: {{text}}"
'''
        path.write_text(template, encoding="utf-8")
        self.reload()
        return path
