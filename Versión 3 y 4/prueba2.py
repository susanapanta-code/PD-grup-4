#imitar

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

        # Mejoras para vuelo real:
        self.integral_limit = integral_limit
        self.previous_derivative = 0
        self.alpha = alpha  # Filtro pasa-bajos para la derivada

    def compute(self, setpoint, current_value, dt):
        """Calcula la respuesta del controlador PID."""
        if dt <= 0.0:
            return 0.0

        error = setpoint - current_value

        # Integral con Anti-Windup (evita descontrol si el dron no puede alcanzar la velocidad)
        self.integral += error * dt
        self.integral = max(min(self.integral, self.integral_limit), -self.integral_limit)

        # Derivada filtrada (suaviza los pequeños "saltos" en sensores GPS reales)
        raw_derivative = (error - self.previous_error) / dt
        derivative = (self.alpha * raw_derivative) + ((1 - self.alpha) * self.previous_derivative)

        output = (self.kp * error) + (self.ki * self.integral) + (self.kd * derivative)

        self.previous_error = error
        self.previous_derivative = derivative
        return output

# =========================
# CONFIG
# =========================

# ABRIENDO 2 INSTANCIAS DE SITL EN EL MISMO ORDENADOR:
LEADER_CONNECTION   = "udp:127.0.0.1:14551"
FOLLOWER_CONNECTION = "udp:127.0.0.1:14561"
BAUDIOS = 57600


# Coordenadas NOROESTE de ambas geofences para calcular la traslación
# REEMPLAZA las coordenadas del líder con el punto noroeste de tu foto
LEADER_GEOFENCE_NW_LAT = 41.2764287
LEADER_GEOFENCE_NW_LON = 1.9882478

FOLLOWER_GEOFENCE_NW_LAT = 41.2763072
FOLLOWER_GEOFENCE_NW_LON = 1.9882987

# Calculamos el vector de desplazamiento de la geofence entera
OFFSET_LAT = FOLLOWER_GEOFENCE_NW_LAT - LEADER_GEOFENCE_NW_LAT
OFFSET_LON = FOLLOWER_GEOFENCE_NW_LON - LEADER_GEOFENCE_NW_LON

# Tolerancia máxima entre la posición inicial del dron y su punto de referencia (metros)
REF_TOLERANCE_M = 1.0

# Tiempo máximo esperando a que el follower llegue a su punto de referencia (segundos)
GOTO_TIMEOUT = 30

# Tiempo máximo sin recibir telemetría del líder antes de parar el follower (segundos)
MAX_TELEMETRY_AGE = 2.0

# Altitud por debajo de la cual consideramos que el líder está aterrizando (metros)
LANDING_ALT_THRESHOLD = 1.0

# Frecuencia del loop de control (Hz) y periodo correspondiente (segundos)
LOOP_HZ = 20
LOOP_DT = 1.0 / LOOP_HZ

# =========================
# CONEXIÓN
# =========================
print("Creando instancias para los drones...")
leader   = Dron()
follower = Dron()
print("Instancias creadas.")

print("Conectando al líder...")
if leader.connect(connection_string=LEADER_CONNECTION, baud=BAUDIOS):
    print("Líder conectado.")
else:
    print("Error al conectar con el líder.")
    exit(1)

print("Conectando al seguidor...")
if follower.connect(connection_string=FOLLOWER_CONNECTION, baud=BAUDIOS):
    print("Seguidor conectado.")
else:
    print("Error al conectar con el seguidor.")
    exit(1)

# Pequeña pausa para asegurar que la telemetría inicial se recibe
time.sleep(2)

# =========================
# ACTIVAR TELEMETRÍA
# =========================

leader_telemetry   = {}
follower_telemetry = {}


def on_leader_telemetry(info):
    leader_telemetry.update(info)


def on_follower_telemetry(info):
    follower_telemetry.update(info)


leader.send_telemetry_info(on_leader_telemetry)
follower.send_telemetry_info(on_follower_telemetry)

print("Telemetría activada. Esperando primeros datos...")
time.sleep(2)

# =========================
# PID
# =========================

pid_x = PIDController(0.2, 0.0, 0.15)
pid_y = PIDController(0.2, 0.0, 0.15)
pid_z = PIDController(0.6, 0.0, 0.2)

# '''
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

# Lanzamos la interfaz en un hilo separado para que no pause el bucle del dron
gui_thread = threading.Thread(target=create_gui, daemon=True)
gui_thread.start()
# '''

# =========================
# FUNCIONES AUX
# =========================

def get_position_from_telemetry(telemetry_dict):
    """Lee la posición del dict de telemetría actualizado por el callback."""
    lat = telemetry_dict.get('lat', 0.0)
    lon = telemetry_dict.get('lon', 0.0)
    alt = telemetry_dict.get('alt', 0.0)
    # Si las coordenadas son 0.0, es que todavía no hay telemetría válida
    if lat == 0.0 and lon == 0.0:
        raise TimeoutError("Telemetría no válida")
    return lat, lon, alt


