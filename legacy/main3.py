import serial,math,time,threading
import matplotlib.pyplot as plt
import matplotlib
import keyboard
matplotlib.use("TkAgg")

# ---- パラメータ ----
L1=L2=0.5
L_SCALE=5
LL_SCALE=1.05
PORT_XY="COM5" # 左右方向
PORT_Z ="COM10" # 上下＋グリッパー

# ---- グローバル状態 ----
prev_t1, prev_t2 = None, None
is_gripping = False
sent_prev_x = None
sent_prev_y = None
sent_prev_z = None
sent_prev_t1 = None
sent_prev_t2 = None

# ---- スレッド制御用フラグ ----
motion_in_progress = False
motion_stop_event = threading.Event()

# ---- ユーティリティ関数 ----
def non_blocking_sleep(duration):
    """ウィンドウをフリーズさせない待機"""
    end_time = time.time() + duration
    while time.time() < end_time:
        plt.gcf().canvas.draw_idle()
        plt.gcf().canvas.flush_events()
        plt.pause(0.01)
        if motion_stop_event.is_set():
            break

def ik_both(x,y):
    r2=x*x+y*y
    r=math.sqrt(r2)
    if r > L1+L2 or r < abs(L1-L2):
        raise ValueError("unreachable")

    c2=(r2-L1*L1-L2*L2)/(2*L1*L2)
    c2=max(-1,min(1,c2))
    s=math.sqrt(1-c2*c2)

    t2a=math.atan2( s,c2)
    t2b=math.atan2(-s,c2)

    def solve(t2):
        k1=L1+L2*c2
        k2=L2*math.sin(t2)
        t1=math.atan2(y,x)-math.atan2(k2,k1)
        return t1,t2

    return solve(t2a),solve(t2b)

def ik(x,y):
    global prev_t1,prev_t2
    (a1,a2),(b1,b2)=ik_both(x,y)
    if prev_t1 is None:
        prev_t1,prev_t2=a1,a2
        return a1,a2
    if y<=0:
        prev_t1,prev_t2=a1,a2
        return a1,a2
    else:
        prev_t1,prev_t2=b1,b2
        return b1,b2

# ---- FK ----
def fk(t1,t2):
    x1=L1*math.cos(t1)
    y1=L1*math.sin(t1)
    x2=x1+L2*math.cos(t1+t2)
    y2=y1+L2*math.sin(t1+t2)
    return (0,0),(x1,y1),(x2,y2)

# ---- 描画 ----
plt.ion()
fig,ax=plt.subplots()
ax.set_aspect('equal')
ax.set_xlim(-1.2,1.2)
ax.set_ylim(-1.2,1.2)
arm_line,=ax.plot([],[],'o-',lw=2)
target_dot,=ax.plot([],[],'rx')
z_arrow = ax.arrow(0,0,0,0, head_width=0.05, color="blue")

def draw_arm(t1,t2,x,y,theta_z):
    global z_arrow
    p0,p1,p2=fk(t1,t2)

    arm_line.set_data([p0[1],p1[1],p2[1]],
                      [p0[0],p1[0],p2[0]])
    target_dot.set_data([y],[x])

    # Z 回転矢印（0° = 上）
    z_arrow.remove()
    dx = 0.3*math.sin(theta_z)
    dy = 0.3*math.cos(theta_z)
    z_arrow = ax.arrow(0,0,dx,dy, head_width=0.05, color="blue")

    plt.gcf().canvas.draw_idle()
    plt.gcf().canvas.flush_events()
    plt.pause(0.001)

# ---- Serial 接続 ----
try:
    ser_xy=serial.Serial(PORT_XY,115200,timeout=1)
    time.sleep(2)
    def set_t1(v): ser_xy.write(f"X,{v:.3f}\n".encode())
    def set_t2(v): ser_xy.write(f"Y,{v:.3f}\n".encode())
except:
    def set_t1(v): pass
    def set_t2(v): pass

try:
    ser_z =serial.Serial(PORT_Z,115200,timeout=1)
    time.sleep(2)
    def send_z(z): ser_z.write(f"Z,{z:.3f},0\n".encode())
    def close_grip(): ser_z.write(b"G\n")
    def open_grip():  ser_z.write(b"R\n")
    def get_distance(timeout=0.2):
        ser_z.reset_input_buffer()
        ser_z.write(b"U\n")

        latest_ur = None
        t0 = time.time()

        while time.time() - t0 < timeout:
            if ser_z.in_waiting:
                line = ser_z.readline().decode('utf-8', errors='ignore').strip()
                print(line)

                parts = line.split(",")
                if len(parts) >= 2 and parts[0] == "UR":
                    try:
                        latest_ur = float(parts[1])
                    except ValueError:
                        pass

        return latest_ur
