from pathlib import Path

# === BEELINK (ORQUESTADOR) ===
BEELINK_IP = "100.81.82.34"
BEELINK_FASTAPI_PORT = 8050
COMFYUI_BEELINK_PORT = 8188
OLLAMA_BEELINK_PORT = 11434
COMFY_OUTPUT_BEELINK = Path.home() / "ComfyUI" / "output" / "cinek"

# === JETSON (WORKER POLIVALENTE) ===
JETSON_IP = "100.101.96.13"
JETSON_USER = "jetson"
JETSON_WORKER_PORT = 8000  # API custom que construiremos en FASE 4
JETSON_COMFYUI_PORT = 8188  # ComfyUI ya corre aquí

# === MODELOS ===
SDXL_CHECKPOINT = "sd_xl_base_1.0.safetensors"
LLAVA_MODEL = "llava:7b"
QWEN_MODEL = "qwen3"  # Para guion (Beelink)
VOZ_PIPER = "en_US-kathleen-low"

# === GATE TÉRMICO (solo Beelink) ===
TEMP_MAX_HARD = 85.0
TEMP_MAX_SOFT = 80.0
TEMP_RESUME = 75.0

# === WORKER POLIVALENTE (Jetson) ===
# El Jetson carga UN modelo a la vez:
# - SDXL: ~6.5GB VRAM (generación de imagen)
# - LLaVA: ~4.5GB VRAM (QA visual)
# Nunca ambos simultáneamente.
WORKER_MODELS = {
    "sdxl": {"vram_gb": 6.5, "task": "image_generation"},
    "llava": {"vram_gb": 4.5, "task": "qa_visual"}
}

# === ESTADO ===
DB_PATH = Path.home() / "p0x-soberano" / "db" / "aurelius_state.db"
MAX_INTENTOS = 3
QA_MIN_SCORE = 8.0
