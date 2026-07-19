# Windows native build (Nuitka)

`immich-cli` is a command-line tool, so we ship it as a **native Windows
`.exe`** compiled with [Nuitka](https://nuitka.net). Nuitka translates Python
to C and compiles to machine code — the result is a real executable, not a
zipped Python interpreter (that would be PyInstaller, which we dropped).

## Prerequisites (on the Windows build machine)

1. **Python 3.12** (matches `requires-python = ">=3.12,<3.13"`).
2. **Microsoft C/C++ Build Tools (MSVC)** — install via the
   [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
   with the "Desktop development with C++" workload. Nuitka needs a C compiler;
   on Windows that is MSVC (it can also use MinGW-w64, but MSVC is simplest).
3. This project's dependencies: `uv sync` (pulls `nuitka` from the dev group).

> Nuitka **cannot cross-compile a Windows `.exe` from Linux**. The build must
> run on Windows. This repo's Linux/WSL environment has no C compiler and is
> not used to produce the final binary.

## Build

From the repo root, in the activated environment:

```powershell
uv sync
python build_windows.py                 # -> dist/immich-cli.exe  (--onefile)
python build_windows.py --standalone    # -> dist/immich-cli.dist/  (folder)
```

`build_windows.py` compiles the **package directory** (`src/immich_cli`) with
`--python-flag=-m`, so Nuitka runs `immich_cli.__main__` (same as
`python -m immich_cli`) and names the output `immich-cli.exe` natively. There
is no separate rename step.

- `--onefile` produces a single self-contained `immich-cli.exe`. Slower cold
  start (it unpacks to a temp dir) but one file to ship.
- `--standalone` produces a folder with the `.exe` plus support files. Faster
  startup; ship the whole folder.

The build is configured via `build_windows.py` (and mirrored in the
`[tool.nuitka]` section of `pyproject.toml`). Key choices:

- `--python-flag=-m` + package dir — correct `python -m immich_cli` semantics
  and a correctly named `immich-cli.exe`.
- `--include-package=immich_cli,click,httpx,httpcore,certifi` — follow these
  into the binary.
- `--include-package-data=certifi,httpx` — bundle TLS root certificates so
  HTTPS to the Immich server works without a system cert store.
- `--windows-console-mode=force` — keep the console (this is a CLI).

The dev dependency is `nuitka[onefile]`, which pulls in `zstandard` so the
onefile binary is compressed (avoids the "cannot compress" warning).

## Verify the artifact

```powershell
.\dist\immich-cli.exe --help
.\dist\immich-cli.exe --version
```

Both should run with no Python install present on the target machine (only the
MSVC C runtime, normally already on Windows 10/11).

## Notes / gotchas

- First build downloads/compiles a lot — slow. Subsequent builds are faster.
- If Nuitka reports a missing compiler, run the Visual Studio Build Tools
  installer and add the C++ workload, then retry.
- The `[tool.nuitka]` keys are read by `python -m nuitka`; `build_windows.py`
  passes equivalent CLI flags so the two stay in sync.
