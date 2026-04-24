from dronLink.Dron import Dron
import time
import math

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

# ⚠️ CAMBIAR IPs SEGÚN VUESTRA RED
LEADER_CONNECTION = "tcp:127.0.0.1:5763"
FOLLOWER_CONNECTION = "udp:0.0.0.0:14551"
BAUDIOS = 115200

DESIRED_DISTANCE = 5  # metros

# Tiempo máximo sin recibir telemetría del líder antes de parar el follower (segundos)
MAX_TELEMETRY_AGE = 2.0

# Frecuencia del loop de control (Hz) y periodo correspondiente (segundos)
LOOP_HZ = 20
LOOP_DT = 1.0 / LOOP_HZ

# =========================
# CONEXIÓN
# =========================
print("Creando instancias para los drones...")
leader = Dron()
follower = Dron()
print("Instancias creadas.")

print("Conectando al líder...")
if leader.connect(connection_string=LEADER_CONNECTION, baud=BAUDIOS):
    print("Líder conectado.")
else:
    print("Error al conectar con el líder.")

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

leader_telemetry = {}
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

pid_x = PIDController(0.4, 0.0, 0.15)
pid_y = PIDController(0.4, 0.0, 0.15)
pid_z = PIDController(0.6, 0.0, 0.2)

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


def send_movement_command(dron, v_north, v_east, vz):
    # Limitamos velocidades por seguridad (máximo 2 m/s horizontal, 1 m/s vertical)
    v_north_lim = max(min(v_north, 2.0), -2.0)
    v_east_lim = max(min(v_east, 2.0), -2.0)
    vz_lim = max(min(vz, 1.0), -1.0)

    # El eje Z en MAV_FRAME_LOCAL_NED es "Down". Invertimos vz para usar: + = subir
    ned_vz = -vz_lim

    try:
        # Generar el mensaje exacto con el vector de velocidad (X=North, Y=East, Z=Down)
        cmd = dron._prepare_command(v_north_lim, v_east_lim, ned_vz)
        dron.vehicle.mav.send(cmd)
    except Exception as e:
        print(f"Error enviando velocidades directas: {e}")


# =========================
# LOOP PRINCIPAL
# =========================

print("Esperando recepción de telemetría...")
while True:
    try:
        get_position_from_telemetry(leader_telemetry)
        get_position_from_telemetry(follower_telemetry)
        break
    except TimeoutError:
        time.sleep(0.5)
print("Telemetría recibida. Iniciando seguimiento.")

last_valid_leader_time = time.time()

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
    # ERROR (en metros)
    # =========================
    dist_east, dist_north = to_meters(follower_lat, follower_lon, leader_lat, leader_lon)

    distance = math.sqrt(dist_east**2 + dist_north**2)

    # mantener distancia
    if distance > 0:
        scale = (distance - DESIRED_DISTANCE) / distance
    else:
        scale = 0

    # Queremos reducir esta diferencia a 0
    target_east = dist_east * scale
    target_north = dist_north * scale

    # =========================
    # PID
    # =========================
    v_east = pid_x.compute(0, -target_east, LOOP_DT)
    v_north = pid_y.compute(0, -target_north, LOOP_DT)
    vz = pid_z.compute(leader_alt, follower_alt, LOOP_DT)

    # =========================
    # ENVIAR COMANDOS
    # =========================
    send_movement_command(follower, v_north, v_east, vz)

    # =========================
    # DEBUG
    # =========================
    print(f"Dist: {distance:.2f} m | v_north:{v_north:.2f} v_east:{v_east:.2f} vz:{vz:.2f}")

    # Dormimos el tiempo restante del periodo para mantener el loop a LOOP_HZ Hz
    elapsed = time.time() - t_start
    time.sleep(max(0, LOOP_DT - elapsed))