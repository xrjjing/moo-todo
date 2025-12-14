#!/usr/bin/env python3
"""
牛牛待办 - 图标生成脚本
从 SVG 生成 macOS (.icns) 和 Windows (.ico) 图标
"""
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("请先安装 Pillow: pip install Pillow")
    sys.exit(1)


def svg_to_png(svg_path: Path, png_path: Path, size: int):
    """将 SVG 转换为 PNG（尝试多种方法）"""
    # 方法1: 使用 cairosvg
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path),
                        output_width=size, output_height=size)
        return True
    except ImportError:
        pass

    # 方法2: 使用 rsvg-convert (macOS: brew install librsvg)
    try:
        subprocess.run([
            "rsvg-convert", "-w", str(size), "-h", str(size),
            str(svg_path), "-o", str(png_path)
        ], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 方法3: 使用 Inkscape (如果安装)
    try:
        subprocess.run([
            "inkscape", str(svg_path), "--export-type=png",
            f"--export-filename={png_path}",
            f"--export-width={size}", f"--export-height={size}"
        ], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return False


def create_icns(icon_dir: Path, svg_path: Path):
    """创建 macOS .icns 文件"""
    iconset_dir = icon_dir / "icon.iconset"
    iconset_dir.mkdir(exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512]
    success = True

    for size in sizes:
        png_path = iconset_dir / f"icon_{size}x{size}.png"
        if not svg_to_png(svg_path, png_path, size):
            print(f"⚠️ 无法生成 {size}x{size} PNG")
            success = False
            continue

        # 生成 @2x 版本
        if size <= 512:
            png_2x_path = iconset_dir / f"icon_{size}x{size}@2x.png"
            svg_to_png(svg_path, png_2x_path, size * 2)

    if not success:
        print("⚠️ 部分 PNG 生成失败，请安装: pip install cairosvg 或 brew install librsvg")
        return

    # 使用 iconutil 生成 .icns (仅 macOS)
    if sys.platform == "darwin":
        try:
            subprocess.run([
                "iconutil", "-c", "icns", str(iconset_dir),
                "-o", str(icon_dir / "icon.icns")
            ], check=True)
            print(f"✅ 已生成: {icon_dir / 'icon.icns'}")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ iconutil 失败: {e}")
    else:
        print(f"⚠️ 非 macOS 系统，iconset 已保存至: {iconset_dir}")


def create_ico(icon_dir: Path, svg_path: Path):
    """创建 Windows .ico 文件"""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []
    temp_dir = icon_dir / "temp_ico"
    temp_dir.mkdir(exist_ok=True)

    for size in sizes:
        png_path = temp_dir / f"icon_{size}.png"
        if svg_to_png(svg_path, png_path, size):
            img = Image.open(png_path)
            images.append(img.copy())
            img.close()

    if not images:
        print("⚠️ 无法生成 ICO，PNG 转换失败")
        return

    ico_path = icon_dir / "icon.ico"
    images[0].save(ico_path, format='ICO',
                   sizes=[(img.size[0], img.size[1]) for img in images],
                   append_images=images[1:])
    print(f"✅ 已生成: {ico_path}")

    # 清理临时文件
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    icon_dir = Path(__file__).parent
    svg_path = icon_dir / "icon.svg"

    print("🐮 牛牛待办 - 图标生成器")
    print("-" * 30)

    if not svg_path.exists():
        print(f"❌ 未找到 SVG 文件: {svg_path}")
        return

    # 生成预览 PNG
    preview_path = icon_dir / "preview.png"
    if svg_to_png(svg_path, preview_path, 512):
        print(f"✅ 已生成预览: {preview_path}")
    else:
        print("⚠️ 无法生成预览 PNG")
        print("   请安装转换工具:")
        print("   - pip install cairosvg")
        print("   - 或 brew install librsvg")
        return

    # 生成 .ico
    create_ico(icon_dir, svg_path)

    # 生成 .icns
    create_icns(icon_dir, svg_path)

    print("-" * 30)
    print("🎉 图标生成完成!")


if __name__ == "__main__":
    main()
