# Kokoro TTS Server

High-quality TTS powered by [Kokoro ONNX](https://github.com/thewh1teagle/kokoro-onnx) — Ivo's voice engine.

## Quick Start

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download models (~336 MB, one-time)
python download_models.py

# 4. Start server
python server.py
```

Server runs at `http://localhost:8080`

## API

### Health Check
```bash
curl http://localhost:8080/health
```

### List Voices
```bash
curl http://localhost:8080/voices
```

### Synthesize Speech
```bash
curl -X POST http://localhost:8080/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello! I am Ivo, your AI assistant.", "voice": "af_heart"}'
```

### Warmup (pre-load model)
```bash
curl -X POST http://localhost:8080/warmup
```

## Voices

| Voice | Language | Gender | Style |
|-------|----------|--------|-------|
| `af_heart` ★ | American English | Female | Warm (Ivo's default) |
| `af_bella` | American English | Female | Clear |
| `af_nicole` | American English | Female | Soft |
| `af_sarah` | American English | Female | Neutral |
| `af_sky` | American English | Female | Bright |
| `am_adam` | American English | Male | Deep |
| `am_michael` | American English | Male | Warm |
| `bf_emma` | British English | Female | Elegant |
| `bm_george` | British English | Male | Authoritative |
| `ef_dora` | Spanish | Female | — |
| `ff_siwis` | French | Female | — |
| `jf_gong` | Japanese | Female | — |
| `zf_xiaobei` | Chinese | Female | — |

★ = Ivo's default voice

## Deploy to Render

1. Push this folder as a new GitHub repo
2. Connect to Render
3. Render will auto-detect `render.yaml` and deploy

Or manually: New Web Service → Docker → point to this repo.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Server port |
| `MODEL_DIR` | `models` | Path to model files |

## Docker

```bash
# Build
docker build -t kokoro-tts .

# Run
docker run -p 8080:8080 kokoro-tts
```
