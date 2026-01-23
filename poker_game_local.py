# Poker Game with Robot Arm
# ポーカーゲーム制御プログラム
# - カードフィーダから5枚のカードを取得
# - getdistance値が10以下の状態が5秒続くまで待機
# - コンピュータが現在のハンドを評価して自動で最大2回までカードを入れ替え
# - 捨てたカードは座標0.5,0で離す

import sys
import os
import json
import time
import threading
from collections import Counter

# Add parent directory to path so we can import robotics_arm
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.append(ROOT_DIR)
from robot_arm_class import RobotArm

# Path to the hand file written by the card reader server
HAND_FILE = os.path.join(ROOT_DIR, 'robotics_arm', 'yolo_card_reader', 'latest_hand.json')

# Position for discarding cards
DISCARD_POS = (0.5, 0.0, 0)

# Card rank values for comparison
RANK_VALUES = {2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, 10: 10, 11: 11, 12: 12, 13: 13, 14: 14}

def get_latest_card():
    """Read the latest detected card from file."""
    try:
        with open(HAND_FILE, 'r') as f:
            data = json.load(f)
        hand = data.get('hand', [])
        if hand:
            return hand[0]  # Return the first (and only) card from feeder
        return None
    except FileNotFoundError:
        print(f"Warning: {HAND_FILE} not found. Is the card reader running?")
        return None
    except json.JSONDecodeError:
        print("Warning: Could not parse hand file")
        return None


def wait_for_card_in_feeder(robot, timeout_per_check=0.2, required_duration=5.0):
    """
    Wait until distance sensor value <= 10 for required_duration seconds.
    
    Args:
        robot: RobotArm instance
        timeout_per_check: Timeout for each distance measurement
        required_duration: Duration (in seconds) that distance must be <= 10
    
    Returns:
        True if card detected, False if timeout
    """
    print("カードフィーダを監視中（距離値≤10が5秒続くまで待機）...")
    
    start_time = None
    check_interval = 0.5  # Check every 0.5 seconds
    last_check = time.time()
    
    while True:
        current_time = time.time()
        
        # Check distance sensor periodically
        if current_time - last_check >= check_interval:
            distance = robot.get_distance(timeout=timeout_per_check)
            print(f"  距離値: {distance}")
            
            if distance is not None and distance <= 10:
                if start_time is None:
                    start_time = current_time
                    print(f"  カード検出！({required_duration}秒の確認中...)")
                
                # Check if we've maintained the condition for required_duration
                if current_time - start_time >= required_duration:
                    print(f"  カード確認完了！")
                    return True
            else:
                # Reset if distance goes above threshold
                if start_time is not None:
                    print(f"  条件が失われました。リセット。")
                start_time = None
            
            last_check = current_time
        
        time.sleep(0.1)


def fetch_card_from_feeder(robot):
    """
    Fetch one card from the feeder.
    Robot grabs from feeder position.
    """
    print("フィーダからカードを取得中...")
    robot.grab_at('feeder')
    print("カードを取得しました")


def place_card_at_position(robot, position_num):
    """
    Place card at one of the 5 positions (1-5).
    
    Args:
        position_num: Position number (1-5)
    """
    pos_key = f'pos_{position_num}'
    robot.place_at(pos_key)
    print(f"カードを位置{position_num}に配置しました")


def move_card_between_positions(robot, from_pos, to_pos):
    """Move card from one position to another."""
    robot.grab_at(f'pos_{from_pos}')
    robot.place_at(f'pos_{to_pos}')


def discard_card(robot):
    """
    Discard the currently held card at coordinates (0.5, 0).
    """
    print("カードを捨てています...")
    robot.move_to(0.5, 0.0, 0, should_grip=True)
    robot.move_to(0.5, 0.0, -8.7, should_grip=False)  # Lower to drop
    robot.move_to(0.5, 0.0, 0, should_grip=False)     # Return to neutral
    print("カードを捨てました")
    
def evaluate_hand(hand):
    ranks = [card[0] for card in hand]
    suits = [card[1] for card in hand]

    rank_count = Counter(ranks)
    counts = sorted(rank_count.values(), reverse=True)

    is_flush = len(set(suits)) == 1
    sorted_ranks = sorted(set(ranks))
    is_straight = (
        len(sorted_ranks) == 5 and
        max(sorted_ranks) - min(sorted_ranks) == 4
    )

    if is_straight and is_flush:
        return "straight_flush"
    if counts[0] == 4:
        return "four"
    if counts[0] == 3 and counts[1] == 2:
        return "full_house"
    if is_flush:
        return "flush"
    if is_straight:
        return "straight"
    if counts[0] == 3:
        return "three"
    if counts[0] == 2 and counts[1] == 2:
        return "two_pair"
    if counts[0] == 2:
        return "one_pair"
    return "high_card"

def decide_exchange_positions(hand, exchange_count):
    hand_type = evaluate_hand(hand)
    ranks = [card[0] for card in hand]
    rank_count = Counter(ranks)

    # 2回目以降は保守的に
    if exchange_count >= 1 and hand_type != "high_card":
        return []

    if hand_type in ("straight", "flush", "full_house", "four", "straight_flush"):
        return []

    if hand_type == "three":
        keep_ranks = [r for r, c in rank_count.items() if c == 3]
    elif hand_type == "two_pair":
        keep_ranks = [r for r, c in rank_count.items() if c == 2]
    elif hand_type == "one_pair":
        keep_ranks = [r for r, c in rank_count.items() if c == 2]
    else:  # high_card
        max_rank = max(ranks)
        keep_ranks = [max_rank]

    discard_positions = [
        i + 1 for i, card in enumerate(hand)
        if card[0] not in keep_ranks
    ]

    return discard_positions


