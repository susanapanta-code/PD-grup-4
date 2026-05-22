# imitar
# igual a prueba2.py pero con el heading del follower siempre viendo al leader y visión artificial en GUI

from pymavlink import mavutil
from dronLink.Dron import Dron
import time
import math
import tkinter as tk
import threading
import cv2
from PIL import Image, ImageTk
from ultralytics import YOLO


# =========================
# PID CLASS
# =========================
class PIDController:
    def __init__(self, kp, ki, kd, integral_limit=5.0, alpha=0.2):
        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.integral = 0
        self.previous_error = 0

        self.integral_limit = integral_limit
        self.previous_derivative = 0
        self.alpha = alpha

    def compute(self, setpoint, current_value, dt):
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
# CONFIG
# =========================
LEADER_CONNECTION   = "udp:127.0.0.1:14561"
#LEADER_CONNECTION   = "tcp:127.0.0.1:5762"
FOLLOWER_CONNECTION = "udp:127.0.0.1:14551"
#FOLLOWER_CONNECTION = "tcp:127.0.0.1:5772"
BAUDIOS = 57600
#BAUDIOS = 115200

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

# Archivo del modelo YOLO
YOLO_MODEL_PATH = "/Users/LENOVO/Desktop/Uni/4B/PD/PD-grup-4/Versión 3 y 4/Entrenamiento_Red_Neuronal/runs/dron_yolov8n/weights/best.pt"

# =========================
# CONEXIÓN
# =========================
print("Creando instancias para los drones...")
leader = Dron()
follower = Dron()
print("Instancias creadas.")

leader_connected = threading.Event()
follower_connected = threading.Event()
telemetry_ready = threading.Event()

leader_telemetry = {}
follower_telemetry = {}


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
    print("Telemetría activada.")


pid_x = PIDController(0.2, 0.0, 0.15)
pid_y = PIDController(0.2, 0.0, 0.15)
pid_z = PIDController(0.2, 0.0, 0.05)

follow_requested = threading.Event()
follow_enabled = threading.Event()
initial_position_checked = threading.Event()


def is_airborne(telemetry_dict):
    alt = telemetry_dict.get('alt', 0.0)
    state = telemetry_dict.get('state', '')
    return alt >= AIRBORNE_ALT_THRESHOLD or state in ('flying', 'returning', 'landing')


def both_airborne():
    return is_airborne(leader_telemetry) and is_airborne(follower_telemetry)


def stop_follow(status_var=None):
    follow_requested.clear()
    follow_enabled.clear()
    initial_position_checked.clear()
    if status_var:
        status_var.set("Seguimiento: OFF")
    print("\nSeguimiento detenido.")
    send_movement_command(follower, 0, 0, 0, 0)


