"""
FASE 7: Síntesis de voz con Piper TTS
"""
import subprocess
import time
from pathlib import Path
import config as C

PIPER_MODEL_PATH = Path.home() / ".local" / "share" / "piper" / "voices" / f"{C.VOZ_PIPER}.onnx"

def generar_audio(guion: str, output_dir: Path = None) -> Path:
    """
    Genera archivo .wav desde texto usando Piper TTS.
    Retorna el path del audio .wav generado.
    """
    if not PIPER_MODEL_PATH.exists():
        raise RuntimeError(f"Modelo Piper no encontrado: {PIPER_MODEL_PATH}")
    
    if output_dir is None:
        output_dir = Path("outputs/audio")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    audio_path = output_dir / f"audio_{int(time.time())}.wav"
    
    # Ejecutar Piper TTS
    cmd = [
        "piper",
        "--model", str(PIPER_MODEL_PATH),
        "--output_file", str(audio_path)
    ]
    
    result = subprocess.run(
        cmd,
        input=guion.encode('utf-8'),
        capture_output=True,
        timeout=120
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"Piper TTS falló: {result.stderr.decode()}")
    
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError("Piper TTS no generó archivo de audio")
    
    return audio_path
