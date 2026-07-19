#!/usr/bin/env python3
"""Build a native Windows executable for immich-cli using Nuitka.

Nuitka compiles Python to C and then to a native binary, so the output is a
real ``.exe`` with no bundled Python interpreter (unlike PyInstaller).

IMPORTANT - WHERE THIS RUNS
---------------------------
This script must be run on **Windows** with the Microsoft C/C++ Build Tools
(MSVC) installed. Nuitka cannot cross-compile a Windows ``.exe`` from Linux.
On Windows, from the activated uv venv:

    uv sync
    python build_windows.py            # --onefile exe in ./dist
    python build_windows.py --standalone   # --standalone folder in ./dist

If Nuitka/the C compiler are missing, the script will tell you what to install.

Flags worth knowing
-------------------
--onefile        : single self-contained .exe (slower startup, one file).
--standalone     : a folder with the .exe + support files (faster startup).
--windows-console-mode=force : keep the console (this is a CLI tool).
We point Nuitka at the package directory with `--python-flag=-m` so it runs
`immich_cli.__main__` (same as `python -m immich_cli`) and names the binary
`immich-cli.exe`. HTTPX/certifi data is bundled so TLS works standalone.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Entry: the package directory, compiled with `-m` so Nuitka uses
# `immich_cli.__main__` (mirrors the `immich_cli.cli:main` console_scripts
# target and `python -m immich_cli`). The output is named `immich-cli.exe`.
ENTRY_PACKAGE = "src/immich_cli"
OUTPUT_FILENAME = "immich-cli"
OUTPUT_DIR = Path("dist")

# Packages Nuitka must follow into the binary. The entry package
# (src/immich_cli) is already given on the command line, so we don't list it
# here — re-including it triggers a benign "already included" warning. httpx
# pulls in certificates and optional trust-store machinery; click is the CLI
# framework.
INCLUDE_PACKAGES = [
    "click",
    "httpx",
    "httpcore",
    "certifi",
]


def build(standalone: bool = False) -> int:
    nuitka = shutil.which("nuitka") or shutil.which("python -m nuitka")
    if not nuitka:
        # Fall back to `python -m nuitka` which works once the dep is installed.
        nuitka = [sys.executable, "-m", "nuitka"]
    else:
        nuitka = [nuitka]

    cmd = [
        *nuitka,
        "--assume-yes-for-downloads",  # fetch the right C compiler/dep if missing
        "--output-dir=" + str(OUTPUT_DIR),
        "--output-filename=" + OUTPUT_FILENAME,
        "--python-flag=-m",
        "--windows-console-mode=force",
        "--include-package-data=certifi",
        "--include-package-data=httpx",
    ]

    for pkg in INCLUDE_PACKAGES:
        cmd.append(f"--include-package={pkg}")

    if standalone:
        cmd.append("--standalone")
    else:
        cmd.append("--onefile")

    cmd.append(ENTRY_PACKAGE)

    print("Running:", " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    standalone = "--standalone" in sys.argv[1:]
    return build(standalone=standalone)


if __name__ == "__main__":
    raise SystemExit(main())
