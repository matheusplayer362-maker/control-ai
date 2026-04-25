from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_root() -> Path:
    return Path(__file__).resolve().parents[1]


def get_runtime_root() -> Path:
    configured = os.getenv("CONTROL_AI_RUNTIME_DIR")
    if configured:
        return Path(configured)
    return get_root() / "runtime"


def get_venv_python(runtime_root: Path) -> Path:
    return runtime_root / "venv" / "Scripts" / "python.exe"


def can_import_backend(python_executable: Path) -> bool:
    probe = subprocess.run(
        [
            str(python_executable),
            "-c",
            "import fastapi, uvicorn, pydantic, requests, bs4, lxml, httpx, dateutil",
        ],
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


def ensure_runtime_venv(runtime_root: Path) -> Path:
    runtime_root.mkdir(parents=True, exist_ok=True)
    venv_python = get_venv_python(runtime_root)

    if venv_python.exists() and can_import_backend(venv_python):
        return venv_python

    venv_dir = venv_python.parent.parent
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)

    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)

    requirements = get_root() / "backend" / "requirements.txt"
    subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(requirements)], check=True)

    return venv_python


def main() -> int:
    runtime_root = get_runtime_root()
    python_executable = ensure_runtime_venv(runtime_root)
    print(python_executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
