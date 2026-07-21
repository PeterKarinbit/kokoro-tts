#!/bin/bash
# Start Kokoro TTS server (background)
cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Starting Kokoro TTS server on port 8080..."
setsid python server.py >> /tmp/kokoro-tts.log 2>&1 &
echo "PID: $!"
sleep 5
python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=10); print(r.read().decode())"