# =========================
# INTERFAZ GRAFICA Y VISIÓN
# =========================
def create_gui():
    root = tk.Tk()
    root.title("Control PID y Seguimiento con Visión")
    root.geometry("1000x650")  # Interfaz más ancha para incluir la cámara

    main_frame = tk.Frame(root)
    main_frame.pack(fill="both", expand=True)

    left_frame = tk.Frame(main_frame, width=380)
    left_frame.pack(side="left", fill="y", padx=10, pady=10)

    right_frame = tk.Frame(main_frame)
    right_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)

    status_var = tk.StringVar(value="Seguimiento: OFF")
    connection_var = tk.StringVar(value="Conexión: esperando")
    takeoff_alt_var = tk.DoubleVar(value=DEFAULT_TAKEOFF_ALT)

    # --- CARGAR MODELO YOLO Y CÁMARA ---
    try:
        model = YOLO(YOLO_MODEL_PATH)
        print(f"Modelo YOLO cargado: {YOLO_MODEL_PATH}")
    except Exception as e:
        print(f"Advertencia: No se pudo cargar el modelo YOLO ({e}). Usando versión por defecto.")
        model = YOLO("yolov8n.pt")

    cap = cv2.VideoCapture(0)  # 0 para la webcam del portátil
    #cap = cv2.VideoCapture("http://192.168.141.11:8080/video")
    video_label = tk.Label(right_frame, text="Iniciando cámara...")
    video_label.pack(fill="both", expand=True)

    def update_frame():
        ret, frame = cap.read()
        if ret:
            # Procesamiento YOLO
            results = model.predict(frame, conf=0.25, verbose=False)
            annotated_frame = results[0].plot()

            # Convertir formato BGR (OpenCV) a RGB (Pillow)
            rgb_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            rgb_frame = cv2.resize(rgb_frame, (600, 450))  # Ajustar tamaño para la GUI

            img = Image.fromarray(rgb_frame)
            imgtk = ImageTk.PhotoImage(image=img)
            video_label.imgtk = imgtk
            video_label.configure(image=imgtk, text="")

        # Volver a llamar a esta función luego de 30ms (~30 FPS)
        video_label.after(30, update_frame)

    # Iniciar ciclo de captura de vídeo
    update_frame()

    # --- CONTROLES GUI ---
    def update_pids_xy(val):
        pid_x.kp = pid_y.kp = float(slider_kp_xy.get())
        pid_x.ki = pid_y.ki = float(slider_ki_xy.get())
        pid_x.kd = pid_y.kd = float(slider_kd_xy.get())

    def update_pids_z(val):
        pid_z.kp = float(slider_kp_z.get())
        pid_z.ki = float(slider_ki_z.get())
        pid_z.kd = float(slider_kd_z.get())

    def _connect_leader():
        if leader_connected.is_set(): return
        print("Conectando al líder...")

        def on_leader_connected():
            leader_connected.set()
            print("Líder conectado.")

        ok = leader.connect(connection_string=LEADER_CONNECTION, baud=BAUDIOS, blocking=False,
                            callback=on_leader_connected)
        if not ok: print("Error al conectar con el líder.")

    def _connect_follower():
        if follower_connected.is_set(): return
        print("Conectando al seguidor...")

        def on_follower_connected():
            follower_connected.set()
            print("Seguidor conectado.")

        ok = follower.connect(connection_string=FOLLOWER_CONNECTION, baud=BAUDIOS, blocking=False,
                              callback=on_follower_connected)
        if not ok: print("Error al conectar con el seguidor.")

    def connect_leader():
        threading.Thread(target=_connect_leader, daemon=True).start()

    def connect_follower():
        threading.Thread(target=_connect_follower, daemon=True).start()

    def connect_both():
        connect_leader()
        connect_follower()

    def _start_telemetry_safe():
        if not (leader_connected.is_set() and follower_connected.is_set()):
            print("Conecta ambos drones antes de activar telemetría.")
            return
        start_telemetry()

    def start_telemetry_button():
        threading.Thread(target=_start_telemetry_safe, daemon=True).start()

    def _arm_and_takeoff_both():
        try:
            alt = float(takeoff_alt_var.get())
            print("🚁 Armando LÍDER...")
            leader.arm()
            time.sleep(1)
            print(f"📤 Despegando LÍDER a {alt}m...")
            leader.takeOff(alt)
            time.sleep(1)
            print("🚁 Armando SEGUIDOR...")
            follower.arm()
            time.sleep(1)
            print(f"📤 Despegando SEGUIDOR a {alt}m...")
            follower.takeOff(alt)
            print("\n✈️  ¡Ambos drones en vuelo!")
        except Exception as e:
            print(f"❌ Error armando/despegando drones: {e}")

    def arm_and_takeoff_both():
        threading.Thread(target=_arm_and_takeoff_both, daemon=True).start()

    def request_follow():
        if not (telemetry_ready.is_set() and both_airborne()):
            print("ERROR: Ambos drones deben estar conectados y en el aire.")
            status_var.set("Seguimiento: ¡Error! Despega primero.")
            return
        follow_requested.set()
        status_var.set("Seguimiento: iniciando...")

    def stop_follow_button():
        stop_follow(status_var)

    def refresh_status():
        if leader_connected.is_set() and follower_connected.is_set():
            connection_var.set("Conexión: lista")
        elif leader_connected.is_set() or follower_connected.is_set():
            connection_var.set("Conexión: parcial")
        else:
            connection_var.set("Conexión: esperando")

        if follow_enabled.is_set():
            status_var.set("Seguimiento: ON")
        elif follow_requested.is_set():
            status_var.set("Seguimiento: calibrando...")
        root.after(500, refresh_status)

    control_frame = tk.LabelFrame(left_frame, text="Control de vuelo")
    control_frame.pack(fill="x", pady=8)

    tk.Label(control_frame, textvariable=connection_var).pack(pady=2)
    tk.Button(control_frame, text="Conectar líder", command=connect_leader).pack(fill="x", padx=10, pady=2)
    tk.Button(control_frame, text="Conectar seguidor", command=connect_follower).pack(fill="x", padx=10, pady=2)
    tk.Button(control_frame, text="Conectar ambos", command=connect_both).pack(fill="x", padx=10, pady=2)
    tk.Button(control_frame, text="Activar telemetría", command=start_telemetry_button).pack(fill="x", padx=10, pady=3)

    tk.Label(control_frame, text="Altitud despegue (m)").pack(pady=2)
    tk.Scale(control_frame, from_=1.0, to=20.0, resolution=0.5, orient="horizontal", variable=takeoff_alt_var).pack(
        fill="x", padx=10)

    tk.Button(control_frame, text="Armar y Despegar", command=arm_and_takeoff_both).pack(fill="x", padx=10, pady=3)
    tk.Button(control_frame, text="Activar seguimiento", command=request_follow).pack(fill="x", padx=10, pady=3)
    tk.Button(control_frame, text="Parar seguimiento", command=stop_follow_button).pack(fill="x", padx=10, pady=3)
    tk.Label(control_frame, textvariable=status_var).pack(pady=4)

    tk.Label(left_frame, text="Ajuste PID (Ejes X e Y)").pack(pady=5)
    slider_kp_xy = tk.Scale(left_frame, label="Kp XY", from_=0.0, to=2.0, resolution=0.01, orient="horizontal",
                            command=update_pids_xy)
    slider_kp_xy.set(pid_x.kp)
    slider_kp_xy.pack(fill="x", padx=10)
    slider_ki_xy = tk.Scale(left_frame, label="Ki XY", from_=0.0, to=0.5, resolution=0.01, orient="horizontal",
                            command=update_pids_xy)
    slider_ki_xy.set(pid_x.ki)
    slider_ki_xy.pack(fill="x", padx=10)
    slider_kd_xy = tk.Scale(left_frame, label="Kd XY", from_=0.0, to=1.0, resolution=0.01, orient="horizontal",
                            command=update_pids_xy)
    slider_kd_xy.set(pid_x.kd)
    slider_kd_xy.pack(fill="x", padx=10)

    tk.Label(left_frame, text="Ajuste PID (Eje Z)").pack(pady=5)
    slider_kp_z = tk.Scale(left_frame, label="Kp Z", from_=0.0, to=2.0, resolution=0.01, orient="horizontal",
                           command=update_pids_z)
    slider_kp_z.set(pid_z.kp)
    slider_kp_z.pack(fill="x", padx=10)
    slider_ki_z = tk.Scale(left_frame, label="Ki Z", from_=0.0, to=0.5, resolution=0.01, orient="horizontal",
                           command=update_pids_z)
    slider_ki_z.set(pid_z.ki)
    slider_ki_z.pack(fill="x", padx=10)
    slider_kd_z = tk.Scale(left_frame, label="Kd Z", from_=0.0, to=1.0, resolution=0.01, orient="horizontal",
                           command=update_pids_z)
    slider_kd_z.set(pid_z.kd)
    slider_kd_z.pack(fill="x", padx=10)

    def on_closing():
        cap.release()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    refresh_status()
    root.mainloop()


