"""
ロボットアームの制御スクリプト（クラス版）
"""
import threading
import keyboard
from robot_arm_class import RobotArm


def key_loop(robot):
    """キーボード監視スレッド"""
    while True:
        if keyboard.is_pressed("g"):
            robot.close_grip()
            import time
            time.sleep(0.3)
        if keyboard.is_pressed("r"):
            robot.open_grip()
            import time
            time.sleep(0.3)
        if keyboard.is_pressed("q"):
            break
        import time
        time.sleep(0.05)

def pick_and_place(robot):
    """ピック&プレイス動作"""
    print("ピック&プレイス開始...")
    
    # ホームポジション
    robot.move_to_angle(*robot.POSITIONS['home'], should_grip=False)
    
    # シーン1: 3番からつかんで5番に置く
    robot.grab_at(3)
    robot.move_to_angle(*robot.POSITIONS['pos_5'], should_grip=True)
    robot.place_at(5)
    
    # シーン2: 2番からつかんで4番に置く
    robot.grab_at(2)
    robot.move_to_angle(*robot.POSITIONS['pos_4'], should_grip=True)
    robot.place_at(4)
    
    # シーン3: 1番からつかんで3番に置く
    robot.grab_at(1)
    robot.move_to_angle(*robot.POSITIONS['pos_3'], should_grip=True)
    robot.place_at(3)
    
    # ホームに戻す
    robot.move_to_angle(*robot.POSITIONS['home'], should_grip=False)
    
    print("ピック&プレイス完了")

def main():
    """メイン処理"""
    # ロボットアーム初期化
    robot = RobotArm(port_xy="COM5", port_z="COM10")
    
    # 初期姿勢を設定
    robot.initialize(x0=0.5, y0=-0.5, z0=0.0)
    
    # キーボード監視スレッド開始
    threading.Thread(target=key_loop, args=(robot,), daemon=True).start()
    
    try:
        # ピック&プレイス実行
        pick_and_place(robot)
    except KeyboardInterrupt:
        print("\n中断しました")
    finally:
        robot.close()


if __name__ == "__main__":
    main()
