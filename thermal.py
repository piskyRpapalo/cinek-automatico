"""
FASE 3: Gate térmico k10temp (Beelink)
Doctrina: IronClaw (propone/señaliza, nunca mata) · Honestidad (NO_DATA > dato falso)
Histéresis: >=85 OVERHEAT · >80 FRENO proporcional · <=75 libera freno
"""
import time, json, glob
from pathlib import Path
import config as C
import db

def encontrar_sensor_k10temp() -> Optional[str]:
    """Descubre el path de k10temp dinámicamente. Nunca hardcodea índice."""
    for name_path in glob.glob("/sys/class/hwmon/hwmon*/name"):
        try:
            with open(name_path, "r") as f:
                if f.read().strip() == "k10temp":
                    return name_path.replace("/name", "/temp1_input")
        except OSError:
            continue
    return None  # NO_DATA: el gate no procede

SENSOR_PATH = encontrar_sensor_k10temp()
LOG_PATH = Path.home() / "p0x-soberano" / "logs" / "thermal.jsonl"

class GateTermico:
    def __init__(self, sensor_path: str = SENSOR_PATH):
        self.sensor_path = sensor_path
        self.buf = bytearray(32)
        self.freno_activo = False

    def leer(self):
        if self.sensor_path is None:
            return None  # NO_DATA bloqueante
        try:
            with open(self.sensor_path, "rb") as f:
                n = f.readinto(self.buf)
                if n:
                    return int(bytes(self.buf[:n]).decode().strip()) / 1000.0
        except OSError:
            return None
        return None

    def decidir(self, temp):
        """Puro y testeable: retorna (accion, segundos, mensaje). Sin sleeps."""
        if temp is None:
            return ("NO_DATA", 0, "sensor k10temp ilegible")
        if temp >= C.TEMP_MAX_HARD:
            self.freno_activo = True
            return ("OVERHEAT", 30, f"{temp:.1f}C >= HARD {C.TEMP_MAX_HARD}")
        if temp > C.TEMP_MAX_SOFT:
            self.freno_activo = True
            return ("FRENO", (temp - C.TEMP_MAX_SOFT) * 2, f"{temp:.1f}C > SOFT {C.TEMP_MAX_SOFT}")
        if self.freno_activo:
            if temp <= C.TEMP_RESUME:
                self.freno_activo = False
                return ("PROCEED", 0, f"freno liberado a {temp:.1f}C")
            return ("FRENO", 10, f"freno activo hasta <= {C.TEMP_RESUME}C")
        return ("PROCEED", 0, f"{temp:.1f}C ok")

    def esperar_seguro(self):
        """Bloquea hasta PROCEED. El orquestador lo llama antes de cada fase pesada."""
        while True:
            acc, seg, msg = self.decidir(self.leer())
            self._log(acc, msg)
            if acc == "NO_DATA":
                raise RuntimeError("NO_DATA termico: k10temp ilegible")
            if acc == "PROCEED":
                return
            print(f"[thermal] {acc}: {msg} (sleep {seg:.0f}s)")
            time.sleep(seg)

    def _log(self, acc, msg):
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "accion": acc, "detalle": msg}) + "\n")
        except OSError:
            pass

def registrar_temp_max(job_id: int, temp) -> None:
    """Alimenta la telemetría del job: temperatura máxima alcanzada."""
    if temp is None:
        return
    c = db.conn()
    c.execute("UPDATE cinek_jobs SET temp_max = MAX(COALESCE(temp_max,0), ?) WHERE id=?",
              (temp, job_id))
    c.commit(); c.close()
