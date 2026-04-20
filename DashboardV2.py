"""
DashboardV2.py — Dashboard unificado (versión 2)

Integra:
  • Servicio de autopiloto (modo Local o modo Global)
  • Servicio de cámara (WebRTC, receptor local)

Modo LOCAL  → comandos directos al dron a través de dronLink (Dron)
Modo GLOBAL → comandos publicados vía MQTT al AutopilotService

##########  DEPENDENCIAS ##########
# paho-mqtt
# aiortc
# opencv-python
# pymavlink   (necesario para dronLink)
####################################
"""

import asyncio
import json
import threading
import tkinter as tk
from tkinter import messagebox

import cv2
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.signaling import TcpSocketSignaling

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from dronLink.Dron import Dron


# ══════════════════════════════════════════
#  CONSTANTES
# ══════════════════════════════════════════

COLOR_DISPONIBLE = "dark orange"
COLOR_EN_PROCESO = "yellow"
COLOR_ACTIVO     = "green"
FG_NORMAL        = "black"
FG_ACTIVO        = "white"

# Broker MQTT (modo Global)
BROKER_ADDRESS   = "broker.hivemq.com"
BROKER_PORT      = 8000
MQTT_CLIENT_ID   = "InterfazGlobalV2"
MQTT_TOPIC_SEND  = "interfazGlobalV2/autopilotServiceDemo"
MQTT_TOPIC_RECV  = "autopilotServiceDemo/interfazGlobalV2/#"

# Conexión local por defecto (modo Local)
LOCAL_CONNECTION_STRING = "tcp:127.0.0.1:5763"
LOCAL_BAUD              = 115200

# WebRTC – servicio de cámara (CameraService.py actúa como servidor)
CAMERA_SERVER_IP     = "localhost"
CAMERA_SERVER_PORT   = 9999
CAMERA_MAX_SESSION_S = 3600   # duración máxima de la sesión de cámara (segundos)

# Identificadores de modo
MODE_LOCAL  = "local"
MODE_GLOBAL = "global"


# ══════════════════════════════════════════
#  CONTROLADOR LOCAL
# ══════════════════════════════════════════

class LocalController:
    """Controla el dron directamente a través de dronLink."""

    def __init__(self):
        self.dron = Dron()

    def connect(self):
        self.dron.connect(LOCAL_CONNECTION_STRING, LOCAL_BAUD)

    def arm(self):
        self.dron.arm()

    def takeoff(self, alt=5, callback=None):
        self.dron.takeOff(alt, blocking=False, callback=callback)

    def land(self):
        self.dron.Land()

    def rtl(self):
        self.dron.RTL()

    def go(self, direction):
        self.dron.go(direction)

    def start_telemetry(self, callback):
        self.dron.send_telemetry_info(callback)

    def stop_telemetry(self):
        self.dron.stop_sending_telemetry_info()

    def change_heading(self, degrees):
        self.dron.changeHeading(int(degrees))

    def change_nav_speed(self, speed):
        self.dron.changeNavSpeed(float(speed))

    @property
    def state(self):
        return self.dron.state


# ══════════════════════════════════════════
#  CONTROLADOR GLOBAL
# ══════════════════════════════════════════

