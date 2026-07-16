"""
2D 动漫效果动图生成器
使用 OpenCV 将照片转为动漫风格，并生成多种动画效果：
  1. 变身动画 —— 照片逐渐"变身"为动漫角色
  2. 浮动动画 —— 动漫画面带呼吸感缩放/平移
  3. 光影流动 —— 动漫画面上的光影/粒子飘过
  4. 线稿上色 —— 线稿描出 → 色彩填入
"""

import os, sys, io, random, math
import cv2
import numpy as np
from PIL import Image

# ── 配置 ──────────────────────────────────────────
INPUT_DIR  = r"C:\Users\ASUA\OneDrive\Desktop\cc\游戏图"
OUTPUT_DIR = os.path.join(INPUT_DIR, "anime_output")
MAX_SIZE   = 500            # 长边最大像素
FRAMES     = 24             # 每张 GIF 帧数
DURATION   = 80             # 每帧 ms
LOOP       = 0              # 无限循环

os.makedirs(OUTPUT_DIR, exist_ok=True)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ══════════════════════════════════════════════════
# 动漫化核心滤镜
# ══════════════════════════════════════════════════

def load_img(path: str) -> np.ndarray:
    """用 PIL 加载（支持中文路径）→ 转 OpenCV BGR 格式"""
    pil_img = Image.open(path).convert("RGB")
    w, h = pil_img.size
    if max(w, h) > MAX_SIZE:
        ratio = MAX_SIZE / max(w, h)
        pil_img = pil_img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    # PIL RGB → numpy → OpenCV BGR
    img = np.array(pil_img)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img


def anime_style(img: np.ndarray,
                edge_strength: float = 1.0,
                color_levels: int = 8,
                saturation: float = 1.3) -> np.ndarray:
    """
    核心动漫化算法 —— 多步骤 pipeline:

    1. 双边滤波 → 平滑颜色区域，保留边缘（模拟赛璐珞上色）
    2. 自适应边缘检测 → 提取黑色轮廓线
    3. K-means 颜色量化 → 减少颜色层级（动漫风格关键）
    4. 叠加轮廓线 + 增强饱和度
    """
    h, w = img.shape[:2]

    # ── Step 1: 多轮双边滤波（颜色区域平坦化）──
    smooth = img.copy()
    for _ in range(2):
        smooth = cv2.bilateralFilter(smooth, d=9, sigmaColor=75, sigmaSpace=75)

    # ── Step 2: 边缘检测生成轮廓线 ──
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    edges = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        blockSize=9,
        C=2
    )
    # 边缘膨胀使线条更粗/更细
    kernel_size = max(1, int(2 * edge_strength))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    edges = cv2.dilate(edges, kernel, iterations=1)
    edges = cv2.bitwise_not(edges)  # 白色背景黑色线条

    # ── Step 3: K-means 颜色量化 ──
    data = smooth.reshape((-1, 3)).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(
        data, color_levels, None, criteria, 10, cv2.KMEANS_PP_CENTERS
    )
    centers = centers.astype(np.uint8)
    quantized = centers[labels.flatten()].reshape(smooth.shape)

    # ── Step 4: 叠加轮廓 ──
    edges_3ch = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
    # 颜色区域 * 边缘蒙版 — 边缘处变暗变黑
    result = cv2.bitwise_and(quantized, edges_3ch)
    # 轻微降低边缘亮度让线更明显
    edge_mask = cv2.bitwise_not(edges)
    edge_mask_3ch = cv2.cvtColor(edge_mask, cv2.COLOR_GRAY2BGR)
    dark_overlay = (result.astype(np.float32) * 0.3).astype(np.uint8)
    # 只在边缘处加暗
    edge_dark = cv2.bitwise_and(dark_overlay, edge_mask_3ch)
    edge_bright = cv2.bitwise_and(result, cv2.bitwise_not(edge_mask_3ch))
    result = cv2.add(edge_dark, edge_bright)

    # ── Step 5: 饱和度增强 ──
    hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
    result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    return result


def anime_stylization(img: np.ndarray) -> np.ndarray:
    """OpenCV 内置风格化滤镜 —— 备用方案，效果偏水彩"""
    return cv2.stylization(img, sigma_s=60, sigma_r=0.6)


