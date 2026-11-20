#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SynSimplify 图标生成器：渐变底 + 白色文件夹 + 双向箭头。

一张母图同步产出：
    host/icon.ico                        Windows exe 图标（16~256 多尺寸）
    host/icon.png                        窗口图标
    android/.../mipmap-*/ic_launcher.png Android 启动图标五档

用法：
    python tools/make_icon.py --out host
    python tools/make_icon.py --android app/android/app/src/main/res
    python tools/make_icon.py --png preview.png --size 512
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:  # pragma: no cover
    raise SystemExit("需要 Pillow：pip install Pillow")

BASE = 1024
MASTER = 2048

# 渐变：电光蓝 → 紫 → 青
GRAD_TL = (79, 140, 255)
GRAD_TR = (155, 107, 255)
GRAD_BL = (56, 94, 240)
GRAD_BR = (34, 211, 238)

WHITE = (255, 255, 255, 255)
FOLDER_TOP = (255, 255, 255, 255)
FOLDER_BOTTOM = (226, 236, 255, 255)
ARROW_TOP = (66, 118, 255, 255)
ARROW_BOTTOM = (150, 96, 255, 255)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def diag_gradient(size: int) -> Image.Image:
    """低分辨率算好再放大，比逐像素画 2048² 快很多。"""
    small = 96
    img = Image.new("RGB", (small, small))
    px = img.load()
    for y in range(small):
        ty = y / (small - 1)
        left = lerp(GRAD_TL, GRAD_BL, ty)
        right = lerp(GRAD_TR, GRAD_BR, ty)
        for x in range(small):
            px[x, y] = lerp(left, right, x / (small - 1))
    return img.resize((size, size), Image.BICUBIC)


def radial_glow(size: int, color, center, radius: float, max_alpha: int, steps: int = 80) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    for i in range(steps):
        k = i / (steps - 1)
        r = radius * (1 - k)
        alpha = int(max_alpha * (k ** 1.9))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (alpha,))
    return layer


def rounded_mask(size: int, radius: int, inset: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (inset, inset, size - inset - 1, size - inset - 1), radius=radius, fill=255
    )
    return mask


def _clip(layer: Image.Image, mask: Image.Image) -> Image.Image:
    filled = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    filled.paste(layer, (0, 0), mask)
    return filled


def vertical_gradient(size: int, box, top, bottom) -> Image.Image:
    """在 size² 透明画布上，把 box 区域内做竖直渐变。"""
    x0, y0, x1, y1 = box
    grad = Image.new("RGBA", (1, max(2, int(y1 - y0))), (0, 0, 0, 0))
    px = grad.load()
    h = grad.height
    for y in range(h):
        px[0, y] = lerp(top, bottom, y / (h - 1))
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    layer.paste(grad.resize((int(x1 - x0), h), Image.BICUBIC), (int(x0), int(y0)))
    return layer


def star(draw, cx, cy, r, color, waist=0.18):
    pts = [
        (cx, cy - r), (cx + r * waist, cy - r * waist), (cx + r, cy),
        (cx + r * waist, cy + r * waist), (cx, cy + r),
        (cx - r * waist, cy + r * waist), (cx - r, cy), (cx - r * waist, cy - r * waist),
    ]
    draw.polygon(pts, fill=color)


def arrow(draw, x0, x1, y, color, width, head):
    """一根带圆头箭头的水平箭头（方向由 x1>x0 决定）。"""
    r = width / 2
    if x1 > x0:
        body_end = x1 - head * 0.72
        draw.line([(x0, y), (body_end, y)], fill=color, width=width)
        draw.ellipse([x0 - r, y - r, x0 + r, y + r], fill=color)
        draw.polygon([(x1, y), (body_end, y - head * 0.78), (body_end, y + head * 0.78)], fill=color)
    else:
        body_end = x1 + head * 0.72
        draw.line([(x0, y), (body_end, y)], fill=color, width=width)
        draw.ellipse([x0 - r, y - r, x0 + r, y + r], fill=color)
        draw.polygon([(x1, y), (body_end, y - head * 0.78), (body_end, y + head * 0.78)], fill=color)


