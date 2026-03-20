##########  INSTALAR ##########
# pymavlink
###############################

import tkinter as tk
from tkinter import messagebox
import math
from dronLink.Dron import Dron

# ---- Configuración de conexión ----
connection_str = 'tcp:127.0.0.1:5763'
baudios = 115200

# ---- Colores del sistema ----
COLOR_DISPONIBLE = "dark orange"
COLOR_NO_DISPONIBLE = "#4682B4"
COLOR_EN_PROCESO = "yellow"
COLOR_ACTIVO = "green"
COLOR_STOP = "red"
FG_NORMAL = "black"
FG_ACTIVO = "white"
FG_NO_DISPONIBLE = "#D0D0D0"

SQRT2 = math.sqrt(2)

# ---- Flag global ----
_enTransicion = False


# ---- Helpers para habilitar/deshabilitar botones ----
def _habilitarBtn(btn, text=None, bg=None, fg=None):
    btn['state'] = 'normal'
    if text:
        btn['text'] = text
    btn['bg'] = bg if bg else COLOR_DISPONIBLE
    btn['fg'] = fg if fg else FG_NORMAL

def _deshabilitarBtn(btn, text=None, bg=None, fg=None):
    if text:
        btn['text'] = text
    btn['bg'] = bg if bg else COLOR_NO_DISPONIBLE
    btn['fg'] = fg if fg else FG_NO_DISPONIBLE
    btn.configure(disabledforeground=fg if fg else FG_NO_DISPONIBLE)
    btn['state'] = 'disabled'

def _activarBtn(btn, text=None):
    if text:
        btn['text'] = text
    btn['bg'] = COLOR_ACTIVO
    btn['fg'] = FG_ACTIVO
    btn.configure(disabledforeground=FG_ACTIVO)
    btn['state'] = 'disabled'

def _procesoBtn(btn, text=None):
    if text:
        btn['text'] = text
    btn['bg'] = COLOR_EN_PROCESO
    btn['fg'] = FG_NORMAL
    btn.configure(disabledforeground=FG_NORMAL)
    btn['state'] = 'disabled'


def resetBtn(btn, originalText, delay=3000):
    def _reset():
        global _enTransicion
        _enTransicion = False
        btn['state'] = 'normal'
        btn['text'] = originalText
        btn['fg'] = FG_NORMAL
        btn['bg'] = COLOR_DISPONIBLE
        actualizarBotonesSegunEstado()
    btn.after(delay, _reset)


# ══════════════════════════════════════════
#  REBUILD CMD — Construye y envía inmediatamente
# ══════════════════════════════════════════

def _rebuildCmd():
    """Reconstruye dron.cmd y lo envía inmediatamente.
    Diagonales normalizadas. NO llama a unfixHeading/fixHeading
    (que era lo que causaba colisiones). Solo envía el mensaje
    de velocidad limpio, igual que hace el thread."""
    from pymavlink import mavutil

    speed = dron.navSpeed
    diag = speed / SQRT2
    d = dron.direction

    DIR_MAP = {
        "North":     ( speed, 0,     0, False),
        "South":     (-speed, 0,     0, False),
        "East":      ( 0,     speed, 0, False),
        "West":      ( 0,    -speed, 0, False),
        "NorthWest": ( diag, -diag,  0, False),
        "NorthEast": ( diag,  diag,  0, False),
        "SouthWest": (-diag, -diag,  0, False),
        "SouthEast": (-diag,  diag,  0, False),
        "Forward":   ( speed, 0,     0, True),
        "Back":      (-speed, 0,     0, True),
        "Left":      ( 0,    -speed, 0, True),
        "Right":     ( 0,     speed, 0, True),
        "Up":        ( 0,     0, -speed, True),
        "Down":      ( 0,     0,  speed, True),
        "Stop":      ( 0,     0,     0, False),
    }

    vx, vy, vz, bodyRef = DIR_MAP.get(d, (0, 0, 0, False))

    if bodyRef:
        msg = mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
            10, dron.vehicle.target_system, dron.vehicle.target_component,
            mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
            0b0000111111000111,
            0, 0, 0, vx, vy, vz, 0, 0, 0, 0, 0)
    else:
        msg = mavutil.mavlink.MAVLink_set_position_target_global_int_message(
            10, dron.vehicle.target_system, dron.vehicle.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000111111000111,
            0, 0, 0, vx, vy, vz, 0, 0, 0, 0, 0)

    # Asignar para que el thread lo siga enviando cada segundo
    dron.cmd = msg
    # Enviar inmediatamente para que ArduPilot no vea un gap
    dron.vehicle.mav.send(msg)