gui_thread = threading.Thread(target=create_gui, daemon=True)
gui_thread.start()
print("Dashboard abierto. Pulsa los botones para conectar y activar telemetría.")
print("Mientras tanto, el script esperará a que completes estas acciones...\n")


# =========================
# FUNCIONES AUX
# =========================

def get_position_from_telemetry(telemetry_dict):
    lat = telemetry_dict.get('lat', 0.0)
    lon = telemetry_dict.get('lon', 0.0)
    alt = telemetry_dict.get('alt', 0.0)
    if lat == 0.0 and lon == 0.0:
        raise TimeoutError("Telemetría no válida")
    return lat, lon, alt


def to_meters(lat1, lon1, lat2, lon2):
    lat_mid = math.radians((lat1 + lat2) / 2.0)
    dist_north = (lat2 - lat1) * 111320.0
    dist_east = (lon2 - lon1) * 111320.0 * math.cos(lat_mid)
    return dist_east, dist_north


def distance_meters(lat1, lon1, lat2, lon2):
    dist_east, dist_north = to_meters(lat1, lon1, lat2, lon2)
    return math.sqrt(dist_east ** 2 + dist_north ** 2)


def send_movement_command(dron, v_north, v_east, vz, yaw_rad):
    v_north_lim = max(min(v_north, 3.0), -3.0)
    v_east_lim = max(min(v_east, 3.0), -3.0)
    vz_lim = max(min(vz, 1.0), -1.0)
    ned_vz = -vz_lim

    try:
        cmd = mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
            0,
            dron.vehicle.target_system,
            dron.vehicle.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000101111000111,
            0, 0, 0,
            v_north_lim, v_east_lim, ned_vz,
            0, 0, 0,
            yaw_rad, 0
        )
        dron.vehicle.mav.send(cmd)
    except Exception as e:
        print(f"Error enviando comando integral: {e}")


# =========================
# ESPERAR ACCIONES DEL USUARIO
# =========================
print("Esperando a que el usuario conecte ambos drones...")
leader_connected.wait()
follower_connected.wait()

print("Esperando a que el usuario active telemetría...")
telemetry_ready.wait()

