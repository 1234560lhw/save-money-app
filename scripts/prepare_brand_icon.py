"""把汤姆猫那张水彩画做成应用图标。

产出（都在 ``assets/branding/`` 下）
------------------------------------
* ``app_icon.png``         1024×1024 方形场景图 —— 应用图标（手机 App / 备用）
* ``app_icon_rounded.png`` 圆角方形 —— 实际使用的图标（观感更现代）
* ``app_icon.ico``         多尺寸 ico —— Windows 快捷方式与 exe 图标
* ``icon_preview.png``     预览拼图

为什么不把猫单独抠出来
----------------------
试过两种抠图思路，都不成立：

1. "与背景色不同" —— 会把彩色天空当成前景，结果留下天空、丢掉猫；
2. "按饱和度分离（猫是灰的、背景是彩色的）" —— 水彩画里猫的灰白毛、
   雪地、天空的浅色区在饱和度与明度上互相重叠，抠出来是一团糊。

原图只有 1055px，猫只占其中约 250px，硬抠再放大 4 倍只会更糟。
所以最终**直接用猫 + 日落背景的方形构图**当图标——这本来就是一张完整、
好看的画，比一个边缘破碎的抠图强得多。

用法::

    .venv\\Scripts\\python.exe scripts\\prepare_brand_icon.py
    .venv\\Scripts\\python.exe scripts\\prepare_brand_icon.py --source "D:\\...\\图.jpg"
"""

from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "assets" / "branding"
#: Flet 打包默认读取的位置；保持一致，打包时不用额外参数
LEGACY_DIR = PROJECT_ROOT / "assets"

#: 图标输出尺寸（Flet 打包建议 1024）
ICON_SIZE = 1024
#: 方形裁剪边长占原图宽度的比例（把猫和它周围的天空一起框进来）
CROP_RATIO = 0.68
#: 裁剪框中心的水平/垂直偏移（占原图比例，正数向右/向下）
CENTER_OFFSET_X = 0.02
CENTER_OFFSET_Y = 0.06
#: 圆角比例
CORNER_RATIO = 0.22


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成应用图标")
    parser.add_argument("--source", required=False,
                        default=r"D:\个人材料\绘画素材\微信图片_20261005183727_21_27.jpg",
                        help="汤姆猫原图路径")
    parser.add_argument("--crop-ratio", type=float, default=CROP_RATIO)
    return parser.parse_args(argv)


def square_crop(image, *, ratio: float, offset_x: float, offset_y: float):
    """按比例裁一个正方形（猫大致居中）。"""
    width, height = image.size
    side = int(min(width, height) * ratio)
    cx = width * (0.5 + offset_x)
    cy = height * (0.5 + offset_y)
    left = int(max(0, min(width - side, cx - side / 2)))
    top = int(max(0, min(height - side, cy - side / 2)))
    return image.crop((left, top, left + side, top + side))


def rounded_square(image, *, radius_ratio: float = CORNER_RATIO):
    """圆角方形：Flet 的图标推荐自带圆角，避免被系统裁得不一致。"""
    from PIL import Image, ImageDraw

    size = image.size[0]
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=int(size * radius_ratio), fill=255)
    out = image.convert("RGBA")
    out.putalpha(mask)
    return out


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    from PIL import Image

    source = Path(args.source)
    if not source.is_file():
        print(f"[icon] 找不到原图：{source}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[icon] 原图：{source.name} {Image.open(source).size}")

    image = Image.open(source).convert("RGB")
    crop = square_crop(image, ratio=args.crop_ratio,
                       offset_x=CENTER_OFFSET_X, offset_y=CENTER_OFFSET_Y)
    icon = crop.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)

    # 方形版（备用 / Android 自适应图标的前景）
    square_path = OUT_DIR / "app_icon.png"
    icon.save(square_path, optimize=True)
    print(f"[icon] {square_path.relative_to(PROJECT_ROOT)}  {icon.size}  "
          f"{square_path.stat().st_size // 1024} KB")

    # 圆角版（实际使用）
    rounded = rounded_square(icon)
    rounded_path = OUT_DIR / "app_icon_rounded.png"
    rounded.save(rounded_path, optimize=True)
    print(f"[icon] {rounded_path.relative_to(PROJECT_ROOT)}  "
          f"{rounded_path.stat().st_size // 1024} KB")

    # Windows ico：快捷方式与 exe 都用它
    ico_path = OUT_DIR / "app_icon.ico"
    icon.save(ico_path, format="ICO",
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                     (64, 64), (128, 128), (256, 256)])
    print(f"[icon] {ico_path.relative_to(PROJECT_ROOT)}  {ico_path.stat().st_size // 1024} KB")

    # 同时放到 Flet 打包默认位置，省得打包时再指定参数
    rounded.save(LEGACY_DIR / "icon.png", optimize=True)
    icon.save(LEGACY_DIR / "icon.ico", format="ICO",
              sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"[icon] 同时输出到 {LEGACY_DIR.relative_to(PROJECT_ROOT)}/icon.png 与 icon.ico"
          f"（Flet 打包默认读这里）")

    # 预览：小尺寸下是否还看得清
    tile = 260
    preview = Image.new("RGB", (tile * 4, tile), (245, 246, 250))
    sizes = (ICON_SIZE, 128, 64, 32)
    for index, size in enumerate(sizes):
        thumb = rounded.resize((size, size), Image.LANCZOS)
        base = Image.new("RGB", (size, size), (255, 255, 255))
        base.paste(thumb, mask=thumb.getchannel("A"))
        preview.paste(base, (index * tile + (tile - size) // 2, (tile - size) // 2))
    preview_path = OUT_DIR / "icon_preview.png"
    preview.save(preview_path, optimize=True)
    print(f"[icon] 预览 {preview_path.relative_to(PROJECT_ROOT)}"
          f"（1024 / 128 / 64 / 32 px，检查小尺寸是否还认得出）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
