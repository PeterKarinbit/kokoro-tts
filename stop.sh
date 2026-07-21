#!/bin/bash
# Stop Kokoro TTS server
pkill -f "kokoro-tts-server/server.py" && echo "Kokoro TTS server stopped" || echo "No Kokoro TTS server running"
