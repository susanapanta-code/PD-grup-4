############  INSTALAR ##############
# paho-mqtt
#####################################

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import json
import threading
from pymavlink import mavutil
from dronLink.Dron import Dron

# esta función sirve para generar un publisher específico para un origen
def create_publish_event(client, origin):
    def publish_event(event):
        topic = f"autopilotService04/{origin}/{event}"
        print(f"Publicando evento: {topic}")
        client.publish(topic)
    return publish_event

def create_publish_telemetry(client, origin):
    def publish_telemetry(telemetry_info):
        topic = f"autopilotService04/{origin}/telemetryInfo"
        client.publish(topic, json.dumps(telemetry_info))
    return publish_telemetry


def publish_event_payload(event, payload):
    """Publica un evento con payload de texto para diagnostico en el dashboard."""
    global sending_topic, client
    topic = sending_topic + '/' + event
    print(f"Publicando evento con payload: {topic} -> {payload}")
    client.publish(topic, str(payload))


def publish_telemetry_info (telemetry_info):
    # cuando reciba datos de telemetría los publico
    global sending_topic, client
    client.publish(sending_topic + '/telemetryInfo', json.dumps(telemetry_info))


def on_message(cli, userdata, message):
    global dron
    # el mensaje que se recibe tiene este formato:
    #    "origen"/autopilotService04/"command"

    try:
        topic_str = message.topic
        payload_str = message.payload.decode('utf-8')
    except:
        return

    splited = topic_str.split("/")
    if len(splited) < 3:
        return

    origin = splited[0] # nombre de la aplicación origen
    command = splited[2] # comando

    # IMPORTANTE: Ignorar ecos (mensajes enviados por nosotros mismos)
    if origin == "autopilotService04":
        return

    print(f"Mensaje recibido: topic={topic_str}, payload={payload_str}, dron.state={dron.state}")

    # Crear funciones de callback específicas para este origen
    # Esto evita el uso de variables globales y permite concurrencia
    publish_event = create_publish_event(cli, origin)
    publish_telemetry = create_publish_telemetry(cli, origin)

    if command == 'connect':
        if dron.state != 'disconnected':
            print(f'Dron ya conectado (state={dron.state}), reenviando evento connected')
            publish_event('connected')
            # Si ya estábamos enviando telemetría, aseguramos que este nuevo cliente también reciba
            # (Nota: DronLink generalmente soporta un solo callback de telemetría a la vez en esta versión simple,
            #  pero al menos refrescamos la conexión lógica).
            dron.send_telemetry_info(publish_telemetry)
        else:
            #connection_string = 'COM14'
            connection_string = 'tcp:127.0.0.1:5763'
            #connection_string = 'udp:127.0.0.1:14551'
            #baud = 57600
            baud = 115200
            print('Conectando al dron...')
            # Ejecutar en hilo aparte para NO bloquear el loop MQTT
            
            def do_connect():
                try:
                    dron.connect(connection_string, baud, freq=10)
                    print(f'Dron conectado, state={dron.state}')
                    publish_event('connected')
                    dron.send_telemetry_info(publish_telemetry)
                    print('Telemetría iniciada automáticamente')
                except Exception as e:
                    print(f"Error conectando al 5763: {e}")
                    # Reintento opcional en 5762 si falla
                    try:
                        print("Reintentando en tcp:127.0.0.1:5762...")
                        dron.connect('tcp:127.0.0.1:5762', baud, freq=10)
                        print(f'Dron conectado en 5762, state={dron.state}')
                        publish_event('connected')
                        dron.send_telemetry_info(publish_telemetry)
                    except Exception as e2:
                        print(f"Error final de conexión: {e2}")

            threading.Thread(target=do_connect, daemon=True).start()

    if command == 'disconnect':
        print(f'Comando disconnect recibido')
        if dron.state != 'disconnected':
            try:
                # Detenemos telemetría antes de desconectar para evitar errores
                dron.stop_sending_telemetry_info()
                dron.disconnect()
                print('Dron desconectado correctamente')
                publish_event('disconnected')
            except Exception as e:
                print(f"Error desconectando: {e}")
        else:
            print('El dron ya estaba desconectado')
            publish_event('disconnected')

    if command == 'arm':
        print(f'Comando arm recibido, dron.state={dron.state}')
        # Permitimos reintentar si falla la UI o si ya está armado (idempotente)
        if dron.state == 'connected' or dron.state == 'armed':
            def do_arm():
                if dron.state == 'armed':
                    print('Ya está armado, enviando evento armed')
                    publish_event('armed')
                    return

                try:
                    print('Iniciando armado...')
                    dron.arm()
                    print(f'Armado completado, state={dron.state}')
                    if dron.state == 'armed':
                        publish_event('armed')
                except Exception as e:
                    print(f'ERROR en arm: {e}')
            threading.Thread(target=do_arm, daemon=True).start()
        elif dron.state == 'armed':
            publish_event('armed')
        else:
            print(f'No se puede armar: dron.state={dron.state} (se esperaba "connected")')

    if command == 'disarm':
        print(f'Comando disarm recibido, dron.state={dron.state}')
        if dron.state == 'armed' and getattr(dron, 'vehicle', None):
            try:
                dron.vehicle.mav.command_long_send(
                    dron.vehicle.target_system,
                    dron.vehicle.target_component,
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                )
                dron.state = 'connected'
                publish_event('disarmed')
            except Exception as e:
                print(f'ERROR en disarm: {e}')
        elif dron.state == 'connected':
            publish_event('disarmed')
        else:
            print(f'No se puede desarmar: dron.state={dron.state} (se esperaba "armed")')

    if command == 'takeOff':
        print(f'Comando takeOff recibido, dron.state={dron.state}')
        if dron.state == 'armed':
            try:
                alt = float(message.payload.decode("utf-8"))
            except:
                alt = 5
            dron.takeOff(alt, blocking=False, callback=publish_event, params='flying')
        else:
            print(f'No se puede despegar: dron.state={dron.state} (se esperaba "armed")')

    if command == 'arm_takeOff':
        print(f'Comando arm_takeOff recibido, dron.state={dron.state}')
        # Permitimos despegar si está connected (flujo completo) o ya armed (solo takeoff)
        if dron.state == 'connected' or dron.state == 'armed':
            try:
                alt = float(payload_str)
            except:
                alt = 5

            def do_arm_takeoff():
                try:
                    # Solo intentamos armar si NO estamos ya armados
                    if dron.state != 'armed':
                        print(f'vamos a armar, altura={alt}')
                        dron.arm()
                        print(f'armado completado, state={dron.state}')

                    # Verificamos si estamos armados antes de despegar
                    if dron.state == 'armed':
                        print('vamos a despegar')
                        dron.takeOff(alt, blocking=False, callback=publish_event, params='flying')
                    else:
                        print(f'ERROR: No se pudo armar o estado incorrecto state={dron.state}')
                except Exception as e:
                    print(f'ERROR en arm/takeoff: {e}')
            threading.Thread(target=do_arm_takeoff, daemon=True).start()
        else:
            print(f'No se puede despegar: dron.state={dron.state}')

    if command == 'go':
        print(f'Comando go recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            direction = payload_str
            dron.go(direction)
        else:
            print(f'No se puede mover: dron.state={dron.state}')

    if command == 'goTo':
        print(f'Comando goTo recibido, dron.state={dron.state}')

        if dron.state == 'flying':
            try:
                coords = message.payload.decode("utf-8")
                lat, lon = coords.split(',')

                lat = float(lat)
                lon = float(lon)

                print(f'Ir a: {lat}, {lon}')

                # usamos la altitud actual del dron
                alt = dron.alt if dron.alt is not None else 5

                # llamada no bloqueante directa
                dron.goto(lat, lon, alt, blocking=False)

            except Exception as e:
                print(f'ERROR en goTo: {e}')
        else:
            print(f'No se puede ir a punto: dron.state={dron.state}')

    if command == 'Land':
        print(f'Comando Land recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            dron.Land(blocking=False, callback=publish_event, params='landed')
        else:
            print(f'No se puede aterrizar: dron.state={dron.state}')

    if command == 'RTL':
        print(f'Comando RTL recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            dron.RTL(blocking=False, callback=publish_event, params='atHome')
        else:
            print(f'No se puede RTL: dron.state={dron.state}')

    if command == 'startTelemetry':
        print(f'Comando startTelemetry recibido, dron.state={dron.state}')
        if dron.state != 'disconnected':
            dron.send_telemetry_info(publish_telemetry)

    if command == 'stopTelemetry':
        dron.stop_sending_telemetry_info()

    if command == 'changeHeading':
        if dron.state == 'flying':
            try:
                heading = int(payload_str)
                dron.changeHeading(heading, blocking=False)
            except:
                pass


    if command == 'changeNavSpeed':
        if dron.state == 'flying':
            try:
                speed = float(payload_str)
                dron.changeNavSpeed(speed)
            except:
                pass

    if command == 'rotate':
        print(f'Comando rotate recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            payload = message.payload.decode("utf-8") if message.payload else "cw:90"
            direction = 'cw'
            offset = 90
            try:
                if ':' in payload:
                    direction_part, offset_part = payload.split(':', 1)
                    direction = direction_part.strip().lower() or 'cw'
                    offset = int(offset_part.strip())
                else:
                    offset = int(payload)
            except Exception:
                direction = 'cw'
                offset = 90

            try:
                dron.rotate(offset, direction=direction, blocking=False, callback=publish_event, params='rotated')
            except Exception as e:
                print(f'ERROR en rotate: {e}')
        else:
            print(f'No se puede rotar: dron.state={dron.state} (se esperaba "flying")')

    if command == 'changeAltitude':
        print(f'Comando changeAltitude recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            try:
                altitude = int(float(message.payload.decode("utf-8")))
            except Exception:
                altitude = None

            if altitude is None:
                print('No se puede cambiar altitud: payload invalido')
            else:
                try:
                    dron.change_altitude(altitude, blocking=False, callback=publish_event, params='altitudeChanged')
                except Exception as e:
                    print(f'ERROR en changeAltitude: {e}')
        else:
            print(f'No se puede cambiar altitud: dron.state={dron.state} (se esperaba "flying")')

    if command == 'goto':
        print(f'Comando goto recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            lat = lon = None
            alt = None
            speed = None
            try:
                raw = message.payload.decode("utf-8") if message.payload else ""
                data = json.loads(raw)
                lat = float(data.get('lat'))
                lon = float(data.get('lon'))
                # Altitud opcional para compatibilidad con clientes antiguos.
                raw_alt = data.get('alt')
                if raw_alt is not None:
                    alt = float(raw_alt)
                # Velocidad opcional para fijar WPNAV_SPEED antes de iniciar goto.
                raw_speed = data.get('speed')
                if raw_speed is not None:
                    speed = float(raw_speed)
            except Exception as e:
                print(f'Payload goto invalido: {e}')
                publish_event_payload('gotoError', f'payload_invalido: {e}')

            if lat is None or lon is None:
                print('No se puede ejecutar goto: faltan lat/lon')
                publish_event_payload('gotoError', 'faltan_lat_lon')
            else:
                publish_event('gotoStarted')

                try:
                    if speed is not None:
                        # Usamos setParams directamente para evitar que changeNavSpeed reinicie
                        # el hilo de navegación (go), ya que goto lo detendrá inmediatamente.
                        dron.setParams([{'ID': "WPNAV_SPEED", 'Value': speed*100}])

                    if alt is None:
                        # Sin altitud, dronLink usa la altitud relativa actual.
                        dron.goto(lat, lon, blocking=False, callback=publish_event, params='gotoReached')
                    else:
                        dron.goto(lat, lon, alt, blocking=False, callback=publish_event, params='gotoReached')
                except Exception as e:
                    print(f'ERROR en goto: {e}')
                    publish_event_payload('gotoError', f'ejecucion_fallida: {e}')
        else:
            reason = f'estado_invalido:{dron.state}'
            print(f'No se puede hacer goto: dron.state={dron.state} (se esperaba "flying")')
            publish_event_payload('gotoError', reason)


def on_connect(client, userdata, flags, reason_code, properties):
    global connected
    if reason_code == 0:
        print("connected OK Returned code=", reason_code)
        connected = True
        # Re-suscribirse aquí para que al reconectar no se pierdan las suscripciones
        client.subscribe('+/autopilotService04/#')
        print('Suscrito a +/autopilotService04/#')
    else:
        print("Bad connection Returned code=", reason_code)


dron = Dron()

client = mqtt.Client(CallbackAPIVersion.VERSION2, "autopilotService04", transport="tcp")

# Usar broker test.mosquitto.org público
broker_address = "test.mosquitto.org"
broker_port = 1883

client.on_message = on_message
client.on_connect = on_connect
client.connect(broker_address, broker_port)

print('AutopilotServiceDemo esperando peticiones')
client.loop_forever()

