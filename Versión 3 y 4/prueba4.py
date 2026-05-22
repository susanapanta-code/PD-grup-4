from __future__ import annotations

import argparse
import math
import threading
import time
from typing import Optional
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dronLink.Dron import Dron

# =========================
# CONFIG
# =========================
#LEADER_CONNECTION   = "udp:127.0.0.1:14551"
LEADER_CONNECTION   = "tcp:127.0.0.1:5762"
#FOLLOWER_CONNECTION = "udp:127.0.0.1:14561"
FOLLOWER_CONNECTION = "tcp:127.0.0.1:5772"
#BAUDIOS = 57600
BAUDIOS = 115200

# Geofence NW points to compute map offset
LEADER_GEOFENCE_NW_LAT = 41.2764287
LEADER_GEOFENCE_NW_LON = 1.9882478
FOLLOWER_GEOFENCE_NW_LAT = 41.2763072
FOLLOWER_GEOFENCE_NW_LON = 1.9882987

OFFSET_LAT = FOLLOWER_GEOFENCE_NW_LAT - LEADER_GEOFENCE_NW_LAT
OFFSET_LON = FOLLOWER_GEOFENCE_NW_LON - LEADER_GEOFENCE_NW_LON

REF_TOLERANCE_M = 1.0
GOTO_TIMEOUT = 30
MAX_TELEMETRY_AGE = 2.0
LANDING_ALT_THRESHOLD = 1.0

LOOP_HZ = 20
LOOP_DT = 1.0 / LOOP_HZ

DEFAULT_TAKEOFF_ALT = 5.0
AIRBORNE_ALT_THRESHOLD = 1.0

# Vision config
MODEL_PATH = "./Entrenamiento_Red_Neuronal/runs/dron_yolov8n/weights/best.pt"
VIDEO_SOURCE = "0"  # 0 webcam, or URL
CONFIDENCE = 0.5
FOV_X_DEG = 78.0
YAW_DEADZONE_DEG = 2.0
YAW_COOLDOWN_SEC = 0.5
YAW_MAX_STEP_DEG = 20.0


# =========================
# PID
# =========================
class PIDController:
    def __init__(self, kp: float, ki: float, kd: float, integral_limit: float = 5.0, alpha: float = 0.2):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral = 0.0
        self.previous_error = 0.0
        self.integral_limit = integral_limit
        self.previous_derivative = 0.0
        self.alpha = alpha

    def compute(self, setpoint: float, current_value: float, dt: float) -> float:
        if dt <= 0.0:
            return 0.0

        error = setpoint - current_value
        self.integral += error * dt
        self.integral = max(min(self.integral, self.integral_limit), -self.integral_limit)

        raw_derivative = (error - self.previous_error) / dt
        derivative = (self.alpha * raw_derivative) + ((1 - self.alpha) * self.previous_derivative)

        output = (self.kp * error) + (self.ki * self.integral) + (self.kd * derivative)
        self.previous_error = error
        self.previous_derivative = derivative
        return output


# =========================
# STATE
# =========================
leader = Dron()
follower = Dron()

leader_connected = threading.Event()
follower_connected = threading.Event()
telemetry_ready = threading.Event()

leader_telemetry = {}
follower_telemetry = {}

follow_requested = threading.Event()
follow_enabled = threading.Event()
initial_position_checked = threading.Event()

vision_running = threading.Event()
vision_running.set()

pid_x = PIDController(0.2, 0.0, 0.15)
pid_y = PIDController(0.2, 0.0, 0.15)
pid_z = PIDController(0.6, 0.0, 0.2)

