import serial,time
s=serial.Serial("COM10",115200,timeout=1)
time.sleep(2)
print(s.read(100))

s.write(b'X')
print(s.read(1))
