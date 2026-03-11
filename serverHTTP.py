########  INSTALAR  ##########
# Flask, paho-mqtt
##############################

import json
from flask import Flask, request, jsonify, send_from_directory
from threading import Lock
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

app = Flask(__name__, static_folder="static", static_url_path="/static")

# ---- Identificador de esta webapp ante el broker ----
ORIGIN = "mobileFlask"

# ---- Flag: el usuario ha pulsado "Conectar" desde la webapp ----
user_connected = False

# ---- Estado compartido de telemetría (lo actualiza el callback MQTT) ----
telemetry = {
    "lat": 0.0,
    "lon": 0.0,
    "alt": 0.0,
    "groundSpeed": 0.0,
    "heading": 0,
    "state": "disconnected",
}
telemetry_lock = Lock()


# ===================== MQTT =====================

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[MQTT] Conectado al broker OK")
        # Suscribirse a todo lo que venga del AutopilotService dirigido a nosotros
        client.subscribe(f"autopilotServiceDemo/{ORIGIN}/#")
        print(f"[MQTT] Suscrito a autopilotServiceDemo/{ORIGIN}/#")
    else:
        print(f"[MQTT] Error de conexión, código={reason_code}")


def on_message(client, userdata, message):
    global user_connected
    topic = message.topic
    payload = message.payload.decode("utf-8")

    # topic tiene formato: autopilotServiceDemo/mobileFlask/<evento>
    parts = topic.split("/")
    if len(parts) < 3:
        return
    event = parts[2]

    # No actualizar el estado visible hasta que el usuario pulse Conectar
    if not user_connected:
        return

    if event == "telemetryInfo":
        try:
            info = json.loads(payload)
            with telemetry_lock:
                telemetry["lat"] = info.get("lat", 0.0)
                telemetry["lon"] = info.get("lon", 0.0)
                telemetry["alt"] = info.get("alt", 0.0)
                telemetry["groundSpeed"] = info.get("groundSpeed", 0.0)
                telemetry["heading"] = info.get("heading", 0)
                telemetry["state"] = info.get("state", "disconnected")
        except json.JSONDecodeError:
            pass

    elif event == "connected":
        with telemetry_lock:
            telemetry["state"] = "connected"

    elif event == "flying":
        with telemetry_lock:
            telemetry["state"] = "flying"

    elif event == "landed":
        with telemetry_lock:
            telemetry["state"] = "connected"

    elif event == "atHome":
        with telemetry_lock:
            telemetry["state"] = "connected"


# Crear cliente MQTT (paho v2)
mqtt_client = mqtt.Client(
    CallbackAPIVersion.VERSION2,
    ORIGIN,
    transport="websockets",
)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

broker_address = "broker.hivemq.com"
broker_port = 8000

print("[MQTT] Conectando al broker HiveMQ...")
mqtt_client.connect(broker_address, broker_port)
mqtt_client.loop_start()  # hilo de fondo para MQTT


# ===================== Helpers =====================

def publish(command, payload=""):
    """Publica un comando al AutopilotService vía MQTT."""
    topic = f"{ORIGIN}/autopilotServiceDemo/{command}"
    mqtt_client.publish(topic, payload)
    print(f"[HTTP→MQTT] Publicado {topic}  payload={payload}")


# ===================== Endpoints HTTP =====================

@app.route("/connect", methods=["POST"])
def http_connect():
    global user_connected
    user_connected = True
    publish("connect")
    return ("", 204)


@app.route("/takeoff", methods=["POST"])
def http_takeoff():
    data = request.get_json() or {}
    altura = data.get("altura") or data.get("alt") or data.get("height")
    if altura is None:
        return jsonify({"error": "falta campo 'altura'"}), 400
    publish("arm_takeOff", str(int(float(altura))))
    return ("", 204)


@app.route("/land", methods=["POST"])
def http_land():
    publish("Land")
    return ("", 204)


@app.route("/rtl", methods=["POST"])
def http_rtl():
    publish("RTL")
    return ("", 204)


@app.route("/move", methods=["POST"])
def http_move():
    data = request.get_json() or {}
    direction = data.get("direction") or data.get("dir")
    if not direction:
        return jsonify({"error": "falta campo 'direction'"}), 400
    publish("go", direction)
    return ("", 204)


@app.route("/changeHeading", methods=["POST"])
def http_change_heading():
    data = request.get_json() or {}
    heading = data.get("heading")
    if heading is None:
        return jsonify({"error": "falta campo 'heading'"}), 400
    publish("changeHeading", str(int(heading)))
    return ("", 204)


@app.route("/changeNavSpeed", methods=["POST"])
def http_change_speed():
    data = request.get_json() or {}
    speed = data.get("speed")
    if speed is None:
        return jsonify({"error": "falta campo 'speed'"}), 400
    publish("changeNavSpeed", str(float(speed)))
    return ("", 204)


@app.route("/telemetry", methods=["GET"])
def http_telemetry():
    with telemetry_lock:
        resp = dict(telemetry)
    return jsonify(resp)


@app.route("/")
def index():
    return send_from_directory("templates", "indexHTTP.html")


# ===================== Main =====================

if __name__ == "__main__":
    print("Arrancando Flask en http://127.0.0.1:5000")
    print("Recuerda iniciar primero AutopilotService.py")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
