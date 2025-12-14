#!/usr/bin/env python3
"""将 SVG 图标转换为 PNG、ICO、ICNS 格式 - 使用 Wand (ImageMagick)"""
import subprocess
import sys
from pathlib import Path


def check_dependencies():
    """检查并安装依赖"""
    try:
        from wand.image import Image
        from PIL import Image as PILImage
        return True
    except ImportError:
        print("正在安装依赖...")
        subprocess.run([sys.executable, "-m", "pip", "install", "wand", "pillow"], check=True)
        return True


def svg_to_png(svg_path: Path, png_path: Path, size: int = 512):
    """SVG 转 PNG"""
    from wand.image import Image

    with Image(filename=str(svg_path)) as img:
        img.resize(size, size)
        img.format = 'png'
        img.save(filename=str(png_path))
    print(f"  PNG: {png_path}")
    return True


def png_to_ico(png_path: Path, ico_path: Path):
    """PNG 转 ICO (Windows)"""
    from PIL import Image
    img = Image.open(png_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format='ICO', sizes=sizes)
    print(f"  ICO: {ico_path}")


def png_to_icns(png_path: Path, icns_path: Path):
    """PNG 转 ICNS (macOS) - 使用 iconutil"""
    from PIL import Image
    import tempfile
    import shutil

    iconset_dir = Path(tempfile.mkdtemp()) / "icon.iconset"
    iconset_dir.mkdir()

    img = Image.open(png_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    sizes = [16, 32, 64, 128, 256, 512]

    for size in sizes:
        resized = img.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(iconset_dir / f"icon_{size}x{size}.png")
        if size <= 256:
            resized_2x = img.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
            resized_2x.save(iconset_dir / f"icon_{size}x{size}@2x.png")

    try:
        subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)], check=True, capture_output=True)
        print(f"  ICNS: {icns_path}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  ICNS: 跳过 ({e})")
    finally:
        shutil.rmtree(iconset_dir.parent)


def main():
    check_dependencies()

    app_dir = Path(__file__).parent
    icons_dir = app_dir / "icons"
    svg_path = icons_dir / "icon.svg"

    print("转换图标...")

    if not svg_path.exists():
        print(f"  错误: {svg_path} 不存在")
        return

    png_path = app_dir / "icon.png"
    ico_path = app_dir / "icon.ico"
    icns_path = app_dir / "icon.icns"

    if not svg_to_png(svg_path, png_path, 512):
        return

    png_to_ico(png_path, ico_path)
    png_to_icns(png_path, icns_path)

    print(f"图标已生成到 {app_dir}")


if __name__ == "__main__":
    main()
