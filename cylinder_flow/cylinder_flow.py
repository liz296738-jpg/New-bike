"""
圆柱绕流 CFD 模拟 — Lattice Boltzmann Method (D2Q9 + BGK)
=========================================================

模拟不可压缩流体绕过圆柱体时的流场演化:
  - 对称回流泡 (低 Re)
  - 卡门涡街 (Re ~ 60-200)
  - 升力/阻力系数时间序列

数值方法:
  - D2Q9 离散速度模型
  - BGK 碰撞算子 (单松弛时间)
  - Zou-He 速度入口 / 对流出口 / 半步反弹壁面

运行:
  python cylinder_flow.py                      # Re=100 实时动画
  python cylinder_flow.py --Re 150             # 更高 Re
  python cylinder_flow.py --Re 60 --save       # 保存动画
  python cylinder_flow.py --no-anim            # 仅计算, 打印日志
"""

import argparse
import time
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Circle
from matplotlib.colors import TwoSlopeNorm


# ============================================================================
# D2Q9 常量
# ============================================================================

C = np.array([
    [ 0,  0], [ 1,  0], [ 0,  1], [-1,  0], [ 0, -1],
    [ 1,  1], [-1,  1], [-1, -1], [ 1, -1],
], dtype=np.int32)

W = np.array([4/9, 1/9, 1/9, 1/9, 1/9, 1/36, 1/36, 1/36, 1/36])
OPP = np.array([0, 3, 4, 1, 2, 7, 8, 5, 6], dtype=np.int32)
CX, CY = C[:, 0], C[:, 1]


# ============================================================================
# LBM 求解器
# ============================================================================

