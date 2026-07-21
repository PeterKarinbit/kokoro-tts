#!/usr/bin/env python3
"""
Ivo TTS Server — Dual provider: Edge TTS (fast) + Kokoro (quality)
Edge TTS is default for real-time chat. Kokoro for high-quality pre-generated content.
"""

import asyncio
import base64
import io
import logging
import os
import time
from pathlib import Path

import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

# ─── Configuration ────────────────────────────────────────────────────────────

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "models"))
KOKORO_MODEL_PATH = MODEL_DIR / "kokoro-v1.0.int8.onnx"
KOKORO_VOICES_PATH = MODEL_DIR / "voices-v1.0.bin"

DEFAULT_VOICE_EDGE = "en-US-AvaMultilingualNeural"  # Edge TTS — fast, free
DEFAULT_VOICE_KOKORO = "af_heart"  # Kokoro — quality, Ivo's voice
DEFAULT_SPEED = 1.0

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ivo-tts")

# ─── Kokoro Model Loading (lazy singleton) ────────────────────────────────────

_kokoro_instance = None
_kokoro_load_time = None


def _load_kokoro():
    global _kokoro_instance, _kokoro_load_time
    if _kokoro_instance is not None:
        return _kokoro_instance

    logger.info(f"Loading Kokoro model from {KOKORO_MODEL_PATH}...")
    t0 = time.time()

    from kokoro_onnx import Kokoro

    _kokoro_instance = Kokoro(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH))
    _kokoro_load_time = time.time() - t0
    logger.info(f"Kokoro model loaded in {_kokoro_load_time:.2f}s")
    return _kokoro_instance


# ─── Voices ───────────────────────────────────────────────────────────────────

KOKORO_VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_michael", "bf_emma", "bf_isabella",
    "bm_george", "bm_lewis", "ef_dora", "ef_luna", "em_daniel",
    "ff_siwis", "hf_bhairavi", "hm_puru", "if_sara", "im_nico",
    "jf_gong", "jm_kumo", "pf_lilac", "pm_tadeu", "zf_xiaobei", "zm_yunxi",
]

EDGE_VOICES = [
    "en-US-AvaMultilingualNeural", "en-US-JennyNeural", "en-US-AriaNeural",
    "en-US-GuyNeural", "en-KE-AsiliaNeural", "en-KE-ChilembaNeural",
    "en-NG-EzinneNeural", "en-GB-SoniaNeural", "en-GB-RyanNeural",
]

# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="Ivo TTS Server", version="2.0.0", description="Dual TTS: Edge (fast) + Kokoro (quality)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ─── Request/Response Models ─────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10_000)
    provider: str = Field("edge", description="TTS provider: 'edge' (fast) or 'kokoro' (quality)")
    voice: str | None = Field(None, description="Voice ID (auto-selected per provider if omitted)")
    speed: float = Field(DEFAULT_SPEED, ge=0.5, le=2.0)


class SynthesizeResponse(BaseModel):
    audio_base64: str
    sample_rate: int
    duration_seconds: float
    provider: str
    voice: str
    inference_time_ms: float


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "ivo-tts", "providers": ["edge", "kokoro"], "message": "Ivo's voice engine"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "edge": "ready",
        "kokoro": "loaded" if _kokoro_instance else "standby",
        "kokoro_load_time_ms": round(_kokoro_load_time * 1000, 1) if _kokoro_load_time else None,
    }


@app.get("/voices")
def list_voices():
    return {
        "edge": {"voices": EDGE_VOICES, "default": DEFAULT_VOICE_EDGE},
        "kokoro": {"voices": KOKORO_VOICES, "default": DEFAULT_VOICE_KOKORO},
    }


async def _synthesize_edge(text: str, voice: str, speed: float) -> tuple[bytes, int]:
    """Edge TTS — fast, cloud-based, ~1-3s."""
    rate_str = f"+{int((speed - 1) * 100)}%" if speed >= 1 else f"-{int((1 - speed) * 100)}%"
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate_str)
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    audio_bytes = b"".join(audio_chunks)
    return audio_bytes, 24000


