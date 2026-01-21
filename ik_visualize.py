import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider

# ---- パラメータ ----
L1 = 0.5
L2 = 0.5

# ---- 逆運動学 ----
def inverse_kinematics(x, y):
    r2 = x*x + y*y
    c2 = (r2 - L1*L1 - L2*L2) / (2*L1*L2)

    if c2 < -1.0 or c2 > 1.0:
        return None

    theta2 = np.arccos(c2)
    s2 = np.sin(theta2)
    theta1 = np.arctan2(y, x) - np.arctan2(L2*s2, L1 + L2*c2)

    return theta1, theta2

# ---- 描画初期化 ----
fig, ax = plt.subplots()
plt.subplots_adjust(bottom=0.25)

ax.set_aspect('equal')
ax.set_xlim(-1, 1)
ax.set_ylim(-1, 1)
ax.grid(True)

arm_line, = ax.plot([], [], 'o-', lw=4)

# ---- スライダー ----
ax_x = plt.axes([0.2, 0.1, 0.6, 0.03])
ax_y = plt.axes([0.2, 0.05, 0.6, 0.03])

slider_x = Slider(ax_x, 'X', -1, 1, valinit=1)
slider_y = Slider(ax_y, 'Y', -1, 1, valinit=0)

# ---- 更新関数 ----
def update(val):
    x = slider_x.val
    y = slider_y.val

    ik = inverse_kinematics(x, y)
    if ik is None:
        return

    th1, th2 = ik

    x1 = L1 * np.cos(th1)
    y1 = L1 * np.sin(th1)

    x2 = x1 + L2 * np.cos(th1 + th2)
    y2 = y1 + L2 * np.sin(th1 + th2)

    arm_line.set_data([0, x1, x2], [0, y1, y2])
    fig.canvas.draw_idle()

slider_x.on_changed(update)
slider_y.on_changed(update)

# ---- 初期描画 ----
update(None)
plt.show()