def showTelemetryInfo(telemetry_info):
    global altShowLbl, headingShowLbl, stateShowLbl
    global speedShowLbl, flightModeShowLbl, latShowLbl, lonShowLbl

    altShowLbl['text'] = round(telemetry_info['alt'], 2)
    headingShowLbl['text'] = round(telemetry_info['heading'], 2)
    stateShowLbl['text'] = telemetry_info['state']
    speedShowLbl['text'] = round(telemetry_info['groundSpeed'], 2)
    flightModeShowLbl['text'] = telemetry_info['flightMode']
    latShowLbl['text'] = round(telemetry_info['lat'], 6)
    lonShowLbl['text'] = round(telemetry_info['lon'], 6)

    actualizarBotonesSegunEstado()


def actualizarBotonesSegunEstado():
    global _enTransicion
    if _enTransicion:
        return

    state = dron.state

    if state == 'disconnected':
        _habilitarBtn(connectBtn, 'Conectar')
    else:
        _activarBtn(connectBtn, 'Conectado')

    if state == 'connected':
        _habilitarBtn(disconnectBtn, 'Desconectar')
    else:
        _deshabilitarBtn(disconnectBtn, 'Desconectar')

    if state == 'connected':
        _habilitarBtn(armBtn, 'Armar')
    elif state == 'arming':
        _procesoBtn(armBtn, 'Armando...')
    elif state in ('armed', 'takingOff', 'flying', 'returning', 'landing'):
        _activarBtn(armBtn, 'Armado')
    else:
        _deshabilitarBtn(armBtn, 'Armar')

    if state == 'armed':
        _habilitarBtn(disarmBtn, 'Desarmar')
    else:
        _deshabilitarBtn(disarmBtn, 'Desarmar')

    if state == 'armed':
        _habilitarBtn(takeOffBtn, 'Despegar')
    elif state == 'takingOff':
        _procesoBtn(takeOffBtn, 'Despegando...')
    elif state in ('flying', 'returning'):
        _activarBtn(takeOffBtn, 'En el aire ✈')
    elif state == 'landing':
        _procesoBtn(takeOffBtn, 'Aterrizando...')
    else:
        _deshabilitarBtn(takeOffBtn, 'Despegar')

    if state in ('flying', 'returning'):
        _habilitarBtn(landBtn, 'Aterrizar')
    elif state == 'landing':
        _procesoBtn(landBtn, 'Aterrizando...')
    else:
        _deshabilitarBtn(landBtn, 'Aterrizar')

    if state == 'flying':
        _habilitarBtn(RTLBtn, 'RTL')
    elif state == 'returning':
        _procesoBtn(RTLBtn, 'Volviendo a casa...')
    else:
        _deshabilitarBtn(RTLBtn, 'RTL')

    if state == 'flying':
        if rotateCWBtn['bg'] != COLOR_EN_PROCESO:
            _habilitarBtn(rotateCWBtn, '↻ 90° CW')
        if rotateCCWBtn['bg'] != COLOR_EN_PROCESO:
            _habilitarBtn(rotateCCWBtn, '↺ 90° CCW')
    else:
        _deshabilitarBtn(rotateCWBtn, '↻ 90° CW')
        _deshabilitarBtn(rotateCCWBtn, '↺ 90° CCW')

    for b in navBtns:
        if state == 'flying':
            if b['bg'] != COLOR_ACTIVO:
                if b == StopBtn:
                    _habilitarBtn(b, bg=COLOR_STOP, fg=FG_ACTIVO)
                else:
                    _habilitarBtn(b)
        else:
            _deshabilitarBtn(b)

    if state == 'flying':
        if gotoBtn['bg'] != COLOR_EN_PROCESO:
            _habilitarBtn(gotoBtn, 'Ir a posición')
    else:
        if gotoBtn['bg'] != COLOR_EN_PROCESO:
            _deshabilitarBtn(gotoBtn, 'Ir a posición')

    if state == 'flying':
        if applyAltBtn['bg'] != COLOR_EN_PROCESO:
            _habilitarBtn(applyAltBtn, 'Aplicar altitud')
    else:
        if applyAltBtn['bg'] != COLOR_EN_PROCESO:
            _deshabilitarBtn(applyAltBtn, 'Aplicar altitud')

    if state != 'disconnected':
        _habilitarBtn(StartTelemBtn, '▶ Iniciar telemetría')
        _habilitarBtn(StopTelemBtn, '■ Parar telemetría')
    else:
        _deshabilitarBtn(StartTelemBtn, '▶ Iniciar telemetría')
        _deshabilitarBtn(StopTelemBtn, '■ Parar telemetría')


