#imitar
#igual a prueba2.py pero con el heading del follower siempre viendo al leader

from pymavlink import mavutil
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
#LEADER_CONNECTION   = "udp:127.0.0.1:14551"
LEADER_CONNECTION   = "tcp:127.0.0.1:5762"
#FOLLOWER_CONNECTION = "udp:127.0.0.1:14561"
FOLLOWER_CONNECTION = "tcp:127.0.0.1:5772"
#BAUDIOS = 57600
BAUDIOS = 115200


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

# Altitud de despegue por defecto para la botonera (metros)
DEFAULT_TAKEOFF_ALT = 5.0

# Umbral para considerar que el dron esta en el aire (metros)
AIRBORNE_ALT_THRESHOLD = 1.0

# =========================
# CONEXIÓN
# =========================
print("Creando instancias para los drones...")
leader   = Dron()
follower = Dron()
print("Instancias creadas.")

leader_connected = threading.Event()
follower_connected = threading.Event()
telemetry_ready = threading.Event()

# =========================
# ACTIVAR TELEMETRÍA
# =========================

leader_telemetry   = {}
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


# =========================
# PID
# =========================

pid_x = PIDController(0.2, 0.0, 0.15)
pid_y = PIDController(0.2, 0.0, 0.15)
pid_z = PIDController(0.2, 0.0, 0.05)

# =========================
# CONTROL DE FLUJO (GUI/SEGUIMIENTO)
# =========================
follow_requested = threading.Event()
follow_enabled = threading.Event()
initial_position_checked = threading.Event()


def is_airborne(telemetry_dict):
    alt = telemetry_dict.get('alt', 0.0)
    state = telemetry_dict.get('state', '')
    return alt >= AIRBORNE_ALT_THRESHOLD or state in ('flying', 'returning', 'landing')


def both_airborne():
    return is_airborne(leader_telemetry) and is_airborne(follower_telemetry)


# =========================
# FUNCIONES DE CONTROL DE SEGUIMIENTO
# =========================

def stop_follow(status_var=None):
    """Para el seguimiento, resetea los flags y detiene el movimiento del follower."""
    follow_requested.clear()
    follow_enabled.clear()
    initial_position_checked.clear()
    if status_var:
        status_var.set("Seguimiento: OFF")
    print("\nSeguimiento detenido.")
    # Enviamos un comando para que el dron se quede quieto (hover)
    send_movement_command(follower, 0, 0, 0)


# =========================
# INTERFAZ GRAFICA PARA TUNING PID + CONTROL DE VUELO
# =========================
def create_gui():
    root = tk.Tk()
    root.title("Control PID y Seguimiento")
    root.geometry("380x620")

    status_var = tk.StringVar(value="Seguimiento: OFF")
    connection_var = tk.StringVar(value="Conexión: esperando")
    takeoff_alt_var = tk.DoubleVar(value=DEFAULT_TAKEOFF_ALT)

    def update_pids_xy(val):
        pid_x.kp = pid_y.kp = float(slider_kp_xy.get())
        pid_x.ki = pid_y.ki = float(slider_ki_xy.get())
        pid_x.kd = pid_y.kd = float(slider_kd_xy.get())

    def update_pids_z(val):
        pid_z.kp = float(slider_kp_z.get())
        pid_z.ki = float(slider_ki_z.get())
        pid_z.kd = float(slider_kd_z.get())

    def _connect_leader():
        if leader_connected.is_set():
            return
        print("Conectando al líder...")
        def on_leader_connected():
            leader_connected.set()
            print("Líder conectado.")
        ok = leader.connect(connection_string=LEADER_CONNECTION, baud=BAUDIOS, blocking=False, callback=on_leader_connected)
        if not ok:
            print("Error al conectar con el líder.")

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
            print("Conecta ambos drones antes de activar telemetría.")
            return
        start_telemetry()

    def start_telemetry_button():
        threading.Thread(target=_start_telemetry_safe, daemon=True).start()

    def _arm_and_takeoff_both():
        try:
            alt = float(takeoff_alt_var.get())

            # Armar al líder primero
            print("🚁 Armando LÍDER...")
            leader.arm()
            print("✅ LÍDER armado correctamente")

            # Pequeño delay para evitar conflictos de recursos
            time.sleep(2)

            # Armar al seguidor
            print("🚁 Armando SEGUIDOR...")
            follower.arm()
            print("✅ SEGUIDOR armado correctamente")

            # Pequeño delay antes de despegar
            time.sleep(1)

            # Despegar ambos con pequeño delay
            print(f"📤 Despegando LÍDER a {alt}m...")
            leader.takeOff(alt)
            print("✅ LÍDER despegando")

            time.sleep(1)

            print(f"📤 Despegando SEGUIDOR a {alt}m...")
            follower.takeOff(alt)
            print("✅ SEGUIDOR despegando")

            print("\n✈️  ¡Ambos drones en vuelo!")

        except Exception as e:
            print(f"❌ Error armando/despegando drones: {e}")

    def arm_and_takeoff_both():
        threading.Thread(target=_arm_and_takeoff_both, daemon=True).start()

    def request_follow():
        if not (telemetry_ready.is_set() and both_airborne()):
            print("ERROR: Ambos drones deben estar conectados, con telemetría y en el aire para iniciar el seguimiento.")
            status_var.set("Seguimiento: ¡Error! Despega primero.")
            return

        follow_requested.set()
        status_var.set("Seguimiento: iniciando...")


    def stop_follow_button():
        # Llama a la función global stop_follow, pasándole la variable de estado de la GUI
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

    control_frame = tk.LabelFrame(root, text="Control de vuelo")
    control_frame.pack(fill="x", padx=10, pady=8)

    tk.Label(control_frame, textvariable=connection_var).pack(pady=2)
    tk.Button(control_frame, text="Conectar líder", command=connect_leader).pack(fill="x", padx=10, pady=2)
    tk.Button(control_frame, text="Conectar seguidor", command=connect_follower).pack(fill="x", padx=10, pady=2)
    tk.Button(control_frame, text="Conectar ambos", command=connect_both).pack(fill="x", padx=10, pady=2)
    tk.Button(control_frame, text="Activar telemetría", command=start_telemetry_button).pack(fill="x", padx=10, pady=3)

    tk.Label(control_frame, text="Altitud despegue (m)").pack(pady=2)
    tk.Scale(control_frame, from_=1.0, to=20.0, resolution=0.5, orient="horizontal", variable=takeoff_alt_var).pack(fill="x", padx=10)

    tk.Button(control_frame, text="Armar y Despegar", command=arm_and_takeoff_both).pack(fill="x", padx=10, pady=3)
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

