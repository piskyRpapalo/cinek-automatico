"""
FASE 4: Cliente remoto del worker polivalente del Jetson
Doctrina: IronClaw (el Jetson propone imágenes, el Beelink firma)
         Honestidad (NO_DATA si el Jetson no responde)
Transporte: HTTP sobre Tailscale (100.101.96.13:8000)
"""
import requests
import time
from pathlib import Path
from typing import Optional, List, Dict
import config as C

WORKER_URL = f"http://{C.JETSON_IP}:{C.JETSON_WORKER_PORT}"
TIMEOUT = 60  # Segundos para esperar respuesta del Jetson

class JetsonClient:
    def __init__(self, url: str = WORKER_URL, timeout: int = TIMEOUT):
        self.url = url
        self.timeout = timeout
        self.session = requests.Session()
    
    def ping(self) -> bool:
        """Verifica si el worker del Jetson está vivo"""
        try:
            r = self.session.get(f"{self.url}/health", timeout=5)
            return r.status_code == 200
        except requests.RequestException:
            return False
    
    def estado(self) -> Dict:
        """Retorna el estado actual del worker (modelo cargado, VRAM, etc.)"""
        try:
            r = self.session.get(f"{self.url}/status", timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e), "estado": "NO_DATA"}
    
    def carga_modelo(self, modelo: str) -> Dict:
        """Carga SDXL o LLaVA en el Jetson. Bloqueante."""
        if modelo not in C.WORKER_MODELS:
            raise ValueError(f"Modelo desconocido: {modelo}. Válidos: {list(C.WORKER_MODELS.keys())}")
        try:
            r = self.session.post(f"{self.url}/load-model", json={"modelo": modelo}, timeout=300)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e), "estado": "LOAD_FAILED"}
    
    def purga_modelo(self) -> Dict:
        """Libera VRAM del Jetson"""
        try:
            r = self.session.post(f"{self.url}/purge-model", timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}
    
    def genera_imagen(self, prompt: str, num: int = 1, seed: Optional[int] = None) -> List[Path]:
        """
        Delega generación de imagen a SDXL en el Jetson.
        Retorna lista de Paths locales en Beelink (outputs/genesis/).
        """
        payload = {"prompt": prompt, "num": num}
        if seed is not None:
            payload["seed"] = seed
        try:
            r = self.session.post(f"{self.url}/generate-image", json=payload, timeout=600)
            r.raise_for_status()
            data = r.json()
            
            # Descargar imágenes al Beelink
            paths = []
            for img_url in data.get("image_urls", []):
                img_r = self.session.get(img_url, timeout=30)
                img_r.raise_for_status()
                filename = f"genesis_{int(time.time())}_{len(paths)}.png"
                local_path = Path("outputs/genesis") / filename
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(img_r.content)
                paths.append(local_path)
            return paths
        except Exception as e:
            print(f"❌ Error generando imagen: {e}")
            return []
    
    def diagnostica_herbier(self, foto_bytes: bytes) -> Dict:
        """
        Envía foto al Jetson para diagnóstico botánico (LLaVA).
        Retorna dict con: especie, estado_salud, diagnostico, recomendacion, confianza.
        """
        try:
            files = {"foto": ("planta.jpg", foto_bytes, "image/jpeg")}
            r = self.session.post(f"{self.url}/herbier-diagnose", files=files, timeout=300)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e), "estado_salud": "desconocido",
                    "especie": "NO_DATA", "diagnostico": f"Jetson no responde: {e}"}
    
    def qa_visual(self, imagen_bytes: bytes, contexto: str = "") -> Dict:
        """
        Envía frame de video al Jetson para QA con LLaVA.
        Retorna dict con: score (0-10), report (texto), passed (bool).
        """
        try:
            files = {"imagen": ("frame.png", imagen_bytes, "image/png")}
            data = {"contexto": contexto}
            r = self.session.post(f"{self.url}/qa-visual", files=files, data=data, timeout=300)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e), "score": 0.0, "passed": False,
                    "report": f"Jetson no responde: {e}"}

# Instancia singleton para uso en el orquestador
cliente = JetsonClient()

def wait_for_jetson(max_wait: int = 60) -> bool:
    """Espera a que el worker del Jetson esté disponible"""
    inicio = time.time()
    while time.time() - inicio < max_wait:
        if cliente.ping():
            return True
        time.sleep(2)
    return False