# ══════════════════════════════════════════
#  ACCIONES
# ══════════════════════════════════════════

def connect():
    global dron, speedSldr
    connection_string = connection_str
    baud = baudios
    result = dron.connect(connection_string, baud)
    if result:
        speedSldr.set(1)
        actualizarBotonesSegunEstado()
    else:
        messagebox.showwarning("Aviso", "Ya está conectado o no se puede conectar.")

def disconnect():
    global dron
    if dron.state != 'connected':
        messagebox.showwarning("Aviso",
            "El dron debe estar en estado 'connected' para desconectar.\nEstado actual: " + dron.state)
        return
    result = dron.disconnect()
    if result:
        actualizarBotonesSegunEstado()
        _activarBtn(disconnectBtn, 'Desconectado')
        resetBtn(disconnectBtn, 'Desconectar', 2000)

def onArmError(msg):
    armBtn['state'] = 'normal'
    armBtn['text'] = 'Armar'
    armBtn['fg'] = FG_NORMAL
    armBtn['bg'] = COLOR_DISPONIBLE
    messagebox.showerror("Error al armar", "No se pudo armar.\n\nMotivo: " + msg)

def onArmed():
    actualizarBotonesSegunEstado()

def arm():
    global dron
    if dron.state != 'connected':
        messagebox.showwarning("Aviso",
            "El dron debe estar conectado para armar.\nEstado actual: " + dron.state)
        return
    _procesoBtn(armBtn, 'Armando...')
    result = dron.arm(blocking=False, callback=onArmed, error_callback=onArmError)
    if not result:
        _habilitarBtn(armBtn, 'Armar')
        messagebox.showerror("Error", "No se pudo iniciar el armado.")

def disarm():
    global dron, _enTransicion
    if dron.state != 'armed':
        messagebox.showwarning("Aviso",
            "El dron debe estar armado (sin volar) para desarmar.\nEstado actual: " + dron.state)
        return
    from pymavlink import mavutil
    dron.vehicle.mav.command_long_send(
        dron.vehicle.target_system, dron.vehicle.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 0, 0, 0, 0, 0, 0)
    dron.state = 'connected'
    _enTransicion = False
    actualizarBotonesSegunEstado()
    _activarBtn(disarmBtn, 'Desarmado')
    resetBtn(disarmBtn, 'Desarmar', 2000)

def inTheAir():
    global _enTransicion
    _enTransicion = False
    actualizarBotonesSegunEstado()

def takeoff():
    global dron, altSldr, _enTransicion
    if _enTransicion:
        return
    if dron.state != 'armed':
        messagebox.showwarning("Aviso",
            "El dron debe estar armado para despegar.\nEstado actual: " + dron.state)
        return
    alt = int(altSldr.get())
    _enTransicion = True
    result = dron.takeOff(alt, blocking=False, callback=inTheAir)
    if result:
        _procesoBtn(takeOffBtn, 'Despegando...')
    else:
        _enTransicion = False
        messagebox.showerror("Error", "No se pudo despegar.")

