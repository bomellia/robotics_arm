# Sort Cards Game
# Places cards in order of rank (smallest to largest) at positions 1-4
# Uses position 5 as a temporary holder for swapping

import sys
import os
import json
import time

# Add parent directory to path so we can import robotics_arm
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.append(ROOT_DIR)
from robot_arm_class import RobotArm

# Path to the hand file written by the card reader server
HAND_FILE = os.path.join(ROOT_DIR, 'ik', 'yolo_card_reader', 'latest_hand.json')


def get_hand():
    """Read latest detected cards from file."""
    try:
        with open(HAND_FILE, 'r') as f:
            data = json.load(f)
        return data.get('hand', [])
    except FileNotFoundError:
        print(f"Warning: {HAND_FILE} not found. Is the card reader running?")
        return []
    except json.JSONDecodeError:
        print("Warning: Could not parse hand file")
        return []


def move_card(robot, from_pos, to_pos):
    """Move card from one position to another."""
    robot.grab_at(f'pos_{from_pos}')
    robot.move_to_angle(*robot.POSITIONS[f'pos_{to_pos}'], should_grip=True)
    robot.place_at(f'pos_{to_pos}')


def swap_cards(robot, pos_a, pos_b, temp_pos=5):
    """Swap cards at two positions using temp holder."""
    move_card(robot, pos_a, temp_pos)  # A -> temp
    move_card(robot, pos_b, pos_a)      # B -> A
    move_card(robot, temp_pos, pos_b)   # temp -> B


def rank_to_string(rank):
    """Convert rank number to readable string."""
    names = {11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
    return names.get(rank, str(rank))


def card_to_string(card):
    """Convert card tuple to readable string."""
    if card is None:
        return "Empty"
    rank, suit = card
    return f"{rank_to_string(rank)}{suit}"


def print_positions(card_positions):
    """Print current card positions."""
    for pos in range(1, 5):
        card = card_positions.get(pos)
        print(f"  Position {pos}: {card_to_string(card)}")


def main():
    print("=== Card Sorting Game ===")
    print("Cards at positions 1-4 will be sorted smallest to largest")
    print("Position 5 is used as temp holder")
    print()

    # Initialize robot
    robot = RobotArm(port_xy="COM5", port_z="COM10")
    robot.initialize(x0=0.5, y0=-0.5, z0=0.0)
    robot.set_t1_speed(4.0)
    robot.set_t2_speed(4.0)
    robot.set_z_speed(4.0)

    try:
        # Read cards ONCE from file
        print("Reading cards...")
        hand = get_hand()

        if len(hand) < 4:
            print(f"Error: Need at least 4 card positions, got {len(hand)}")
            return

        # Store cards in memory: position -> card
        # We'll track all moves internally from now on
        card_positions = {}
        for i in range(4):
            card_positions[i + 1] = hand[i]  # positions 1-4
        card_positions[5] = None  # temp holder starts empty

        # Show current hand
        print("Current cards:")
        print_positions(card_positions)

        # Get non-empty cards with their positions
        cards = []
        for pos in range(1, 5):
            card = card_positions[pos]
            if card is not None:
                cards.append((card[0], pos))  # (rank, position)

        if len(cards) < 2:
            print("Need at least 2 cards to sort!")
            return

        # Sort by rank (smallest first)
        sorted_by_rank = sorted(cards, key=lambda x: x[0])

        print()
        print("Target order (smallest to largest):")
        for i, (rank, _) in enumerate(sorted_by_rank):
            print(f"  Position {i+1}: {rank_to_string(rank)}")

        # Helper to swap in memory
        def memory_swap(positions, pos_a, pos_b, temp_pos=5):
            positions[temp_pos] = positions[pos_a]
            positions[pos_a] = positions[pos_b]
            positions[pos_b] = positions[temp_pos]
            positions[temp_pos] = None

        # Calculate all moves first (dry run)
        planned_moves = []
        sim_positions = card_positions.copy()  # simulate positions

        for target_idx in range(len(sorted_by_rank)):
            target_pos = target_idx + 1
            target_rank = sorted_by_rank[target_idx][0]

            # Find where the target card currently is
            current_pos = None
            for pos in range(1, 5):
                card = sim_positions[pos]
                if card is not None and card[0] == target_rank:
                    current_pos = pos
                    break

            if current_pos is None or current_pos == target_pos:
                continue

            # Record the swap
            card_a = sim_positions[current_pos]
            card_b = sim_positions[target_pos]
            planned_moves.append({
                'from': current_pos,
                'to': target_pos,
                'card_moving': card_a,
                'card_displaced': card_b
            })
            memory_swap(sim_positions, current_pos, target_pos)

        # Show planned moves
        print()
        print("=" * 40)
        print("PLANNED MOVES:")
        print("=" * 40)
        if not planned_moves:
            print("  Cards already sorted! No moves needed.")
        else:
            for i, move in enumerate(planned_moves, 1):
                card_a = card_to_string(move['card_moving'])
                card_b = card_to_string(move['card_displaced'])
                print(f"  {i}. Swap position {move['from']} <-> {move['to']}")
                print(f"     ({card_a} <-> {card_b})")
                print(f"     Actions: grab_at({move['from']}) -> place_at(5)")
                print(f"              grab_at({move['to']}) -> place_at({move['from']})")
                print(f"              grab_at(5) -> place_at({move['to']})")
                print()

        print("=" * 40)
        input("Press Enter to start sorting...")

        # Now execute the actual moves
        for target_idx in range(len(sorted_by_rank)):
            target_pos = target_idx + 1
            target_rank = sorted_by_rank[target_idx][0]

            # Find where the target card currently is (from memory)
            current_pos = None
            for pos in range(1, 5):
                card = card_positions[pos]
                if card is not None and card[0] == target_rank:
                    current_pos = pos
                    break

            if current_pos is None:
                print(f"Warning: Could not find card with rank {target_rank}")
                continue

            if current_pos == target_pos:
                print(f"Card {rank_to_string(target_rank)} already at position {target_pos}")
                continue

            # Swap cards
            print(f"Swapping position {current_pos} <-> {target_pos}")
            swap_cards(robot, current_pos, target_pos)
            memory_swap(card_positions, current_pos, target_pos)

            time.sleep(0.5)

        robot.move_to_angle(*robot.POSITIONS[f'home'], should_grip=False)
        print()
        print("Sorting complete!")

        # Show final result (from memory)
        print("Final cards:")
        print_positions(card_positions)

    finally:
        robot.close()


if __name__ == "__main__":
    main()
