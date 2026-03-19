############  INSTALAR ##############
# paho-mqtt
#####################################

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import json
import threading
from dronLink.Dron import Dron

# esta función sirve para generar un publisher específico para un origen
def create_publish_event(client, origin):
    def publish_event(event):
        topic = f"autopilotServiceDemo/{origin}/{event}"
        print(f"Publicando evento: {topic}")
        client.publish(topic)
    return publish_event

def create_publish_telemetry(client, origin):
    def publish_telemetry_info(telemetry_info):
        topic = f"autopilotServiceDemo/{origin}/telemetryInfo"
        client.publish(topic, json.dumps(telemetry_info))
    return publish_telemetry_info


def on_message(cli, userdata, message):
    global dron
    # el mensaje que se recibe tiene este formato:
    #    "origen"/autopilotServiceDemo/"command"

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
    if origin == "autopilotServiceDemo":
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
            connection_string = 'tcp:127.0.0.1:5762'
            baud = 115200
            print(f'Conectando al dron en {connection_string}...')

            def do_connect():
                try:
                    dron.connect(connection_string, baud, freq=10)
                    print(f'Dron conectado, state={dron.state}')
                    publish_event('connected')
                    dron.send_telemetry_info(publish_telemetry)
                    print('Telemetría iniciada automáticamente')
                except Exception as e:
                    print(f"Error conectando: {e}")

            threading.Thread(target=do_connect, daemon=True).start()

    if command == 'arm_takeOff':
        print(f'Comando arm_takeOff recibido, dron.state={dron.state}')
        if dron.state == 'connected':
            try:
                alt = float(payload_str)
            except:
                alt = 5

            def do_arm_takeoff():
                try:
                    print(f'vamos a armar, altura={alt}')
                    dron.arm()
                    print(f'armado completado, state={dron.state}')
                    if dron.state == 'armed':
                        print('vamos a despegar')
                        dron.takeOff(alt, blocking=False, callback=publish_event, params='flying')
                    else:
                        print(f'ERROR: arm() completó pero state={dron.state}')
                except Exception as e:
                    print(f'ERROR en arm/takeoff: {e}')
            threading.Thread(target=do_arm_takeoff, daemon=True).start()
        else:
            print(f'No se puede despegar: dron.state={dron.state}')

    if command == 'go':
        print(f'Comando go recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            direction = payload_str
            threading.Thread(target=dron.go, args=[direction], daemon=True).start()
        else:
            print(f'No se puede mover: dron.state={dron.state}')

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
                threading.Thread(target=dron.changeHeading, args=[heading], daemon=True).start()
            except:
                pass

    if command == 'changeNavSpeed':
        if dron.state == 'flying':
            try:
                speed = float(payload_str)
                threading.Thread(target=dron.changeNavSpeed, args=[speed], daemon=True).start()
            except:
                pass


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

# me conecto al broker de la universidad
broker_address = "dronseetac.upc.edu"
broker_port = 8000
client.username_pw_set("dronsEETAC", "mimara1456.")

client.on_message = on_message
client.on_connect = on_connect
client.connect (broker_address,broker_port)

print ('AutopilotServiceDemo esperando peticiones')
client.loop_forever()