class GlobalController:
    """Controla el dron publicando comandos MQTT al AutopilotService."""

    def __init__(self, on_message_cb, on_connect_cb):
        self._client = mqtt.Client(
            CallbackAPIVersion.VERSION2, MQTT_CLIENT_ID, transport="websockets"
        )
        self._client.on_message = on_message_cb
        self._client.on_connect = on_connect_cb
        self._client.connect(BROKER_ADDRESS, BROKER_PORT)
        self._client.subscribe(MQTT_TOPIC_RECV)
        self._client.loop_start()

    def _pub(self, command, payload=None):
        topic = f"{MQTT_TOPIC_SEND}/{command}"
        if payload is not None:
            self._client.publish(topic, str(payload))
        else:
            self._client.publish(topic)

    def connect(self):
        self._pub("connect")

    def arm(self):
        # En modo Global, armar y despegar se hacen juntos (arm_takeOff)
        self._pub("arm_takeOff")

    def takeoff(self, alt=5, callback=None):
        self._pub("arm_takeOff", alt)

    def land(self):
        self._pub("Land")

    def rtl(self):
        self._pub("RTL")

    def go(self, direction):
        self._pub("go", direction)

    def start_telemetry(self, callback=None):
        # En Global la telemetría llega por MQTT (callback no se usa aquí)
        self._pub("startTelemetry")

    def stop_telemetry(self):
        self._pub("stopTelemetry")

    def change_heading(self, degrees):
        self._pub("changeHeading", int(degrees))

    def change_nav_speed(self, speed):
        self._pub("changeNavSpeed", float(speed))

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()


# ══════════════════════════════════════════
#  RECEPTOR DE CÁMARA  (WebRTC)
# ══════════════════════════════════════════

