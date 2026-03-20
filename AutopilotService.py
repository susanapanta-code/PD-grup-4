############  INSTALAR ##############
# paho-mqtt
#####################################

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import json
import threading
from pymavlink import mavutil
from dronLink.Dron import Dron

# esta función sirve para publicar los eventos resultantes de las acciones solicitadas
def publish_event (event):
    global sending_topic, client
    topic = sending_topic + '/'+event
    print(f"Publicando evento: {topic}")
    client.publish(topic)


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
    global  sending_topic, client
    global dron
    # el mensaje que se recibe tiene este formato:
    #    "origen"/autopilotServiceDemo/"command"
    # tengo que averiguar el origen y el command
    splited = message.topic.split("/")
    if len(splited) < 3:
        return
    origin = splited[0] # aqui tengo el nombre de la aplicación que origina la petición
    command = splited[2] # aqui tengo el comando

    # IMPORTANTE: Ignorar los mensajes que publica este propio servicio.
    # La suscripción +/autopilotServiceDemo/# también captura
    # autopilotServiceDemo/origen/telemetryInfo (nuestras propias publicaciones).
    # Si origin == "autopilotServiceDemo" es un eco de lo que publicamos nosotros.
    if origin == "autopilotServiceDemo":
        return

    print(f"Mensaje recibido: topic={message.topic}, payload={message.payload.decode('utf-8')}, dron.state={dron.state}")

    sending_topic = "autopilotServiceDemo/" + origin # lo necesitaré para enviar las respuestas

    if command == 'connect':
        if dron.state != 'disconnected':
            # Ya conectado — avisamos al cliente y nos aseguramos de que la telemetría va
            print(f'Dron ya conectado (state={dron.state}), reenviando evento connected')
            publish_event('connected')
            if not dron.sendTelemetryInfo:
                dron.send_telemetry_info(publish_telemetry_info)
                print('Telemetría reiniciada')
        else:
            connection_string = 'tcp:127.0.0.1:5763'
            baud = 115200
            print('Conectando al dron...')
            # Ejecutar en hilo aparte para NO bloquear el loop MQTT
            def do_connect():
                try:
                    dron.connect(connection_string, baud, freq=10)
                    print(f'Dron conectado, state={dron.state}')
                    publish_event('connected')
                    # Iniciar telemetría automáticamente al conectar
                    dron.send_telemetry_info(publish_telemetry_info)
                    print('Telemetría iniciada automáticamente')
                except Exception as e:
                    err = str(e)
                    print(f'ERROR connect: {err}')
                    publish_event_payload('connect_error', err)
            threading.Thread(target=do_connect, daemon=True).start()

    if command == 'arm':
        print(f'Comando arm recibido, dron.state={dron.state}')
        if dron.state == 'connected':
            def do_arm_only():
                try:
                    dron.arm()
                    print(f'Armado completado, state={dron.state}')
                    if dron.state == 'armed':
                        publish_event('armed')
                except Exception as e:
                    print(f'ERROR en arm: {e}')
            threading.Thread(target=do_arm_only, daemon=True).start()
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
        if dron.state == 'connected':
            # leer la altura del payload; si no viene, usar 5 por defecto
            try:
                alt = float(message.payload.decode("utf-8"))
            except:
                alt = 5
            # Ejecutar en hilo aparte para NO bloquear el loop MQTT
            def do_arm_takeoff():
                try:
                    print(f'vamos a armar, altura={alt}')
                    dron.arm()
                    print(f'armado completado, state={dron.state}')
                    if dron.state == 'armed':
                        print('vamos a despegar')
                        dron.takeOff(alt, blocking=False, callback=publish_event, params='flying')
                    else:
                        print(f'ERROR: arm() completó pero state={dron.state}, no se puede despegar')
                except Exception as e:
                    print(f'ERROR en arm/takeoff: {e}')
            threading.Thread(target=do_arm_takeoff, daemon=True).start()
        else:
            print(f'No se puede despegar: dron.state={dron.state} (se esperaba "connected")')

    if command == 'go':
        print(f'Comando go recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            direction = message.payload.decode("utf-8")
            # go() no es bloqueante en sí, pero lo lanzamos en hilo por seguridad
            threading.Thread(target=dron.go, args=[direction], daemon=True).start()
        else:
            print(f'No se puede mover: dron.state={dron.state} (se esperaba "flying")')

    if command == 'Land':
        print(f'Comando Land recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            # operación no bloqueante. Cuando acabe publicará el evento correspondiente
            dron.Land(blocking=False, callback=publish_event, params='landed')
        else:
            print(f'No se puede aterrizar: dron.state={dron.state} (se esperaba "flying")')

    if command == 'RTL':
        print(f'Comando RTL recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            # operación no bloqueante. Cuando acabe publicará el evento correspondiente
            dron.RTL(blocking=False, callback=publish_event, params='atHome')
        else:
            print(f'No se puede RTL: dron.state={dron.state} (se esperaba "flying")')

    if command == 'startTelemetry':
        print(f'Comando startTelemetry recibido, dron.state={dron.state}')
        if dron.state != 'disconnected':
            # indico qué función va a procesar los datos de telemetría cuando se reciban
            dron.send_telemetry_info(publish_telemetry_info)
        else:
            print('No se puede iniciar telemetría: dron no conectado aún')

    if command == 'stopTelemetry':
        dron.stop_sending_telemetry_info()

    if command == 'changeHeading':
        if dron.state == 'flying':
            heading = int(message.payload.decode("utf-8"))
            # changeHeading es BLOQUEANTE (espera a que el dron alcance el heading)
            # DEBE ejecutarse en hilo aparte para no bloquear el loop MQTT
            threading.Thread(target=dron.changeHeading, args=[heading], daemon=True).start()

    if command == 'changeNavSpeed':
        if dron.state == 'flying':
            speed = float(message.payload.decode("utf-8"))
            # changeNavSpeed llama a setParams (bloqueante) y luego a go()
            # DEBE ejecutarse en hilo aparte para no bloquear el loop MQTT
            threading.Thread(target=dron.changeNavSpeed, args=[speed], daemon=True).start()

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

                def do_goto_with_speed():
                    try:
                        if speed is not None:
                            dron.changeNavSpeed(speed)
                        if alt is None:
                            # Sin altitud, dronLink usa la altitud relativa actual.
                            dron.goto(lat, lon, blocking=False, callback=publish_event, params='gotoReached')
                        else:
                            dron.goto(lat, lon, alt, blocking=False, callback=publish_event, params='gotoReached')
                    except Exception as e:
                        print(f'ERROR en goto: {e}')
                        publish_event_payload('gotoError', f'ejecucion_fallida: {e}')

                threading.Thread(target=do_goto_with_speed, daemon=True).start()
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
        client.subscribe('+/autopilotServiceDemo/#')
        print('Suscrito a +/autopilotServiceDemo/#')
    else:
        print("Bad connection Returned code=", reason_code)


dron = Dron()

client = mqtt.Client(CallbackAPIVersion.VERSION2, "autopilotServiceDemo", transport="websockets")

# me conecto al broker publico y gratuito
broker_address = "broker.hivemq.com"
broker_port = 8000

client.on_message = on_message
client.on_connect = on_connect
client.connect (broker_address,broker_port)

print ('AutopilotServiceDemo esperando peticiones')
client.loop_forever()