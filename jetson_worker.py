"""
FASE 4: Worker polivalente del Jetson Orin Nano
Se ejecuta EN EL JETSON, escucha en :8000 (Tailscale)
Delega a:
  - ComfyUI (:8188) para SDXL (imagen)
  - Ollama (:11434) para LLaVA (QA + herbier)
Máquina de estados: IDLE → LOADING → READY → PURGING
"""
import json
import time
import subprocess
import tempfile
import base64
from pathlib import Path
from typing import Optional, Dict
from threading import Lock
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
import requests
import uvicorn

# === CONFIGURACIÓN (ajustar según el Jetson real) ===
COMFYUI_URL = "http://127.0.0.1:8188"
OLLAMA_URL = "http://127.0.0.1:11434"
COMFYUI_OUTPUT_DIR = Path.home() / "ComfyUI" / "output"
WORKFLOW_IMAGE_PATH = Path(__file__).parent / "comfy_workflows" / "image_workflow.json"
PURGE_TIMEOUT_SEC = 300  # 5 minutos sin uso → purgar automáticamente

# === ESTADO GLOBAL DEL WORKER ===
class WorkerState:
    def __init__(self):
        self.modelo_actual: Optional[str] = None  # "sdxl" | "llava" | None
        self.ultimo_uso: float = 0.0
        self.lock = Lock()
        self.vram_usada_gb: float = 0.0
    
    def marcar_uso(self):
        self.ultimo_uso = time.time()
    
    def debe_purgar(self) -> bool:
        return (self.modelo_actual is not None and
                time.time() - self.ultimo_uso > PURGE_TIMEOUT_SEC)

state = WorkerState()
app = FastAPI(title="CineK Jetson Worker", version="1.0")

# === MIDDLEWARE: PURGA AUTOMÁTICA POR INACTIVIDAD ===
@app.middleware("http")
async def auto_purge_middleware(request, call_next):
    if state.debe_purgar():
        print(f"[worker] Purga automática tras {PURGE_TIMEOUT_SEC}s de inactividad")
        _purga_interna()
    response = await call_next(request)
    return response

# === ENDPOINTS ===
@app.get("/health")
def health():
    return {"status": "ok", "worker": "jetson", "ts": time.time()}

@app.get("/status")
def status():
    return {
        "modelo_cargado": state.modelo_actual,
        "vram_usada_gb": state.vram_usada_gb,
        "segundos_inactivo": time.time() - state.ultimo_uso if state.modelo_actual else 0,
        "comfyui_vivo": _ping(COMFYUI_URL),
        "ollama_vivo": _ping(OLLAMA_URL),
    }

@app.post("/load-model")
def load_model(payload: Dict):
    """Carga SDXL o LLaVA en VRAM. Bloqueante, serializado."""
    with state.lock:
        modelo = payload.get("modelo")
        if modelo not in ("sdxl", "llava"):
            return JSONResponse({"error": f"modelo inválido: {modelo}"}, status_code=400)
        
        # Si ya está cargado, no hacer nada
        if state.modelo_actual == modelo:
            state.marcar_uso()
            return {"estado": "READY", "modelo": modelo, "mensaje": "ya cargado"}
        
        # Purgar modelo anterior si existe
        if state.modelo_actual is not None:
            _purga_interna()
        
        # Cargar nuevo modelo
        try:
            if modelo == "sdxl":
                # Cargar SDXL en ComfyUI via workflow vacío (warmup)
                _warmup_comfyui_sdxl()
                state.vram_usada_gb = 6.5
            elif modelo == "llava":
                # Cargar LLaVA en Ollama
                _warmup_ollama_llava()
                state.vram_usada_gb = 4.5
            
            state.modelo_actual = modelo
            state.marcar_uso()
            return {"estado": "READY", "modelo": modelo, "vram_gb": state.vram_usada_gb}
        except Exception as e:
            return JSONResponse({"error": str(e), "estado": "LOAD_FAILED"}, status_code=500)

@app.post("/purge-model")
def purge_model():
    """Libera VRAM explícitamente"""
    with state.lock:
        _purga_interna()
    return {"estado": "IDLE", "modelo": None, "vram_gb": 0.0}

