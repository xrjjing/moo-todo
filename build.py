#!/usr/bin/env python3
"""
牛牛待办 - PyInstaller 打包脚本
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

# 项目配置
APP_NAME = "牛牛待办"
APP_VERSION = "1.0.0"
MAIN_SCRIPT = "main.py"
ICON_DIR = Path(__file__).parent / "icons"


def get_platform():
    """获取当前平台"""
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform == "win32":
        return "windows"
    else:
        return "linux"


def clean_build():
    """清理构建目录"""
    dirs_to_clean = ["build", "dist", f"{APP_NAME}.spec"]
    for d in dirs_to_clean:
        path = Path(d)
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"已清理: {d}")


def cleanup_temp():
    """清理打包临时文件（保留 dist）"""
    root = Path(__file__).parent
    build_dir = root / "build"
    spec_file = root / f"{APP_NAME}.spec"

    if build_dir.exists():
        shutil.rmtree(build_dir)
        print(f"已删除: {build_dir}")
    if spec_file.exists():
        spec_file.unlink()
        print(f"已删除: {spec_file}")


def build_app():
    """构建应用"""
    platform = get_platform()
    print(f"开始构建 {APP_NAME} ({platform})...")

    # 基础 PyInstaller 参数
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",  # GUI 应用，无控制台
        "--onedir",    # 打包为目录
        "--noconfirm", # 覆盖已有构建
    ]

    # 添加数据文件
    web_dir = Path(__file__).parent / "web"
    if web_dir.exists():
        if platform == "windows":
            cmd.extend(["--add-data", f"{web_dir};web"])
        else:
            cmd.extend(["--add-data", f"{web_dir}:web"])

    # 添加图标
    if platform == "macos":
        icon_path = ICON_DIR / "icon.icns"
        if icon_path.exists():
            cmd.extend(["--icon", str(icon_path)])
    elif platform == "windows":
        icon_path = ICON_DIR / "icon.ico"
        if icon_path.exists():
            cmd.extend(["--icon", str(icon_path)])

    # 隐藏导入
    cmd.extend([
        "--hidden-import", "webview",
        "--hidden-import", "webview.platforms.cocoa",
        "--hidden-import", "webview.platforms.winforms",
        "--hidden-import", "webview.platforms.gtk",
    ])

    # 主脚本
    cmd.append(MAIN_SCRIPT)

    print("执行命令:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=Path(__file__).parent)

    if result.returncode == 0:
        print(f"\n✅ 构建成功！")
        dist_path = Path(__file__).parent / "dist" / APP_NAME
        if platform == "macos":
            dist_path = dist_path.with_suffix(".app")
        print(f"输出路径: {dist_path}")

        # 清理临时文件
        cleanup_temp()
    else:
        print(f"\n❌ 构建失败，退出码: {result.returncode}")
        sys.exit(1)


def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description=f"{APP_NAME} 打包工具")
    parser.add_argument("--clean", action="store_true", help="仅清理构建目录")
    parser.add_argument("--rebuild", action="store_true", help="清理后重新构建")
    args = parser.parse_args()

    os.chdir(Path(__file__).parent)

    if args.clean:
        clean_build()
    elif args.rebuild:
        clean_build()
        build_app()
    else:
        build_app()


if __name__ == "__main__":
    main()
