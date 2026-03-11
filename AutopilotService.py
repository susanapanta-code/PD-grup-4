############  INSTALAR ##############
# paho-mqtt, version 1.6.1
#####################################

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import json
import threading
from dronLink.Dron import Dron

# esta función sirve para publicar los eventos resultantes de las acciones solicitadas
def publish_event (event):
    global sending_topic, client
    topic = sending_topic + '/'+event
    print(f"Publicando evento: {topic}")
    client.publish(topic)


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
    origin = splited[0] # aqui tengo el nombre de la aplicación que origina la petición
    command = splited[2] # aqui tengo el comando

    print(f"Mensaje recibido: topic={message.topic}, payload={message.payload.decode('utf-8')}, dron.state={dron.state}")

    sending_topic = "autopilotServiceDemo/" + origin # lo necesitaré para enviar las respuestas

    if command == 'connect':
        connection_string = 'tcp:127.0.0.1:5763'
        baud = 115200
        print('Conectando al dron...')
        # Ejecutar en hilo aparte para NO bloquear el loop MQTT
        def do_connect():
            dron.connect(connection_string, baud, freq=10)
            print(f'Dron conectado, state={dron.state}')
            publish_event('connected')
            # Iniciar telemetría automáticamente al conectar
            dron.send_telemetry_info(publish_telemetry_info)
            print('Telemetría iniciada automáticamente')
        threading.Thread(target=do_connect, daemon=True).start()

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
                print(f'vamos a armar, altura={alt}')
                dron.arm()
                print(f'armado completado, state={dron.state}')
                print('vamos a despegar')
                dron.takeOff(alt, blocking=False, callback=publish_event, params='flying')
            threading.Thread(target=do_arm_takeoff, daemon=True).start()
        else:
            print(f'No se puede despegar: dron.state={dron.state} (se esperaba "connected")')

    if command == 'go':
        print(f'Comando go recibido, dron.state={dron.state}')
        if dron.state == 'flying':
            direction = message.payload.decode("utf-8")
            dron.go(direction)
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
            dron.changeHeading(heading)

    if command == 'changeNavSpeed':
        if dron.state == 'flying':
            speed = float(message.payload.decode("utf-8"))
            dron.changeNavSpeed(speed)


def on_connect(client, userdata, flags, rc):
    global connected
    if rc==0:
        print("connected OK Returned code=",rc)
        connected = True
        # Re-suscribirse aquí para que al reconectar no se pierdan las suscripciones
        client.subscribe('+/autopilotServiceDemo/#')
        print('Suscrito a +/autopilotServiceDemo/#')
    else:
        print("Bad connection Returned code=",rc)


dron = Dron()

client = mqtt.Client(CallbackAPIVersion.VERSION1, "autopilotServiceDemo", transport="websockets")

# me conecto al broker publico y gratuito
broker_address = "broker.hivemq.com"
broker_port = 8000

client.on_message = on_message
client.on_connect = on_connect
client.connect (broker_address,broker_port)

print ('AutopilotServiceDemo esperando peticiones')
client.loop_forever()