print("Esperando recepción de telemetría inicial...")
while True:
    try:
        get_position_from_telemetry(leader_telemetry)
        get_position_from_telemetry(follower_telemetry)
        print("Telemetría recibida. Listo para armar y despegar.")
        break
    except TimeoutError:
        time.sleep(0.5)

print("Esperando a que el usuario active el seguimiento...")
leader_origin_lat, leader_origin_lon, leader_origin_alt = 0, 0, 0
follower_origin_lat, follower_origin_lon, follower_origin_alt = 0, 0, 0
last_valid_leader_time = 0

# =========================
# LOOP PRINCIPAL
# =========================
while True:
    t_start = time.time()

    if not follow_requested.is_set():
        time.sleep(0.1)
        continue

    if not initial_position_checked.is_set():
        print("\n--- INICIANDO SECUENCIA DE SEGUIMIENTO ---")
        if not both_airborne():
            print("Esperando a que ambos drones despeguen...")
            time.sleep(0.5)
            continue

        leader_lat, leader_lon, leader_alt = get_position_from_telemetry(leader_telemetry)
        follower_lat, follower_lon, follower_alt = get_position_from_telemetry(follower_telemetry)

        LEADER_REF_LAT = leader_lat
        LEADER_REF_LON = leader_lon
        FOLLOWER_REF_LAT = LEADER_REF_LAT + OFFSET_LAT
        FOLLOWER_REF_LON = LEADER_REF_LON + OFFSET_LON

        dist_follower_to_ref = distance_meters(follower_lat, follower_lon, FOLLOWER_REF_LAT, FOLLOWER_REF_LON)

        if dist_follower_to_ref > REF_TOLERANCE_M:
            follower.goto(FOLLOWER_REF_LAT, FOLLOWER_REF_LON, follower_alt, 2)
            t_goto_start = time.time()
            while True:
                follower_lat, follower_lon, _ = get_position_from_telemetry(follower_telemetry)
                dist_now = distance_meters(follower_lat, follower_lon, FOLLOWER_REF_LAT, FOLLOWER_REF_LON)
                if dist_now <= REF_TOLERANCE_M: break
                if time.time() - t_goto_start > GOTO_TIMEOUT: break
                time.sleep(0.5)

        leader_origin_lat, leader_origin_lon, leader_origin_alt = get_position_from_telemetry(leader_telemetry)
        follower_origin_lat, follower_origin_lon, follower_origin_alt = get_position_from_telemetry(follower_telemetry)

        follower.fixHeading()

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
            send_movement_command(follower, 0, 0, 0, 0)
            stop_follow()
            break
        time.sleep(0.1)
        continue

    try:
        follower_lat, follower_lon, follower_alt = get_position_from_telemetry(follower_telemetry)
    except TimeoutError:
        time.sleep(0.1)
        continue

    leader_mode = leader_telemetry.get('flightMode', '')
    leader_state = leader_telemetry.get('state', '')

    if (leader_mode in ('LAND', 'RTL') and leader_alt < LANDING_ALT_THRESHOLD) or \
            (leader_state == 'disarmed' and leader_alt < AIRBORNE_ALT_THRESHOLD):
        follower.Land()
        stop_follow()
        break

    leader_disp_east, leader_disp_north = to_meters(leader_origin_lat, leader_origin_lon, leader_lat, leader_lon)
    leader_disp_alt = leader_alt - leader_origin_alt

    follower_disp_east, follower_disp_north = to_meters(follower_origin_lat, follower_origin_lon, follower_lat,
                                                        follower_lon)
    target_alt = follower_origin_alt + leader_disp_alt

    error_east = leader_disp_east - follower_disp_east
    error_north = leader_disp_north - follower_disp_north

    v_east = pid_x.compute(0, -error_east, LOOP_DT)
    v_north = pid_y.compute(0, -error_north, LOOP_DT)
    vz = pid_z.compute(target_alt, follower_alt, LOOP_DT)

    vec_to_leader_east, vec_to_leader_north = to_meters(follower_lat, follower_lon, leader_lat, leader_lon)
    yaw_rad = math.atan2(vec_to_leader_east, vec_to_leader_north)

    send_movement_command(follower, v_north, v_east, vz, yaw_rad)

    yaw_deg = math.degrees(yaw_rad)
    if yaw_deg < 0: yaw_deg += 360

    print(
        f"Disp líder: N={leader_disp_north:.2f} E={leader_disp_east:.2f} | "
        f"Error: N={error_north:.2f} E={error_east:.2f} | "
        f"Vels: N={v_north:.2f} E={v_east:.2f} | "
        f"Yaw: {yaw_deg:.1f}°", end='\r'
    )

    elapsed = time.time() - t_start
    time.sleep(max(0, LOOP_DT - elapsed))
