import serial, math, time, threading
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("TkAgg")


class RobotArm:
    """2軸ロボットアームの制御クラス"""
    
    # ---- クラス定数 ----
    L1 = L2 = 0.5
    L1_SCALE = 5.1
    L2_SCALE = L1_SCALE*(4.75/5)
    LL_SCALE = 1.05
    
    # ---- プリセット位置 ----
    POSITIONS = {
        'home': (-90, 90, 0),
        'pos_1': (-70, 70, 0),
        'pos_2': (-35, 35, 0),
        'pos_3': (0, 0, 0),
        'pos_4': (35, -35, 0),
        'pos_5': (70, -70, 0),
        'feeder': (-90, 0, 0),
    }
    
    POSITIONS_GRAB = {
        'home': (-90, 90, -8.7),
        'pos_1': (-70, 70, -8.7),
        'pos_2': (-35, 35, -8.7),
        'pos_3': (0, 0, -8.7),
        'pos_4': (35, -35, -8.7),
        'pos_5': (70, -70, -8.7),
        'feeder': (-90, 0, -8.7),
    }
    
    def __init__(self, port_xy="COM5", port_z="COM10"):
        """
        ロボットアームの初期化
        
        Args:
            port_xy: XY関節のシリアルポート
            port_z: Z軸・グリッパのシリアルポート
        """
        # ---- 状態管理 ----
        self.prev_t1 = None
        self.prev_t2 = None
        self.is_gripping = False
        self.sent_prev_x = None
        self.sent_prev_y = None
        self.sent_prev_z = None
        self.sent_prev_t1 = None
        self.sent_prev_t2 = None
        
        # ---- スレッド制御 ----
        self.motion_stop_event = threading.Event()
        
        # ---- Serial接続 ----
        self.ser_xy = None
        self.ser_z = None
        self._init_serial(port_xy, port_z)
        
        # ---- 描画 ----
        self.fig = None
        self.ax = None
        self.arm_line = None
        self.target_dot = None
        self.z_arrow = None
        self.t1_initial = None
        self.t2_initial = None
        self._init_plot()
    
    def _init_serial(self, port_xy, port_z):
        """Serial接続の初期化"""
        try:
            self.ser_xy = serial.Serial(port_xy, 115200, timeout=1)
            time.sleep(2)
            print(f"XY関節接続: {port_xy}")
        except Exception as e:
            print(f"XY関節接続失敗: {e}")
            self.ser_xy = None
        
        try:
            self.ser_z = serial.Serial(port_z, 115200, timeout=1)
            time.sleep(2)
            print(f"Z軸・グリッパ接続: {port_z}")
        except Exception as e:
            print(f"Z軸・グリッパ接続失敗: {e}")
            self.ser_z = None
    
    def _init_plot(self):
        """matplotlib描画の初期化"""
        plt.ion()
        self.fig, self.ax = plt.subplots()
        self.status_text = self.ax.text(
            0.02, 0.98, f"G:{self.is_gripping}",
            transform=self.ax.transAxes,
            ha='left', va='top', fontsize=14
        )

        self.ax.set_aspect('equal')
        self.ax.set_xlim(-1.2, 1.2)
        self.ax.set_ylim(-1.2, 1.2)
        self.arm_line, = self.ax.plot([], [], 'o-', lw=2)
        self.target_dot, = self.ax.plot([], [], 'rx')
        self.z_arrow = self.ax.arrow(0, 0, 0, 0, head_width=0.05, color="blue")
        
    # ---- 描画 ----
    def draw_arm(self, t1, t2, x, y, theta_z):
        p0, p1, p2 = self.fk(t1, t2)

        self.arm_line.set_data([p0[1], p1[1], p2[1]],
                            [p0[0], p1[0], p2[0]])
        self.target_dot.set_data([y], [x])

        self.z_arrow.remove()
        dx = 0.3 * math.sin(theta_z)
        dy = 0.3 * math.cos(theta_z)
        self.z_arrow = self.ax.arrow(0, 0, dx, dy, head_width=0.05, color="blue")

        self.status_text.set_text(f"G:{self.is_gripping}")


        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()
        plt.pause(0.001)
    
    # ---- 逆運動学 ----
    def ik_both(self, x, y):
        """両解を求める"""
        r2 = x*x + y*y
        r = math.sqrt(r2)
        if r > self.L1 + self.L2 or r < abs(self.L1 - self.L2):
            raise ValueError("unreachable")
        
        c2 = (r2 - self.L1*self.L1 - self.L2*self.L2) / (2*self.L1*self.L2)
        c2 = max(-1, min(1, c2))
        s = math.sqrt(1 - c2*c2)
        
        t2a = math.atan2(s, c2)
        t2b = math.atan2(-s, c2)
        
        def solve(t2):
            k1 = self.L1 + self.L2*c2
            k2 = self.L2*math.sin(t2)
            t1 = math.atan2(y, x) - math.atan2(k2, k1)
            return t1, t2
        
        return solve(t2a), solve(t2b)
    
    def ik(self, x, y):
        """連続性を考慮した逆運動学"""
        (a1, a2), (b1, b2) = self.ik_both(x, y)
        if self.prev_t1 is None:
            self.prev_t1, self.prev_t2 = a1, a2
            return a1, a2
        if y <= 0:
            self.prev_t1, self.prev_t2 = a1, a2
            return a1, a2
        else:
            self.prev_t1, self.prev_t2 = b1, b2
            return b1, b2
    
    # ---- 順運動学 ----
    def fk(self, t1, t2):
        """順運動学"""
        x1 = self.L1 * math.cos(t1)
        y1 = self.L1 * math.sin(t1)
        x2 = x1 + self.L2 * math.cos(t1 + t2)
        y2 = y1 + self.L2 * math.sin(t1 + t2)
        return (0, 0), (x1, y1), (x2, y2)
    
    # ---- Serial通信 ----
    def set_t1(self, v):
        """第1関節をセット"""
        if self.ser_xy:
            self.ser_xy.write(f"X,{v:.3f}\n".encode())
    
    def set_t2(self, v):
        """第2関節をセット"""
        if self.ser_xy:
            self.ser_xy.write(f"Y,{v:.3f}\n".encode())
    
    def send_z(self, z):
        """Z軸をセット"""
        if self.ser_z:
            self.ser_z.write(f"Z,{z:.3f},0\n".encode())
    
    def set_t1_speed(self, speed):
        if self.ser_xy:
            self.ser_xy.write(f"S1,{speed}\n".encode())
            
    def set_t2_speed(self, speed):
        if self.ser_xy:
            self.ser_xy.write(f"S2,{speed}\n".encode())

    def set_z_speed(self, speed):
        if self.ser_z:
            self.ser_z.write(f"Sz,{speed}\n".encode())
            
    
    def close_grip(self):
        """グリップを閉じる"""
        if self.ser_z:
            self.ser_z.write(b"G\n")
    
    def open_grip(self):
        """グリップを開く"""
        if self.ser_z:
            self.ser_z.write(b"R\n")
    
    def get_distance(self, timeout=0.2):
        """距離センサ値を取得"""
        if not self.ser_z:
            return -1
        
        self.ser_z.reset_input_buffer()
        self.ser_z.write(b"U\n")
        
        latest_ur = None
        t0 = time.time()
        
        while time.time() - t0 < timeout:
            if self.ser_z.in_waiting:
                line = self.ser_z.readline().decode('utf-8', errors='ignore').strip()
                print(line)
                
                parts = line.split(",")
                if len(parts) >= 2 and parts[0] == "UR":
                    try:
                        latest_ur = float(parts[1])
                    except ValueError:
                        pass
        
        return latest_ur

    # ---- ユーティリティ ----
    def non_blocking_sleep(self, duration):
        """ウィンドウをフリーズさせない待機"""
        end_time = time.time() + duration
        while time.time() < end_time:
            plt.gcf().canvas.draw_idle()
            plt.gcf().canvas.flush_events()
            plt.pause(0.01)
            if self.motion_stop_event.is_set():
                break
    
    # ---- 制御メソッド ----
    def set_pose(self, t1, t2, z, draw=True, send_xy=True, send_z_signal=True, 
                 is_z_xy=True, wait_xy=2.5, wait_z=2.0):
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
        _, (x1, y1), (x2, y2) = self.fk(t1, t2)
        
        if draw:
            self.draw_arm(t1, t2, x2, y2, z)
        
        if is_z_xy:
            # Z先行
            if send_z_signal:
                if self.sent_prev_z != z:
                    self.send_z(z * self.LL_SCALE)
                    time.sleep(wait_z)
            if send_xy:
                if self.sent_prev_t1 != t1:
                    self.set_t1((t1 - self.t1_initial) * self.L1_SCALE)
                    time.sleep(wait_xy)
                if self.sent_prev_t2 != t2:
                    self.set_t2((t2 - self.t2_initial) * self.L2_SCALE)
                    time.sleep(wait_xy)
        else:
            # XY先行
            if send_xy:
                if self.sent_prev_t1 != t1:
                    self.set_t1((t1 - self.t1_initial) * self.L1_SCALE)
                    time.sleep(wait_xy)
                if self.sent_prev_t2 != t2:
                    self.set_t2((t2 - self.t2_initial) * self.L2_SCALE)
                    time.sleep(wait_xy)
            if send_z_signal:
                if self.sent_prev_z != z:
                    self.send_z(z * self.LL_SCALE)
                    time.sleep(wait_z)
        
        self.sent_prev_t1, self.sent_prev_t2, self.sent_prev_z = t1, t2, z
    
    def move_to(self, x, y, z, should_grip, draw=True, wait_xy=2.5, wait_z=2.0):
        """
        座標指定でアームを移動・グリップ
        
        Args:
            x, y: 目標座標
            z: Z軸回転角度
            should_grip: True=グリップ、False=リリース
            draw: UIに描画するか
            wait_xy: XY関節送信後の待機時間(秒)
            wait_z: Z軸送信後の待機時間(秒)
        """
        try:
            t1, t2 = self.ik(x, y)
        except ValueError:
            print(f"到達不可能な座標: ({x}, {y})")
            return

        wait_xy = wait_xy+2.0*(max(abs(t1 - self.sent_prev_t1), abs(t2 - self.sent_prev_t2))/math.pi-0.5)
        self.get_distance()
        
        is_z_xy = (self.sent_prev_z == 0)
        
        self.set_pose(t1, t2, z, draw=draw, send_xy=True, send_z_signal=True,
                     is_z_xy=is_z_xy, wait_xy=wait_xy, wait_z=wait_z)
        
        if should_grip:
            self.close_grip()
            self.is_gripping = True
        else:
            self.open_grip()
            self.is_gripping = False
        
        self.sent_prev_x, self.sent_prev_y = x, y
        time.sleep(1.0)
    
    def move_to_angle(self, t1_deg, t2_deg, z, should_grip, draw=True, wait_xy=2.0, wait_z=2.0):
        """
        角度指定でアームを移動・グリップ
        
        Args:
            t1_deg, t2_deg: 目標関節角度（degree）
            z: Z軸回転角度
            should_grip: True=グリップ、False=リリース
            draw: UIに描画するか
            wait_xy: XY関節送信後の待機時間(秒)
            wait_z: Z軸送信後の待機時間(秒)
        """
        t1 = math.radians(t1_deg)
        t2 = math.radians(t2_deg)

        wait_xy = wait_xy+2.0*(max(abs(t1 - self.sent_prev_t1), abs(t2 - self.sent_prev_t2))/math.pi-0.5)
        
        self.get_distance()
        
        is_z_xy = (self.sent_prev_z == 0)
        
        self.set_pose(t1, t2, z, draw=draw, send_xy=True, send_z_signal=True,
                     is_z_xy=is_z_xy, wait_xy=wait_xy, wait_z=wait_z)
        
        if should_grip:
            self.close_grip()
            self.is_gripping = True
        else:
            self.open_grip()
            self.is_gripping = False
        
        _, (x1, y1), (x2, y2) = self.fk(t1, t2)
        self.sent_prev_x, self.sent_prev_y = x2, y2
        time.sleep(1.0)
    
    # ---- 初期化 ----
    def initialize(self, x0=0.5, y0=-0.5, z0=0.0):
        """初期姿勢を設定"""
        self.t1_initial, self.t2_initial = self.ik(x0, y0)
        self.sent_prev_t1, self.sent_prev_t2 = self.t1_initial, self.t2_initial
        self.sent_prev_z = z0
        self.sent_prev_x, self.sent_prev_y = x0, y0
        
        self.draw_arm(self.t1_initial, self.t2_initial, x0, y0, z0)
        time.sleep(1.0)
    
    # ---- タスク実行 ----
    def grab_at(self, pos_key):
        """
        指定位置からオブジェクトをつかむ
        
        Args:
            pos_key: 位置キー (e.g., 'pos_1', 'feeder')
        """
        # pos_key = f'pos_{position_num}'
        
        # 上から下へ移動してつかむ
        self.move_to_angle(*self.POSITIONS[pos_key], should_grip=False)
        self.move_to_angle(*self.POSITIONS_GRAB[pos_key], should_grip=True)
        self.move_to_angle(*self.POSITIONS[pos_key], should_grip=True)
    
    def place_at(self, pos_key):
        """
        指定位置にオブジェクトを置く（離す）
        
        Args:
            pos_key: 位置キー (e.g., 'pos_1', 'feeder')
        """
        # pos_key = f'pos_{position_num}'
        
        # 上から下へ移動して離す
        self.move_to_angle(*self.POSITIONS[pos_key], should_grip=True)
        self.move_to_angle(*self.POSITIONS_GRAB[pos_key], should_grip=False)
        self.move_to_angle(*self.POSITIONS[pos_key], should_grip=False)
    
    
    
    def close(self):
        """リソース解放"""
        self.motion_stop_event.set()
        if self.ser_xy:
            self.ser_xy.close()
        if self.ser_z:
            self.ser_z.close()
        plt.ioff()
        plt.show()