def to_meters(lat1, lon1, lat2, lon2):
    # La distancia en grados de latitud es prácticamente constante
    # pero la de longitud varía según el coseno de la latitud.
    lat_mid = math.radians((lat1 + lat2) / 2.0)

    # 1 grado de latitud son aprox 111.32 km.
    dist_north = (lat2 - lat1) * 111320.0
    # 1 grado de longitud se escala usando el coseno de la latitud media.
    dist_east = (lon2 - lon1) * 111320.0 * math.cos(lat_mid)

    return dist_east, dist_north


def distance_meters(lat1, lon1, lat2, lon2):
    """Distancia en metros entre dos puntos GPS."""
    dist_east, dist_north = to_meters(lat1, lon1, lat2, lon2)
    return math.sqrt(dist_east**2 + dist_north**2)


def send_movement_command(dron, v_north, v_east, vz):
    # Limitamos velocidades por seguridad (máximo 2 m/s horizontal, 1 m/s vertical)
    v_north_lim = max(min(v_north, 2.0), -2.0)
    v_east_lim  = max(min(v_east,  2.0), -2.0)
    vz_lim      = max(min(vz,      1.0), -1.0)

    # El eje Z en MAV_FRAME_LOCAL_NED es "Down". Invertimos vz para usar: + = subir
    ned_vz = -vz_lim

    try:
        # Generar el mensaje exacto con el vector de velocidad (X=North, Y=East, Z=Down)
        cmd = dron._prepare_command(v_north_lim, v_east_lim, ned_vz)
        dron.vehicle.mav.send(cmd)
    except Exception as e:
        print(f"Error enviando velocidades directas: {e}")


# =========================
# ESPERAR TELEMETRÍA VÁLIDA
# =========================

print("Esperando recepción de telemetría...")
while True:
    try:
        get_position_from_telemetry(leader_telemetry)
        get_position_from_telemetry(follower_telemetry)
        break
    except TimeoutError:
        time.sleep(0.5)

# =========================
# COMPROBACIÓN DE POSICIÓN INICIAL
# =========================

leader_lat, leader_lon, leader_alt       = get_position_from_telemetry(leader_telemetry)
follower_lat, follower_lon, follower_alt = get_position_from_telemetry(follower_telemetry)

# El punto de referencia del líder es donde está ahora mismo
LEADER_REF_LAT = leader_lat
LEADER_REF_LON = leader_lon

# El punto de referencia del follower es la posición equivalente trasladada
FOLLOWER_REF_LAT = LEADER_REF_LAT + OFFSET_LAT
FOLLOWER_REF_LON = LEADER_REF_LON + OFFSET_LON

dist_leader_to_ref   = 0.0 # El líder ya está en su propia referencia actual
dist_follower_to_ref = distance_meters(follower_lat, follower_lon, FOLLOWER_REF_LAT, FOLLOWER_REF_LON)

print(f"\n--- POSICIÓN INICIAL EQUIVALENTE ---")
print(f"Líder en: lat={LEADER_REF_LAT:.7f}, lon={LEADER_REF_LON:.7f}")
print(f"Objetivo Follower: lat={FOLLOWER_REF_LAT:.7f}, lon={FOLLOWER_REF_LON:.7f}")
print(f"Distancia actual del follower al objetivo: {dist_follower_to_ref:.2f} m")

# El follower se recoloca para emparejar la posición proporcional
if dist_follower_to_ref > REF_TOLERANCE_M:
    print(f"\n🔄 Moviendo FOLLOWER automáticamente al punto equivalente...")

    follower.goto(FOLLOWER_REF_LAT, FOLLOWER_REF_LON, follower_alt)

    t_goto_start = time.time()
    while True:
        follower_lat, follower_lon, follower_alt = get_position_from_telemetry(follower_telemetry)
        dist_now = distance_meters(follower_lat, follower_lon, FOLLOWER_REF_LAT, FOLLOWER_REF_LON)

        print(f"   Distancia al punto de referencia: {dist_now:.2f} m", end='\r')

        if dist_now <= REF_TOLERANCE_M:
            print(f"\n✅ Follower en su posición equivalente ({dist_now:.2f} m).")
            break

        if time.time() - t_goto_start > GOTO_TIMEOUT:
            print(f"\n⚠️ Tiempo de espera excedido. Continuando...")
            break

        time.sleep(0.5)
else:
    print("✅ El follower ya se encuentra en la posición equivalente.")

# =========================
# CALIBRACIÓN DE ORÍGENES
# Guardamos la posición actual de ambos drones como origen.
# A partir de aquí el follower replicará el desplazamiento relativo
# del líder respecto a su propio origen.
# =========================

