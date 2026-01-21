import serial,math,time
# ---- パラメータ ----
L1=L2=0.5
L_SCALE=6
PORT_XY="COM5"
PORT_Z ="COM10"

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
except:
    def send_z(z): pass
    def close_grip(): pass
    def open_grip(): pass

import keyboard
while True:
    if keyboard.is_pressed("g"):
        
        time.sleep(2)
        close_grip()
        time.sleep(0.3)
    if keyboard.is_pressed("r"):
        open_grip()
        time.sleep(0.3)