except:
    def send_z(z): pass
    def close_grip(): pass
    def open_grip(): pass
    def get_distance(): return -1

# ---- 角度指定で UI 表示・信号送信する関数 ----
def set_pose(t1, t2, z, draw=True, send_xy=True, send_z_signal=True, is_z_xy=True, wait_xy=1.5, wait_z=2.0):
    """
    角度指定でアーム姿勢を設定
    
    Args:
        t1, t2: 関節角度（ラジアン）
        z: Z軸回転角度
        draw: UIに描画するか
        send_xy: XY関節信号を送信するか
        send_z_signal: Z軸信号を送信するか
        is_z_xy: True=Z先行、False=XY先行
        wait_xy: XY関節送信後の待機時間(秒)
        wait_z: Z軸送信後の待機時間(秒)
    """
    global sent_prev_t1, sent_prev_t2, sent_prev_z, sent_prev_x, sent_prev_y
    
    # IKから対応する座標を計算（描画用）
    _, (x1, y1), (x2, y2) = fk(t1, t2)
    
    if draw:
        draw_arm(t1, t2, x2, y2, z)
    
    if is_z_xy:
        # Z先行
        if send_z_signal:
            if sent_prev_z != z:
                send_z(z * LL_SCALE)
                non_blocking_sleep(wait_z)
        if send_xy:
            if sent_prev_t1 != t1:
                set_t1((t1 - t1_initial) * L_SCALE)
                non_blocking_sleep(wait_xy)
            if sent_prev_t2 != t2:
                set_t2((t2 - t2_initial) * L_SCALE)
                non_blocking_sleep(wait_xy)
    else:
        # XY先行
        if send_xy:
            if sent_prev_t1 != t1:
                set_t1((t1 - t1_initial) * L_SCALE)
                non_blocking_sleep(wait_xy)
            if sent_prev_t2 != t2:
                set_t2((t2 - t2_initial) * L_SCALE)
                non_blocking_sleep(wait_xy)
        if send_z_signal:
            if sent_prev_z != z:
                send_z(z * LL_SCALE)
                non_blocking_sleep(wait_z)
    
    sent_prev_t1, sent_prev_t2, sent_prev_z = t1, t2, z

# ---- 座標指定で移動・グリップする関数 ----
def move_to(x, y, z, should_grip, draw=True, wait_xy=1.5, wait_z=2.0):
    """
    座標指定でアームを移動・グリップ
    動作順序（is_z_xy）は現在のzの値から自動判定
    
    Args:
        x, y: 目標座標
        z: Z軸回転角度
        should_grip: True=グリップ、False=リリース
        draw: UIに描画するか
        wait_xy: XY関節送信後の待機時間(秒)
        wait_z: Z軸送信後の待機時間(秒)
    """
    global is_gripping, sent_prev_z, sent_prev_x, sent_prev_y
    
    try:
        t1, t2 = ik(x, y)
    except ValueError:
        print(f"到達不可能な座標: ({x}, {y})")
        return
    
    get_distance()
    
    # 現在のzが0かどうかで動作順序を判定
    # z=0 なら Z先行、z!=0 なら XY先行
    is_z_xy = (sent_prev_z == 0)
    
    set_pose(t1, t2, z, draw=draw, send_xy=True, send_z_signal=True,
             is_z_xy=is_z_xy, wait_xy=wait_xy, wait_z=wait_z)
    
    if should_grip:
        if not is_gripping:
            close_grip()   
            is_gripping = True
            non_blocking_sleep(1.2)
    else:
        if is_gripping:
            open_grip()
            is_gripping = False
            non_blocking_sleep(1.2)
    
    sent_prev_x, sent_prev_y = x, y
    non_blocking_sleep(0.1)

