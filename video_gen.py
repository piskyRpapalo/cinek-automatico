"""
FASE 6: Generación de video con SVD en Beelink ComfyUI
"""
import json
import time
import requests
from pathlib import Path
import config as C

COMFYUI_URL = f"http://127.0.0.1:{C.COMFYUI_BEELINK_PORT}"
WORKFLOW_VIDEO_PATH = Path(__file__).parent / "comfy_workflows" / "video_workflow.json"

def generar_video(image_path: Path, output_dir: Path = None) -> Path:
    """
    Genera video SVD desde una imagen estática.
    Retorna el path del video .mp4 generado.
    """
    if not WORKFLOW_VIDEO_PATH.exists():
        raise RuntimeError(f"Workflow no encontrado: {WORKFLOW_VIDEO_PATH}")
    
    # Cargar workflow
    workflow = json.loads(WORKFLOW_VIDEO_PATH.read_text())
    
    # Inyectar nombre de imagen (solo el filename, no el path completo)
    image_filename = image_path.name
    for node_id, node in workflow.items():
        if node.get("class_type") == "LoadImage":
            node["inputs"]["image"] = image_filename
            break
    
    # Copiar imagen al directorio de input de ComfyUI
    comfy_input_dir = Path.home() / "ComfyUI" / "input"
    comfy_input_dir.mkdir(exist_ok=True)
    dest_path = comfy_input_dir / image_filename
    if not dest_path.exists():
        import shutil
        shutil.copy2(image_path, dest_path)
    
    # Enviar a ComfyUI
    r = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
    r.raise_for_status()
    prompt_id = r.json()["prompt_id"]
    
    # Esperar a que termine (polling /history)
    print(f"   Generando video (prompt_id: {prompt_id[:8]}...)")
    for i in range(120):  # 10 min max
        time.sleep(5)
        h = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10).json()
        if prompt_id in h:
            outputs = h[prompt_id].get("outputs", {})
            for node_id, node_out in outputs.items():
                if "gifs" in node_out:
                    for video in node_out["gifs"]:
                        filename = video["filename"]
                        subfolder = video.get("subfolder", "")
                        # Descargar video
                        video_url = f"{COMFYUI_URL}/view?filename={filename}&subfolder={subfolder}&type=output"
                        video_r = requests.get(video_url, timeout=30)
                        video_r.raise_for_status()
                        
                        # Guardar localmente
                        if output_dir is None:
                            output_dir = Path("outputs/videos")
                        output_dir.mkdir(parents=True, exist_ok=True)
                        video_path = output_dir / f"video_{int(time.time())}.mp4"
                        video_path.write_bytes(video_r.content)
                        
                        return video_path
    
    raise TimeoutError("ComfyUI no respondió en 10 min")
