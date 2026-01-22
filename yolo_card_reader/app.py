from flask import Flask, render_template, request, jsonify
import cv2
import json
import os
import sys
import numpy as np
from threading import Lock

# Import detect_cards from the YOLO repo
sys.path.append('yolo11-poker-hand-detection-and-analysis-main')
from yolo.detect_cards import detect_cards

app = Flask(__name__)

# Card string to tuple conversion
RANK_MAP = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
    '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
}

def card_string_to_tuple(card_str):
    """Convert YOLO card string (e.g., 'AH', '10D') to tuple (rank, suit)."""
    # Handle 10 specially since it's two characters
    if card_str.startswith('10'):
        rank_str = '10'
        suit = card_str[2]
    else:
        rank_str = card_str[0]
        suit = card_str[1]

    rank = RANK_MAP.get(rank_str)
    if rank is None:
        return None
    return (rank, suit)

# Global variables
config = {}
config_lock = Lock()
card_results = []
latest_hand = None  # Store latest detected hand for /hand endpoint

# Model path (hardcoded)
MODEL_PATH = 'yolo/weights/poker_best.pt'

def load_config():
    """Load configuration from config.json"""
    global config
    with config_lock:
        with open('config.json', 'r') as f:
            config = json.load(f)
    return config

def save_config(new_config):
    """Save configuration to config.json"""
    global config
    with config_lock:
        config = new_config
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=2)


def split_image_vertical(image, num_zones):
    """Split image into equal vertical zones"""
    height, width = image.shape[:2]
    zone_width = width // num_zones
    zones = []

    for i in range(num_zones):
        x_start = i * zone_width
        x_end = (i + 1) * zone_width if i < num_zones - 1 else width
        zone = image[:, x_start:x_end]
        zones.append((zone, x_start, x_end))

    return zones

def detect_cards_in_zones(image, num_zones, confidence_threshold):
    """Detect cards in each zone and return results"""
    zones = split_image_vertical(image, num_zones)
    results = []
    card_presence = []
    temp_files = []

    try:
        for i, (zone, x_start, x_end) in enumerate(zones):
            # Save zone as temporary image
            temp_path = f'temp_zone_{i}.jpg'
            cv2.imwrite(temp_path, zone)
            temp_files.append(temp_path)

            # Detect cards in zone
            try:
                detected_cards_str = detect_cards(temp_path, MODEL_PATH, conf=confidence_threshold)
                # Convert to tuples (rank, suit)
                detected_cards = [card_string_to_tuple(c) for c in detected_cards_str]
                detected_cards = [c for c in detected_cards if c is not None]  # Filter invalid
                has_card = len(detected_cards) > 0
                card_presence.append(has_card)

                results.append({
                    'zone': i,
                    'x_start': x_start,
                    'x_end': x_end,
                    'cards': detected_cards,  # List of tuples like [(14, 'H'), (2, 'S')]
                    'cards_str': detected_cards_str,  # Original strings like ['AH', '2S']
                    'has_card': has_card
                })
            except Exception as e:
                print(f"Error detecting cards in zone {i}: {e}")
                card_presence.append(False)
                results.append({
                    'zone': i,
                    'x_start': x_start,
                    'x_end': x_end,
                    'cards': [],
                    'has_card': False
                })
    finally:
        # Clean up all temp files after processing
        for temp_path in temp_files:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                print(f"Warning: Could not remove {temp_path}: {e}")

    return results, card_presence

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/config', methods=['GET', 'POST'])
def config_endpoint():
    """Get or update configuration"""
    if request.method == 'GET':
        return jsonify(config)
    elif request.method == 'POST':
        new_config = request.json
        save_config(new_config)
        return jsonify({'status': 'success', 'config': config})

@app.route('/hand', methods=['GET'])
def get_hand():
    """Return the latest detected hand."""
    if latest_hand is None:
        return jsonify({'status': 'no_data', 'hand': []})
    return jsonify({'status': 'success', 'hand': latest_hand})

@app.route('/upload_frame', methods=['POST'])
def upload_frame():
    """Receive frame from phone camera"""
    global card_results, latest_hand

    try:
        # Get image from request
        file = request.files['frame']
        npimg = np.frombuffer(file.read(), np.uint8)
        image = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

        # Process image
        num_zones = config['detection']['num_cards']
        confidence_threshold = config['detection']['confidence_threshold']

        results, card_presence = detect_cards_in_zones(image, num_zones, confidence_threshold)

        # Build hand list: first detected card per zone, or None if empty
        hand = []
        for result in results:
            if result['cards'] and len(result['cards']) > 0:
                hand.append(result['cards'][0])  # Take first card in zone
            else:
                hand.append(None)

        # Store for /hand endpoint
        latest_hand = hand

        # Write to file for external access
        with open('latest_hand.json', 'w') as f:
            json.dump({'hand': hand}, f)

        return jsonify({
            'status': 'success',
            'results': results,
            'card_presence': card_presence,
            'hand': hand  # e.g., [(14, 'H'), None, (2, 'S'), None, None]
        })
    except Exception as e:
        print(f"Error processing frame: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Card Reader Flask Server')
    parser.add_argument('--https', action='store_true', help='Run with HTTPS (required for mobile camera)')
    args = parser.parse_args()

    # Load config
    load_config()

    if args.https:
        # Generate self-signed certificate if it doesn't exist
        cert_file = 'cert.pem'
        key_file = 'key.pem'

        if not os.path.exists(cert_file) or not os.path.exists(key_file):
            print("Generating self-signed certificate...")
            from OpenSSL import crypto

            # Create key pair
            k = crypto.PKey()
            k.generate_key(crypto.TYPE_RSA, 2048)

            # Create self-signed cert
            cert = crypto.X509()
            cert.get_subject().C = "US"
            cert.get_subject().ST = "State"
            cert.get_subject().L = "City"
            cert.get_subject().O = "Card Reader"
            cert.get_subject().OU = "Card Reader"
            cert.get_subject().CN = "localhost"
            cert.set_serial_number(1000)
            cert.gmtime_adj_notBefore(0)
            cert.gmtime_adj_notAfter(365*24*60*60)  # Valid for 1 year
            cert.set_issuer(cert.get_subject())
            cert.set_pubkey(k)
            cert.sign(k, 'sha256')

            # Write files
            with open(cert_file, "wb") as f:
                f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
            with open(key_file, "wb") as f:
                f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))

            print("Certificate generated successfully!")

        # Run Flask app with HTTPS
        print("Starting server on https://0.0.0.0:5000")
        print("Note: You'll need to accept the self-signed certificate warning in your browser")
        app.run(host='0.0.0.0', port=5000, debug=True, threaded=True,
                ssl_context=(cert_file, key_file))
    else:
        # Run Flask app without HTTPS
        print("Starting server on http://0.0.0.0:5000")
        print("Warning: Camera access requires HTTPS on mobile devices. Use --https flag for mobile access.")
        app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