# Lanzamos la interfaz en un hilo separado para que no pause el bucle del dron
gui_thread = threading.Thread(target=create_gui, daemon=True)
gui_thread.start()
print("Dashboard abierto. Pulsa los botones para conectar y activar telemetría.")
print("Mientras tanto, el script esperará a que completes estas acciones...\n")

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

def send_movement_command(dron, v_north, v_east, vz, yaw_rad):
    # Limitamos velocidades por seguridad
    v_north_lim = max(min(v_north, 5.0), -5.0)
    v_east_lim  = max(min(v_east,  5.0), -5.0)
    vz_lim      = max(min(vz,      1.0), -1.0)
    ned_vz = -vz_lim

    try:
        # La máscara 0b0000101111000111 (Bit 10 = 0) indica al dron que debe
        # hacer caso a los parámetros de velocidad Y al de yaw simultáneamente.
        cmd = mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
            0,
            dron.vehicle.target_system,
            dron.vehicle.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000101111000111,
            0, 0, 0,                              # posiciones ignoradas
            v_north_lim, v_east_lim, ned_vz,      # velocidades aplicadas
            0, 0, 0,                              # aceleraciones ignoradas
            yaw_rad, 0                            # YAW aplicado (en radianes), yaw_rate ignorado
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

# Variables de origen que se calibrarán después del despegue
leader_origin_lat,   leader_origin_lon,   leader_origin_alt   = 0, 0, 0
follower_origin_lat, follower_origin_lon, follower_origin_alt = 0, 0, 0
last_valid_leader_time = 0

# =========================
# LOOP PRINCIPAL
# =========================

