# YOLO Card Reader

A web-based card detection system using YOLO11 for poker card recognition. The system splits camera frames into vertical zones to detect cards in specific positions and identify when cards are removed.

## Features

- Real-time card detection using YOLO11
- Vertical zone splitting to track multiple card positions
- Empty slot detection (knows when a card is removed)
- Web-based interface for phone camera streaming
- Editable configuration (number of cards, confidence threshold)
- Visual zone divisions with card detection results
- Minimalistic white UI design

## Setup Instructions

### 1. Install Dependencies

Create a conda environment and install the required packages:

```bash
conda create -n card_reader python=3.10
conda activate card_reader
pip install -r requirements.txt
```

### 2. Verify YOLO Model

Make sure the YOLO poker detection model is in place:
- Path: `yolo11-poker-hand-detection-and-analysis-main/weights/poker_best.pt`
- If missing, check the YOLO repository for the pre-trained weights

### 3. Run the Flask Server

```bash
python app.py --https
```

The `--https` flag will:
- Auto-generate a self-signed SSL certificate on first run (required for camera access)
- Start the server on `https://0.0.0.0:5000`

You can also run without HTTPS for testing (camera won't work on mobile):
```bash
python app.py
```

### 4. Access from Phone

1. Make sure your phone and PC are on the same network
2. Find your PC's IP address:
   - Windows: `ipconfig` (look for IPv4 Address)
   - Mac/Linux: `ifconfig` or `ip addr`
3. Open browser on phone and go to: `https://[YOUR_PC_IP]:5000`
4. **Accept the security warning** (self-signed certificate - this is safe)
   - Chrome: Click "Advanced" → "Proceed to [IP] (unsafe)"
   - Safari: Click "Show Details" → "visit this website"
   - Firefox: Click "Advanced" → "Accept the Risk and Continue"
5. Click "Start Camera" to begin streaming

**Note**: HTTPS is required for camera access on mobile browsers. The self-signed certificate will trigger a security warning - this is expected and safe to bypass.

## Configuration

Edit settings in the web UI or directly in `config.json`:

- **num_cards**: Number of vertical zones to split the image into (1-10)
- **confidence_threshold**: YOLO detection confidence threshold (0.0-1.0)

## How It Works

1. **Camera Streaming**: Phone camera streams video frames to Flask server
2. **Zone Splitting**: Each frame is divided into N equal vertical zones
3. **Card Detection**: YOLO model processes each zone independently
4. **Empty Detection**: Zones with no detected cards are marked as "EMPTY"
5. **Results Display**: Processed frame shows zone divisions, detected cards, and empty slots
6. **Card Presence Array**: Returns boolean array `[true, false, true]` indicating which zones have cards

## API Endpoints

- `GET /`: Main web interface
- `GET /config`: Get current configuration
- `POST /config`: Update configuration
- `POST /upload_frame`: Upload camera frame for processing
- `GET /video_feed`: Video stream of processed frames

## File Structure

```
yolo_card_reader/
├── app.py                          # Flask application
├── config.json                     # Configuration file
├── requirements.txt                # Python dependencies
├── templates/
│   └── index.html                  # Web UI
└── yolo11-poker-hand-detection-and-analysis-main/
    ├── detect_cards.py             # YOLO detection functions
    └── weights/
        └── poker_best.pt           # YOLO model weights
```

## Card Detection Format

Cards are returned in shorthand notation:
- `2C` = 2 of Clubs
- `7H` = 7 of Hearts
- `KS` = King of Spades
- `AD` = Ace of Diamonds

Ranks: `2-10, J, Q, K, A`
Suits: `C (Clubs), D (Diamonds), H (Hearts), S (Spades)`

## Notes

- Model works best with square-ish images where cards are centered
- Adjust the number of zones to match your physical card slots
- Lower confidence threshold detects more cards but may have false positives
- Higher confidence threshold is more accurate but may miss some cards

## Credits

YOLO11 Poker Detection: [Gholamrezadar/yolo11-poker-hand-detection-and-analysis](https://github.com/Gholamrezadar/yolo11-poker-hand-detection-and-analysis/)