class CylinderFlowLBM:
    """D2Q9 LBM 圆柱扰流 — 全向量化"""

    def __init__(self, nx=400, ny=120, Re=100.0,
                 cylinder_d=24, u_inlet=0.08):
        self.nx, self.ny = nx, ny
        self.Re = Re
        self.cylinder_d = cylinder_d
        self.cylinder_r = cylinder_d / 2.0
        self.cx = nx // 5
        self.cy = ny // 2
        self.u_inlet = u_inlet

        # 松弛参数
        self.nu = u_inlet * cylinder_d / Re
        self.tau = 3.0 * self.nu + 0.5
        self.omega = 1.0 / self.tau
        self.omega_1 = 1.0 - self.omega

        # 含 ghost 层
        self.snx = nx + 2
        self.sny = ny + 2

        # 场变量
        self.f = np.zeros((9, self.snx, self.sny))
        self.rho = np.ones((self.snx, self.sny))
        self.ux = np.zeros((self.snx, self.sny))
        self.uy = np.zeros((self.snx, self.sny))

        # 固体掩码
        self.solid = self._make_cylinder_mask()

        # 历史
        self.step_count = 0
        self.hist_cd, self.hist_cl, self.hist_step = [], [], []

    def _make_cylinder_mask(self):
        ii, jj = np.meshgrid(np.arange(self.snx), np.arange(self.sny), indexing="ij")
        gx, gy = self.cx + 1, self.cy + 1
        return (ii - gx)**2 + (jj - gy)**2 <= self.cylinder_r**2

    # ── 宏观量 ──

    def compute_macro(self):
        self.rho = self.f.sum(axis=0)
        inv_rho = np.where(self.rho > 1e-10, 1.0 / self.rho, 1.0)
        self.ux = (self.f[1] - self.f[3] + self.f[5] - self.f[6]
                   - self.f[7] + self.f[8]) * inv_rho
        self.uy = (self.f[2] - self.f[4] + self.f[5] + self.f[6]
                   - self.f[7] - self.f[8]) * inv_rho
        self.ux[self.solid] = 0.0
        self.uy[self.solid] = 0.0
        self.rho[self.solid] = 1.0

    # ── 平衡态 ──

    def equilibrium(self):
        u2 = self.ux**2 + self.uy**2
        cu = CX[:, None, None] * self.ux + CY[:, None, None] * self.uy
        return W[:, None, None] * self.rho * (1 + 3*cu + 4.5*cu**2 - 1.5*u2)

    # ── 碰撞 + 迁移 ──

    def collide_and_stream(self):
        feq = self.equilibrium()
        f_post = self.omega_1 * self.f + self.omega * feq
        f_new = np.zeros_like(self.f)
        for k in range(9):
            f_new[k] = np.roll(np.roll(f_post[k], CX[k], axis=0), CY[k], axis=1)
        self.f = f_new

    # ── 边界条件 ──

    def apply_inlet(self):
        """Zou-He 速度入口"""
        i = 1
        u0 = self.u_inlet
        rho_in = (self.f[0,i,:] + self.f[2,i,:] + self.f[4,i,:]
                  + 2*(self.f[3,i,:] + self.f[6,i,:] + self.f[7,i,:])) / (1 - u0)
        rho_in = np.clip(rho_in, 0.5, 2.0)
        self.f[1,i,:] = self.f[3,i,:] + (2/3)*rho_in*u0
        self.f[5,i,:] = (self.f[7,i,:] - 0.5*(self.f[2,i,:] - self.f[4,i,:])
                         + (1/6)*rho_in*u0)
        self.f[8,i,:] = (self.f[6,i,:] + 0.5*(self.f[2,i,:] - self.f[4,i,:])
                         + (1/6)*rho_in*u0)

    def apply_outlet(self):
        """对流出口"""
        self.f[:, self.nx, :] = self.f[:, self.nx - 1, :]

    def apply_top_bottom(self):
        """上下壁面: 自由滑移"""
        jt, jb = self.ny, 1
        for ka, kb in [(2,4), (5,8), (6,7)]:
            self.f[[ka,kb], :, jt] = self.f[[kb,ka], :, jt]
            self.f[[ka,kb], :, jb] = self.f[[kb,ka], :, jb]

    def apply_cylinder_bounceback(self):
        """圆柱半步反弹"""
        f = self.f
        solid = self.solid
        for k in range(9):
            k_op = OPP[k]
            solid_nbr = np.roll(np.roll(solid, -CX[k], axis=0), -CY[k], axis=1)
            mask = solid_nbr & ~solid
            src = np.roll(np.roll(f[k], -CX[k], axis=0), -CY[k], axis=1)
            f[k_op] = np.where(mask, src, f[k_op])

    def apply_boundaries(self):
        self.apply_inlet()
        self.apply_outlet()
        self.apply_top_bottom()
        self.apply_cylinder_bounceback()

    # ── 力计算 ──

    def compute_forces(self):
        fx, fy = 0.0, 0.0
        solid = self.solid
        f = self.f
        for k in range(9):
            k_op = OPP[k]
            solid_nbr = np.roll(np.roll(solid, -CX[k], axis=0), -CY[k], axis=1)
            mask = (~solid) & solid_nbr
            f_solid = np.roll(np.roll(f[k_op], CX[k], axis=0), CY[k], axis=1)
            fx += np.sum((f[k] + f_solid) * mask * CX[k])
            fy += np.sum((f[k] + f_solid) * mask * CY[k])
        denom = 0.5 * self.u_inlet**2 * self.cylinder_d
        return (fx/denom, fy/denom) if denom > 0 else (0.0, 0.0)

    # ── 涡量 ──

    def compute_vorticity(self):
        u = self.ux[1:self.nx+1, 1:self.ny+1]
        v = self.uy[1:self.nx+1, 1:self.ny+1]
        dvdx = (v[2:, 1:-1] - v[:-2, 1:-1]) * 0.5
        dudy = (u[1:-1, 2:] - u[1:-1, :-2]) * 0.5
        vort = np.zeros((self.nx, self.ny))
        vort[1:-1, 1:-1] = dvdx - dudy
        return vort

    # ── 速度场 ──

    def get_velocity_field(self):
        return (self.ux[1:self.nx+1, 1:self.ny+1],
                self.uy[1:self.nx+1, 1:self.ny+1])

    # ── 初始化 ──

    def init(self):
        self.rho.fill(1.0)
        self.ux.fill(self.u_inlet)
        self.uy.fill(0.0)
        self.ux[self.solid] = 0.0
        self.uy[self.solid] = 0.0
        self.f = self.equilibrium().copy()

    # ── 单步 ──

    def step(self):
        self.compute_macro()
        cd, cl = self.compute_forces()
        self.collide_and_stream()
        self.apply_boundaries()
        self.step_count += 1
        self.hist_step.append(self.step_count)
        self.hist_cd.append(cd)
        self.hist_cl.append(cl)
        return cd, cl