# ---- 角度指定で移動・グリップする関数 ----
def move_to_angle(t1, t2, z, should_grip, draw=True, wait_xy=1.5, wait_z=2.0):
    """
    角度指定でアームを移動・グリップ
    動作順序（is_z_xy）は現在のzの値から自動判定
    
    Args:
        t1, t2: 目標関節角度（degree）
        z: Z軸回転角度
        should_grip: True=グリップ、False=リリース
        draw: UIに描画するか
        wait_xy: XY関節送信後の待機時間(秒)
        wait_z: Z軸送信後の待機時間(秒)
    """
    t1 = math.radians(t1)
    t2 = math.radians(t2)
    global is_gripping, sent_prev_z, sent_prev_x, sent_prev_y
    
    get_distance()
    
    # 現在のzが0かどうかで動作順序を判定
    is_z_xy = (sent_prev_z == 0)
    
    set_pose(t1, t2, z, draw=draw, send_xy=True, send_z_signal=True,
             is_z_xy=is_z_xy, wait_xy=wait_xy, wait_z=wait_z)
    
    if should_grip:
        if not is_gripping:
            close_grip()   
            is_gripping = True
            non_blocking_sleep(1.2)
    else:
        if is_gripping:
            open_grip()
            is_gripping = False
            non_blocking_sleep(1.2)
    
    # 座標はFKで計算
    _, (x1, y1), (x2, y2) = fk(t1, t2)
    sent_prev_x, sent_prev_y = x2, y2
    non_blocking_sleep(0.1)

# ---- 非同期キーボード監視 ----
def key_loop():
    while True:
        if keyboard.is_pressed("g"):
            close_grip()
            time.sleep(0.3)
        if keyboard.is_pressed("r"):
            open_grip()
            time.sleep(0.3)
        if keyboard.is_pressed("q"):
            break
        time.sleep(0.05)

threading.Thread(target=key_loop,daemon=True).start()

# ---- プリセット位置定義 ----
POSITIONS = {
    'home': (-90, 90, 0),
    'pos_1': (-70, 70, 0),
    'pos_2': (-30, 30, 0),
    'pos_3': (0, 0, 0),
    'pos_4': (30, -30, 0),
    'pos_5': (70, -70, 0),
}

POSITIONS_GRAB = {
    'home': (-90, 90, -8.7),
    'pos_1': (-70, 70, -8.7),
    'pos_2': (-30, 30, -8.7),
    'pos_3': (0, 0, -8.7),
    'pos_4': (30, -30, -8.7),
    'pos_5': (70, -70, -8.7),
}

# ---- メイン実行関数 ----
def main_pick_and_place():
    """ピック&プレイス動作のメイン処理"""
    # ホームポジション
    move_to_angle(*POSITIONS['home'], should_grip=False)
    
    # シーン 1: 3番位置をつかむ
    move_to_angle(*POSITIONS['pos_3'], should_grip=False)
    move_to_angle(*POSITIONS_GRAB['pos_3'], should_grip=True)
    move_to_angle(*POSITIONS['pos_3'], should_grip=True)
    
    # 5番位置で離す
    move_to_angle(*POSITIONS['pos_5'], should_grip=True)
    move_to_angle(*POSITIONS_GRAB['pos_5'], should_grip=False)
    move_to_angle(*POSITIONS['pos_5'], should_grip=False)
    
    # シーン 2: 2番位置をつかむ
    move_to_angle(*POSITIONS['pos_2'], should_grip=False)
    move_to_angle(*POSITIONS_GRAB['pos_2'], should_grip=True)
    move_to_angle(*POSITIONS['pos_2'], should_grip=True)
    
    # 4番位置で離す
    move_to_angle(*POSITIONS['pos_4'], should_grip=True)
    move_to_angle(*POSITIONS_GRAB['pos_4'], should_grip=False)
    move_to_angle(*POSITIONS['pos_4'], should_grip=False)
    
    # シーン 3: 1番位置をつかむ
    move_to_angle(*POSITIONS['pos_1'], should_grip=False)
    move_to_angle(*POSITIONS_GRAB['pos_1'], should_grip=True)
    move_to_angle(*POSITIONS['pos_1'], should_grip=True)
    
    # 3番位置で離す
    move_to_angle(*POSITIONS['pos_3'], should_grip=True)
    move_to_angle(*POSITIONS_GRAB['pos_3'], should_grip=False)
    move_to_angle(*POSITIONS['pos_3'], should_grip=False)
    
    # ホームに戻す
    move_to_angle(*POSITIONS['home'], should_grip=False)
    
    print("Pick & Place 完了")

threading.Thread(target=key_loop,daemon=True).start()

# ---- 初期姿勢 ----
z = 0.0  # 0度 = 上向き
x0,y0=0.5,-0.5 # xは前方向、yは横方向
t1_initial,t2_initial=ik(x0,y0)
sent_prev_t1,sent_prev_t2=t1_initial,t2_initial
sent_prev_z=z
sent_prev_x,sent_prev_y=x0,y0
draw_arm(t1_initial,t2_initial,x0,y0,z)
non_blocking_sleep(1.0)

# ---- メイン処理 ----
if __name__ == "__main__":
    try:
        main_pick_and_place()
    except KeyboardInterrupt:
        print("中断しました")
    finally:
        motion_stop_event.set()
        plt.ioff()
        plt.show()
