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
  python build_dist.py                      # 打包（自动检测当前系统）
  python build_dist.py --platform windows   # 明确指定平台（必须与当前系统一致）
  python build_dist.py --platform macos
  python build_dist.py --platform linux
  python build_dist.py --clean              # 清理后打包
  python build_dist.py --platform linux --clean

注意：PyInstaller 不支持交叉编译，--platform 必须与当前运行系统匹配。
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT      = Path(__file__).resolve().parent
DIST_DIR  = ROOT / "dist"
BUILD_DIR = ROOT / "build"

sys.path.insert(0, str(ROOT / "src"))
try:
    from mira import __version__
except ImportError:
    __version__ = "0.0.0"

# 平台别名映射 → platform.system() 的值
_PLATFORM_MAP = {
    "windows": "Windows",
    "win":     "Windows",
    "macos":   "Darwin",
    "mac":     "Darwin",
    "darwin":  "Darwin",
    "linux":   "Linux",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Mira 打包脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--platform", "-p",
        metavar="PLATFORM",
        help="目标平台：windows / macos / linux（必须与当前运行系统一致）",
    )
    parser.add_argument(
        "--clean", "-c",
        action="store_true",
        help="打包前清理旧产物（dist/ build/ *.spec）",
    )
    return parser.parse_args()


def resolve_platform(arg: str | None) -> str:
    """返回规范化的 platform.system() 值，并校验与当前系统是否匹配。"""
    current = platform.system()   # Windows / Darwin / Linux

    if arg is None:
        return current

    normalized = _PLATFORM_MAP.get(arg.lower())
    if normalized is None:
        valid = "windows / macos / linux"
        print(f"错误：未知平台 '{arg}'，可选值：{valid}", file=sys.stderr)
        sys.exit(1)

    if normalized != current:
        friendly = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}
        print(
            f"错误：指定了 --platform {arg}（{friendly[normalized]}），"
            f"但当前运行系统是 {friendly.get(current, current)}。\n"
            f"PyInstaller 不支持交叉编译，请在目标系统上执行打包。",
            file=sys.stderr,
        )
        sys.exit(1)

    return normalized


def clean():
    for d in (DIST_DIR, BUILD_DIR):
        if d.exists():
            shutil.rmtree(d)
            print(f"  删除: {d}")
    for spec in ROOT.glob("*.spec"):
        spec.unlink()
        print(f"  删除: {spec}")


def build(system: str):
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
    if system == "Windows":
        icon = ROOT / "assets" / "icon.ico"
    elif system == "Darwin":
        icon = ROOT / "assets" / "icon.icns"
    else:
        icon = ROOT / "assets" / "icon-256.png"
    if icon.exists():
        cmd += ["--icon", str(icon)]

    cmd.append(str(entry))

    friendly = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}
    print(f"▶  PyInstaller — {friendly.get(system, system)} v{__version__}")
    subprocess.run(cmd, check=True)

    # 删除 PyInstaller 自动生成的 .spec 文件
    for spec in ROOT.glob("*.spec"):
        spec.unlink()

    mira_dir = DIST_DIR / "mira"
    _write_web_launcher(mira_dir, system)
    _write_uninstall(mira_dir, system)

    exe = mira_dir / ("mira.exe" if system == "Windows" else "mira")
    print(f"\n✅  {exe}")
    print(f"    Web UI 启动脚本: {mira_dir}")
    print(f"    卸载脚本:        {mira_dir}")


# ── Web UI 无控制台启动脚本 ────────────────────────────────────────────────────

def _write_web_launcher(dest: Path, system: str):
    if system == "Windows":
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

def _write_uninstall(dest: Path, system: str):
    if system == "Windows":
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
    args = parse_args()
    system = resolve_platform(args.platform)
    if args.clean:
        clean()
    build(system)
