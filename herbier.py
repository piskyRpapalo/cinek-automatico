"""
FASE 2.5: Botánico de Bolsillo
Beelink = cartero (recibe foto, guarda en Bronze, delega a Jetson, renderiza en ficha)
Jetson = worker polivalente (carga LLaVA una vez, sirve QA + botánico)
"""
import os
import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
import config as C
import db

HERBIER_OUTPUT_DIR = Path.home() / "p0x-soberano" / "cinek_outputs" / "herbier"

def guardar_foto_bronce(foto_bytes: bytes, extension: str = ".jpg") -> Path:
    """Guarda la foto en Bronze (~/p0x-soberano/cinek_outputs/herbier/)"""
    HERBIER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    foto_hash = hashlib.sha256(foto_bytes).hexdigest()[:16]
    filename = f"planta_{timestamp}_{foto_hash}{extension}"
    foto_path = HERBIER_OUTPUT_DIR / filename
    with open(foto_path, "wb") as f:
        f.write(foto_bytes)
    return foto_path

def guardar_sidecar_json(foto_path: Path, diagnostico: dict) -> None:
    """Guarda un JSON sidecar junto a la foto con metadatos del diagnóstico"""
    sidecar_path = foto_path.with_suffix(".json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(diagnostico, f, indent=2, ensure_ascii=False)

def parse_diagnostico_jetson(raw_response: str) -> dict:
    """Parsea la respuesta del Jetson (LLaVA) en un dict estructurado"""
    # El Jetson devolverá algo como:
    # "Especie: Ficus lyrata\nEstado: atencion\nDiagnóstico: Manchas marrones..."
    lineas = raw_response.strip().split("\n")
    resultado = {
        "especie": "Desconocida",
        "estado_salud": "desconocido",
        "diagnostico": raw_response,
        "recomendacion": "",
        "confianza": 0.0
    }
    for linea in lineas:
        if ":" in linea:
            clave, valor = linea.split(":", 1)
            clave = clave.strip().lower()
            valor = valor.strip()
            if "especie" in clave or "species" in clave:
                resultado["especie"] = valor
            elif "estado" in clave or "status" in clave:
                if any(w in valor.lower() for w in ["sano", "healthy", "bien"]):
                    resultado["estado_salud"] = "sano"
                elif any(w in valor.lower() for w in ["atencion", "warning", "cuidado"]):
                    resultado["estado_salud"] = "atencion"
                elif any(w in valor.lower() for w in ["critico", "critical", "grave"]):
                    resultado["estado_salud"] = "critico"
            elif "diagnostico" in clave or "diagnosis" in clave:
                resultado["diagnostico"] = valor
            elif "recomendacion" in clave or "recommendation" in clave:
                resultado["recomendacion"] = valor
    return resultado

async def diagnostica_planta(foto_bytes: bytes) -> dict:
    """
    Flujo completo:
    1. Guarda foto en Bronze
    2. Delega al Jetson (endpoint /herbier-diagnose)
    3. Parsea respuesta
    4. Guarda sidecar JSON
    5. Inserta en SQLite
    6. Retorna dict completo
    """
    # 1. Guardar en Bronze
    foto_path = guardar_foto_bronce(foto_bytes)
    print(f"📸 Foto guardada: {foto_path}")
    
    # 2. Delegar al Jetson (placeholder - se implementa en FASE 4)
    # response = requests.post(f"http://{C.JETSON_IP}:{C.JETSON_WORKER_PORT}/herbier-diagnose", 
    #                          files={"foto": foto_bytes})
    # raw_response = response.json()["diagnostico"]
    
    # MOCK para desarrollo (sin Jetson aún)
    raw_response = """Especie: Ficus lyrata
Estado: atencion
Diagnostico: Manchas marrones en las hojas inferiores. Posible exceso de riego o falta de drenaje.
Recomendacion: Dejar secar el sustrato 5 dias antes de regar de nuevo. Verificar que la maceta tenga agujeros de drenaje."""
    
    # 3. Parsear respuesta
    diagnostico = parse_diagnostico_jetson(raw_response)
    diagnostico["foto_path"] = str(foto_path)
    diagnostico["jetson_latency_ms"] = 1500  # Mock
    
    # 4. Guardar sidecar JSON
    guardar_sidecar_json(foto_path, diagnostico)
    print(f"📄 Sidecar JSON guardado: {foto_path.with_suffix('.json')}")
    
    # 5. Insertar en SQLite
    diag_id = db.create_diagnostico(
        foto_path=str(foto_path),
        especie=diagnostico["especie"],
        diagnostico=diagnostico["diagnostico"],
        estado_salud=diagnostico["estado_salud"],
        recomendacion=diagnostico["recomendacion"],
        confianza=diagnostico["confianza"],
        jetson_latency_ms=diagnostico["jetson_latency_ms"]
    )
    diagnostico["id"] = diag_id
    
    print(f"✅ Diagnóstico #{diag_id} guardado en SQLite")
    return diagnostico
