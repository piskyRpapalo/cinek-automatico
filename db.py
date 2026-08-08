"""
FASE 2: Modelo de datos para CineK Automático
Tabla cinek_jobs en aurelius_state.db (WAL, busy_timeout=5000)
Estados atómicos para worker polivalente (SDXL o LLaVA, nunca ambos)
"""
import sqlite3
import json
from pathlib import Path
from typing import Optional
import config as C

def conn() -> sqlite3.Connection:
    """Conexión SQLite con WAL y busy_timeout para concurrencia robusta"""
    c = sqlite3.connect(f"file:{C.DB_PATH}?mode=rwc", uri=True, timeout=5.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    c.execute("PRAGMA busy_timeout=5000;")
    return c

def init_schema() -> None:
    """Inicializa la tabla cinek_jobs si no existe"""
    c = conn()
    c.execute("""CREATE TABLE IF NOT EXISTS cinek_jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prompt_original TEXT NOT NULL,
        prompt_video TEXT,
        
        status TEXT DEFAULT 'CREATED' CHECK(status IN (
            'CREATED',
            'GENESIS_RENDERING',    -- Jetson genera 5 imgs con SDXL
            'GENESIS_DONE',         -- 5 imgs listas, esperando seleccion
            'IMAGE_SELECTED',       -- Operador eligio 1 img
            'VIDEO_RENDERING',      -- Beelink ComfyUI genera video (SVD)
            'OVERHEAT',             -- Pausado por temperatura alta
            'VIDEO_DONE',           -- Video listo
            'AUDIO_RENDERING',      -- Piper TTS + FFmpeg mux
            'AUDIO_DONE',           -- Audio pegado
            'QA_RENDERING',         -- Jetson evalua con LLaVA
            'QA_PASSED',            -- Canon OK
            'QA_FAILED',            -- Canon rechazado
            'GOLD',                 -- Aprobado final
            'STALE_FATAL',          -- Error irrecuperable
            'STALE_MAX_INTENTOS'    -- 3 intentos fallidos
        )),
        
        -- Genesis (Jetson SDXL)
        genesis_images TEXT,        -- JSON array de 5 filenames
        selected_image_index INTEGER,
        
        -- Paths
        path_image TEXT,
        path_video TEXT,
        path_audio TEXT,
        path_final TEXT,
        
        -- Doblaje
        audio_cues TEXT,            -- JSON: [{text, start, end}]
        guion TEXT,                 -- Guion generado por qwen3
        
        -- QA (Jetson LLaVA)
        qa_score REAL,
        qa_report TEXT,             -- JSON con metricas del Jetson
        intentos INTEGER DEFAULT 0,
        last_error TEXT,
        
        -- Telemetria (solo termica, solar eliminado)
        temp_max REAL,              -- Temperatura maxima alcanzada durante el job
        
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );""")
    c.commit()
    c.close()

def create_job(prompt: str) -> int:
    """Crea un nuevo job y retorna su ID"""
    init_schema()
    c = conn()
    cur = c.execute("INSERT INTO cinek_jobs(prompt_original) VALUES (?)", (prompt,))
    c.commit()
    job_id = cur.lastrowid
    c.close()
    return job_id

def set_status(job_id: int, status: str, **kwargs) -> None:
    """Actualiza el status y campos opcionales de un job"""
    c = conn()
    updates = ["status=?", "updated_at=CURRENT_TIMESTAMP"]
    values = [status]
    
    for key, value in kwargs.items():
        if value is not None:
            updates.append(f"{key}=?")
            if isinstance(value, (dict, list)):
                values.append(json.dumps(value))
            else:
                values.append(value)
    
    values.append(job_id)
    c.execute(f"UPDATE cinek_jobs SET {', '.join(updates)} WHERE id=?", values)
    c.commit()
    c.close()

def get_job(job_id: int) -> Optional[dict]:
    """Retorna un job por ID"""
    c = conn()
    row = c.execute("SELECT * FROM cinek_jobs WHERE id=?", (job_id,)).fetchone()
    c.close()
    return dict(row) if row else None

def get_latest_job() -> Optional[dict]:
    """Retorna el job más reciente"""
    c = conn()
    row = c.execute("SELECT * FROM cinek_jobs ORDER BY id DESC LIMIT 1").fetchone()
    c.close()
    return dict(row) if row else None

# === HERBIER BOTÁNICO (FASE 2.5) ===
def init_herbier_schema() -> None:
    """Inicializa la tabla herbier_diagnosticos si no existe"""
    c = conn()
    c.execute("""CREATE TABLE IF NOT EXISTS herbier_diagnosticos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        foto_path TEXT NOT NULL,           -- Ruta en ~/p0x-soberano/cinek_outputs/herbier/
        foto_hash TEXT,                    -- SHA-256 de la foto (futuro)
        especie_detectada TEXT,            -- 'Ficus lyrata', 'Monstera deliciosa', etc.
        diagnostico TEXT,                  -- Texto libre del Jetson (LLaVA)
        estado_salud TEXT CHECK(estado_salud IN ('sano', 'atencion', 'critico', 'desconocido')),
        recomendacion TEXT,                -- Consejo de cuidado
        confianza REAL,                    -- 0.0 a 1.0 (score del modelo)
        jetson_latency_ms INTEGER,         -- Tiempo de inferencia en Jetson
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_herbier_created ON herbier_diagnosticos(created_at DESC);")
    c.commit()
    c.close()

def create_diagnostico(foto_path: str, especie: str, diagnostico: str, 
                       estado_salud: str, recomendacion: str, 
                       confianza: float = 0.0, jetson_latency_ms: int = 0) -> int:
    """Crea un nuevo diagnóstico botánico"""
    init_herbier_schema()
    c = conn()
    cur = c.execute("""INSERT INTO herbier_diagnosticos 
                       (foto_path, especie_detectada, diagnostico, estado_salud, 
                        recomendacion, confianza, jetson_latency_ms) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (foto_path, especie, diagnostico, estado_salud, 
                     recomendacion, confianza, jetson_latency_ms))
    c.commit()
    diag_id = cur.lastrowid
    c.close()
    return diag_id

def get_ultimos_diagnosticos(limit: int = 10) -> list:
    """Retorna los N diagnósticos más recientes"""
    init_herbier_schema()
    c = conn()
    rows = c.execute("""SELECT * FROM herbier_diagnosticos 
                        ORDER BY created_at DESC LIMIT ?""", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]
