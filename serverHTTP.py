########  INSTALAR  ##########
# Flask
##############################

import json
import threading
from flask import Flask, request, jsonify, send_from_directory
from threading import Lock
from dronLink.Dron import Dron

app = Flask(__name__, static_folder="static", static_url_path="/static")

# ---- Instancia del dron (directa, sin MQTT) ----
dron = Dron()

# Estado compartido de telemetría
telemetry = {
    "lat": 0.0,
    "lon": 0.0,
    "alt": 0.0,
    "groundSpeed": 0.0,
    "heading": 0,
    "state": "disconnected",
}
telemetry_lock = Lock()


def telemetry_callback(telemetry_info):
    """Callback que dronLink llama periódicamente con datos de telemetría."""
    with telemetry_lock:
        telemetry["lat"] = telemetry_info.get("lat", 0.0)
        telemetry["lon"] = telemetry_info.get("lon", 0.0)
        telemetry["alt"] = telemetry_info.get("alt", 0.0)
        telemetry["groundSpeed"] = telemetry_info.get("groundSpeed", 0.0)
        telemetry["heading"] = telemetry_info.get("heading", 0)
        telemetry["state"] = telemetry_info.get("state", dron.state)


# ------------------ Endpoints HTTP ------------------

@app.route("/connect", methods=["POST"])
def http_connect():
    if dron.state != "disconnected":
        return jsonify({"status": "ya conectado", "state": dron.state}), 200

    def do_connect():
        try:
            print("Conectando al dron...")
            dron.connect("tcp:127.0.0.1:5763", 115200, freq=10)
            print(f"Dron conectado, state={dron.state}")
            # Iniciar telemetría automáticamente
            dron.send_telemetry_info(telemetry_callback)
            print("Telemetría iniciada")
        except Exception as e:
            print(f"Error conectando al dron: {e}")

    threading.Thread(target=do_connect, daemon=True).start()
    return ("", 204)


@app.route("/takeoff", methods=["POST"])
def http_takeoff():
    data = request.get_json() or {}
    altura = data.get("altura") or data.get("alt") or data.get("height")
    if altura is None:
        return jsonify({"error": "falta campo 'altura'"}), 400

    altura = int(float(altura))
    print(f"Takeoff solicitado, altura={altura}, dron.state={dron.state}")

    if dron.state != "connected":
        return jsonify({"error": f"dron.state={dron.state}, se necesita 'connected'"}), 400

    def do_arm_takeoff():
        try:
            print("Armando...")
            dron.arm()
            print(f"Armado OK, state={dron.state}")
            print(f"Despegando a {altura}m...")
            dron.takeOff(altura, blocking=False)
            print(f"Takeoff lanzado, state={dron.state}")
        except Exception as e:
            print(f"Error en arm/takeoff: {e}")

    threading.Thread(target=do_arm_takeoff, daemon=True).start()
    return ("", 204)


@app.route("/land", methods=["POST"])
def http_land():
    print(f"Land solicitado, dron.state={dron.state}")
    if dron.state in ("flying", "takingOff"):
        dron.Land(blocking=False)
    else:
        print(f"  -> Ignorado, state no es flying/takingOff")
    return ("", 204)


@app.route("/rtl", methods=["POST"])
def http_rtl():
    print(f"RTL solicitado, dron.state={dron.state}")
    if dron.state in ("flying", "takingOff"):
        dron.RTL(blocking=False)
    else:
        print(f"  -> Ignorado, state no es flying/takingOff")
    return ("", 204)


@app.route("/move", methods=["POST"])
def http_move():
    data = request.get_json() or {}
    direction = data.get("direction") or data.get("dir")
    if not direction:
        return jsonify({"error": "falta campo 'direction'"}), 400

    print(f"Move solicitado, direction={direction}, dron.state={dron.state}")
    if dron.state == "flying":
        dron.go(direction)
    else:
        print(f"  -> Ignorado, state no es flying")
    return ("", 204)


@app.route("/telemetry", methods=["GET"])
def http_telemetry():
    resp = {
        "alt": dron.alt,
        "state": dron.state,
    }
    return jsonify(resp)


@app.route("/")
def index():
    return send_from_directory("templates", "indexHTTP.html")


# ----------------------------------------------------

if __name__ == "__main__":
    print("Arrancando Flask en http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