def render(size: int = MASTER) -> Image.Image:
    k = size / BASE
    s = lambda v: int(round(v * k))  # noqa: E731

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = rounded_mask(size, s(228), s(26))
    canvas.paste(diag_gradient(size), (0, 0), mask)

    canvas = Image.alpha_composite(
        canvas, _clip(radial_glow(size, (255, 255, 255), (s(300), s(240)), s(600), 78), mask)
    )
    canvas = Image.alpha_composite(
        canvas, _clip(radial_glow(size, (24, 10, 70), (s(880), s(900)), s(660), 66), mask)
    )

    # ---------- 文件夹投影
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((s(196), s(392), s(828), s(772)), radius=s(82), fill=(10, 18, 50, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(s(26)))
    shadow = shadow.point(lambda v: v)
    canvas = Image.alpha_composite(canvas, _clip(shadow, mask))

    # ---------- 文件夹本体（白色渐变）
    folder_mask = Image.new("L", (size, size), 0)
    fm = ImageDraw.Draw(folder_mask)
    fm.rounded_rectangle((s(196), s(300), s(474), s(432)), radius=s(52), fill=255)
    fm.rounded_rectangle((s(196), s(372), s(828), s(748)), radius=s(78), fill=255)

    body = vertical_gradient(size, (s(196), s(300), s(828), s(748)), FOLDER_TOP, FOLDER_BOTTOM)
    canvas = Image.alpha_composite(canvas, _clip(body, folder_mask))

    # 折页的高光线
    edge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge)
    ed.line([(s(232), s(410)), (s(792), s(410))], fill=(180, 200, 240, 90), width=s(4))
    canvas = Image.alpha_composite(canvas, _clip(edge, folder_mask))

    # ---------- 双向箭头
    arrows = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ad = ImageDraw.Draw(arrows)
    arrow(ad, s(320), s(716), s(492), ARROW_TOP, s(56), s(96))     # 向右
    arrow(ad, s(704), s(308), s(632), ARROW_BOTTOM, s(56), s(96))  # 向左
    canvas = Image.alpha_composite(canvas, _clip(arrows, folder_mask))

    # ---------- 星光
    spark = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(spark)
    star(draw, s(838), s(262), s(74), (255, 255, 255, 235))
    star(draw, s(890), s(392), s(34), (255, 255, 255, 190))
    star(draw, s(168), s(806), s(30), (255, 255, 255, 165))
    canvas = Image.alpha_composite(canvas, _clip(spark, mask))
    canvas = Image.alpha_composite(canvas, _clip(spark.filter(ImageFilter.GaussianBlur(s(10))), mask))

    # ---------- 边缘光
    rim = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle(
        (s(26), s(26), size - s(26) - 1, size - s(26) - 1),
        radius=s(228), outline=(255, 255, 255, 56), width=s(8),
    )
    canvas = Image.alpha_composite(canvas, rim)

    canvas.putalpha(
        Image.composite(canvas.getchannel("A"), Image.new("L", (size, size), 0), mask)
    )
    return canvas


def build_ico(path: Path, master: Image.Image) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sizes = [256, 128, 64, 48, 32, 16]
    frames = [master.resize((sz, sz), Image.LANCZOS) for sz in sizes]
    frames[0].save(path, format="ICO", sizes=[(sz, sz) for sz in sizes], append_images=frames[1:])
    return path


def build_png(path: Path, master: Image.Image, size: int = 512) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    master.resize((size, size), Image.LANCZOS).save(path)
    return path


def build_android_icons(res_dir: Path, master: Image.Image) -> list[Path]:
    densities = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }
    written = []
    for folder, px in densities.items():
        target = res_dir / folder / "ic_launcher.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        master.resize((px, px), Image.LANCZOS).save(target)
        written.append(target)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 SynSimplify 图标")
    parser.add_argument("--out", default="", help="输出目录（写 icon.ico + icon.png）")
    parser.add_argument("--android", default="", help="Android res 目录（写 mipmap-*）")
    parser.add_argument("--png", default="", help="额外导出预览 PNG")
    parser.add_argument("--size", type=int, default=0, help="预览 PNG 尺寸")
    args = parser.parse_args()

    master = render(MASTER)
    print(f"[icon] 母图 {MASTER}px 生成完毕")

    if args.out:
        ico = build_ico(Path(args.out) / "icon.ico", master)
        png = build_png(Path(args.out) / "icon.png", master, 512)
        print(f"[icon] {ico}")
        print(f"[icon] {png}")

    if args.android:
        for p in build_android_icons(Path(args.android), master):
            print(f"[icon] {p}")

    if args.png:
        size = args.size or 512
        print(f"[icon] {build_png(Path(args.png), master, size)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