# ══════════════════════════════════════════════════
# 动画 1: 变身动画 —— 照片 → 动漫角色
# ══════════════════════════════════════════════════
def make_transformation(img: np.ndarray, name: str):
    """从原始照片逐渐过渡到动漫风格"""
    anime = anime_style(img)
    frames = []

    for i in range(FRAMES):
        t = i / (FRAMES - 1)
        # 使用 ease-in-out 曲线
        alpha = t ** 2 * (3 - 2 * t)  # smoothstep

        # 交叉淡入淡出
        blended = cv2.addWeighted(img, 1 - alpha, anime, alpha, 0)

        # 中途添加一些"能量波动"线条
        if 0.2 < t < 0.8:
            # 随机闪烁
            flicker = 1.0 + 0.05 * math.sin(t * 30)
            blended = np.clip(blended.astype(np.float32) * flicker, 0, 255).astype(np.uint8)

        frame = Image.fromarray(cv2.cvtColor(blended, cv2.COLOR_BGR2RGB))
        frames.append(frame)

    out_path = os.path.join(OUTPUT_DIR, f"{name}_01_变身动画.gif")
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=DURATION, loop=LOOP, optimize=False)
    print(f"  ✅ 变身动画 → {os.path.basename(out_path)}")
    return anime  # 返回动漫版供后续复用


# ══════════════════════════════════════════════════
# 动画 2: 浮动呼吸感 —— 画面轻轻缩放
# ══════════════════════════════════════════════════
def make_floating(img: np.ndarray, anime: np.ndarray, name: str):
    """动漫画面带有缓缓缩放/平移的呼吸感"""
    h, w = anime.shape[:2]
    frames = []

    for i in range(FRAMES):
        t = i / (FRAMES - 1)
        # 轻微缩放: 1.0 → 1.04 → 1.0，模拟呼吸
        scale = 1.0 + 0.04 * math.sin(t * 2 * math.pi)
        new_w = int(w * scale)
        new_h = int(h * scale)
        scaled = cv2.resize(anime, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        # 居中裁剪
        x = (new_w - w) // 2
        y = (new_h - h) // 2
        crop = scaled[y:y+h, x:x+w]

        frame = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        frames.append(frame)

    out_path = os.path.join(OUTPUT_DIR, f"{name}_02_浮动呼吸.gif")
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=DURATION, loop=LOOP, optimize=False)
    print(f"  ✅ 浮动呼吸 → {os.path.basename(out_path)}")


# ══════════════════════════════════════════════════
# 动画 3: 光影粒子 —— 闪烁光点飘过画面
# ══════════════════════════════════════════════════
def make_sparkles(img: np.ndarray, anime: np.ndarray, name: str):
    """动漫画面上叠加飘过的闪烁光点粒子"""
    h, w = anime.shape[:2]
    frames = []

    # 预生成 25 个光点的轨迹
    particles = []
    for _ in range(25):
        particles.append({
            'x': random.uniform(0, w),
            'y': random.uniform(0, h),
            'vx': random.uniform(-2.5, 2.5),
            'vy': random.uniform(-1.5, -0.3),  # 轻微上飘
            'size': random.uniform(1.5, 5.0),
            'brightness': random.uniform(0.4, 1.0),
            'phase': random.uniform(0, math.pi * 2),
        })

    for i in range(FRAMES):
        t = i / (FRAMES - 1)
        canvas = anime.copy().astype(np.float32)

        for p in particles:
            x = p['x'] + p['vx'] * i
            y = p['y'] + p['vy'] * i
            # 光点闪烁
            alpha = 0.5 + 0.5 * math.sin(i * 0.4 + p['phase'])
            alpha *= p['brightness']

            px, py = int(x), int(y)
            if 0 <= px < w and 0 <= py < h:
                size = int(p['size'] * (0.8 + 0.4 * alpha))
                # 画发光十字星
                color = np.array([255, 255, 240]) * alpha
                cv2.circle(canvas, (px, py), size,
                           (200, 220, 255), -1, cv2.LINE_AA)
                # 十字光芒
                cv2.line(canvas, (px - size*2, py), (px + size*2, py),
                         (255, 255, 220), 1, cv2.LINE_AA)
                cv2.line(canvas, (px, py - size*2), (px, py + size*2),
                         (255, 255, 220), 1, cv2.LINE_AA)

        canvas = np.clip(canvas, 0, 255).astype(np.uint8)
        frame = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
        frames.append(frame)

    out_path = os.path.join(OUTPUT_DIR, f"{name}_03_光影粒子.gif")
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=DURATION, loop=LOOP, optimize=False)
    print(f"  ✅ 光影粒子 → {os.path.basename(out_path)}")


