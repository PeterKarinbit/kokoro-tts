#!/usr/bin/env python3
"""
Kokoro TTS Server — FastAPI wrapper around kokoro-onnx
Loads model ONCE at startup, serves TTS requests with ~50-100ms inference.
"""

import asyncio
import base64
import io
import logging
import os
import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

# ─── Configuration ────────────────────────────────────────────────────────────

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "models"))
MODEL_PATH = MODEL_DIR / "kokoro-v1.0.int8.onnx"
VOICES_PATH = MODEL_DIR / "voices-v1.0.bin"

DEFAULT_VOICE = "af_heart"  # Ivo's voice — American Female, warm/heart style
DEFAULT_SPEED = 1.0

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kokoro-tts")

# ─── Model Loading (singleton) ───────────────────────────────────────────────

_kokoro_instance = None
_model_load_time = None


def _load_model():
    """Load Kokoro ONNX model once. Returns the Kokoro instance."""
    global _kokoro_instance, _model_load_time
    if _kokoro_instance is not None:
        return _kokoro_instance

    logger.info(f"Loading Kokoro model from {MODEL_PATH}...")
    t0 = time.time()

    from kokoro_onnx import Kokoro

    _kokoro_instance = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
    _model_load_time = time.time() - t0
    logger.info(f"Kokoro model loaded in {_model_load_time:.2f}s")
    return _kokoro_instance


def get_model():
    """Get or lazy-load the Kokoro model."""
    return _load_model()


# ─── Available Voices ─────────────────────────────────────────────────────────

AVAILABLE_VOICES = [
    # American Female
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    # American Male
    "am_adam", "am_michael",
    # British Female
    "bf_emma", "bf_isabella",
    # British Male
    "bm_george", "bm_lewis",
    # Spanish Female
    "ef_dora", "ef_luna",
    # Spanish Male
    "em_daniel",
    # French Female
    "ff_siwis",
    # Hindi Female
    "hf_bhairavi",
    # Hindi Male
    "hm_puru",
    # Italian Female
    "if_sara",
    # Italian Male
    "im_nico",
    # Japanese Female
    "jf_gong",
    # Japanese Male
    "jm_kumo",
    # Portuguese Brazilian Female
    "pf_lilac",
    # Portuguese Brazilian Male
    "pm_tadeu",
    # Chinese Female
    "zf_xiaobei",
    # Chinese Male
    "zm_yunxi",
]

# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Kokoro TTS Server",
    version="1.0.0",
    description="High-quality TTS powered by Kokoro ONNX",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response Models ─────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10_000, description="Text to synthesize")
    voice: str = Field(DEFAULT_VOICE, description="Voice ID (e.g. af_heart, am_adam)")
    speed: float = Field(DEFAULT_SPEED, ge=0.5, le=2.0, description="Speech speed multiplier")
    format: str = Field("wav", description="Output format: wav or mp3")


class SynthesizeResponse(BaseModel):
    audio_base64: str
    sample_rate: int
    duration_seconds: float
    voice: str
    load_time_ms: float
    inference_time_ms: float


class WarmupResponse(BaseModel):
    status: str
    model: str
    load_time_ms: float
    voices: list[str]


class HealthResponse(BaseModel):
    status: str
    model: str
    model_loaded: bool
    load_time_ms: float | None


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Root route — always responds instantly (for Render health checks)."""
    return {"status": "ok", "service": "kokoro-tts", "message": "Ivo's voice engine is running"}


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        model="kokoro-onnx",
        model_loaded=_kokoro_instance is not None,
        load_time_ms=round(_model_load_time * 1000, 1) if _model_load_time else None,
    )


@app.get("/voices")
def list_voices():
    return {"voices": AVAILABLE_VOICES, "default": DEFAULT_VOICE}


@app.post("/synthesize", response_model=SynthesizeResponse)
def synthesize(req: SynthesizeRequest):
    t_start = time.time()

    # Validate voice
    if req.voice not in AVAILABLE_VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice '{req.voice}'. Available: {AVAILABLE_VOICES}",
        )

    # Load model (first call loads, subsequent calls are instant)
    model = get_model()

    # Synthesize
    t_infer = time.time()
    try:
        audio, sample_rate = model.create(
            req.text,
            voice=req.voice,
            speed=req.speed,
        )
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    inference_time_ms = (time.time() - t_infer) * 1000

    # Convert to WAV bytes
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV")
    wav_bytes = buf.getvalue()

    # Convert to base64
    audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

    duration = len(audio) / sample_rate
    total_time_ms = (time.time() - t_start) * 1000

    logger.info(
        f"Synthesized {len(req.text)} chars -> {duration:.1f}s audio "
        f"(inference: {inference_time_ms:.0f}ms, total: {total_time_ms:.0f}ms)"
    )

    return SynthesizeResponse(
        audio_base64=audio_b64,
        sample_rate=sample_rate,
        duration_seconds=round(duration, 2),
        voice=req.voice,
        load_time_ms=round(_model_load_time * 1000, 1) if _model_load_time else 0,
        inference_time_ms=round(inference_time_ms, 1),
    )


@app.post("/synthesize/file")
def synthesize_file(req: SynthesizeRequest):
    """Returns raw WAV audio file (for direct playback)."""
    if req.voice not in AVAILABLE_VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice '{req.voice}'. Available: {AVAILABLE_VOICES}",
        )

    model = get_model()

    try:
        audio, sample_rate = model.create(
            req.text,
            voice=req.voice,
            speed=req.speed,
        )
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV")
    wav_bytes = buf.getvalue()

    duration = len(audio) / sample_rate
    logger.info(f"Served WAV file: {duration:.1f}s audio for '{req.text[:50]}...'")

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=ivo_tts.wav"},
    )


@app.post("/warmup", response_model=WarmupResponse)
def warmup():
    """Load model and do a test synthesis to warm up."""
    t0 = time.time()
    model = get_model()

    # Do a quick test synthesis
    try:
        audio, sr = model.create("Hello, world!", voice=DEFAULT_VOICE, speed=1.0)
        logger.info(f"Warmup complete: {len(audio)/sr:.1f}s audio generated")
    except Exception as e:
        logger.warning(f"Warmup synthesis failed: {e}")

    load_ms = (time.time() - t0) * 1000
    return WarmupResponse(
        status="ready",
        model="kokoro-onnx",
        load_time_ms=round(load_ms, 1),
        voices=AVAILABLE_VOICES,
    )


# ─── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Pre-load model on server start."""
    logger.info("Server starting — pre-loading Kokoro model...")
    get_model()
    logger.info("Kokoro model ready!")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # Ensure models directory exists
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if not MODEL_PATH.exists():
        logger.error(f"Model not found at {MODEL_PATH}")
        logger.info("Run: python download_models.py")
        exit(1)

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
