# El dron follower trata de posicionarse en la misma posición relativa al líder, pero dentro de su propia geofence.
# y de ahí calcula a qué distancia está del lider y esa será la referencia para mantener esa distancia constante durante el seguimiento.

from dronLink.Dron import Dron
import time
import math
import tkinter as tk
import threading


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
        if dt <= 0.0: return 0.0
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
# CONFIGURACIÓN
# =========================
LEADER_CONNECTION = "tcp:127.0.0.1:5763"
FOLLOWER_CONNECTION = "tcp:127.0.0.1:5773"
BAUDIOS = 115200

# Puntos NOROESTE de las geofences para usar como referencia
LEADER_GEOFENCE_NW_LAT, LEADER_GEOFENCE_NW_LON = 41.2764287, 1.9882478
FOLLOWER_GEOFENCE_NW_LAT, FOLLOWER_GEOFENCE_NW_LON = 41.2763072, 1.9882987

MAX_TELEMETRY_AGE = 2.0
LANDING_ALT_THRESHOLD = 1.0
LOOP_HZ = 20
LOOP_DT = 1.0 / LOOP_HZ

# =========================
# CONEXIÓN Y TELEMETRÍA
# =========================
leader = Dron()
follower = Dron()

leader.connect(connection_string=LEADER_CONNECTION, baud=BAUDIOS)
follower.connect(connection_string=FOLLOWER_CONNECTION, baud=BAUDIOS)
time.sleep(2)

leader_telemetry = {}
follower_telemetry = {}


def on_leader_telemetry(info): leader_telemetry.update(info)


def on_follower_telemetry(info): follower_telemetry.update(info)


leader.send_telemetry_info(on_leader_telemetry)
follower.send_telemetry_info(on_follower_telemetry)
time.sleep(2)


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


def send_movement_command(dron, v_north, v_east, vz):
    v_north_lim = max(min(v_north, 2.0), -2.0)
    v_east_lim = max(min(v_east, 2.0), -2.0)
    vz_lim = max(min(vz, 1.0), -1.0)
    ned_vz = -vz_lim
    try:
        cmd = dron._prepare_command(v_north_lim, v_east_lim, ned_vz)
        dron.vehicle.mav.send(cmd)
    except Exception as e:
        print(f"Error: {e}")


# =========================
# FASE 1: POSICIONAMIENTO INICIAL FRENTE A GEOFENCE
# =========================
print("Esperando recepción de telemetría inicial...")
while True:
    try:
        l_lat, l_lon, l_alt = get_position_from_telemetry(leader_telemetry)
        f_lat, f_lon, f_alt = get_position_from_telemetry(follower_telemetry)
        break
    except TimeoutError:
        time.sleep(0.5)

print("\n--- FASE 1: Alineación con Geofence ---")
pid_init_x = PIDController(0.2, 0.0, 0.1)
pid_init_y = PIDController(0.2, 0.0, 0.1)

while True:
    t_start = time.time()
    try:
        l_lat, l_lon, l_alt = get_position_from_telemetry(leader_telemetry)
        f_lat, f_lon, f_alt = get_position_from_telemetry(follower_telemetry)
    except TimeoutError:
        continue

    # 1. ¿Dónde está el líder respecto al NW de su geofence?
    offset_l_east, offset_l_north = to_meters(LEADER_GEOFENCE_NW_LAT, LEADER_GEOFENCE_NW_LON, l_lat, l_lon)

    # 2. ¿Dónde está el follower respecto al NW de su geofence?
    offset_f_east, offset_f_north = to_meters(FOLLOWER_GEOFENCE_NW_LAT, FOLLOWER_GEOFENCE_NW_LON, f_lat, f_lon)

    # 3. El error es la diferencia entre el offset que tiene el follower y el que DEBERÍA tener (el del líder)
    init_error_east = offset_l_east - offset_f_east
    init_error_north = offset_l_north - offset_f_north
    init_error_dist = math.sqrt(init_error_east ** 2 + init_error_north ** 2)

    if init_error_dist < 0.5:
        print("Follower posicionado correctamente en su geofence. Iniciando Fase 2...")
        send_movement_command(follower, 0, 0, 0)
        break

    v_east = pid_init_x.compute(0, -init_error_east, LOOP_DT)
    v_north = pid_init_y.compute(0, -init_error_north, LOOP_DT)

    send_movement_command(follower, v_north, v_east, 0)
    print(f"Alineando... Distancia restante al punto de inicio: {init_error_dist:.2f}m")

    time.sleep(max(0, LOOP_DT - (time.time() - t_start)))

