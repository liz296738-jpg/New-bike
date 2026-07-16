"""
像素化动图生成脚本
为每张照片生成多种风格的像素化 GIF 动图：
  1. 分辨率渐变 —— 从极度像素化逐渐变清晰（复古游戏加载效果）
  2. 像素波浪 —— 像素化波浪从左到右扫过画面
  3. 块状溶解 —— 随机像素块逐个淡入
"""

import os
import sys
import io
from PIL import Image
import random

# 修复 Windows GBK 终端 emoji 输出问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── 配置 ──────────────────────────────────────────
INPUT_DIR   = r"C:\Users\ASUA\OneDrive\Desktop\cc\游戏图"
OUTPUT_DIR  = os.path.join(INPUT_DIR, "output")
MAX_SIZE    = 600          # 长边最大像素（控制输出大小）
FRAME_COUNT = 20           # 每张 GIF 的帧数
DURATION    = 80           # 每帧持续时间 (ms)，80ms ≈ 12.5fps
LOOP        = 0            # 0 = 无限循环

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 工具函数 ──────────────────────────────────────
def load_and_resize(path: str, max_size: int = MAX_SIZE) -> Image.Image:
    """加载图片并等比缩放到合理尺寸，转为 RGB"""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    return img

def pixelate(img: Image.Image, block_size: int) -> Image.Image:
    """
    像素化：将图像缩小到 (原尺寸 / block_size)，再用 NEAREST 放大回原尺寸。
    block_size 越大，像素块越大 = 越模糊。
    """
    w, h = img.size
    small_w = max(1, w // block_size)
    small_h = max(1, h // block_size)
    small = img.resize((small_w, small_h), Image.LANCZOS)
    return small.resize((w, h), Image.NEAREST)


# ══════════════════════════════════════════════════
# 风格 1：分辨率渐变（De-pixelation）
# ══════════════════════════════════════════════════
def make_resolution_ramp(img: Image.Image, name: str):
    """
    从极度像素化（block_size=50）平滑过渡到原始清晰图像。
    """
    frames = []
    # 从最大像素块到 1（原始图）
    for i in range(FRAME_COUNT):
        # 指数衰减让过渡更自然：前面变化慢，后面加速
        t = i / (FRAME_COUNT - 1)
        block_size = int(50 * (1 - t)**2) + 1
        px = pixelate(img, block_size)
        frames.append(px)

    out_path = os.path.join(OUTPUT_DIR, f"{name}_01_分辨率渐变.gif")
    frames[0].save(
        out_path, save_all=True, append_images=frames[1:],
        duration=DURATION, loop=LOOP, optimize=False
    )
    print(f"  ✅ 分辨率渐变 → {out_path}")


# ══════════════════════════════════════════════════
# 风格 2：像素波浪（Pixel Wave）
# ══════════════════════════════════════════════════
def make_pixel_wave(img: Image.Image, name: str):
    """
    像素化波浪从左到右扫过画面。左边先变清晰，右边还是像素块。
    """
    w, h = img.size
    frames = []

    # 准备多级像素化版本
    pixelated = {}
    for bs in [64, 32, 16, 12, 8, 6, 4, 3, 2, 1]:
        pixelated[bs] = pixelate(img, bs)

    for i in range(FRAME_COUNT):
        t = i / (FRAME_COUNT - 1)  # 0→1，波浪位置从左到右
        wave_pos = int(t * w)      # 分界线 x 坐标

        # 左边清晰，右边像素化
        frame = Image.new("RGB", (w, h))
        # 右侧用像素化版本（block_size 从大到小对应越右越像素）
        for bs in [64, 32, 16, 8, 4, 2, 1]:
            seg_start = int(w * (bs - 1) / 10)
            seg_end   = int(w * bs / 10)
            seg_start = max(0, min(w, seg_start))
            seg_end   = max(0, min(w, seg_end))

            if seg_end <= wave_pos:
                continue  # 在分界线左侧，保持清晰

            region = pixelated[bs].crop((max(seg_start, wave_pos), 0, seg_end, h))
            frame.paste(region, (max(seg_start, wave_pos), 0))

        # 左边贴原始图
        if wave_pos > 0:
            frame.paste(img.crop((0, 0, wave_pos, h)), (0, 0))

        frames.append(frame)

    out_path = os.path.join(OUTPUT_DIR, f"{name}_02_像素波浪.gif")
    frames[0].save(
        out_path, save_all=True, append_images=frames[1:],
        duration=DURATION, loop=LOOP, optimize=False
    )
    print(f"  ✅ 像素波浪 → {out_path}")


# ══════════════════════════════════════════════════
# 风格 3：块状溶解（Block Dissolve）
# ══════════════════════════════════════════════════
def make_block_dissolve(img: Image.Image, name: str):
    """
    将画面分成像素块网格，块随机逐个从像素化变成清晰。
    """
    w, h = img.size
    grid_cols, grid_rows = 12, 12
    bw, bh = w // grid_cols, h // grid_rows

    px_img = pixelate(img, block_size=max(4, min(w, h) // 80))

    # 所有块的坐标
    blocks = [(cx, cy) for cy in range(grid_rows) for cx in range(grid_cols)]
    random.shuffle(blocks)

    frames = []
    for i in range(FRAME_COUNT):
        t = i / (FRAME_COUNT - 1)
        revealed_count = int(t * len(blocks))

        frame = px_img.copy()  # 从全像素化开始
        # 逐个贴上清晰的块
        for j in range(revealed_count):
            cx, cy = blocks[j]
            x, y = cx * bw, cy * bh
            box = (x, y, x + bw, y + bh)
            frame.paste(img.crop(box), box)

        frames.append(frame)

    out_path = os.path.join(OUTPUT_DIR, f"{name}_03_块状溶解.gif")
    frames[0].save(
        out_path, save_all=True, append_images=frames[1:],
        duration=DURATION, loop=LOOP, optimize=False
    )
    print(f"  ✅ 块状溶解 → {out_path}")


# ══════════════════════════════════════════════════
# 风格 4：像素闪烁循环（Pixel Flicker Loop）
# ══════════════════════════════════════════════════
def make_pixel_flicker(img: Image.Image, name: str):
    """
    在像素化和清晰之间来回切换，形成闪烁/故障效果，完美循环。
    """
    w, h = img.size
    block_sizes = [32, 24, 16, 12, 8, 6, 4, 3, 2, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32]
    frames = []

    for bs in block_sizes:
        frames.append(pixelate(img, bs))

    # 反向再一遍构成完美循环（去重首尾）
    out_path = os.path.join(OUTPUT_DIR, f"{name}_04_像素闪烁.gif")
    frames[0].save(
        out_path, save_all=True, append_images=frames[1:],
        duration=DURATION, loop=LOOP, optimize=False
    )
    print(f"  ✅ 像素闪烁 → {out_path}")


# ══════════════════════════════════════════════════
# 主程序
# ══════════════════════════════════════════════════
def main():
    png_files = sorted([
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(".png")
    ])
    print(f"\n📁 找到 {len(png_files)} 张图片\n")

    for png in png_files:
        name = os.path.splitext(png)[0]
        path = os.path.join(INPUT_DIR, png)
        print(f"🎨 处理: {png} ({os.path.getsize(path)//1024} KB)")

        img = load_and_resize(path)
        w, h = img.size
        print(f"   尺寸: {w}×{h}")

        make_resolution_ramp(img, name)
        make_pixel_wave(img, name)
        make_block_dissolve(img, name)
        make_pixel_flicker(img, name)
        print()

    print(f"🎉 全部完成！输出目录: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
