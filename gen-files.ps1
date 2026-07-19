# gen-files.ps1 — generate files-to-copy.txt for sync to Windows.
#
# Collects every Python source file in the project and writes their RELATIVE
# paths (one per line) to files-to-copy.txt, which winclirun.ps1 / the copy
# script consumes. Run this (or have the copy script call it) BEFORE syncing,
# so newly added modules (e.g. src/immich_cli/meta_export.py) are never missed.
#
# Usage:
#   .\gen-files.ps1              # writes ./files-to-copy.txt
#   .\gen-files.ps1 out.txt      # write to a different file
#
# Mirrors the Linux generator's exclusions: skip __pycache__; skip a stray
# root-level __init__.py.

param(
    [string]$OutFile = "files-to-copy.txt"
)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
if (-not $root) { $root = Get-Location }

$files = @()

# Package sources under src/immich_cli (exclude __pycache__).
Get-ChildItem -Path $root -Recurse -Filter *.py |
    Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]?' } |
    ForEach-Object { $files += $_.FullName }

# Root-level .py (e.g. build_windows.py); skip a stray root __init__.py.
Get-ChildItem -Path $root -File -Filter *.py |
    Where-Object { $_.Name -ne "__init__.py" } |
    ForEach-Object { $files += $_.FullName }

# Emit relative paths, sorted, one per line, no ./ prefix.
$sorted = $files |
    ForEach-Object { [System.IO.Path]::GetRelativePath($root, $_).Replace('\', '/') } |
    Sort-Object -Unique

$sorted | Set-Content -Path (Join-Path $root $OutFile) -Encoding utf8

Write-Host "Wrote $($sorted.Count) file(s) to $OutFile"
