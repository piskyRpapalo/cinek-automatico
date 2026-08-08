"""
FASE 5: Orquestador completo de CineK Automático
Pipeline secuencial: prompt → imagen → video → audio → mux final
"""
import sys
import time
from pathlib import Path
import db
import thermal
import jetson_client

def run_pipeline(prompt: str) -> int:
    """Ejecuta el pipeline completo y retorna el job_id"""
    print(f"\n{'='*60}")
    print(f"CINEK AUTOMÁTICO - PIPELINE SECUENCIAL")
    print(f"{'='*60}")
    print(f"Prompt: {prompt}")
    print(f"{'='*60}\n")
    
    # Crear job en SQLite
    job_id = db.create_job(prompt)
    print(f"✅ Job creado: #{job_id}")
    
    # Gate térmico: verificar que el Beelink esté frío
    print("\n[1/6] Gate térmico (Beelink)...")
    gate = thermal.GateTermico()
    gate.esperar_seguro()
    print("✅ Temperatura OK")
    
    # FASE 5.1: Generación de imagen (Jetson SDXL)
    print("\n[2/6] Generación de imagen (Jetson SDXL)...")
    db.set_status(job_id, "GENESIS_RENDERING")
    
    cliente = jetson_client.cliente
    load_result = cliente.carga_modelo("sdxl")
    if load_result.get("estado") != "READY":
        db.set_status(job_id, "STALE_FATAL", last_error="No se pudo cargar SDXL")
        return job_id
    
    image_paths = cliente.genera_imagen(prompt, num=1)
    cliente.purga_modelo()
    
    if not image_paths:
        db.set_status(job_id, "STALE_FATAL", last_error="Generación de imagen falló")
        return job_id
    
    image_path = image_paths[0]
    db.set_status(job_id, "GENESIS_DONE", path_image=str(image_path))
    print(f"✅ Imagen generada: {image_path.name}")
    
    # FASE 5.2: Generación de video (Beelink ComfyUI SVD)
    print("\n[3/6] Generación de video (Beelink ComfyUI SVD)...")
    db.set_status(job_id, "VIDEO_RENDERING")
    print("⚠️  FASE 6 pendiente: implementar video SVD en Beelink")
    print("   Saltando a FASE 5.3 (audio)")
    
    # FASE 5.3: Generación de guion (Beelink Ollama qwen3)
    print("\n[4/6] Generación de guion (Beelink Ollama qwen3)...")
    db.set_status(job_id, "AUDIO_RENDERING")
    guion = f"This is a test script for job {job_id}. The image shows: {prompt}"
    db.set_status(job_id, "AUDIO_DONE", guion=guion)
    print(f"✅ Guion generado: {guion[:50]}...")
    
    # FASE 5.4: Síntesis de voz (Beelink Piper)
    print("\n[5/6] Síntesis de voz (Beelink Piper)...")
    print("⚠️  FASE 7 pendiente: implementar Piper TTS")
    print("   Saltando a FASE 5.5 (QA)")
    
    # FASE 5.5: QA visual (Jetson LLaVA)
    print("\n[6/6] QA visual (Jetson LLaVA)...")
    db.set_status(job_id, "QA_RENDERING")
    
    load_result = cliente.carga_modelo("llava")
    if load_result.get("estado") != "READY":
        db.set_status(job_id, "QA_FAILED", last_error="No se pudo cargar LLaVA")
        cliente.purga_modelo()
        return job_id
    
    image_bytes = image_path.read_bytes()
    qa_result = cliente.qa_visual(image_bytes, contexto=prompt)
    cliente.purga_modelo()
    
    if qa_result.get("passed"):
        db.set_status(job_id, "GOLD", qa_score=qa_result.get("score"), qa_report=qa_result.get("report"))
        print(f"✅ QA PASSED (score: {qa_result.get('score')})")
    else:
        db.set_status(job_id, "QA_FAILED", qa_score=qa_result.get("score"), qa_report=qa_result.get("report"))
        print(f"❌ QA FAILED (score: {qa_result.get('score')})")
    
    return job_id

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 cinek_pipeline.py 'un gato cyberpunk meditando en un jardín japonés'")
        sys.exit(1)
    
    prompt = " ".join(sys.argv[1:])
    job_id = run_pipeline(prompt)
    
    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETADO - Job #{job_id}")
    print(f"{'='*60}")
    
    job = db.get_job(job_id)
    print(f"Status final: {job['status']}")
    print(f"Imagen: {job['path_image']}")
    print(f"QA Score: {job['qa_score']}")