_landedCallbackFired = False

def onLanded():
    """Callback llamado desde hilo secundario cuando el dron ha aterrizado.
    Usa ventana.after() para ejecutar cambios de UI en el hilo principal de Tkinter."""
    def _ui():
        global _enTransicion, _landedCallbackFired
        if _landedCallbackFired:
            return
        _landedCallbackFired = True
        _enTransicion = False
        _activarBtn(landBtn, 'Aterrizado ✓')
        resetBtn(landBtn, 'Aterrizar', 2000)
    ventana.after(0, _ui)

def _monitorLanding():
    """Comprueba cada 500 ms si el dron se ha desarmado mientras aterriza
    (p.ej. impacto en tejado). Si es así, dispara onLanded manualmente."""
    global _landedCallbackFired
    if dron.state != 'landing' or _landedCallbackFired:
        return  # ya aterrizó o ya no está aterrizando → parar el monitor
    try:
        from pymavlink import mavutil
        msg = dron.vehicle.recv_match(type='HEARTBEAT', blocking=False)
        if msg and not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            # El dron se ha desarmado → está en tierra
            onLanded()
            return
    except Exception:
        pass
    ventana.after(500, _monitorLanding)

def land():
    global dron, previousBtn, _enTransicion, _landedCallbackFired
    if _enTransicion:
        return
    if dron.state not in ('flying', 'returning'):
        messagebox.showwarning("Aviso",
            "El dron debe estar volando para aterrizar.\nEstado actual: " + dron.state)
        return
    if previousBtn and previousBtn['bg'] == COLOR_ACTIVO:
        dron.go("Stop")
    _landedCallbackFired = False
    result = dron.Land(blocking=False, callback=onLanded)
    if result:
        _enTransicion = True
        _procesoBtn(landBtn, 'Aterrizando...')
        if gotoBtn['bg'] == COLOR_EN_PROCESO:
            _habilitarBtn(gotoBtn, 'Ir a posición')
        if previousBtn:
            _habilitarBtn(previousBtn)
            previousBtn = None
        ventana.after(500, _monitorLanding)  # arranca el monitor de seguridad

def onRTLComplete():
    """Callback llamado desde hilo secundario cuando el RTL ha completado.
    Usa ventana.after() para ejecutar cambios de UI en el hilo principal de Tkinter."""
    def _ui():
        global _enTransicion
        _enTransicion = False
        _activarBtn(RTLBtn, 'Aterrizado ✓')
        resetBtn(RTLBtn, 'RTL', 2000)
    ventana.after(0, _ui)

def RTL():
    global dron, previousBtn, _enTransicion
    if _enTransicion:
        return
    if dron.state != 'flying':
        messagebox.showwarning("Aviso",
            "El dron debe estar volando para RTL.\nEstado actual: " + dron.state)
        return
    if previousBtn and previousBtn['bg'] == COLOR_ACTIVO:
        dron.go("Stop")
    result = dron.RTL(blocking=False, callback=onRTLComplete)
    if result:
        _enTransicion = True
        _procesoBtn(RTLBtn, 'Volviendo a casa...')
        if gotoBtn['bg'] == COLOR_EN_PROCESO:
            _habilitarBtn(gotoBtn, 'Ir a posición')
        if previousBtn:
            _habilitarBtn(previousBtn)
            previousBtn = None


def go(direction, btn):
    """Cambia la dirección de navegación.
    Primera vez: dron.go() arranca el thread.
    Después: _rebuildCmd() actualiza y envía inmediatamente."""
    global dron, previousBtn
    if dron.state != 'flying':
        return

    if previousBtn:
        _habilitarBtn(previousBtn)

    dron.direction = direction

    if dron.going:
        # Thread ya corriendo → rebuild + envío inmediato, sin unfixHeading
        _rebuildCmd()
    else:
        # Primera vez → arrancar thread
        dron.go(direction)

    if direction == "Stop":
        btn['state'] = 'normal'
        btn['bg'] = COLOR_STOP
        btn['fg'] = FG_ACTIVO
        previousBtn = None
    else:
        btn['state'] = 'normal'
        btn['bg'] = COLOR_ACTIVO
        btn['fg'] = FG_ACTIVO
        previousBtn = btn

    if gotoBtn['bg'] == COLOR_EN_PROCESO:
        _habilitarBtn(gotoBtn, 'Ir a posición')


