# ==============================
# Poker Game with Robot Arm + Flask UI
# ==============================

import sys
import os
import json
import time
import threading
from collections import Counter
from flask import Flask, jsonify, render_template

# ------------------------------
# Path setup
# ------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.append(ROOT_DIR)

from robot_arm_class import RobotArm

HAND_FILE = os.path.join(
    ROOT_DIR,
    'robotics_arm',
    'yolo_card_reader',
    'latest_hand.json'
)

DISCARD_POS = (0.5, 0.0, 0)

# ==============================
# UI 状態管理
# ==============================

class GameStatus:
    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "INIT"
        self.message = "待機中"
        self.hand = []
        self.final_hand = []
        self.role = None
        self.chat = []
        self.debug = False
        self.show_hand = False   # 追加
        self.running = False

    def log(self, msg):
        self.chat.append(msg)
        self.message = msg

STATUS = GameStatus()

# ==============================
# Flask UI
# ==============================

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/status")
def status():
    # 進行中の手札
    if STATUS.show_hand or STATUS.debug:
        hand = STATUS.hand
    else:
        hand = ["?"] * len(STATUS.hand)

    # 最終手札は常に表示
    final_hand = STATUS.final_hand

    return jsonify({
        "state": STATUS.state,
        "hand": hand,
        "final_hand": final_hand,
        "role": STATUS.role,
        "chat": STATUS.chat,
        "show_hand": STATUS.show_hand
    })


@app.route("/start")
def start():
    if STATUS.running:
        return jsonify({"ok": False})

    STATUS.reset()
    STATUS.running = True
    threading.Thread(target=game_main, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/toggle_hand")
def toggle_hand():
    STATUS.show_hand = not STATUS.show_hand
    return jsonify({"show": STATUS.show_hand})


# ==============================
# カード取得
# ==============================

def get_latest_card():
    try:
        with open(HAND_FILE, 'r') as f:
            data = json.load(f)
        hand = data.get('hand', [])
        if hand:
            return hand[0]
        return None
    except Exception:
        return None

# ==============================
# 距離センサ待機（完全保持）
# ==============================

def wait_for_card_in_feeder(robot, timeout_per_check=0.2, required_duration=5.0):
    STATUS.state = "WAIT"
    STATUS.log("カード待機中（距離≤10 が5秒）")

    start_time = None
    last_check = time.time()

    while True:
        now = time.time()
        if now - last_check >= 0.5:
            distance = robot.get_distance(timeout=timeout_per_check)

            if distance is not None and distance <= 10:
                if start_time is None:
                    start_time = now
                if now - start_time >= required_duration:
                    return True
            else:
                start_time = None

            last_check = now

        time.sleep(0.1)

# ==============================
# ロボット操作（完全保持）
# ==============================

def fetch_card_from_feeder(robot):
    STATUS.log("カードを取得")
    robot.grab_at('feeder')

def place_card_at_position(robot, position_num):
    STATUS.log(f"{position_num}番に配置")
    robot.place_at(f'pos_{position_num}')

def discard_card(robot):
    STATUS.log("カードを捨てる")
    robot.move_to(0.5, 0.0, 0, should_grip=True)
    robot.move_to(0.5, 0.0, -8.7, should_grip=False)
    robot.move_to(0.5, 0.0, 0, should_grip=False)

# ==============================
# 役判定（元ロジック）
# ==============================

def evaluate_hand(hand):
    ranks = [c[0] for c in hand]
    suits = [c[1] for c in hand]
    count = Counter(ranks).values()

    flush = len(set(suits)) == 1
    straight = max(ranks) - min(ranks) == 4 and len(set(ranks)) == 5

    if straight and flush: return "straight_flush"
    if 4 in count: return "four"
    if 3 in count and 2 in count: return "full_house"
    if flush: return "flush"
    if straight: return "straight"
    if 3 in count: return "three"
    if list(count).count(2) == 2: return "two_pair"
    if 2 in count: return "one_pair"
    return "high_card"

ROLE_MSG = {
    "straight_flush": "ストレートフラッシュ",
    "four": "フォーカード",
    "full_house": "フルハウス",
    "flush": "フラッシュ",
    "straight": "ストレート",
    "three": "スリーカード",
    "two_pair": "ツーペア",
    "one_pair": "ワンペア",
    "high_card": "ハイカード"
}

# ==============================
# 交換判断（元ロジック）
# ==============================

def decide_exchange_positions(hand, exchange_count):
    hand_type = evaluate_hand(hand)
    ranks = [c[0] for c in hand]
    rank_count = Counter(ranks)

    if exchange_count >= 1 and hand_type != "high_card":
        STATUS.log("これ以上の交換はリスクが高いのでやめときます")
        return []

    if hand_type in ("straight", "flush", "full_house", "four", "straight_flush"):
        STATUS.log("自信あり！交換しません")
        return []

    if hand_type == "three":
        keep = [r for r, c in rank_count.items() if c == 3]
        STATUS.log("スリーカードがあるのでそれ以外を交換しましょう")
    elif hand_type in ("two_pair", "one_pair"):
        keep = [r for r, c in rank_count.items() if c == 2]
        STATUS.log("ペアがあるのでそれ以外を交換しましょう")
    else:
        keep = [max(ranks)]
        STATUS.log("最大ランク1枚を維持")

    return [i+1 for i,c in enumerate(hand) if c[0] not in keep]

# ==============================
# メイン制御（ロボット制御そのまま）
# ==============================

def game_main():
    robot = RobotArm(port_xy="COM5", port_z="COM10")
    STATUS.log("ロボット準備開始")
    robot.initialize(x0=0.5, y0=-0.5, z0=0)
    robot.set_t1_speed(4)
    robot.set_t2_speed(4)
    robot.set_z_speed(4)
    
    if robot.ser_xy is None or robot.ser_z is None:
        STATUS.state = "ERROR"
        STATUS.log("ロボット接続失敗: シミュレーションモード")
        STATUS.running = False
    else:
    
        STATUS.log("ロボット準備完了")

    hand = []

    try:
        STATUS.state = "FETCH"
        STATUS.log("カード取得開始")

        for i in range(1, 6):
            wait_for_card_in_feeder(robot)
            fetch_card_from_feeder(robot)
            card = get_latest_card() or (i * 2, 'C')
            hand.append(card)
            place_card_at_position(robot, i)
            STATUS.hand = [str(c) for c in hand]
            time.sleep(0.5)

        for exch in range(2):
            pos = decide_exchange_positions(hand, exch)
            if not pos:
                break

            STATUS.state = "EXCHANGE"
            STATUS.log(f"{len(pos)}枚交換")

            for p in pos:
                robot.grab_at(f'pos_{p}')
                discard_card(robot)
                wait_for_card_in_feeder(robot)
                fetch_card_from_feeder(robot)
                hand[p-1] = get_latest_card() or (0,'?')
                place_card_at_position(robot, p)
                STATUS.hand = [str(c) for c in hand]
                time.sleep(0.5)

        role = evaluate_hand(hand)
        STATUS.final_hand = [str(c) for c in hand]
        STATUS.role = ROLE_MSG[role]
        STATUS.state = "END"
        STATUS.log(f"ゲーム終了：{ROLE_MSG[role]}")

        robot.move_to_angle(*robot.POSITIONS['home'], should_grip=False)

    finally:
        robot.close()
        STATUS.running = False

# ==============================
# 起動
# ==============================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
