import serial,math,time
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("TkAgg")

# ---- パラメータ ----
L1=L2=0.5
L_SCALE=6
PORT_XY="COM10"
PORT_Z ="COM5"

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

    if da<db:
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

def draw_arm(t1,t2,x,y):
    p0,p1,p2=fk(t1,t2)

    arm_line.set_data([p0[1],p1[1],p2[1]],
                      [p0[0],p1[0],p2[0]])

    target_dot.set_data([y],[x])

    plt.gcf().canvas.draw_idle()
    plt.gcf().canvas.flush_events()
    plt.pause(0.001)


# ---- Serial 接続（失敗時シミュレーション） ----
try:
    ser_xy=serial.Serial(PORT_XY,115200,timeout=1)
    time.sleep(2)
    print("Serial connected.")

    def set_t1(v): ser_xy.write(f"X,{v:.3f}\n".encode())
    def set_t2(v): ser_xy.write(f"Y,{v:.3f}\n".encode())

except Exception as e:
    print("Serial not available. Simulation only.")
    print(e)

    def set_t1(v): pass
    def set_t2(v): pass

try:
    ser_z =serial.Serial(PORT_Z,115200,timeout=1)
    time.sleep(2)
    print("Serial connected.")

    def send_z(z): ser_z.write(f"Z,{z:.3f},0\n".encode())
    def close_grip(): ser_z.write(b"G\n")
    def open_grip():  ser_z.write(b"R\n")

except Exception as e:
    print("Serial not available. Simulation only.")
    print(e)

    def send_z(z): pass
    def close_grip(): pass
    def open_grip(): pass

# ---- 初期姿勢 ----
x0,y0=1.0,0.0
t1,t2=ik(x0,y0)
draw_arm(t1,t2,x0,y0)
time.sleep(1)

# ---- パス ----
path=[(0.5,0.75,0),(0.8,0.0,1.58),(0.5,0.3,1.58/2),(1.0,0.0,0)]

for x,y,z in path:
    t1,t2=ik(x,y)
    print(f"target=({x:.2f},{y:.2f}) t1={math.degrees(t1):.1f}° t2={math.degrees(t2):.1f}°")

    draw_arm(t1,t2,x,y)
    
    send_z(z*L_SCALE)
    time.sleep(1)
    set_t1(t1*L_SCALE)
    time.sleep(1)
    set_t2(t2*L_SCALE)
    time.sleep(1)

plt.ioff()
plt.show(block=False)