def startTelem():
    if dron.state == 'disconnected':
        return
    dron.send_telemetry_info(showTelemetryInfo)

def stopTelem():
    if dron.state == 'disconnected':
        return
    dron.stop_sending_telemetry_info()

def changeHeading(event):
    if dron.state == 'flying':
        dron.changeHeading(int(gradesSldr.get()), blocking=False)

def changeNavSpeed(event):
    global dron, speedSldr
    if dron.state not in ('flying', 'returning'):
        return
    dron.navSpeed = float(speedSldr.get())
    if dron.going and dron.direction != 'Stop':
        _rebuildCmd()

def applyAltitude():
    global dron, altSldr, previousBtn, applyAltBtn
    if dron.state != 'flying':
        return
    alt = int(altSldr.get())
    currentDirection = None
    if dron.going and dron.direction != 'Stop':
        currentDirection = dron.direction
        dron.go("Stop")
    _procesoBtn(applyAltBtn, 'Cambiando...')

    def onAltReached():
        if currentDirection and dron.state == 'flying':
            dron.go(currentDirection)
        _activarBtn(applyAltBtn, 'Altitud ✓')
        resetBtn(applyAltBtn, 'Aplicar altitud', 2000)

    result = dron.change_altitude(alt, blocking=False, callback=onAltReached)
    if not result:
        if currentDirection and dron.state == 'flying':
            dron.go(currentDirection)
        _habilitarBtn(applyAltBtn, 'Aplicar altitud')

def gotoReached():
    _activarBtn(gotoBtn, 'Destino alcanzado')
    resetBtn(gotoBtn, 'Ir a posición', 3000)

def gotoPosition():
    global dron, gotoBtn, latEntry, lonEntry, previousBtn
    try:
        lat = float(latEntry.get())
        lon = float(lonEntry.get())
    except ValueError:
        messagebox.showerror("Error", "Los campos Lat y Lon deben ser números válidos.")
        return
    if dron.state != 'flying':
        messagebox.showwarning("Aviso",
            "El dron debe estar volando para ir a una posición.\nEstado actual: " + dron.state)
        return
    alt = dron.alt if dron.alt is not None else 5
    dron.goto(lat, lon, alt, blocking=False, callback=gotoReached)
    _procesoBtn(gotoBtn, 'Navegando...')
    if previousBtn:
        _habilitarBtn(previousBtn)
        previousBtn = None

def rotateFinished():
    global previousBtn
    _habilitarBtn(rotateCWBtn, '↻ 90° CW')
    _habilitarBtn(rotateCCWBtn, '↺ 90° CCW')
    if previousBtn in (rotateCWBtn, rotateCCWBtn):
        previousBtn = None

def rotateCW():
    if dron.state != 'flying':
        return
    _procesoBtn(rotateCWBtn, 'Rotando CW...')
    dron.rotate(90, direction='cw', blocking=False, callback=rotateFinished)

def rotateCCW():
    if dron.state != 'flying':
        return
    _procesoBtn(rotateCCWBtn, 'Rotando CCW...')
    dron.rotate(90, direction='ccw', blocking=False, callback=rotateFinished)


# ══════════════════════════════════════════
#  CREAR VENTANA
# ══════════════════════════════════════════

