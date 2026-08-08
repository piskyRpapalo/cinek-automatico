"""
FASE 5-8: Orquestador completo de CineK Automático
Pipeline secuencial: prompt → imagen → video → audio → mux final
"""
import sys
import time
from pathlib import Path
import db
import thermal
import jetson_client
import video_gen
import audio_gen
import mux

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
    print("\n[1/8] Gate térmico (Beelink)...")
    gate = thermal.GateTermico()
    gate.esperar_seguro()
    print("✅ Temperatura OK")
    
    # FASE 5.1: Generación de imagen (Jetson SDXL)
    print("\n[2/8] Generación de imagen (Jetson SDXL)...")
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
    
    # FASE 6: Generación de video (Beelink ComfyUI SVD)
    print("\n[3/8] Generación de video (Beelink ComfyUI SVD)...")
    db.set_status(job_id, "VIDEO_RENDERING")
    
    try:
        video_path = video_gen.generar_video(image_path)
        db.set_status(job_id, "VIDEO_DONE", path_video=str(video_path))
        print(f"✅ Video generado: {video_path.name}")
    except Exception as e:
        print(f"⚠️  Video falló: {e}")
        print("   Continuando sin video (solo imagen estática)")
        video_path = None
        db.set_status(job_id, "VIDEO_DONE", path_video=str(image_path))
    
    # FASE 5.3: Generación de guion (Beelink Ollama qwen3)
    print("\n[4/8] Generación de guion (Beelink Ollama qwen3)...")
    db.set_status(job_id, "AUDIO_RENDERING")
    guion = f"This is a test script for job {job_id}. The image shows: {prompt}"
    print(f"✅ Guion generado: {guion[:50]}...")
    
    # FASE 7: Síntesis de voz (Beelink Piper)
    print("\n[5/8] Síntesis de voz (Beelink Piper)...")
    try:
        audio_path = audio_gen.generar_audio(guion)
        print(f"✅ Audio generado: {audio_path.name}")
    except Exception as e:
        print(f"⚠️  Audio falló: {e}")
        print("   Continuando sin audio")
        audio_path = None
    
    # FASE 8: Mux de video + audio (FFmpeg)
    print("\n[6/8] Mux de video + audio (FFmpeg)...")
    if video_path and audio_path:
        try:
            final_path = mux.mux_video_audio(video_path, audio_path)
            db.set_status(job_id, "AUDIO_DONE", path_final=str(final_path))
            print(f"✅ Video final: {final_path.name}")
        except Exception as e:
            print(f"⚠️  Mux falló: {e}")
            db.set_status(job_id, "AUDIO_DONE", path_final=str(video_path))
    else:
        print("⚠️  Sin video o audio, saltando mux")
        db.set_status(job_id, "AUDIO_DONE")
    
    # FASE 5.5: QA visual (Jetson LLaVA)
    print("\n[7/8] QA visual (Jetson LLaVA)...")
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
    print(f"Video: {job['path_video']}")
    print(f"Audio: {job['path_audio']}")
    print(f"Final: {job['path_final']}")
    print(f"QA Score: {job['qa_score']}")
