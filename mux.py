"""
FASE 8: Mux de video + audio con FFmpeg
"""
import subprocess
import time
from pathlib import Path

def mux_video_audio(video_path: Path, audio_path: Path, output_dir: Path = None) -> Path:
    """
    Une video + audio en un archivo .mp4 final.
    Retorna el path del video final.
    """
    if output_dir is None:
        output_dir = Path("outputs/gold")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    final_path = output_dir / f"final_{int(time.time())}.mp4"
    
    # Ejecutar FFmpeg
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        "-y",
        str(final_path)
    ]
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=120
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg falló: {result.stderr.decode()}")
    
    if not final_path.exists() or final_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg no generó archivo final")
    
    return final_path