def crear_ventana():
    global dron
    global altShowLbl, headingShowLbl, speedSldr, gradesSldr, stateShowLbl
    global speedShowLbl, flightModeShowLbl, latShowLbl, lonShowLbl
    global connectBtn, armBtn, takeOffBtn, landBtn, RTLBtn
    global disconnectBtn, disarmBtn
    global previousBtn
    global altSldr, applyAltBtn
    global latEntry, lonEntry, gotoBtn
    global rotateCWBtn, rotateCCWBtn
    global NWBtn, NoBtn, NEBtn, WeBtn, StopBtn, EaBtn, SWBtn, SoBtn, SEBtn
    global navBtns
    global StartTelemBtn, StopTelemBtn

    dron = Dron()
    previousBtn = None

    ventana = tk.Tk()
    ventana.title("Dashboard con conexión directa")
    ventana.geometry("600x750")
    ventana.minsize(500, 700)

    for i in range(12):
        ventana.rowconfigure(i, weight=1)
    for i in range(4):
        ventana.columnconfigure(i, weight=1)

    btn_font = ("Arial", 10, "bold")

    connectBtn = tk.Button(ventana, text="Conectar", bg=COLOR_DISPONIBLE, fg=FG_NORMAL,
                           font=btn_font, command=connect)
    connectBtn.grid(row=0, column=0, padx=3, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)

    armBtn = tk.Button(ventana, text="Armar", font=btn_font, command=arm)
    armBtn.grid(row=0, column=1, padx=3, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(armBtn, 'Armar')

    takeOffBtn = tk.Button(ventana, text="Despegar", font=btn_font, command=takeoff)
    takeOffBtn.grid(row=0, column=2, padx=3, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(takeOffBtn, 'Despegar')

    disconnectBtn = tk.Button(ventana, text="Desconectar", font=btn_font, command=disconnect)
    disconnectBtn.grid(row=0, column=3, padx=3, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(disconnectBtn, 'Desconectar')

    landBtn = tk.Button(ventana, text="Aterrizar", font=btn_font, command=land)
    landBtn.grid(row=1, column=0, padx=3, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(landBtn, 'Aterrizar')

    RTLBtn = tk.Button(ventana, text="RTL", font=btn_font, command=RTL)
    RTLBtn.grid(row=1, column=1, padx=3, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(RTLBtn, 'RTL')

    rotateFrame = tk.Frame(ventana)
    rotateFrame.grid(row=1, column=2, padx=3, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)
    rotateFrame.columnconfigure(0, weight=1)
    rotateFrame.columnconfigure(1, weight=1)
    rotateFrame.rowconfigure(0, weight=1)

    rotateCWBtn = tk.Button(rotateFrame, text="↻ 90° CW", font=("Arial", 9), command=rotateCW)
    rotateCWBtn.grid(row=0, column=0, padx=1, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(rotateCWBtn, '↻ 90° CW')

    rotateCCWBtn = tk.Button(rotateFrame, text="↺ 90° CCW", font=("Arial", 9), command=rotateCCW)
    rotateCCWBtn.grid(row=0, column=1, padx=1, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(rotateCCWBtn, '↺ 90° CCW')

    disarmBtn = tk.Button(ventana, text="Desarmar", font=btn_font, command=disarm)
    disarmBtn.grid(row=1, column=3, padx=3, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(disarmBtn, 'Desarmar')

    gradesSldr = tk.Scale(ventana, label="Heading (grados):", resolution=5, from_=0, to=360,
                          tickinterval=45, orient=tk.HORIZONTAL, length=400, font=("Arial", 9))
    gradesSldr.grid(row=2, column=0, columnspan=4, padx=10, pady=5, sticky=tk.E+tk.W)
    gradesSldr.bind("<ButtonRelease-1>", changeHeading)

    navFrame = tk.LabelFrame(ventana, text="Navegación", font=btn_font)
    navFrame.grid(row=3, column=0, columnspan=4, padx=30, pady=5, sticky=tk.N+tk.S+tk.E+tk.W)
    for r in range(3):
        navFrame.rowconfigure(r, weight=1)
    for c in range(3):
        navFrame.columnconfigure(c, weight=1)

    nav_font = ("Arial", 10, "bold")

    NWBtn = tk.Button(navFrame, text="NW", font=nav_font, command=lambda: go("NorthWest", NWBtn))
    NWBtn.grid(row=0, column=0, padx=2, pady=2, sticky=tk.N+tk.S+tk.E+tk.W)
    NoBtn = tk.Button(navFrame, text="N", font=nav_font, command=lambda: go("North", NoBtn))
    NoBtn.grid(row=0, column=1, padx=2, pady=2, sticky=tk.N+tk.S+tk.E+tk.W)
    NEBtn = tk.Button(navFrame, text="NE", font=nav_font, command=lambda: go("NorthEast", NEBtn))
    NEBtn.grid(row=0, column=2, padx=2, pady=2, sticky=tk.N+tk.S+tk.E+tk.W)
    WeBtn = tk.Button(navFrame, text="W", font=nav_font, command=lambda: go("West", WeBtn))
    WeBtn.grid(row=1, column=0, padx=2, pady=2, sticky=tk.N+tk.S+tk.E+tk.W)
    StopBtn = tk.Button(navFrame, text="STOP", font=nav_font, command=lambda: go("Stop", StopBtn))
    StopBtn.grid(row=1, column=1, padx=2, pady=2, sticky=tk.N+tk.S+tk.E+tk.W)
    EaBtn = tk.Button(navFrame, text="E", font=nav_font, command=lambda: go("East", EaBtn))
    EaBtn.grid(row=1, column=2, padx=2, pady=2, sticky=tk.N+tk.S+tk.E+tk.W)
    SWBtn = tk.Button(navFrame, text="SW", font=nav_font, command=lambda: go("SouthWest", SWBtn))
    SWBtn.grid(row=2, column=0, padx=2, pady=2, sticky=tk.N+tk.S+tk.E+tk.W)
    SoBtn = tk.Button(navFrame, text="S", font=nav_font, command=lambda: go("South", SoBtn))
    SoBtn.grid(row=2, column=1, padx=2, pady=2, sticky=tk.N+tk.S+tk.E+tk.W)
    SEBtn = tk.Button(navFrame, text="SE", font=nav_font, command=lambda: go("SouthEast", SEBtn))
    SEBtn.grid(row=2, column=2, padx=2, pady=2, sticky=tk.N+tk.S+tk.E+tk.W)

    navBtns = [NWBtn, NoBtn, NEBtn, WeBtn, StopBtn, EaBtn, SWBtn, SoBtn, SEBtn]
    for b in navBtns:
        _deshabilitarBtn(b)

    speedSldr = tk.Scale(ventana, label="Velocidad nav. (m/s):", resolution=1, from_=0, to=20,
                         tickinterval=5, orient=tk.HORIZONTAL, length=400, font=("Arial", 9))
    speedSldr.grid(row=4, column=0, columnspan=4, padx=10, pady=5, sticky=tk.E+tk.W)
    speedSldr.bind("<ButtonRelease-1>", changeNavSpeed)

    altSldr = tk.Scale(ventana, label="Altitud objetivo (m):", resolution=1, from_=1, to=50,
                       tickinterval=10, orient=tk.HORIZONTAL, length=300, font=("Arial", 9))
    altSldr.grid(row=5, column=0, columnspan=3, padx=10, pady=5, sticky=tk.E+tk.W)
    altSldr.set(5)

    applyAltBtn = tk.Button(ventana, text="Aplicar altitud", font=btn_font, command=applyAltitude)
    applyAltBtn.grid(row=5, column=3, padx=5, pady=5, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(applyAltBtn, 'Aplicar altitud')

    StartTelemBtn = tk.Button(ventana, text="▶ Iniciar telemetría", font=("Arial", 10), command=startTelem)
    StartTelemBtn.grid(row=6, column=0, columnspan=2, padx=3, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(StartTelemBtn, '▶ Iniciar telemetría')

    StopTelemBtn = tk.Button(ventana, text="■ Parar telemetría", font=("Arial", 10), command=stopTelem)
    StopTelemBtn.grid(row=6, column=2, columnspan=2, padx=3, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(StopTelemBtn, '■ Parar telemetría')

    telemetryFrame = tk.LabelFrame(ventana, text="Telemetría", font=btn_font)
    telemetryFrame.grid(row=7, column=0, columnspan=4, padx=10, pady=5, sticky=tk.N+tk.S+tk.E+tk.W)
    for r in range(4):
        telemetryFrame.rowconfigure(r, weight=1)
    for c in range(4):
        telemetryFrame.columnconfigure(c, weight=1)

    lbl_font = ("Arial", 9, "bold")
    val_font = ("Arial", 11)

    tk.Label(telemetryFrame, text='Altitud', font=lbl_font).grid(row=0, column=0, padx=4, pady=2)
    tk.Label(telemetryFrame, text='Heading', font=lbl_font).grid(row=0, column=1, padx=4, pady=2)
    tk.Label(telemetryFrame, text='Estado', font=lbl_font).grid(row=0, column=2, padx=4, pady=2)
    tk.Label(telemetryFrame, text='Velocidad', font=lbl_font).grid(row=0, column=3, padx=4, pady=2)

    altShowLbl = tk.Label(telemetryFrame, text='--', font=val_font, fg='blue')
    altShowLbl.grid(row=1, column=0, padx=4, pady=2)
    headingShowLbl = tk.Label(telemetryFrame, text='--', font=val_font, fg='blue')
    headingShowLbl.grid(row=1, column=1, padx=4, pady=2)
    stateShowLbl = tk.Label(telemetryFrame, text='--', font=val_font, fg='blue')
    stateShowLbl.grid(row=1, column=2, padx=4, pady=2)
    speedShowLbl = tk.Label(telemetryFrame, text='--', font=val_font, fg='blue')
    speedShowLbl.grid(row=1, column=3, padx=4, pady=2)

    tk.Label(telemetryFrame, text='Modo vuelo', font=lbl_font).grid(row=2, column=0, padx=4, pady=2)
    tk.Label(telemetryFrame, text='Latitud', font=lbl_font).grid(row=2, column=1, padx=4, pady=2)
    tk.Label(telemetryFrame, text='Longitud', font=lbl_font).grid(row=2, column=2, padx=4, pady=2)

    flightModeShowLbl = tk.Label(telemetryFrame, text='--', font=val_font, fg='blue')
    flightModeShowLbl.grid(row=3, column=0, padx=4, pady=2)
    latShowLbl = tk.Label(telemetryFrame, text='--', font=val_font, fg='blue')
    latShowLbl.grid(row=3, column=1, padx=4, pady=2)
    lonShowLbl = tk.Label(telemetryFrame, text='--', font=val_font, fg='blue')
    lonShowLbl.grid(row=3, column=2, padx=4, pady=2)

    gotoFrame = tk.LabelFrame(ventana, text="Ir a posición (GoTo)", font=btn_font)
    gotoFrame.grid(row=8, column=0, columnspan=4, padx=10, pady=5, sticky=tk.N+tk.S+tk.E+tk.W)
    for c in range(2):
        gotoFrame.columnconfigure(c, weight=1)

    tk.Label(gotoFrame, text='Lat:', font=("Arial", 9)).grid(row=0, column=0, padx=4, pady=2)
    latEntry = tk.Entry(gotoFrame, font=("Arial", 10))
    latEntry.grid(row=1, column=0, padx=4, pady=2, sticky=tk.E+tk.W)

    tk.Label(gotoFrame, text='Lon:', font=("Arial", 9)).grid(row=0, column=1, padx=4, pady=2)
    lonEntry = tk.Entry(gotoFrame, font=("Arial", 10))
    lonEntry.grid(row=1, column=1, padx=4, pady=2, sticky=tk.E+tk.W)

    gotoBtn = tk.Button(ventana, text="Ir a posición", font=btn_font, command=gotoPosition)
    gotoBtn.grid(row=9, column=0, columnspan=4, padx=5, pady=3, sticky=tk.N+tk.S+tk.E+tk.W)
    _deshabilitarBtn(gotoBtn, 'Ir a posición')

    return ventana


if __name__ == "__main__":
    ventana = crear_ventana()
    ventana.mainloop()