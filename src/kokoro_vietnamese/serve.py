from __future__ import annotations

import argparse
import io
import os
import numpy as np
import soundfile as sf
from typing import Literal, Any

try:
    from fastapi import FastAPI, Response, HTTPException
    from pydantic import BaseModel, Field
    import uvicorn
except ImportError:
    raise ImportError("Please install fastapi, uvicorn and pydantic to run the server. Run: pip install -e \".[serve]\"")

from .core import (
    DEFAULT_CROSSFADE_MS,
    DEFAULT_HF_REPO_ID,
    DEFAULT_VOICE,
    SAMPLE_RATE,
    VOICES,
    resolve_voicepack_filename,
    _download_or_resolve,
    DEFAULT_VOICEPACK_FILE,
)
from .onnx_cli import KokoroVietnameseONNX
from .onnx_utils import phonemes_to_input_ids, select_voice_style, speed_input
from .core import split_text, phonemize, merge_audio_chunks

# Global variables to store the single model instance and cached voicepacks
tts_instance: KokoroVietnameseONNX | None = None
voicepacks: dict[str, Any] = {}
repo_id_global: str = DEFAULT_HF_REPO_ID

app = FastAPI(title="Kokoro Vietnamese TTS Server (ONNX)", version="1.0.0")

class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Nội dung văn bản TTS")
    voice: str = Field(DEFAULT_VOICE, description="Giọng đọc (ví dụ: diem_trinh, hung_thinh...)")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Tốc độ đọc")
    response_format: Literal["wav"] = Field("wav", description="Định dạng output")

def get_voicepack(voice_name: str) -> Any:
    global voicepacks
    # Fallback if voice not found
    if voice_name not in VOICES:
        voice_name = DEFAULT_VOICE
    
    voicepack_filename = resolve_voicepack_filename(voice_name, None)
    if voicepack_filename not in voicepacks:
        from pathlib import Path
        pkg_root = Path(__file__).parent.parent.parent
        local_models_dir = pkg_root / 'models'
        local_npy_path = (local_models_dir / voicepack_filename).with_suffix('.npy')
        
        if local_npy_path.exists():
            voicepacks[voicepack_filename] = np.load(local_npy_path)
        else:
            vp_path = _download_or_resolve(repo_id_global, DEFAULT_VOICEPACK_FILE, voicepack_filename)
            npy_path = vp_path.with_suffix('.npy')
            if npy_path.exists():
                voicepacks[voicepack_filename] = np.load(npy_path)
            else:
                import torch
                voicepacks[voicepack_filename] = torch.load(vp_path, map_location='cpu', weights_only=True)
    
    return voicepacks[voicepack_filename]

def synthesize_with_voicepack_onnx(
    tts: KokoroVietnameseONNX,
    voicepack: Any,
    text: str,
    speed: float = 1.0,
    crossfade_ms: int = DEFAULT_CROSSFADE_MS,
) -> tuple[np.ndarray, str]:
    audio_chunks: list[np.ndarray] = []
    phoneme_chunks: list[str] = []
    speed_value = speed_input(speed)
    for index, text_chunk in enumerate(split_text(text), start=1):
        ps = phonemize(text_chunk)
        if not ps:
            continue
        phoneme_chunks.append(f'[{index}] {ps}')
        input_ids = phonemes_to_input_ids(
            ps,
            tts.config['vocab'],
            context_length=tts.context_length,
        )
        ref_s = select_voice_style(voicepack, len(ps))
        waveform, _duration = tts.session.run(
            None,
            {
                'input_ids': input_ids,
                'ref_s': ref_s,
                'speed': speed_value,
            },
        )
        audio_chunks.append(np.asarray(waveform, dtype=np.float32).reshape(-1))

    crossfade_samples = round(SAMPLE_RATE * int(crossfade_ms) / 1000)
    return merge_audio_chunks(audio_chunks, crossfade_samples), '\n'.join(phoneme_chunks)

@app.get("/health")
@app.get("/v1/health")
def health():
    return {"ok": True, "status": "healthy"}

@app.post("/v1/tts")
async def tts_endpoint(req: TTSRequest):
    global tts_instance
    if tts_instance is None:
        raise HTTPException(status_code=500, detail="TTS Model is not loaded")
    
    try:
        voicepack = get_voicepack(req.voice)
        audio, phonemes = synthesize_with_voicepack_onnx(
            tts=tts_instance,
            voicepack=voicepack,
            text=req.text,
            speed=req.speed,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")

    if len(audio) == 0:
        raise HTTPException(status_code=500, detail="Generated audio is empty")

    buffer = io.BytesIO()
    sf.write(buffer, audio, SAMPLE_RATE, format="WAV")
    
    return Response(
        content=buffer.getvalue(),
        media_type="audio/wav"
    )

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Launch Kokoro Vietnamese ONNX API server')
    parser.add_argument('--repo-id', default=DEFAULT_HF_REPO_ID)
    parser.add_argument('--device', default='cpu', choices=['cuda', 'cpu'])
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=7888)
    return parser

def main(argv: list[str] | None = None) -> int:
    global tts_instance, repo_id_global
    args = build_parser().parse_args(argv)
    
    repo_id_global = args.repo_id
    print(f"Loading Kokoro Vietnamese ONNX model ({args.device})...")
    tts_instance = KokoroVietnameseONNX(repo_id=args.repo_id, device=args.device)
    
    # Warm up default voice
    get_voicepack(DEFAULT_VOICE)
    
    print(f"Starting server at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
