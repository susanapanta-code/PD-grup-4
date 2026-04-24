import time
import math
from pymavlink import mavutil

class PIDController:
    """
    Controlador PID genérico.
    """
    def __init__(self, kp, ki, kd, max_out=2.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.integral = 0.0
        self.previous_error = 0.0
        self.max_out = max_out  # Satura la salida (ej: max velocidad en m/s)
        self.last_time = time.time()

    def compute(self, setpoint, current_value):
        now = time.time()
        dt = now - self.last_time
        if dt <= 0:
            dt = 1e-4

        error = setpoint - current_value
        self.integral += error * dt

        # Anti-windup básico
        self.integral = max(min(self.integral, self.max_out), -self.max_out)

        derivative = (error - self.previous_error) / dt

        output = (self.kp * error) + (self.ki * self.integral) + (self.kd * derivative)

        # Saturación de salida (limitador de velocidad)
        output = max(min(output, self.max_out), -self.max_out)

        self.previous_error = error
        self.last_time = now

        return output

def connect_drones(leader_conn_str, follower_conn_str):
    """Establece conexión con el líder y el seguidor."""
    print(f"Conectando al Líder en {leader_conn_str}...")
    leader = mavutil.mavlink_connection(leader_conn_str)
    leader.wait_heartbeat()
    print("¡Líder conectado!")

    print(f"Conectando al Seguidor en {follower_conn_str}...")
    follower = mavutil.mavlink_connection(follower_conn_str)
    follower.wait_heartbeat()
    print("¡Seguidor conectado!")

    return leader, follower

def set_mode(vehicle, mode_name):
    """Cambia el modo de vuelo del vehículo especificado."""
    if mode_name not in vehicle.mode_mapping():
        print(f"Modo {mode_name} no disponible.")
        return False
    mode_id = vehicle.mode_mapping()[mode_name]
    vehicle.mav.set_mode_send(
        vehicle.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id
    )
    # Esperamos a que confirme el modo
    while True:
        ack = vehicle.recv_match(type='HEARTBEAT', blocking=True)
        if ack.custom_mode == mode_id:
            print(f"Modo cambiado exitosamente a {mode_name}")
            break
        time.sleep(0.1)

def arm_and_takeoff(vehicle, tx_alt):
    """Arma motores y despega a una altitud dada."""
    print("Armando motores...")
    vehicle.mav.command_long_send(
        vehicle.target_system, vehicle.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 0, 0, 0, 0, 0, 0
    )
    vehicle.motors_armed_wait()
    print("¡Motores armados!")

    print(f"Despegando a {tx_alt} metros...")
    vehicle.mav.command_long_send(
        vehicle.target_system, vehicle.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0, 0, 0, 0, 0, 0, 0, tx_alt
    )

    # Bucle para esperar que alcance la altura
    while True:
        msg = vehicle.recv_match(type='LOCAL_POSITION_NED', blocking=True)
        if msg:
            # altitud NED es negativa hacia arriba
            current_alt = -msg.z
            print(f" Altitud actual: {current_alt:.2f}m")
            if current_alt >= tx_alt * 0.95:  # 95% de la altura objetivo
                print("¡Altitud objetivo alcanzada!")
                break
        time.sleep(0.5)

def send_velocity_command(vehicle, vx, vy, vz=0.0):
    """
    Envía comandos de velocidad (m/s) en el cuadro Local NED (North, East, Down).
    Para un dron pesado como el EDU-450, los cambios de velocidad tienen un efecto de
    inercia real en la simulación SITL de ArduPilot.
    """
    # Type_mask: ignorar posiciones (bits 0,1,2 = 7) y aceleraciones (bits 6,7,8 = 448)
    # También ignoramos Mapeo de Guiñada (Yaw) (bits 10,11 = 3072)
    # Total ignorado: 7 + 448 + 3072 = 3527 = 0x0DC7
    type_mask = 0b0000110111000111

    vehicle.mav.set_position_target_local_ned_send(
        0,  # time_boot_ms (no importa aquí)
        vehicle.target_system, vehicle.target_component,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        type_mask,
        0, 0, 0,         # x, y, z (ignorados)
        vx, vy, vz,      # vx, vy, vz en m/s
        0, 0, 0,         # afx, afy, afz (aceleraciones ignoradas)
        0, 0             # yaw, yaw_rate (ignorados)
    )

def main():
    # Parámetros PID (tendrás que ajustarlos según la inercia del EDU-450)
    # Un dron pesado necesitará un P no muy agresivo para no oscilar,
    # y un D alto para frenar antes de llegar.
    KP = 0.5
    KI = 0.01
    KD = 0.8
    MAX_VEL = 5.0 # Max 5 m/s

    pid_x = PIDController(KP, KI, KD, max_out=MAX_VEL)
    pid_y = PIDController(KP, KI, KD, max_out=MAX_VEL)

    target_altitude = 5.0  # en metros
    hz = 10                # 10 ciclos por segundo
    loop_time = 1.0 / hz

    try:
        # 1. Conexión de los drones
        leader, follower = connect_drones('tcp:127.0.0.1:5760', 'tcp:127.0.0.1:5770')

        # Opcional: Solicitar stream de mensajes frecuentes para la posición
        leader.mav.request_data_stream_send(leader.target_system, leader.target_component,
                                            mavutil.mavlink.MAV_DATA_STREAM_POSITION, hz, 1)
        follower.mav.request_data_stream_send(follower.target_system, follower.target_component,
                                              mavutil.mavlink.MAV_DATA_STREAM_POSITION, hz, 1)

        # 2. Preparar al seguidor (Asegúrate de que SITL tenga la estimación EKF lista)
        print("Cambiando Seguidor a modo GUIDED...")
        set_mode(follower, "GUIDED")

        print("Iniciando secuencia de despegue (Seguidor)...")
        arm_and_takeoff(follower, target_altitude)

        print("\n--- INICIANDO SEGUIMIENTO PID ---")

        # 3. Bucle Principal de Control a 10Hz
        leader_pos = {"x": 0.0, "y": 0.0}
        follower_pos = {"x": 0.0, "y": 0.0}

        while True:
            start_time = time.time()

            # Recibir actualizaciones sin bloqueo de ejecución
            # LEADER: Buscar MAVLink LOCAL_POSITION_NED
            msg_l = leader.recv_match(type='LOCAL_POSITION_NED', blocking=False)
            if msg_l:
                leader_pos["x"] = msg_l.x
                leader_pos["y"] = msg_l.y

            # FOLLOWER: Buscar MAVLink LOCAL_POSITION_NED
            msg_f = follower.recv_match(type='LOCAL_POSITION_NED', blocking=False)
            if msg_f:
                follower_pos["x"] = msg_f.x
                follower_pos["y"] = msg_f.y

            # 4. Calcular PID y Comandar vuelo
            # Asumimos que la Z la mantiene SITL en Guided por defecto con enviar comando vx,vy,vz(0)
            vel_x = pid_x.compute(setpoint=leader_pos["x"], current_value=follower_pos["x"])
            vel_y = pid_y.compute(setpoint=leader_pos["y"], current_value=follower_pos["y"])

            send_velocity_command(follower, vel_x, vel_y, vz=0.0)

            # Log de Monitorización opcional
            # print(f"ErrorX/Y: {leader_pos['x']-follower_pos['x']:.2f}/{leader_pos['y']-follower_pos['y']:.2f} | VelX/Y: {vel_x:.2f}/{vel_y:.2f}")

            # Control manual de frecuencia
            elapsed = time.time() - start_time
            if elapsed < loop_time:
                time.sleep(loop_time - elapsed)

    except KeyboardInterrupt:
        print("\nInterrupción por el usuario (Ctrl+C). Aterrizando el Seguidor...")
        set_mode(follower, "LAND")
        print("Fin de simulación.")
    except Exception as e:
        print(f"Error inesperado: {e}")

if __name__ == "__main__":
    main()