while True:
    t_start = time.time()

    # Si el seguimiento no está activado, no hacemos nada
    if not follow_requested.is_set():
        time.sleep(0.1)
        continue

    # --- INICIALIZACIÓN DEL SEGUIMIENTO (se ejecuta solo una vez) ---
    if not initial_position_checked.is_set():
        print("\n--- INICIANDO SECUENCIA DE SEGUIMIENTO ---")
        # 1. Comprobar que ambos drones están en el aire
        if not both_airborne():
            print("Esperando a que ambos drones despeguen...")
            time.sleep(0.5)
            continue

        # 2. COMPROBACIÓN DE POSICIÓN INICIAL
        leader_lat, leader_lon, leader_alt       = get_position_from_telemetry(leader_telemetry)
        follower_lat, follower_lon, follower_alt = get_position_from_telemetry(follower_telemetry)

        LEADER_REF_LAT = leader_lat
        LEADER_REF_LON = leader_lon
        FOLLOWER_REF_LAT = LEADER_REF_LAT + OFFSET_LAT
        FOLLOWER_REF_LON = LEADER_REF_LON + OFFSET_LON

        dist_follower_to_ref = distance_meters(follower_lat, follower_lon, FOLLOWER_REF_LAT, FOLLOWER_REF_LON)

        print(f"Objetivo Follower: lat={FOLLOWER_REF_LAT:.7f}, lon={FOLLOWER_REF_LON:.7f}")
        print(f"Distancia actual del follower al objetivo: {dist_follower_to_ref:.2f} m")

        # 3. Mover follower a su posición si es necesario
        if dist_follower_to_ref > REF_TOLERANCE_M:
            print(f"\n🔄 Moviendo FOLLOWER automáticamente al punto equivalente...")
            follower.goto(FOLLOWER_REF_LAT, FOLLOWER_REF_LON, follower_alt, 2) # Velocidad de 2 m/s

            t_goto_start = time.time()
            while True:
                follower_lat, follower_lon, _ = get_position_from_telemetry(follower_telemetry)
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

        # 4. CALIBRACIÓN DE ORÍGENES
        leader_origin_lat,   leader_origin_lon,   leader_origin_alt   = get_position_from_telemetry(leader_telemetry)
        follower_origin_lat, follower_origin_lon, follower_origin_alt = get_position_from_telemetry(follower_telemetry)

        print(f"\nOrigen líder:    lat={leader_origin_lat:.7f}   lon={leader_origin_lon:.7f}   alt={leader_origin_alt:.2f} m")
        print(f"Origen follower: lat={follower_origin_lat:.7f} lon={follower_origin_lon:.7f} alt={follower_origin_alt:.2f} m")
        print("Orígenes calibrados. Iniciando replicado de movimiento.\n")

        # FIJAMOS EL HEADING DE NAVEGACIÓN UNA SOLA VEZ
        follower.fixHeading()

        last_valid_leader_time = time.time()
        initial_position_checked.set() # Marcamos que la inicialización ha terminado
        follow_enabled.set() # Activamos el seguimiento real
        continue # Pasamos al siguiente ciclo del loop

    # --- LÓGICA DE SEGUIMIENTO (se ejecuta si follow_enabled es true) ---
    if not follow_enabled.is_set():
        time.sleep(0.1)
        continue

    try:
        leader_lat, leader_lon, leader_alt = get_position_from_telemetry(leader_telemetry)
        last_valid_leader_time = time.time()
    except TimeoutError:
        if time.time() - last_valid_leader_time > MAX_TELEMETRY_AGE:
            print("EMERGENCIA: Sin telemetría del líder. Deteniendo follower.")
            send_movement_command(follower, 0, 0, 0)
            stop_follow()
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

    # DETECCION DE ATERRIZAJE DEL LIDER
    leader_mode  = leader_telemetry.get('flightMode', '')
    leader_state = leader_telemetry.get('state', '')

    if (leader_mode in ('LAND', 'RTL') and leader_alt < LANDING_ALT_THRESHOLD) or \
       (leader_state == 'disarmed' and leader_alt < AIRBORNE_ALT_THRESHOLD):
        print(f"Lider aterrizando o desarmado. El follower inicia aterrizaje.")
        follower.Land()
        stop_follow()
        break

    # CÁLCULO DEL DESPLAZAMIENTO RELATIVO DEL LÍDER
    leader_disp_east, leader_disp_north = to_meters(
        leader_origin_lat, leader_origin_lon,
        leader_lat,        leader_lon
    )
    leader_disp_alt = leader_alt - leader_origin_alt

    # POSICIÓN OBJETIVO DEL FOLLOWER
    follower_disp_east, follower_disp_north = to_meters(
        follower_origin_lat, follower_origin_lon,
        follower_lat,        follower_lon
    )
    target_alt = follower_origin_alt + leader_disp_alt

    error_east  = leader_disp_east  - follower_disp_east
    error_north = leader_disp_north - follower_disp_north

    # PID
    v_east  = pid_x.compute(0, -error_east,  LOOP_DT)
    v_north = pid_y.compute(0, -error_north, LOOP_DT)
    vz      = pid_z.compute(target_alt, follower_alt, LOOP_DT)

    # --- NUEVO CÓDIGO PARA CALCULAR Y FIJAR EL HEADING ---
    # Vector real del seguidor al líder usando sus coordenadas GPS actuales
    vec_to_leader_east, vec_to_leader_north = to_meters(
        follower_lat, follower_lon,
        leader_lat,   leader_lon
    )

    # Calcular el ángulo (yaw) en radianes usando atan2(este, norte)
    # En aviación, 0º es Norte (eje Y analítico) y 90º es Este (eje X analítico),
    # por lo que el uso de (Este, Norte) en atan2 es correcto.
    yaw_rad = math.atan2(vec_to_leader_east, vec_to_leader_north)

    # ENVIAR COMANDOS INTEGRADOS DE MOVIMIENTO + ROTACIÓN
    send_movement_command(follower, v_north, v_east, vz, yaw_rad)

    # Convertir a grados (0-360) como espera la función changeHeading de dronLink
    yaw_deg = math.degrees(yaw_rad)
    if yaw_deg < 0:
        yaw_deg += 360

    # --- FIN DEL NUEVO CÓDIGO ---

    # DEBUG
    print(
        f"Disp líder: N={leader_disp_north:.2f} E={leader_disp_east:.2f} | "
        f"Error: N={error_north:.2f} E={error_east:.2f} | "
        f"Vels: N={v_north:.2f} E={v_east:.2f} | "
        f"Yaw: {yaw_deg:.1f}°", end='\r'
    )

    elapsed = time.time() - t_start
    time.sleep(max(0, LOOP_DT - elapsed))