@app.post("/generate-image")
def generate_image(payload: Dict):
    """Genera imagen con SDXL vía ComfyUI. Requiere modelo 'sdxl' cargado."""
    with state.lock:
        if state.modelo_actual != "sdxl":
            return JSONResponse({"error": "modelo 'sdxl' no cargado. Llama /load-model primero."},
                                status_code=400)
        state.marcar_uso()
    
    prompt = payload.get("prompt")
    num = payload.get("num", 1)
    seed = payload.get("seed")
    
    try:
        image_urls = _genera_comfyui(prompt, num, seed)
        return {"estado": "DONE", "image_urls": image_urls, "count": len(image_urls)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/herbier-diagnose")
async def herbier_diagnose(foto: UploadFile = File(...)):
    """Diagnóstico botánico con LLaVA vía Ollama"""
    with state.lock:
        if state.modelo_actual != "llava":
            return JSONResponse({"error": "modelo 'llava' no cargado"}, status_code=400)
        state.marcar_uso()
    
    foto_bytes = await foto.read()
    b64 = base64.b64encode(foto_bytes).decode()
    
    try:
        prompt_img = (
            "Analiza esta planta. Responde EXACTAMENTE en este formato (una línea por campo):\n"
            "Especie: <nombre científico o común>\n"
            "Estado: <sano|atencion|critico>\n"
            "Diagnostico: <qué observas en hojas, tallo, tierra>\n"
            "Recomendacion: <consejo de cuidado>\n"
        )
        respuesta = _query_ollama_llava(prompt_img, b64)
        return {"estado": "DONE", "diagnostico": respuesta}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/qa-visual")
async def qa_visual(imagen: UploadFile = File(...), contexto: str = Form("")):
    """QA de frame de video con LLaVA vía Ollama"""
    with state.lock:
        if state.modelo_actual != "llava":
            return JSONResponse({"error": "modelo 'llava' no cargado"}, status_code=400)
        state.marcar_uso()
    
    img_bytes = await imagen.read()
    b64 = base64.b64encode(img_bytes).decode()
    
    try:
        prompt_qa = (
            "Evalúa la calidad visual de este frame de video generado por IA. "
            f"Contexto: {contexto}. Responde EXACTAMENTE:\n"
            "Score: <número del 1 al 10>\n"
            "Report: <breve justificación>\n"
            "Passed: <true|false si score >= 8>\n"
        )
        respuesta = _query_ollama_llava(prompt_qa, b64)
        score = _parse_score(respuesta)
        return {
            "estado": "DONE",
            "score": score,
            "passed": score >= 8.0,
            "report": respuesta
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# === FUNCIONES INTERNAS ===
def _ping(url: str) -> bool:
    try:
        r = requests.get(f"{url}/", timeout=3)
        return r.status_code < 500
    except:
        return False

def _purga_interna():
    """Libera VRAM: ComfyUI (unload) + Ollama (keep_alive=0)"""
    state.modelo_actual = None
    state.vram_usada_gb = 0.0
    try:
        # Descargar modelos de Ollama
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": "llava:7b", "keep_alive": 0}, timeout=10)
    except:
        pass
    # ComfyUI no tiene API de unload directa; el timeout interno lo gestiona

def _warmup_comfyui_sdxl():
    """Verifica que ComfyUI tiene SDXL cargable (no hace inferencia aún)"""
    r = requests.get(f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple", timeout=10)
    r.raise_for_status()
    info = r.json()
    # Verificar que sd_xl_base_1.0.safetensors está en la lista
    checkpoints = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    if "sd_xl_base_1.0.safetensors" not in checkpoints:
        raise RuntimeError("Checkpoint SDXL no encontrado en ComfyUI")

def _warmup_ollama_llava():
    """Carga LLaVA en Ollama (hace una inferencia dummy para forzar carga en VRAM)"""
    r = requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": "llava:7b", "prompt": "warmup", "stream": False},
                      timeout=120)
    r.raise_for_status()

def _genera_comfyui(prompt: str, num: int, seed: Optional[int]) -> list:
    """Envía workflow de SDXL a ComfyUI y espera resultados"""
    if not WORKFLOW_IMAGE_PATH.exists():
        raise RuntimeError(f"Workflow no encontrado: {WORKFLOW_IMAGE_PATH}")
    workflow = json.loads(WORKFLOW_IMAGE_PATH.read_text())
    workflow = _inject_prompt(workflow, prompt)
    if seed is not None:
        workflow = _inject_seed(workflow, seed)
    
    # Enviar a la cola
    r = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
    r.raise_for_status()
    prompt_id = r.json()["prompt_id"]
    
    # Esperar a que termine (polling /history)
    urls = []
    for _ in range(120):  # 10 min max
        time.sleep(5)
        h = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10).json()
        if prompt_id in h:
            outputs = h[prompt_id].get("outputs", {})
            for node_id, node_out in outputs.items():
                for img in node_out.get("images", []):
                    filename = img["filename"]
                    subfolder = img.get("subfolder", "")
                    url = f"{COMFYUI_URL}/view?filename={filename}&subfolder={subfolder}&type=output"
                    urls.append(url)
            if urls:
                return urls[:num]
    raise TimeoutError("ComfyUI no respondió en 10 min")

def _inject_prompt(workflow: dict, prompt: str) -> dict:
    """Reemplaza __PROMPT__ en el nodo CLIPTextEncode positivo"""
    for node_id, node in workflow.items():
        if node.get("class_type") == "CLIPTextEncode":
            inputs = node.get("inputs", {})
            if inputs.get("text") == "__PROMPT__":
                inputs["text"] = prompt
                break
    return workflow

def _inject_seed(workflow: dict, seed: int) -> dict:
    """Inyecta seed fija en KSampler si existe"""
    for node_id, node in workflow.items():
        if node.get("class_type") == "KSampler":
            node.setdefault("inputs", {})["seed"] = seed
            break
    return workflow

def _query_ollama_llava(prompt: str, image_b64: str) -> str:
    r = requests.post(f"{OLLAMA_URL}/api/generate", json={
        "model": "llava:7b",
        "prompt": prompt,
        "images": [image_b64],
        "stream": False
    }, timeout=300)
    r.raise_for_status()
    return r.json().get("response", "")

def _parse_score(texto: str) -> float:
    """Extrae el score numérico del texto de LLaVA"""
    import re
    m = re.search(r"Score:\s*(\d+(?:\.\d+)?)", texto, re.I)
    if m:
        return min(10.0, max(0.0, float(m.group(1))))
    return 0.0

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