# ============================================================================
# 实时动画
# ============================================================================

class FlowVisualizer:
    """圆柱绕流实时动画 — 涡量场 + Cd/Cl 时序"""

    def __init__(self, sim: CylinderFlowLBM, steps_per_frame=20):
        self.sim = sim
        self.spf = steps_per_frame

        self.fig = plt.figure(figsize=(16, 6))
        self.fig.canvas.manager.set_window_title(
            f"Kármán Vortex Street — Re={sim.Re:.0f}")

        # 左: 涡量场
        self.ax1 = self.fig.add_subplot(1, 2, 1)
        self.ax1.set_xlim(0, sim.nx)
        self.ax1.set_ylim(0, sim.ny)
        self.ax1.set_aspect("equal")
        self.ax1.set_xlabel("x (lattice)")
        self.ax1.set_ylabel("y (lattice)")

        cyl = Circle((sim.cx, sim.cy), sim.cylinder_r,
                     fc="black", ec="white", lw=0.5)
        self.ax1.add_patch(cyl)

        # 速度矢量采样
        sx = max(1, sim.nx // 35)
        sy = max(1, sim.ny // 12)
        self.gx = np.arange(0, sim.nx, sx)
        self.gy = np.arange(0, sim.ny, sy)
        self.gX, self.gY = np.meshgrid(self.gx, self.gy, indexing="ij")

        self.vort_img = None

        # 右: Cd/Cl
        self.ax2 = self.fig.add_subplot(1, 2, 2)
        self.ax2.set_xlabel("Time step")
        self.ax2.set_ylabel("Coefficient")
        self.ax2.grid(True, alpha=0.3)

        plt.tight_layout()

    def init_frame(self):
        return []

    def update_frame(self, _frame):
        sim = self.sim

        # 推进计算
        for _ in range(self.spf):
            sim.step()

        # ── 涡量场 ──
        self.ax1.clear()
        self.ax1.set_xlim(0, sim.nx)
        self.ax1.set_ylim(0, sim.ny)
        self.ax1.set_aspect("equal")
        self.ax1.set_xlabel("x")
        self.ax1.set_ylabel("y")

        cyl = Circle((sim.cx, sim.cy), sim.cylinder_r,
                     fc="black", ec="white", lw=0.5, zorder=5)
        self.ax1.add_patch(cyl)

        vort = sim.compute_vorticity()
        vmax = max(float(np.abs(vort).max()), 1e-8)
        norm = TwoSlopeNorm(vcenter=0, vmin=-vmax, vmax=vmax)
        self.ax1.imshow(vort.T, origin="lower",
                        extent=[0, sim.nx, 0, sim.ny],
                        cmap="RdBu_r", norm=norm, aspect="equal")

        # 速度矢量
        u, v = sim.get_velocity_field()
        us = u[self.gX, self.gY]
        vs = v[self.gX, self.gY]
        mag = np.sqrt(us**2 + vs**2)
        mx = max(float(mag.max()), 1e-8)
        self.ax1.quiver(self.gX, self.gY, us, vs, mag,
                        cmap="Greys", clim=[0, mx],
                        scale=mx * 4 + 1e-8, width=0.002, alpha=0.5)

        cd, cl = sim.hist_cd[-1], sim.hist_cl[-1]
        self.ax1.set_title(
            f"Vorticity  |  Re={sim.Re:.0f}  |  step={sim.step_count}\n"
            f"Cd={cd:.3f}  Cl={cl:.3f}",
            fontsize=10)
        self.ax1.grid(alpha=0.15)

        # ── Cd / Cl ──
        self.ax2.clear()
        self.ax2.set_xlabel("Time step")
        self.ax2.set_ylabel("Coefficient")
        self.ax2.grid(True, alpha=0.3)

        steps = sim.hist_step
        self.ax2.plot(steps, sim.hist_cd, "b-", lw=0.7, alpha=0.8,
                      label="Cd (drag)")
        self.ax2.plot(steps, sim.hist_cl, "r-", lw=0.7, alpha=0.8,
                      label="Cl (lift)")
        self.ax2.legend(loc="upper right", fontsize=8)

        # 稳态统计
        if len(steps) > 500:
            half = len(sim.hist_cd) // 2
            cd_mean = np.mean(sim.hist_cd[half:])
            cl_rms = np.std(sim.hist_cl[half:])
            self.ax2.text(0.02, 0.95,
                          f"Cd_mean={cd_mean:.3f}  Cl_rms={cl_rms:.3f}",
                          transform=self.ax2.transAxes, fontsize=8,
                          verticalalignment="top",
                          bbox=dict(boxstyle="round", fc="wheat", alpha=0.5))

        self.fig.canvas.draw_idle()
        return []

    def run(self, n_steps: int):
        frames = max(1, n_steps // self.spf)
        ani = animation.FuncAnimation(
            self.fig, self.update_frame, frames=frames,
            init_func=self.init_frame, interval=40, blit=False, repeat=False)
        plt.show()
        return ani

    def save(self, filename: str, n_steps: int):
        frames = max(1, n_steps // self.spf)
        ani = animation.FuncAnimation(
            self.fig, self.update_frame, frames=frames,
            init_func=self.init_frame, interval=40, blit=False, repeat=False)
        try:
            import subprocess
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            print(f"  Saving -> {filename} (mp4, {frames} frames) ...")
            ani.save(filename, writer="ffmpeg", fps=20, dpi=120)
        except Exception:
            if filename.endswith(".mp4"):
                filename = filename.replace(".mp4", ".gif")
            print(f"  Saving -> {filename} (gif, {frames} frames) ...")
            ani.save(filename, writer="pillow", fps=15, dpi=100)
        print("  Done.")


# ============================================================================
# CLI
# ============================================================================

RES = {0: (400, 120), 1: (600, 180), 2: (800, 240)}

def main():
    p = argparse.ArgumentParser(
        description="Cylinder Flow — LBM D2Q9",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cylinder_flow.py                        # Re=100 animation
  python cylinder_flow.py --Re 150 --res 1       # higher Re
  python cylinder_flow.py --Re 60 --save out.mp4 # save animation
  python cylinder_flow.py --no-anim --steps 8000 # compute only
        """)
    p.add_argument("--Re", type=float, default=100.0)
    p.add_argument("--res", type=int, default=0, choices=[0,1,2])
    p.add_argument("--steps", type=int, default=10000)
    p.add_argument("--u-inlet", type=float, default=0.08)
    p.add_argument("--cylinder-d", type=int, default=24)
    p.add_argument("--no-anim", action="store_true")
    p.add_argument("--save", type=str, nargs="?", const="cylinder_flow")
    p.add_argument("--spf", type=int, default=20, help="steps per frame")

    args = p.parse_args()
    nx, ny = RES[args.res]

    print("=" * 55)
    print("  Cylinder Flow — LBM D2Q9")
    print("=" * 55)
    print(f"  Grid:     {nx} x {ny}")
    print(f"  Re:       {args.Re}")
    print(f"  D:        {args.cylinder_d}")
    print(f"  U_inlet:  {args.u_inlet}  (Ma={args.u_inlet/np.sqrt(1/3):.4f})")
    print(f"  Steps:    {args.steps}")

    sim = CylinderFlowLBM(
        nx=nx, ny=ny, Re=args.Re,
        cylinder_d=args.cylinder_d, u_inlet=args.u_inlet)
    sim.init()
    print(f"  tau={sim.tau:.4f}  nu={sim.nu:.6f}")

    t0 = time.perf_counter()

    if args.no_anim:
        for s in range(1, args.steps + 1):
            cd, cl = sim.step()
            if s % 500 == 0 or s == 1:
                el = time.perf_counter() - t0
                print(f"  step {s:6d}  Cd={cd:+7.4f}  Cl={cl:+7.4f}  ({el:.0f}s)")
        el = time.perf_counter() - t0
        print(f"\n  Done. {el:.0f}s, {sim.step_count/el:.0f} steps/s")
        half = len(sim.hist_cd) // 2
        if half > 0:
            print(f"  Cd_mean={np.mean(sim.hist_cd[half:]):.4f}, "
                  f"Cl_rms={np.std(sim.hist_cl[half:]):.4f}")
    else:
        viz = FlowVisualizer(sim, steps_per_frame=args.spf)
        if args.save:
            viz.save(f"{args.save}.mp4", n_steps=args.steps)
        else:
            viz.run(n_steps=args.steps)


if __name__ == "__main__":
    main()