leader_origin_lat,   leader_origin_lon,   leader_origin_alt   = get_position_from_telemetry(leader_telemetry)
follower_origin_lat, follower_origin_lon, follower_origin_alt = get_position_from_telemetry(follower_telemetry)

print(f"\nOrigen líder:    lat={leader_origin_lat:.7f}   lon={leader_origin_lon:.7f}   alt={leader_origin_alt:.2f} m")
print(f"Origen follower: lat={follower_origin_lat:.7f} lon={follower_origin_lon:.7f} alt={follower_origin_alt:.2f} m")
print("Orígenes calibrados. Iniciando replicado de movimiento.\n")

last_valid_leader_time = time.time()

# =========================
# LOOP PRINCIPAL
# =========================

while True:
    t_start = time.time()

    try:
        leader_lat, leader_lon, leader_alt = get_position_from_telemetry(leader_telemetry)
        # Telemetría del líder válida: actualizamos el timestamp
        last_valid_leader_time = time.time()
    except TimeoutError:
        # Si llevamos demasiado tiempo sin telemetría del líder, paramos el follower por seguridad
        if time.time() - last_valid_leader_time > MAX_TELEMETRY_AGE:
            print("EMERGENCIA: Sin telemetría del líder. Deteniendo follower.")
            send_movement_command(follower, 0, 0, 0)
            break
        print("Advertencia: No se recibió telemetría del líder en este ciclo. Omitiendo comando.")
        time.sleep(0.1)
        continue

    try:
        follower_lat, follower_lon, follower_alt = get_position_from_telemetry(follower_telemetry)
    except TimeoutError:
        print("Advertencia: No se recibió telemetría del follower en este ciclo. Omitiendo comando.")
        time.sleep(0.1)
        continue

    # =========================
    # DETECCIÓN DE ATERRIZAJE DEL LÍDER
    # Si el líder está en modo LAND o RTL y su altitud es menor que el umbral,
    # ordenamos al follower que aterrice y salimos del loop
    # =========================
    leader_mode  = leader_telemetry.get('flightMode', '')
    leader_state = leader_telemetry.get('state', '')

    if leader_mode in ('LAND', 'RTL') and leader_alt < LANDING_ALT_THRESHOLD:
        print(f"Líder aterrizando (modo: {leader_mode}, alt: {leader_alt:.2f} m). El follower inicia aterrizaje.")
        follower.Land()
        break

    # Si el líder ya está en tierra (desarmado), también aterrizamos
    if leader_state in ('disarmed', 'connected'):
        print(f"Líder desarmado (estado: {leader_state}). El follower inicia aterrizaje.")
        follower.Land()
        break

    # =========================
    # CÁLCULO DEL DESPLAZAMIENTO RELATIVO DEL LÍDER
    # Calculamos cuánto se ha movido el líder respecto a su origen (en metros)
    # =========================
    leader_disp_east, leader_disp_north = to_meters(
        leader_origin_lat, leader_origin_lon,
        leader_lat,        leader_lon
    )
    leader_disp_alt = leader_alt - leader_origin_alt

    # =========================
    # POSICIÓN OBJETIVO DEL FOLLOWER
    # El follower debe estar en su propio origen + el mismo desplazamiento que el líder
    # =========================
    follower_disp_east, follower_disp_north = to_meters(
        follower_origin_lat, follower_origin_lon,
        follower_lat,        follower_lon
    )
    target_alt = follower_origin_alt + leader_disp_alt

    # Error: diferencia entre donde debería estar el follower y donde está
    error_east  = leader_disp_east  - follower_disp_east
    error_north = leader_disp_north - follower_disp_north

    # =========================
    # PID
    # =========================
    v_east  = pid_x.compute(0, -error_east,  LOOP_DT)
    v_north = pid_y.compute(0, -error_north, LOOP_DT)
    vz      = pid_z.compute(target_alt, follower_alt, LOOP_DT)

    # =========================
    # ENVIAR COMANDOS
    # =========================
    send_movement_command(follower, v_north, v_east, vz)

    # =========================
    # DEBUG
    # =========================
    print(
        f"Disp líder:    N={leader_disp_north:.2f} m  E={leader_disp_east:.2f} m  alt={leader_disp_alt:.2f} m | "
        f"Error follower: N={error_north:.2f} m  E={error_east:.2f} m | "
        f"v_north:{v_north:.2f}  v_east:{v_east:.2f}  vz:{vz:.2f} | "
        f"leader_mode:{leader_mode}"
    )

    # Dormimos el tiempo restante del periodo para mantener el loop a LOOP_HZ Hz
    elapsed = time.time() - t_start
    time.sleep(max(0, LOOP_DT - elapsed))