class _VideoReceiver:
    """Recibe y muestra el stream de video WebRTC enviado por CameraService.py."""

    def __init__(self):
        self.track = None

    async def handle_track(self, track):
        self.track = track
        frame_count = 0
        while True:
            try:
                frame = await asyncio.wait_for(track.recv(), timeout=5.0)
                frame_count += 1
                frame = frame.to_ndarray(format="bgr24")
                cv2.imshow("Cámara — DashboardV2  [pulsa Q para cerrar]", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            except asyncio.TimeoutError:
                print("[Cámara] Timeout esperando frame")
            except Exception as e:
                print(f"[Cámara] Error en handle_track: {e}")
                if "Connection" in str(e):
                    break
        print("[Cámara] Stream de video finalizado")


async def _camera_receiver_task():
    """Coroutine que establece la conexión WebRTC con CameraService y recibe frames."""
    signaling = TcpSocketSignaling(CAMERA_SERVER_IP, CAMERA_SERVER_PORT)
    pc = RTCPeerConnection()
    video_receiver = _VideoReceiver()

    @pc.on("track")
    def on_track(track):
        if isinstance(track, MediaStreamTrack):
            print("[Cámara] Track de video recibido")
            asyncio.ensure_future(video_receiver.handle_track(track))

    try:
        await signaling.connect()
        print("[Cámara] Esperando oferta WebRTC...")
        offer = await signaling.receive()
        print("[Cámara] Oferta recibida, enviando respuesta...")
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await signaling.send(pc.localDescription)

        print("[Cámara] Esperando conexión...")
        while pc.connectionState != "connected":
            await asyncio.sleep(0.1)
        print("[Cámara] Conexión establecida, recibiendo frames...")

        # Mantener el stream activo hasta el límite configurado en CAMERA_MAX_SESSION_S
        await asyncio.sleep(CAMERA_MAX_SESSION_S)
    except Exception as e:
        print(f"[Cámara] Error en conexión WebRTC: {e}")
    finally:
        await pc.close()
        cv2.destroyAllWindows()
        print("[Cámara] Conexión WebRTC cerrada")


def start_camera_service():
    """Lanza el receptor de cámara WebRTC en un hilo daemon separado."""
    def _thread():
        asyncio.run(_camera_receiver_task())

    t = threading.Thread(target=_thread, daemon=True, name="CameraReceiverThread")
    t.start()
    print("[Cámara] Hilo de recepción iniciado")
    return t


# ══════════════════════════════════════════
#  VARIABLES GLOBALES DE LA UI
# ══════════════════════════════════════════

controller  = None   # LocalController | GlobalController
previousBtn = None   # último botón de navegación clicado
_mode       = None   # "local" | "global"

# Widgets — se asignan en crear_ventana()
altShowLbl = headingShowLbl = stateShowLbl = None
connectBtn = armBtn = takeOffBtn = landBtn = RTLBtn = None
speedSldr  = gradesSldr = None
modoLbl    = None


# ══════════════════════════════════════════
#  CALLBACKS DE TELEMETRÍA
# ══════════════════════════════════════════

def showTelemetryInfo(telemetry_info):
    """Actualiza las etiquetas de telemetría con los datos recibidos."""
    if altShowLbl:
        altShowLbl["text"]     = round(telemetry_info.get("alt", 0), 2)
        headingShowLbl["text"] = round(telemetry_info.get("heading", 0), 2)
        stateShowLbl["text"]   = telemetry_info.get("state", "")


# ══════════════════════════════════════════
#  CALLBACKS MQTT (modo Global)
# ══════════════════════════════════════════

def on_mqtt_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[MQTT] Conectado al broker correctamente")
    else:
        print(f"[MQTT] Error de conexión al broker: {reason_code}")


def on_mqtt_message(client, userdata, message):
    """Procesa mensajes entrantes del AutopilotService en modo Global."""
    topic = message.topic
    if topic.endswith("/telemetryInfo"):
        telemetry_info = json.loads(message.payload)
        showTelemetryInfo(telemetry_info)
    elif topic.endswith("/connected"):
        if connectBtn:
            connectBtn["text"] = "Conectado"
            connectBtn["fg"]   = FG_ACTIVO
            connectBtn["bg"]   = COLOR_ACTIVO
    elif topic.endswith("/flying"):
        if takeOffBtn:
            takeOffBtn["text"] = "En el aire"
            takeOffBtn["fg"]   = FG_ACTIVO
            takeOffBtn["bg"]   = COLOR_ACTIVO
    elif topic.endswith("/landed"):
        if landBtn:
            landBtn["text"] = "En tierra"
            landBtn["fg"]   = FG_ACTIVO
            landBtn["bg"]   = COLOR_ACTIVO
    elif topic.endswith("/atHome"):
        if RTLBtn:
            RTLBtn["text"] = "En tierra"
            RTLBtn["fg"]   = FG_ACTIVO
            RTLBtn["bg"]   = COLOR_ACTIVO


# ══════════════════════════════════════════
#  HELPERS DE BOTONES
# ══════════════════════════════════════════

def _btn_active(btn, text=None):
    if text:
        btn["text"] = text
    btn["fg"] = FG_ACTIVO
    btn["bg"] = COLOR_ACTIVO


def _btn_proceso(btn, text=None):
    if text:
        btn["text"] = text
    btn["fg"] = FG_NORMAL
    btn["bg"] = COLOR_EN_PROCESO


# ══════════════════════════════════════════
#  COMANDOS DE LA UI
# ══════════════════════════════════════════

def cmd_connect():
    global controller, speedSldr
    if controller is None:
        messagebox.showwarning("Aviso", "Primero selecciona un modo e inicia el dashboard.")
        return
    if _mode == MODE_LOCAL:
        def _do():
            controller.connect()
            connectBtn.after(0, lambda: _btn_active(connectBtn, "Conectado"))
            speedSldr.after(0, lambda: speedSldr.set(1))
        threading.Thread(target=_do, daemon=True).start()
    else:
        # En global, la confirmación llega vía MQTT (on_mqtt_message/connected)
        controller.connect()
        speedSldr.set(1)


def cmd_arm():
    """Arma el dron (solo modo Local; en Global el armado se hace junto al despegue)."""
    global controller
    if controller is None:
        return
    if _mode == MODE_LOCAL:
        def _do():
            controller.arm()
            armBtn.after(0, lambda: _btn_active(armBtn, "Armado"))
        threading.Thread(target=_do, daemon=True).start()
    else:
        messagebox.showinfo("Modo Global", "En modo Global, usa 'Despegar' para armar y despegar juntos.")


def _on_in_the_air():
    """Callback ejecutado cuando el dron alcanza la altura de despegue (modo Local)."""
    if takeOffBtn:
        takeOffBtn["text"] = "En el aire"
        takeOffBtn["fg"]   = FG_ACTIVO
        takeOffBtn["bg"]   = COLOR_ACTIVO


def cmd_takeoff():
    global controller
    if controller is None:
        return
    _btn_proceso(takeOffBtn, "Despegando...")
    if _mode == MODE_LOCAL:
        threading.Thread(
            target=controller.takeoff, kwargs={"alt": 5, "callback": _on_in_the_air},
            daemon=True
        ).start()
    else:
        controller.takeoff(5)


def cmd_land():
    global controller
    if controller is None:
        return
    if _mode == MODE_LOCAL:
        threading.Thread(target=controller.land, daemon=True).start()
        _btn_active(landBtn, "En tierra")
    else:
        controller.land()
        _btn_proceso(landBtn, "Aterrizando...")


def cmd_rtl():
    global controller
    if controller is None:
        return
    if _mode == MODE_LOCAL:
        threading.Thread(target=controller.rtl, daemon=True).start()
        _btn_proceso(RTLBtn, "Retornando...")
    else:
        controller.rtl()
        _btn_proceso(RTLBtn, "Retornando...")


def cmd_go(direction, btn):
    global controller, previousBtn
    if controller is None:
        return
    if previousBtn:
        previousBtn["fg"] = FG_NORMAL
        previousBtn["bg"] = COLOR_DISPONIBLE
    controller.go(direction)
    btn["fg"] = FG_ACTIVO
    btn["bg"] = COLOR_ACTIVO
    previousBtn = btn


def cmd_start_telem():
    global controller
    if controller is None:
        return
    if _mode == MODE_LOCAL:
        controller.start_telemetry(showTelemetryInfo)
    else:
        controller.start_telemetry()


def cmd_stop_telem():
    global controller
    if controller is None:
        return
    controller.stop_telemetry()


def cmd_change_heading(event):
    global controller, gradesSldr
    if controller is None:
        return
    controller.change_heading(gradesSldr.get())


def cmd_change_nav_speed(event):
    global controller, speedSldr
    if controller is None:
        return
    controller.change_nav_speed(speedSldr.get())


# ══════════════════════════════════════════
#  SELECTOR DE MODO E INICIO
# ══════════════════════════════════════════

def cmd_iniciar(modo_var, iniciarBtn, modoFrame):
    """
    Inicializa el controlador según el modo seleccionado y arranca el servicio de cámara.
    En modo Local: activa el controlador directo (Dron) y lanza el receptor WebRTC.
    En modo Global: conecta al broker MQTT y suscribe a respuestas del AutopilotService.
    """
    global controller, _mode, modoLbl

    modo = modo_var.get()
    if not modo:
        messagebox.showwarning("Aviso", "Selecciona un modo antes de iniciar.")
        return

    _mode = modo

    if modo == MODE_LOCAL:
        controller = LocalController()
        modoLbl["text"] = "Modo: LOCAL  (control directo al dron)"
        modoLbl["fg"]   = "darkgreen"
        # Activar servicio de cámara local (receptor WebRTC)
        start_camera_service()
        messagebox.showinfo(
            "Modo Local activado",
            "✔ Servicio de autopiloto local listo.\n"
            "✔ Receptor de cámara WebRTC iniciado.\n\n"
            "Asegúrate de que CameraService.py esté en ejecución\n"
            "antes de usar el video."
        )
    else:
        controller = GlobalController(on_mqtt_message, on_mqtt_connect)
        modoLbl["text"] = "Modo: GLOBAL  (vía MQTT / AutopilotService)"
        modoLbl["fg"]   = "darkblue"
        messagebox.showinfo(
            "Modo Global activado",
            "✔ Conectado al broker MQTT (broker.hivemq.com).\n\n"
            "Asegúrate de que AutopilotService.py esté en ejecución."
        )

    # Bloquear selector para evitar reinicializaciones accidentales
    iniciarBtn["state"] = "disabled"
    for child in modoFrame.winfo_children():
        if isinstance(child, tk.Radiobutton):
            child["state"] = "disabled"


# ══════════════════════════════════════════
#  CONSTRUCCIÓN DE LA VENTANA
# ══════════════════════════════════════════

def crear_ventana():
    global altShowLbl, headingShowLbl, stateShowLbl
    global connectBtn, armBtn, takeOffBtn, landBtn, RTLBtn
    global speedSldr, gradesSldr, previousBtn, modoLbl

    previousBtn = None

    ventana = tk.Tk()
    ventana.title("Dashboard V2 — Autopiloto + Cámara")
    ventana.resizable(True, True)

    for r in range(11):
        ventana.rowconfigure(r, weight=1)
    ventana.columnconfigure(0, weight=1)
    ventana.columnconfigure(1, weight=1)

    # ── Fila 0: Selector de modo ──────────────────────────────────────────────
    modoFrame = tk.LabelFrame(ventana, text="Selección de Modo", pady=5)
    modoFrame.grid(row=0, column=0, columnspan=2, padx=10, pady=5,
                   sticky=tk.N + tk.S + tk.E + tk.W)

    modo_var = tk.StringVar(value=MODE_LOCAL)
    tk.Radiobutton(
        modoFrame, text="Local  (control directo al dron)",
        variable=modo_var, value=MODE_LOCAL, font=("Arial", 11)
    ).pack(side=tk.LEFT, padx=15, pady=5)
    tk.Radiobutton(
        modoFrame, text="Global  (vía MQTT / AutopilotService)",
        variable=modo_var, value=MODE_GLOBAL, font=("Arial", 11)
    ).pack(side=tk.LEFT, padx=15, pady=5)

    iniciarBtn = tk.Button(
        modoFrame, text="Iniciar", bg=COLOR_DISPONIBLE, font=("Arial", 11, "bold")
    )
    iniciarBtn["command"] = lambda: cmd_iniciar(modo_var, iniciarBtn, modoFrame)
    iniciarBtn.pack(side=tk.RIGHT, padx=10, pady=5)

    # ── Fila 1: Etiqueta de modo activo ──────────────────────────────────────
    modoLbl = tk.Label(
        ventana, text="Modo: (no iniciado — pulsa Iniciar)",
        font=("Arial", 10, "italic"), fg="gray"
    )
    modoLbl.grid(row=1, column=0, columnspan=2, pady=2)

    # ── Fila 2: Conectar ─────────────────────────────────────────────────────
    connectBtn = tk.Button(ventana, text="Conectar", bg=COLOR_DISPONIBLE, command=cmd_connect)
    connectBtn.grid(row=2, column=0, columnspan=2, padx=5, pady=5,
                    sticky=tk.N + tk.S + tk.E + tk.W)

    # ── Fila 3: Armar / Despegar ──────────────────────────────────────────────
    armBtn = tk.Button(ventana, text="Armar", bg=COLOR_DISPONIBLE, command=cmd_arm)
    armBtn.grid(row=3, column=0, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    takeOffBtn = tk.Button(ventana, text="Despegar", bg=COLOR_DISPONIBLE, command=cmd_takeoff)
    takeOffBtn.grid(row=3, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    # ── Fila 4: Slider Heading ────────────────────────────────────────────────
    gradesSldr = tk.Scale(
        ventana, label="Grados:", resolution=5, from_=0, to=360,
        tickinterval=45, orient=tk.HORIZONTAL
    )
    gradesSldr.grid(row=4, column=0, columnspan=2, padx=5, pady=5,
                    sticky=tk.N + tk.S + tk.E + tk.W)
    gradesSldr.bind("<ButtonRelease-1>", cmd_change_heading)

    # ── Fila 5: Aterrizar / RTL ───────────────────────────────────────────────
    landBtn = tk.Button(ventana, text="Aterrizar", bg=COLOR_DISPONIBLE, command=cmd_land)
    landBtn.grid(row=5, column=0, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    RTLBtn = tk.Button(ventana, text="RTL", bg=COLOR_DISPONIBLE, command=cmd_rtl)
    RTLBtn.grid(row=5, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    # ── Fila 6: Panel de navegación ───────────────────────────────────────────
    navFrame = tk.LabelFrame(ventana, text="Navegación")
    navFrame.grid(row=6, column=0, columnspan=2, padx=50, pady=5,
                  sticky=tk.N + tk.S + tk.E + tk.W)
    for r in range(3):
        navFrame.rowconfigure(r, weight=1)
    for c in range(3):
        navFrame.columnconfigure(c, weight=1)

    nav_grid = [
        ("NW", 0, 0, "NorthWest"), ("No", 0, 1, "North"),  ("NE", 0, 2, "NorthEast"),
        ("We", 1, 0, "West"),      ("St", 1, 1, "Stop"),   ("Ea", 1, 2, "East"),
        ("↓",  2, 0, "Down"),      ("So", 2, 1, "South"),  ("↑",  2, 2, "Up"),
    ]
    for (label, row, col, direction) in nav_grid:
        btn = tk.Button(navFrame, text=label, bg=COLOR_DISPONIBLE)
        btn.grid(row=row, column=col, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)
        btn["command"] = lambda d=direction, b=btn: cmd_go(d, b)

    # ── Fila 7: Slider Velocidad ──────────────────────────────────────────────
    speedSldr = tk.Scale(
        ventana, label="Velocidad (m/s):", resolution=1, from_=0, to=20,
        tickinterval=5, orient=tk.HORIZONTAL
    )
    speedSldr.grid(row=7, column=0, columnspan=2, padx=5, pady=5,
                   sticky=tk.N + tk.S + tk.E + tk.W)
    speedSldr.bind("<ButtonRelease-1>", cmd_change_nav_speed)

    # ── Fila 8: Telemetría botones ────────────────────────────────────────────
    StartTelemBtn = tk.Button(
        ventana, text="Iniciar telemetría", bg=COLOR_DISPONIBLE, command=cmd_start_telem
    )
    StartTelemBtn.grid(row=8, column=0, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    StopTelemBtn = tk.Button(
        ventana, text="Parar telemetría", bg=COLOR_DISPONIBLE, command=cmd_stop_telem
    )
    StopTelemBtn.grid(row=8, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    # ── Fila 9: Frame de Telemetría ───────────────────────────────────────────
    telemetryFrame = tk.LabelFrame(ventana, text="Telemetría")
    telemetryFrame.grid(row=9, column=0, columnspan=2, padx=10, pady=10,
                        sticky=tk.N + tk.S + tk.E + tk.W)
    telemetryFrame.rowconfigure(0, weight=1)
    telemetryFrame.rowconfigure(1, weight=1)
    for c in range(3):
        telemetryFrame.columnconfigure(c, weight=1)

    tk.Label(telemetryFrame, text="Altitud").grid(
        row=0, column=0, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    tk.Label(telemetryFrame, text="Heading").grid(
        row=0, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    tk.Label(telemetryFrame, text="Estado").grid(
        row=0, column=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    altShowLbl     = tk.Label(telemetryFrame, text="")
    headingShowLbl = tk.Label(telemetryFrame, text="")
    stateShowLbl   = tk.Label(telemetryFrame, text="")
    altShowLbl.grid(    row=1, column=0, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    headingShowLbl.grid(row=1, column=1, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    stateShowLbl.grid(  row=1, column=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    return ventana


# ══════════════════════════════════════════
#  PUNTO DE ENTRADA
# ══════════════════════════════════════════

if __name__ == "__main__":
    ventana = crear_ventana()
    ventana.mainloop()