def _synthesize_kokoro(text: str, voice: str, speed: float) -> tuple[bytes, int]:
    """Kokoro ONNX — quality, local, ~5-60s depending on hardware."""
    model = _load_kokoro()
    audio, sample_rate = model.create(text, voice=voice, speed=speed)
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV")
    return buf.getvalue(), sample_rate


@app.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(req: SynthesizeRequest):
    t_start = time.time()

    # Route to provider
    if req.provider == "edge":
        voice = req.voice or DEFAULT_VOICE_EDGE
        if voice not in EDGE_VOICES:
            raise HTTPException(400, f"Unknown Edge voice. Available: {EDGE_VOICES}")
        t0 = time.time()
        audio_bytes, sample_rate = await _synthesize_edge(req.text, voice, req.speed)
        inference_ms = (time.time() - t0) * 1000

    elif req.provider == "kokoro":
        voice = req.voice or DEFAULT_VOICE_KOKORO
        if voice not in KOKORO_VOICES:
            raise HTTPException(400, f"Unknown Kokoro voice. Available: {KOKORO_VOICES}")
        t0 = time.time()
        audio_bytes, sample_rate = await asyncio.get_event_loop().run_in_executor(
            None, _synthesize_kokoro, req.text, voice, req.speed
        )
        inference_ms = (time.time() - t0) * 1000

    else:
        raise HTTPException(400, f"Unknown provider '{req.provider}'. Use 'edge' or 'kokoro'.")

    if not audio_bytes:
        raise HTTPException(500, "No audio generated")

    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    duration = len(audio_bytes) / sample_rate / 2  # rough WAV estimate
    total_ms = (time.time() - t_start) * 1000

    logger.info(f"[{req.provider}] {len(req.text)} chars -> {duration:.1f}s audio in {inference_ms:.0f}ms")

    return SynthesizeResponse(
        audio_base64=audio_b64,
        sample_rate=sample_rate,
        duration_seconds=round(duration, 2),
        provider=req.provider,
        voice=voice,
        inference_time_ms=round(inference_ms, 1),
    )


@app.post("/synthesize/file")
async def synthesize_file(req: SynthesizeRequest):
    """Returns raw WAV audio file."""
    if req.provider == "edge":
        voice = req.voice or DEFAULT_VOICE_EDGE
        audio_bytes, sample_rate = await _synthesize_edge(req.text, voice, req.speed)
    elif req.provider == "kokoro":
        voice = req.voice or DEFAULT_VOICE_KOKORO
        audio_bytes, sample_rate = await asyncio.get_event_loop().run_in_executor(
            None, _synthesize_kokoro, req.text, voice, req.speed
        )
    else:
        raise HTTPException(400, f"Unknown provider '{req.provider}'.")

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": f"attachment; filename=ivo_{req.provider}.wav"},
    )


@app.post("/warmup")
async def warmup():
    """Warm up both providers."""
    results = {}

    # Edge TTS warmup (fast)
    try:
        t0 = time.time()
        await _synthesize_edge("Hello!", DEFAULT_VOICE_EDGE, 1.0)
        results["edge"] = {"status": "ready", "time_ms": round((time.time() - t0) * 1000)}
    except Exception as e:
        results["edge"] = {"status": "error", "error": str(e)}

    # Kokoro warmup (loads model)
    try:
        t0 = time.time()
        await asyncio.get_event_loop().run_in_executor(
            None, _synthesize_kokoro, "Hello!", DEFAULT_VOICE_KOKORO, 1.0
        )
        results["kokoro"] = {"status": "ready", "time_ms": round((time.time() - t0) * 1000)}
    except Exception as e:
        results["kokoro"] = {"status": "error", "error": str(e)}

    return {"status": "ok", "providers": results}


# ─── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info("Ivo TTS Server starting...")
    # Edge TTS is ready immediately (cloud API)
    logger.info("Edge TTS: ready (cloud)")
    # Kokoro loads lazily on first request to save memory on free tier
    logger.info("Kokoro: standby (loads on first request)")


if __name__ == "__main__":
    import uvicorn

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