# ══════════════════════════════════════════════════
# 动画 4: 线稿上色 —— 线描勾出 → 色彩填满
# ══════════════════════════════════════════════════
def make_lineart_reveal(img: np.ndarray, anime: np.ndarray, name: str):
    """
    第一阶段：原始图像渐变为黑白线稿
    第二阶段：线稿上色，填入动漫色彩
    """
    h, w = anime.shape[:2]

    # 生成线稿
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    edges = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 2
    )
    edges = cv2.bitwise_not(edges)
    edges = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

    frames = []
    for i in range(FRAMES):
        t = i / (FRAMES - 1)
        # smoothstep
        alpha = t ** 2 * (3 - 2 * t)

        if t < 0.55:
            # 阶段1: 照片 → 线稿 (0% → 55%)
            local_t = t / 0.55
            # 先降色
            gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray_3ch = cv2.cvtColor(gray_img, cv2.COLOR_GRAY2BGR)
            blended = cv2.addWeighted(img, 1 - local_t, gray_3ch, local_t, 0)
            # 逐渐叠加线稿
            blended = cv2.addWeighted(blended, 1 - local_t*0.7, edges, local_t*0.7, 0)
        else:
            # 阶段2: 线稿 → 上色完毕 (55% → 100%)
            local_t = (t - 0.55) / 0.45
            blended = cv2.addWeighted(edges, 1 - local_t, anime, local_t, 0)

        frame = Image.fromarray(cv2.cvtColor(blended.astype(np.uint8), cv2.COLOR_BGR2RGB))
        frames.append(frame)

    out_path = os.path.join(OUTPUT_DIR, f"{name}_04_线稿上色.gif")
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=DURATION, loop=LOOP, optimize=False)
    print(f"  ✅ 线稿上色 → {os.path.basename(out_path)}")


# ══════════════════════════════════════════════════
# 动画 5: 漫画分镜风 —— 色调偏移循环
# ══════════════════════════════════════════════════
def make_manga_tones(img: np.ndarray, anime: np.ndarray, name: str):
    """动漫画面色调微动 + 网点纸效果，循环"""
    h, w = anime.shape[:2]
    frames = []

    for i in range(FRAMES):
        t = i / (FRAMES - 1)

        # 色调微调 H
        hsv = cv2.cvtColor(anime, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 0] = np.mod(hsv[:, :, 0] + math.sin(t * 2 * math.pi) * 3, 180)
        shifted = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        # 添加半调网点纹理
        overlay = np.zeros((h, w, 3), dtype=np.uint8)
        dot_spacing = 6
        dot_offset_x = int((i * 0.5) % dot_spacing)
        dot_offset_y = int((i * 0.3) % dot_spacing)
        for dy in range(-dot_spacing, h + dot_spacing, dot_spacing):
            for dx in range(-dot_spacing, w + dot_spacing, dot_spacing):
                cx = dx + dot_offset_x
                cy = dy + dot_offset_y
                if 0 <= cx < w and 0 <= cy < h:
                    overlay[cy, cx] = [10, 10, 10]

        overlay = cv2.GaussianBlur(overlay, (3, 3), 1)
        result = cv2.addWeighted(shifted, 1.0, overlay, -0.15, 0)

        frame = Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))
        frames.append(frame)

    out_path = os.path.join(OUTPUT_DIR, f"{name}_05_漫画色调.gif")
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=DURATION, loop=LOOP, optimize=False)
    print(f"  ✅ 漫画色调 → {os.path.basename(out_path)}")


# ══════════════════════════════════════════════════
# 主程序
# ══════════════════════════════════════════════════
def main():
    png_files = sorted([
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(".png") and not f.startswith("pixelate")
    ])

    print(f"\n📁 找到 {len(png_files)} 张图片\n")

    for png in png_files:
        name = os.path.splitext(png)[0]
        path = os.path.join(INPUT_DIR, png)
        size_kb = os.path.getsize(path) // 1024
        print(f"🎨 处理: {png} ({size_kb} KB)")

        img = load_img(path)
        h, w = img.shape[:2]
        print(f"   尺寸: {w}x{h}")

        # 先做动漫化
        anime = make_transformation(img, name)
        make_floating(img, anime, name)
        make_sparkles(img, anime, name)
        make_lineart_reveal(img, anime, name)
        make_manga_tones(img, anime, name)
        print()

    print(f"🎉 全部完成！输出目录: {OUTPUT_DIR}")
    print(f"   共生成 {len(png_files) * 5} 个动图")


if __name__ == "__main__":
    main()