pid_yaw = PIDController(0.8, 0.0, 0.1, integral_limit=30.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seguimiento leader-follower con vision YOLO")
    parser.add_argument("--model", default=MODEL_PATH, help="Ruta al modelo YOLO")
    parser.add_argument("--source", default=VIDEO_SOURCE, help="Fuente de video (0 webcam o URL)")
    parser.add_argument("--conf", type=float, default=CONFIDENCE, help="Confianza minima deteccion")
    parser.add_argument("--fov-x", type=float, default=FOV_X_DEG, help="FOV horizontal en grados")
    parser.add_argument("--dry-run", action="store_true", help="Valida configuracion y sale")
    return parser.parse_args()


def resolve_model_path(model_arg: str) -> Path:
    """
    Resuelve el path del modelo:
    1. Ruta absoluta
    2. Ruta relativa a script
    3. Ruta relativa a ROOT_DIR
    4. Busca cualquier best.pt en runs/**/weights/best.pt
    """
    candidate = Path(model_arg)
    if candidate.is_file():
        return candidate.resolve()

    # Intenta desde carpeta del script
    script_dir = Path(__file__).resolve().parent
    for base in (script_dir, ROOT_DIR):
        alt = base / model_arg
        if alt.is_file():
            return alt.resolve()

    # Busca en cualquier runs/**/weights/best.pt desde script o ROOT
    for search_root in (script_dir, ROOT_DIR):
        runs_dir = search_root / "runs"
        if runs_dir.exists():
            matches = sorted(
                runs_dir.glob("**/weights/best.pt"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if matches:
                return matches[0].resolve()

    raise FileNotFoundError(f"No se encontro el modelo: {model_arg}")


# =========================
# TELEMETRY
# =========================

def on_leader_telemetry(info):
    leader_telemetry.update(info)


def on_follower_telemetry(info):
    follower_telemetry.update(info)


def start_telemetry():
    if telemetry_ready.is_set():
        return
    leader.send_telemetry_info(on_leader_telemetry)
    follower.send_telemetry_info(on_follower_telemetry)
    telemetry_ready.set()
    print("Telemetria activada.")


# =========================
# UTILS
# =========================

def is_airborne(telemetry_dict) -> bool:
    alt = telemetry_dict.get("alt", 0.0)
    state = telemetry_dict.get("state", "")
    return alt >= AIRBORNE_ALT_THRESHOLD or state in ("flying", "returning", "landing")


def both_airborne() -> bool:
    return is_airborne(leader_telemetry) and is_airborne(follower_telemetry)


def get_position_from_telemetry(telemetry_dict):
    lat = telemetry_dict.get("lat", 0.0)
    lon = telemetry_dict.get("lon", 0.0)
    alt = telemetry_dict.get("alt", 0.0)
    if lat == 0.0 and lon == 0.0:
        raise TimeoutError("Telemetria no valida")
    return lat, lon, alt


def to_meters(lat1, lon1, lat2, lon2):
    lat_mid = math.radians((lat1 + lat2) / 2.0)
    dist_north = (lat2 - lat1) * 111320.0
    dist_east = (lon2 - lon1) * 111320.0 * math.cos(lat_mid)
    return dist_east, dist_north


def distance_meters(lat1, lon1, lat2, lon2):
    dist_east, dist_north = to_meters(lat1, lon1, lat2, lon2)
    return math.sqrt(dist_east ** 2 + dist_north ** 2)


def send_movement_command(dron, v_north, v_east, vz):
    v_north_lim = max(min(v_north, 2.0), -2.0)
    v_east_lim = max(min(v_east, 2.0), -2.0)
    vz_lim = max(min(vz, 1.0), -1.0)

    ned_vz = -vz_lim
    try:
        cmd = dron._prepare_command(v_north_lim, v_east_lim, ned_vz)
        dron.vehicle.mav.send(cmd)
    except Exception as exc:
        print(f"Error enviando velocidades: {exc}")


def stop_follow(status_var: Optional[object] = None):
    follow_requested.clear()
    follow_enabled.clear()
    initial_position_checked.clear()
    if status_var:
        status_var.set("Seguimiento: OFF")
    print("Seguimiento detenido.")
    send_movement_command(follower, 0, 0, 0)


def safe_change_heading(dron, target_heading: float):
    if dron.state != "flying":
        return
    dron.changeHeading(target_heading, blocking=False)


# =========================
# VISION THREAD
# =========================

def vision_loop(model_path: str, source_value: str, conf: float, fov_x: float):
    import cv2
    from ultralytics import YOLO

    if not vision_running.is_set():
        print("Vision loop desactivado (sin modelo).")
        return

    if str(source_value).isdigit():
        source = int(source_value)
    else:
        source = source_value

    try:
        model = YOLO(model_path)
        print(f"✓ Modelo YOLO cargado: {model_path}")
    except Exception as exc:
        print(f"✗ Error cargando modelo YOLO: {exc}")
        return

    try:
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"✗ No se pudo abrir la fuente de video: {source}")
            return
        print(f"✓ Fuente de video abierta: {source}")
    except Exception as exc:
        print(f"✗ Error al abrir video: {exc}")
        return

    last_yaw_time = 0.0

    while vision_running.is_set():
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        try:
            results = model.predict(frame, conf=conf, verbose=False)
        except Exception as exc:
            print(f"✗ Error en predicción: {exc}")
            break

        if not results or results[0].boxes is None:
            continue

        boxes = results[0].boxes
        if boxes.xyxy is None or boxes.conf is None:
            continue

        # Selecciona la deteccion con mayor confianza
        best_idx = int(boxes.conf.argmax().item()) if boxes.conf.numel() > 0 else None
        if best_idx is None:
            continue

        x1, y1, x2, y2 = boxes.xyxy[best_idx].tolist()
        cx = (x1 + x2) / 2.0
        width = frame.shape[1]

        # Error angular segun FOV
        error_px = cx - (width / 2.0)
        error_norm = error_px / max(1.0, width / 2.0)
        error_angle = error_norm * (fov_x / 2.0)

        if abs(error_angle) < YAW_DEADZONE_DEG:
            continue

        now = time.time()
        if now - last_yaw_time < YAW_COOLDOWN_SEC:
            continue

        follower_heading = follower_telemetry.get("heading")
        if follower_heading is None:
            continue

        step = max(min(error_angle, YAW_MAX_STEP_DEG), -YAW_MAX_STEP_DEG)
        target_heading = (follower_heading + step) % 360

        safe_change_heading(follower, target_heading)
        last_yaw_time = now

    cap.release()


# =========================
# GUI
# =========================

def create_gui():
    import tkinter as tk

    root = tk.Tk()
    root.title("Control PID y Seguimiento")
    root.geometry("380x620")

    status_var = tk.StringVar(value="Seguimiento: OFF")
    connection_var = tk.StringVar(value="Conexion: esperando")
    takeoff_alt_var = tk.DoubleVar(value=DEFAULT_TAKEOFF_ALT)

    def update_pids_xy(_val):
        pid_x.kp = pid_y.kp = float(slider_kp_xy.get())
        pid_x.ki = pid_y.ki = float(slider_ki_xy.get())
        pid_x.kd = pid_y.kd = float(slider_kd_xy.get())

    def update_pids_z(_val):
        pid_z.kp = float(slider_kp_z.get())
        pid_z.ki = float(slider_ki_z.get())
        pid_z.kd = float(slider_kd_z.get())

    def _connect_leader():
        if leader_connected.is_set():
            return
        print("Conectando al lider...")

        def on_leader_connected():
            leader_connected.set()
            print("Lider conectado.")

        ok = leader.connect(connection_string=LEADER_CONNECTION, baud=BAUDIOS, blocking=False, callback=on_leader_connected)
        if not ok:
            print("Error al conectar con el lider.")

    def _connect_follower():
        if follower_connected.is_set():
            return
        print("Conectando al seguidor...")

        def on_follower_connected():
            follower_connected.set()
            print("Seguidor conectado.")

        ok = follower.connect(connection_string=FOLLOWER_CONNECTION, baud=BAUDIOS, blocking=False, callback=on_follower_connected)
        if not ok:
            print("Error al conectar con el seguidor.")

    def connect_leader():
        threading.Thread(target=_connect_leader, daemon=True).start()

    def connect_follower():
        threading.Thread(target=_connect_follower, daemon=True).start()

    def connect_both():
        connect_leader()
        connect_follower()

    def _start_telemetry_safe():
        if not (leader_connected.is_set() and follower_connected.is_set()):
            print("Conecta ambos drones antes de activar telemetria.")
            return
        start_telemetry()

    def start_telemetry_button():
        threading.Thread(target=_start_telemetry_safe, daemon=True).start()

    def _arm_and_takeoff_both():
        try:
            alt = float(takeoff_alt_var.get())

            print("Armando lider...")
            leader.arm()
            time.sleep(2)
            print("✓ Lider armado.")

            print("Armando seguidor...")
            follower.arm()
            time.sleep(2)
            print("✓ Seguidor armado.")

            print(f"Despegando lider a {alt}m...")
            leader.takeOff(alt)
            
            # Espera a que el lider realmente levante
            leader_alt = 0.0
            t_start = time.time()
            timeout = 30
            while time.time() - t_start < timeout:
                leader_alt = leader_telemetry.get("alt", 0.0)
                if leader_alt >= alt * 0.9:  # 90% de la altura objetivo
                    print(f"✓ Lider despegó a {leader_alt:.1f}m")
                    break
                time.sleep(0.5)
            else:
                print(f"⚠️  Timeout esperando a que lider despegue (alt actual: {leader_alt:.1f}m)")

            time.sleep(1)

            print(f"Despegando seguidor a {alt}m...")
            follower.takeOff(alt)
            
            # Espera a que el seguidor realmente levante
            follower_alt = 0.0
            t_start = time.time()
            timeout = 30
            while time.time() - t_start < timeout:
                follower_alt = follower_telemetry.get("alt", 0.0)
                if follower_alt >= alt * 0.9:  # 90% de la altura objetivo
                    print(f"✓ Seguidor despegó a {follower_alt:.1f}m")
                    break
                time.sleep(0.5)
            else:
                print(f"⚠️  Timeout esperando a que seguidor despegue (alt actual: {follower_alt:.1f}m)")

            print("✓ Ambos drones en vuelo.")
        except Exception as exc:
            print(f"✗ Error armando/despegando: {exc}")
            import traceback
            traceback.print_exc()

    def arm_and_takeoff_both():
        threading.Thread(target=_arm_and_takeoff_both, daemon=True).start()

    def request_follow():
        if not (telemetry_ready.is_set() and both_airborne()):
            print("ERROR: conecta, activa telemetria y despega antes de seguimiento.")
            status_var.set("Seguimiento: error")
            return

        follow_requested.set()
        status_var.set("Seguimiento: iniciando...")

    def stop_follow_button():
        stop_follow(status_var)

    def refresh_status(*args):  # *args para compatibilidad con Tkinter.after()
        if leader_connected.is_set() and follower_connected.is_set():
            connection_var.set("Conexion: lista")
        elif leader_connected.is_set() or follower_connected.is_set():
            connection_var.set("Conexion: parcial")
        else:
            connection_var.set("Conexion: esperando")

        if follow_enabled.is_set():
            status_var.set("Seguimiento: ON")
        elif follow_requested.is_set():
            status_var.set("Seguimiento: calibrando...")

        root.after(500, refresh_status)

    control_frame = tk.LabelFrame(root, text="Control de vuelo")
    control_frame.pack(fill="x", padx=10, pady=8)

    tk.Label(control_frame, textvariable=connection_var).pack(pady=2)
    tk.Button(control_frame, text="Conectar lider", command=connect_leader).pack(fill="x", padx=10, pady=2)
    tk.Button(control_frame, text="Conectar seguidor", command=connect_follower).pack(fill="x", padx=10, pady=2)
    tk.Button(control_frame, text="Conectar ambos", command=connect_both).pack(fill="x", padx=10, pady=2)
    tk.Button(control_frame, text="Activar telemetria", command=start_telemetry_button).pack(fill="x", padx=10, pady=3)

    tk.Label(control_frame, text="Altitud despegue (m)").pack(pady=2)
    tk.Scale(control_frame, from_=1.0, to=20.0, resolution=0.5, orient="horizontal", variable=takeoff_alt_var).pack(fill="x", padx=10)

    tk.Button(control_frame, text="Armar y despegar", command=arm_and_takeoff_both).pack(fill="x", padx=10, pady=3)
    tk.Button(control_frame, text="Activar seguimiento", command=request_follow).pack(fill="x", padx=10, pady=3)
    tk.Button(control_frame, text="Parar seguimiento", command=stop_follow_button).pack(fill="x", padx=10, pady=3)
    tk.Label(control_frame, textvariable=status_var).pack(pady=4)

    tk.Label(root, text="Ajuste PID (Ejes X e Y)").pack(pady=5)
    slider_kp_xy = tk.Scale(root, label="Kp XY", from_=0.0, to=2.0, resolution=0.01, orient="horizontal", command=update_pids_xy)
    slider_kp_xy.set(pid_x.kp)
    slider_kp_xy.pack(fill="x", padx=10)

    slider_ki_xy = tk.Scale(root, label="Ki XY", from_=0.0, to=0.5, resolution=0.01, orient="horizontal", command=update_pids_xy)
    slider_ki_xy.set(pid_x.ki)
    slider_ki_xy.pack(fill="x", padx=10)

    slider_kd_xy = tk.Scale(root, label="Kd XY", from_=0.0, to=1.0, resolution=0.01, orient="horizontal", command=update_pids_xy)
    slider_kd_xy.set(pid_x.kd)
    slider_kd_xy.pack(fill="x", padx=10)

    tk.Label(root, text="Ajuste PID (Eje Z)").pack(pady=5)
    slider_kp_z = tk.Scale(root, label="Kp Z", from_=0.0, to=2.0, resolution=0.01, orient="horizontal", command=update_pids_z)
    slider_kp_z.set(pid_z.kp)
    slider_kp_z.pack(fill="x", padx=10)

    slider_ki_z = tk.Scale(root, label="Ki Z", from_=0.0, to=0.5, resolution=0.01, orient="horizontal", command=update_pids_z)
    slider_ki_z.set(pid_z.ki)
    slider_ki_z.pack(fill="x", padx=10)

    slider_kd_z = tk.Scale(root, label="Kd Z", from_=0.0, to=1.0, resolution=0.01, orient="horizontal", command=update_pids_z)
    slider_kd_z.set(pid_z.kd)
    slider_kd_z.pack(fill="x", padx=10)

    refresh_status()
    root.mainloop()


# =========================
# MAIN LOOP
# =========================

def main() -> None:
    args = parse_args()

    if args.dry_run:
        print("Dry run: configuracion OK.")
        print(f"Modelo: {args.model}")
        print(f"Video source: {args.source}")
        print(f"FOV X: {args.fov_x}")
        try:
            resolved = resolve_model_path(args.model)
            print(f"✓ Modelo resuelto: {resolved}")
        except FileNotFoundError as e:
            print(f"✗ {e}")
        return

    resolved_model = None
    try:
        resolved_model = resolve_model_path(args.model)
        print(f"Modelo cargado: {resolved_model}")
    except FileNotFoundError as exc:
        print(f"⚠️  ADVERTENCIA: {exc}")
        print("   El sistema funcionará SIN detección visual (vision desactivada).")
        print(f"   Para usar visión, entrena un modelo o pasa --model <ruta_modelo>")
        vision_running.clear()

    gui_thread = threading.Thread(target=create_gui, daemon=True)
    gui_thread.start()
    print("Dashboard abierto. Conecta y activa telemetria.")

    if resolved_model:
        vision_thread = threading.Thread(
            target=vision_loop,
            args=(str(resolved_model), args.source, args.conf, args.fov_x),
            daemon=True,
        )
        vision_thread.start()
    else:
        print("Vision thread NO iniciado (sin modelo disponible).")

    print("Esperando a que el usuario conecte ambos drones...")
    leader_connected.wait()
    follower_connected.wait()

    print("Esperando a que el usuario active telemetria...")
    telemetry_ready.wait()

    print("Esperando recepcion de telemetria inicial...")
    while True:
        try:
            get_position_from_telemetry(leader_telemetry)
            get_position_from_telemetry(follower_telemetry)
            print("Telemetria recibida. Listo para armar y despegar.")
            break
        except TimeoutError:
            time.sleep(0.5)

    print("Esperando a que el usuario active el seguimiento...")

    leader_origin_lat = 0.0
    leader_origin_lon = 0.0
    leader_origin_alt = 0.0
    follower_origin_lat = 0.0
    follower_origin_lon = 0.0
    follower_origin_alt = 0.0
    last_valid_leader_time = 0.0

    while True:
        t_start = time.time()

        if not follow_requested.is_set():
            time.sleep(0.1)
            continue

        if not initial_position_checked.is_set():
            print("Iniciando secuencia de seguimiento...")
            if not both_airborne():
                time.sleep(0.5)
                continue

            leader_lat, leader_lon, leader_alt = get_position_from_telemetry(leader_telemetry)
            follower_lat, follower_lon, follower_alt = get_position_from_telemetry(follower_telemetry)

            leader_ref_lat = leader_lat
            leader_ref_lon = leader_lon
            follower_ref_lat = leader_ref_lat + OFFSET_LAT
            follower_ref_lon = leader_ref_lon + OFFSET_LON

            dist_follower_to_ref = distance_meters(follower_lat, follower_lon, follower_ref_lat, follower_ref_lon)
            print(f"Distancia follower a referencia: {dist_follower_to_ref:.2f} m")

            if dist_follower_to_ref > REF_TOLERANCE_M:
                print("Moviendo follower al punto equivalente...")
                follower.goto(follower_ref_lat, follower_ref_lon, follower_alt, 2)

                t_goto_start = time.time()
                while True:
                    follower_lat, follower_lon, _ = get_position_from_telemetry(follower_telemetry)
                    dist_now = distance_meters(follower_lat, follower_lon, follower_ref_lat, follower_ref_lon)
                    if dist_now <= REF_TOLERANCE_M:
                        print("Follower en posicion equivalente.")
                        break
                    if time.time() - t_goto_start > GOTO_TIMEOUT:
                        print("Timeout al mover follower.")
                        break
                    time.sleep(0.5)

            leader_origin_lat, leader_origin_lon, leader_origin_alt = get_position_from_telemetry(leader_telemetry)
            follower_origin_lat, follower_origin_lon, follower_origin_alt = get_position_from_telemetry(follower_telemetry)

            last_valid_leader_time = time.time()
            initial_position_checked.set()
            follow_enabled.set()
            continue

        if not follow_enabled.is_set():
            time.sleep(0.1)
            continue

        try:
            leader_lat, leader_lon, leader_alt = get_position_from_telemetry(leader_telemetry)
            last_valid_leader_time = time.time()
        except TimeoutError:
            if time.time() - last_valid_leader_time > MAX_TELEMETRY_AGE:
                print("Sin telemetria del lider. Deteniendo follower.")
                send_movement_command(follower, 0, 0, 0)
                stop_follow()
                break
            time.sleep(0.1)
            continue

        try:
            follower_lat, follower_lon, follower_alt = get_position_from_telemetry(follower_telemetry)
        except TimeoutError:
            time.sleep(0.1)
            continue

        leader_mode = leader_telemetry.get("flightMode", "")
        leader_state = leader_telemetry.get("state", "")

        if (leader_mode in ("LAND", "RTL") and leader_alt < LANDING_ALT_THRESHOLD) or (
            leader_state == "disarmed" and leader_alt < AIRBORNE_ALT_THRESHOLD
        ):
            print("Lider aterrizando. El follower aterriza.")
            follower.Land()
            stop_follow()
            break

        leader_disp_east, leader_disp_north = to_meters(
            leader_origin_lat, leader_origin_lon, leader_lat, leader_lon
        )
        leader_disp_alt = leader_alt - leader_origin_alt

        follower_disp_east, follower_disp_north = to_meters(
            follower_origin_lat, follower_origin_lon, follower_lat, follower_lon
        )
        target_alt = follower_origin_alt + leader_disp_alt

        error_east = leader_disp_east - follower_disp_east
        error_north = leader_disp_north - follower_disp_north

        v_east = pid_x.compute(0, -error_east, LOOP_DT)
        v_north = pid_y.compute(0, -error_north, LOOP_DT)
        vz = pid_z.compute(target_alt, follower_alt, LOOP_DT)

        send_movement_command(follower, v_north, v_east, vz)

        elapsed = time.time() - t_start
        time.sleep(float(max(0, LOOP_DT - elapsed)))


if __name__ == "__main__":
    main()


