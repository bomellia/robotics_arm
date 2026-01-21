import serial,math,time,threading
import matplotlib.pyplot as plt
import matplotlib
import keyboard
matplotlib.use("TkAgg")

# ---- パラメータ ----
L1=L2=0.5
L_SCALE=5
LL_SCALE=1.05
PORT_XY="COM5"
PORT_Z ="COM10"

# ---- IK（両解＋連続選択） ----
prev_t1, prev_t2 = None, None

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
    da=abs(a1-prev_t1)+abs(a2-prev_t2)
    db=abs(b1-prev_t1)+abs(b2-prev_t2)
    if y<=0:
        prev_t1,prev_t2=a1,a2
        return a1,a2
    else:
        prev_t1,prev_t2=b1,b2
        return b1,b2
    # if da<db:
    #     prev_t1,prev_t2=a1,a2
    #     return a1,a2
    # else:
    #     prev_t1,prev_t2=b1,b2
    #     return b1,b2

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
    def get_distance(): 
        ser_z.write(b"U\n")
        line = ser_z.readline().decode('utf-8', errors='ignore').strip()
        print(line)
        return line
except:
    def send_z(z): pass
    def close_grip(): pass
    def open_grip(): pass
    def get_distance(): return -1

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

# ---- 初期姿勢 ----
z = 0.0  # 0度 = 上向き
x0,y0=0.5,-0.5 # xは前方向、yは横方向
t1_initial,t2_initial=ik(x0,y0)
sent_prev_t1,sent_prev_t2=t1_initial,t2_initial
sent_prev_z=z
draw_arm(t1_initial,t2_initial,x0,y0,z)
time.sleep(1)

#0.5,0.3
#0.4,0.7
# (0.5+0.5*math.cos(math.radians(-35)),0.5*math.sin(math.radians(-35))
# ---- パス ----
# path=[(0.5,-0.5,0,False,False),(1.0,0.0,-8.7,True,False),(0.5,-0.5,0,True,True),(0.5,-0.5,-8.7,False,False),(0.5,-0.5,0,False,False)]
path=[(0.5,-0.5,0,False,False),
    #   (0.7,-0.6,0,True,True),
      (1.0,0.0,-8.7,True,False),#3番をつかむ

      (0.5+0.5*math.sin(math.radians(20)),0.5*math.cos(math.radians(20)),0,True,True),
      (0.5+0.5*math.sin(math.radians(20)),0.5*math.cos(math.radians(20)),-8.7,False,False),#5番で離す

      (0.5+0.5*math.sin(math.radians(60)),-0.5*math.cos(math.radians(60)),0,False,True),
      (0.5+0.5*math.sin(math.radians(60)),-0.5*math.cos(math.radians(60)),-8.7,True,False),#2番をつかむ

      (0.5+0.5*math.sin(math.radians(60)),0.5*math.cos(math.radians(60)),0,True,True),
      (0.5+0.5*math.sin(math.radians(60)),0.5*math.cos(math.radians(60)),-8.7,False,False),#4番で離す

      (0.5+0.5*math.sin(math.radians(20)),-0.5*math.cos(math.radians(20)),0,False,True),
      (0.5+0.5*math.sin(math.radians(20)),-0.5*math.cos(math.radians(20)),-8.7,True,False),#1番をつかむ

      (0.5,-0.5,0,False,True)]
# path=[(0.5,-0.5,0,False,False),
#       (1.0,0.0,-8.7,True,False),
#       (0.5,-0.5,0,False,True)]
# path=[(0.5,-0.5,-8.7,True,True),(1.0,0.0,-8.7,True,False),(0.5,-0.5,0,True,True),(0.5,-0.5,-8.7,False,False)]
open_grip()

for x,y,z,is_grip,is_z_xy in path:
    t1,t2=ik(x,y)
    get_distance()
    # theta_z = z*math.pi/180.0  # z: 0〜1 を 0〜180度に変換

    draw_arm(t1,t2,x,y,z)
    # print(prev_t1,prev_t2,t1,t2,sent_prev_z,theta_z,is_z_xy)

    if not is_z_xy:
        if sent_prev_t1 != t1:
            set_t1((t1-t1_initial)*L_SCALE)
            time.sleep(1.5)
        if sent_prev_t2 != t2:
            set_t2((t2-t2_initial)*L_SCALE)
            time.sleep(1.5)
        
        if sent_prev_z != z:
            send_z(z*LL_SCALE)
            time.sleep(2)
    else:
        if sent_prev_z != z:
            send_z(z*LL_SCALE)
            time.sleep(2)

        if sent_prev_t1 != t1:
            set_t1((t1-t1_initial)*L_SCALE)
            time.sleep(1.5)
        if sent_prev_t2 != t2:
            set_t2((t2-t2_initial)*L_SCALE)
            time.sleep(1.5)
        
    if is_grip:
        close_grip()
        time.sleep(2.0)

    else:
        open_grip()
    time.sleep(2.0)
    
    sent_prev_t1,sent_prev_t2=t1,t2
    sent_prev_z=z

plt.ioff()
plt.show()
