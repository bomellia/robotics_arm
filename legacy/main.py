import serial,math,time

L1=L2=0.5
L_SCALE=6

def ik(x,y):
    r2=x*x+y*y
    r=math.sqrt(r2)
    if r > L1+L2 or r < abs(L1-L2):
        raise ValueError("unreachable")

    c2=(r2-L1*L1-L2*L2)/(2*L1*L2)
    c2=max(-1,min(1,c2))
    s2=math.sqrt(1-c2*c2)
    t2=math.atan2(s2,c2)

    k1=L1+L2*c2
    k2=L2*s2
    t1=math.atan2(y,x)-math.atan2(k2,k1)
    return t1,t2

print(ik(0.5,0.75),ik(0.5,0.75)[0]*(180/math.pi),ik(0.5,0.75)[1]*(180/math.pi))

ser_xy = serial.Serial("COM10",115200,timeout=1)
ser_z  = serial.Serial("COM5",115200,timeout=1)
time.sleep(2)

def send_xy(t1,t2):
    ser_xy.write(f"M,{t1*L_SCALE:.3f},{t2*L_SCALE:.3f}\n".encode())

def set_t1(v): ser_xy.write(f"X,{v:.3f}\n".encode())
def set_t2(v): ser_xy.write(f"Y,{v:.3f}\n".encode())

def send_z(z):
    ser_z.write(f"Z,{z},0\n".encode())

path=[(0.5,0.75,0),(0.8,0.0,1.58),(0.5,0.3,1.58/2),(1.0,0.0,0)]

for x,y,z in path:
    t1,t2=ik(x,y)
    print("send:",x,y,z,t1,t2)
    # send_xy(t1,t2)
    set_t1(t1*L_SCALE)
    time.sleep(1)
    set_t2(t2*L_SCALE)
    time.sleep(1)
    send_z(z)
    time.sleep(1)  # Arduino 側 move_joint_and_wait 相当