# =========================
# FASE 2: SEGUIMIENTO CONTINUO
# =========================
print("\n--- FASE 2: Seguimiento Continuo ---")
init_dist_east, init_dist_north = to_meters(f_lat, f_lon, l_lat, l_lon)
DESIRED_DISTANCE = math.sqrt(init_dist_east ** 2 + init_dist_north ** 2)

print(f"Distancia inicial fijada en {DESIRED_DISTANCE:.2f} metros.")

pid_x = PIDController(0.2, 0.0, 0.15)
pid_y = PIDController(0.2, 0.0, 0.15)
pid_z = PIDController(0.6, 0.0, 0.2)


# =========================
# INTERFAZ GRÁFICA PARA TUNING PID
# =========================
def create_gui():
    root = tk.Tk()
    root.title("Tuning PID")
    root.geometry("350x450")

    def update_pids_xy(val):
        pid_x.kp = pid_y.kp = float(slider_kp_xy.get())
        pid_x.ki = pid_y.ki = float(slider_ki_xy.get())
        pid_x.kd = pid_y.kd = float(slider_kd_xy.get())

    def update_pids_z(val):
        pid_z.kp = float(slider_kp_z.get())
        pid_z.ki = float(slider_ki_z.get())
        pid_z.kd = float(slider_kd_z.get())

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

    root.mainloop()


gui_thread = threading.Thread(target=create_gui, daemon=True)
gui_thread.start()

last_valid_leader_time = time.time()

while True:
    t_start = time.time()

    try:
        leader_lat, leader_lon, leader_alt = get_position_from_telemetry(leader_telemetry)
        last_valid_leader_time = time.time()
    except TimeoutError:
        if time.time() - last_valid_leader_time > MAX_TELEMETRY_AGE:
            send_movement_command(follower, 0, 0, 0)
            break
        time.sleep(0.1)
        continue

    try:
        follower_lat, follower_lon, follower_alt = get_position_from_telemetry(follower_telemetry)
    except TimeoutError:
        time.sleep(0.1)
        continue

    # Aterrizaje
    leader_mode = leader_telemetry.get('flightMode', '')
    leader_state = leader_telemetry.get('state', '')
    if (leader_mode in ('LAND', 'RTL') and leader_alt < LANDING_ALT_THRESHOLD) or leader_state in ('disarmed', 'connected'):
        follower.Land()
        break

    # Seguir
    dist_east, dist_north = to_meters(follower_lat, follower_lon, leader_lat, leader_lon)
    distance = math.sqrt(dist_east ** 2 + dist_north ** 2)

    scale = (distance - DESIRED_DISTANCE) / distance if distance > 0 else 0
    target_east = dist_east * scale
    target_north = dist_north * scale

    v_east = pid_x.compute(0, -target_east, LOOP_DT)
    v_north = pid_y.compute(0, -target_north, LOOP_DT)
    vz = pid_z.compute(leader_alt, follower_alt, LOOP_DT)

    send_movement_command(follower, v_north, v_east, vz)

    print(f"Dist: {distance:.2f}m (Obj: {DESIRED_DISTANCE:.2f}m) | VelN:{v_north:.2f} VelE:{v_east:.2f} vz:{vz:.2f}")

    time.sleep(max(0, LOOP_DT - (time.time() - t_start)))
