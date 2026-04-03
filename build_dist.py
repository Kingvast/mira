#!/usr/bin/env python3
"""
Mira 打包脚本
=============
用 PyInstaller 将 Mira 打包为当前平台的可执行文件，并在输出目录写入
启动 Web UI 的脚本和卸载脚本：

  Windows  →  dist/mira/mira.exe
               dist/mira/启动 Web UI.vbs   （无控制台窗口启动 Web UI）
               dist/mira/uninstall.bat

  macOS    →  dist/mira/mira
               dist/mira/mira-web.sh
               dist/mira/uninstall.sh

  Linux    →  dist/mira/mira
               dist/mira/mira-web.sh
               dist/mira/uninstall.sh

用法
----
  python build_dist.py           # 打包
  python build_dist.py --clean   # 清理后打包
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT      = Path(__file__).resolve().parent
DIST_DIR  = ROOT / "dist"
BUILD_DIR = ROOT / "build"
SYSTEM    = platform.system()   # Windows / Darwin / Linux

sys.path.insert(0, str(ROOT / "src"))
try:
    from mira import __version__
except ImportError:
    __version__ = "0.0.0"


def clean():
    for d in (DIST_DIR, BUILD_DIR):
        if d.exists():
            shutil.rmtree(d)
            print(f"  删除: {d}")
    for spec in ROOT.glob("*.spec"):
        spec.unlink()
        print(f"  删除: {spec}")


def build():
    entry  = ROOT / "src" / "mira" / "main.py"
    static = ROOT / "src" / "mira" / "web" / "static"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "mira",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--add-data", f"{static}{os.pathsep}mira/web/static",
        "--hidden-import", "mira.commands",
        "--hidden-import", "mira.tools",
        "--hidden-import", "mira.services",
        "--hidden-import", "mira.web",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "anthropic",
        "--hidden-import", "openai",
        "--hidden-import", "google.generativeai",
        "--hidden-import", "ddgs",
        "--hidden-import", "PyPDF2",
        "--hidden-import", "fastapi",
        "--hidden-import", "websockets",
        "--hidden-import", "aiofiles",
        "--hidden-import", "pydantic",
    ]

    # 图标
    if SYSTEM == "Windows":
        icon = ROOT / "assets" / "icon.ico"
    elif SYSTEM == "Darwin":
        icon = ROOT / "assets" / "icon.icns"
    else:
        icon = ROOT / "assets" / "icon-256.png"
    if icon.exists():
        cmd += ["--icon", str(icon)]

    cmd.append(str(entry))

    print(f"▶  PyInstaller — {SYSTEM} v{__version__}")
    subprocess.run(cmd, check=True)

    # 删除 PyInstaller 自动生成的 .spec 文件（由 build_dist.py 管理，无需保留）
    for spec in ROOT.glob("*.spec"):
        spec.unlink()

    mira_dir = DIST_DIR / "mira"
    _write_web_launcher(mira_dir)
    _write_uninstall(mira_dir)

    exe = mira_dir / ("mira.exe" if SYSTEM == "Windows" else "mira")
    print(f"\n✅  {exe}")
    print(f"    Web UI 启动脚本: {mira_dir}")
    print(f"    卸载脚本:        {mira_dir}")


# ── Web UI 无控制台启动脚本 ────────────────────────────────────────────────────

def _write_web_launcher(dest: Path):
    if SYSTEM == "Windows":
        # VBScript：用 wscript.exe 以隐藏窗口方式启动 mira.exe --web
        vbs = "\r\n".join([
            'Dim fso, wsh, dir, exe',
            'Set fso = CreateObject("Scripting.FileSystemObject")',
            'Set wsh = CreateObject("WScript.Shell")',
            'dir = fso.GetParentFolderName(WScript.ScriptFullName)',
            'exe = dir & "\\mira.exe"',
            'wsh.Run Chr(34) & exe & Chr(34) & " --web", 0, False',
        ]) + "\r\n"
        path = dest / "启动 Web UI.vbs"
        path.write_text(vbs, encoding="utf-8")
        print(f"  ✓ {path.name}")
    else:
        sh = "#!/bin/sh\nDIR=\"$(cd \"$(dirname \"$0\")\" && pwd)\"\n\"$DIR/mira\" --web\n"
        path = dest / "mira-web.sh"
        path.write_text(sh, encoding="utf-8")
        path.chmod(0o755)
        print(f"  ✓ {path.name}")


# ── 卸载脚本 ──────────────────────────────────────────────────────────────────

def _write_uninstall(dest: Path):
    if SYSTEM == "Windows":
        # 通过 PowerShell 延迟删除自身目录（batch 无法删除正在运行的目录）
        bat = "\r\n".join([
            "@echo off",
            "echo 正在卸载 Mira...",
            'set "DIR=%~dp0"',
            "cd /d %TEMP%",
            'powershell -NoProfile -Command "Start-Sleep 1; Remove-Item -Recurse -Force \'%DIR%\'"',
            "echo Mira 已卸载。",
        ]) + "\r\n"
        path = dest / "uninstall.bat"
        path.write_text(bat, encoding="utf-8")
        print(f"  ✓ {path.name}")
    else:
        sh = "\n".join([
            "#!/bin/sh",
            'DIR="$(cd "$(dirname "$0")" && pwd)"',
            'echo "正在卸载 Mira..."',
            'rm -rf "$DIR"',
            'echo "Mira 已卸载。"',
        ]) + "\n"
        path = dest / "uninstall.sh"
        path.write_text(sh, encoding="utf-8")
        path.chmod(0o755)
        print(f"  ✓ {path.name}")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
    build()