def card_to_string(card):
    """Convert card tuple to readable string."""
    if card is None:
        return "Empty"
    
    rank, suit = card
    rank_names = {2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 
                  7: '7', 8: '8', 9: '9', 10: '10', 
                  11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
    
    return f"{rank_names.get(rank, str(rank))}{suit}"


def print_hand(hand, title="現在の手札"):
    """Print current hand nicely."""
    print()
    print("=" * 40)
    print(title)
    print("=" * 40)
    for i, card in enumerate(hand, 1):
        print(f"  位置{i}: {card_to_string(card)}")
    print("=" * 40)
    print()


def get_exchange_input():
    """
    Get user input for card exchanges.
    Returns list of position numbers (1-5) to exchange.
    Returns empty list if user chooses not to exchange.
    """
    while True:
        print("入れ替えるカードの位置を入力してください（カンマ区切り）")
        print("例: 1,3,5 (1番目、3番目、5番目を入れ替える)")
        print("入れ替えない場合は空白でEnter")
        
        user_input = input("> ").strip()
        
        if user_input == "":
            return []
        
        try:
            positions = [int(x.strip()) for x in user_input.split(",")]
            
            # Validate positions
            if all(1 <= p <= 5 for p in positions):
                if len(positions) == len(set(positions)):  # Check for duplicates
                    return positions
                else:
                    print("重複した位置が入力されています")
                    continue
            else:
                print("位置は1～5の範囲で指定してください")
                continue
                
        except ValueError:
            print("数字をカンマ区切りで入力してください")
            continue


def main():
    print("=" * 50)
    print("ポーカーロボット制御プログラム")
    print("=" * 50)
    print()
    
    # Initialize robot
    robot = RobotArm(port_xy="COM5", port_z="COM10")
    robot.initialize(x0=0.5, y0=-0.5, z0=0.0)
    robot.set_t1_speed(4.0)
    robot.set_t2_speed(4.0)
    robot.set_z_speed(4.0)
    
    try:
        hand = []
        
        # Phase 1: Fetch 5 cards from feeder
        print()
        print("=" * 50)
        print("フェーズ1: カード取得")
        print("=" * 50)
        print("フィーダから5枚のカードを取得します")
        print()
        
        for card_num in range(1, 6):
            print(f"\n--- カード {card_num}/5 ---")
            
            # Wait for card to be in feeder (distance <= 10 for 5 seconds)
            if not wait_for_card_in_feeder(robot, required_duration=5.0):
                print(f"タイムアウト: カード{card_num}を検出できませんでした")
                return
            
            # Fetch card from feeder
            fetch_card_from_feeder(robot)
            
            # Read the card
            detected_card = get_latest_card()
            if detected_card is None:
                print("警告: カード読み込み失敗。ダミーカードとして処理します")
                detected_card = (card_num * 2, 'C')  # Dummy card
            
            hand.append(detected_card)
            print(f"読み込まれたカード: {card_to_string(detected_card)}")
            
            # Place card at position
            place_card_at_position(robot, card_num)
            time.sleep(0.5)
        
        # Show initial hand
        print_hand(hand, "取得した手札")
        
        # Phase 2: Card exchange (up to 2 times)
        print()
        print("=" * 50)
        print("フェーズ2: カード入れ替え")
        print("=" * 50)
        print("最大2回まで任意枚数のカードを入れ替えられます")
        print()
        
        exchange_count = 0
        max_exchanges = 2
        
        while exchange_count < max_exchanges:
            print(f"\n入れ替え {exchange_count + 1}/{max_exchanges}")
            
            positions_to_exchange = decide_exchange_positions(hand, exchange_count)

            if not positions_to_exchange:
                print("コンピュータ判断: 入れ替えなし")
                break

            print(f"コンピュータ判断: 入れ替え位置 {positions_to_exchange}")

            
            if not positions_to_exchange:
                print("入れ替えをスキップします")
                break
            
            # For each position to exchange, get new card from feeder
            for pos in positions_to_exchange:
                print(f"\n位置{pos}のカードを入れ替えます")
                
                # Discard current card at position
                robot.grab_at(f'pos_{pos}')
                discard_card(robot)
                
                # Wait for new card in feeder
                print(f"\n位置{pos}用の新しいカードを待機中...")
                if not wait_for_card_in_feeder(robot, required_duration=5.0):
                    print(f"タイムアウト: 新しいカードを検出できませんでした")
                    # Just place a dummy
                    hand[pos - 1] = (0, '?')
                else:
                    # Fetch new card
                    fetch_card_from_feeder(robot)
                    
                    # Read the card
                    detected_card = get_latest_card()
                    if detected_card is None:
                        print("警告: カード読み込み失敗")
                        detected_card = (0, '?')
                    
                    hand[pos - 1] = detected_card
                    print(f"読み込まれたカード: {card_to_string(detected_card)}")
                
                # Place card at position
                place_card_at_position(robot, pos)
                time.sleep(0.5)
            
            exchange_count += 1
            print_hand(hand, f"入れ替え後の手札 ({exchange_count}/{max_exchanges})")
        
        # Final result
        print()
        print("=" * 50)
        print("ゲーム終了")
        print("=" * 50)
        print_hand(hand, "最終的な手札")
        
        # Return to home
        robot.move_to_angle(*robot.POSITIONS['home'], should_grip=False)
        print("ロボットをホームポジションに戻しました")
        
    except KeyboardInterrupt:
        print("\n処理を中断しました")
    finally:
        robot.close()


if __name__ == "__main__":
    main()
