##########  INSTALAR ##########
# pymavlink
###############################

import tkinter as tk
from tkinter import messagebox
from dronLink.Dron import Dron


# ---- Flag global para bloquear actualizarBotonesSegunEstado durante transiciones ----
_enTransicion = False


# ---- Función para resetear un botón a su estado original después de un tiempo ----
def resetBtn(btn, originalText, delay=3000):
    """Resetea un botón a su estado original (naranja) tras 'delay' ms."""
    def _reset():
        global _enTransicion
        _enTransicion = False
        btn['text'] = originalText
        btn['fg'] = 'black'
        btn['bg'] = 'dark orange'
    btn.after(delay, _reset)


def showTelemetryInfo (telemetry_info):
    global altShowLbl, headingShowLbl, stateShowLbl
    global speedShowLbl, flightModeShowLbl, latShowLbl, lonShowLbl

    altShowLbl['text'] = round(telemetry_info['alt'], 2)
    headingShowLbl['text'] = round(telemetry_info['heading'], 2)
    stateShowLbl['text'] = telemetry_info['state']
    speedShowLbl['text'] = round(telemetry_info['groundSpeed'], 2)
    flightModeShowLbl['text'] = telemetry_info['flightMode']
    latShowLbl['text'] = round(telemetry_info['lat'], 6)
    lonShowLbl['text'] = round(telemetry_info['lon'], 6)

    # Actualizar botones según el estado real del dron
    actualizarBotonesSegunEstado()


def actualizarBotonesSegunEstado():
    """Sincroniza el aspecto de todos los botones con el estado actual del dron.
    Útil al conectarse con el dron ya en vuelo o armado."""
    global _enTransicion
    # Si hay una transición visual en curso (callback mostrando mensaje), no sobreescribir
    if _enTransicion:
        return

    state = dron.state

    # Conectar
    if state == 'disconnected':
        connectBtn['text'] = 'Conectar'
        connectBtn['fg'] = 'black'
        connectBtn['bg'] = 'dark orange'
    else:
        connectBtn['text'] = 'Conectado'
        connectBtn['fg'] = 'white'
        connectBtn['bg'] = 'green'

    # Armar: muestra estado intermedio "Armando..." si corresponde
    if state == 'arming':
        armBtn['text'] = 'Armando...'
        armBtn['fg'] = 'black'
        armBtn['bg'] = 'yellow'
    elif state in ('armed', 'takingOff', 'flying', 'returning', 'landing'):
        armBtn['text'] = 'Armado'
        armBtn['fg'] = 'white'
        armBtn['bg'] = 'green'
    else:
        # state == 'connected' o 'disconnected': el dron no está armado
        armBtn['text'] = 'Armar'
        armBtn['fg'] = 'black'
        armBtn['bg'] = 'dark orange'

    # Despegar: refleja si está en el aire, despegando o en tierra
    if state == 'takingOff':
        takeOffBtn['text'] = 'Despegando...'
        takeOffBtn['fg'] = 'black'
        takeOffBtn['bg'] = 'yellow'
    elif state == 'flying':
        takeOffBtn['text'] = 'En el aire ✈'
        takeOffBtn['fg'] = 'white'
        takeOffBtn['bg'] = 'green'
    elif state == 'returning':
        takeOffBtn['text'] = 'En el aire ✈'
        takeOffBtn['fg'] = 'white'
        takeOffBtn['bg'] = 'green'
    elif state == 'landing':
        takeOffBtn['text'] = 'Aterrizando...'
        takeOffBtn['fg'] = 'black'
        takeOffBtn['bg'] = 'yellow'
    else:
        # connected / disconnected / armed → en tierra
        takeOffBtn['text'] = 'Despegar'
        takeOffBtn['fg'] = 'black'
        takeOffBtn['bg'] = 'dark orange'

    # Aterrizar
    if state == 'landing':
        landBtn['text'] = 'Aterrizando...'
        landBtn['fg'] = 'black'
        landBtn['bg'] = 'yellow'
    else:
        landBtn['text'] = 'Aterrizar'
        landBtn['fg'] = 'black'
        landBtn['bg'] = 'dark orange'

    # RTL
    if state == 'returning':
        RTLBtn['text'] = 'Volviendo a casa...'
        RTLBtn['fg'] = 'black'
        RTLBtn['bg'] = 'yellow'
    else:
        RTLBtn['text'] = 'RTL'
        RTLBtn['fg'] = 'black'
        RTLBtn['bg'] = 'dark orange'


def connect ():
    global dron, speedSldr
    connection_string = 'tcp:127.0.0.1:5763'
    baud = 115200
    result = dron.connect(connection_string, baud)
    if result:
        speedSldr.set(1)
        # Actualizamos todos los botones según el estado real tras conectar
        # (el dron puede ya estar armado o en vuelo)
        actualizarBotonesSegunEstado()
    else:
        messagebox.showwarning("Aviso", "Ya está conectado o no se puede conectar.")


def disconnect():
    global dron
    result = dron.disconnect()
    if result:
        connectBtn['text'] = 'Conectar'
        connectBtn['fg'] = 'black'
        connectBtn['bg'] = 'dark orange'
        armBtn['text'] = 'Armar'
        armBtn['fg'] = 'black'
        armBtn['bg'] = 'dark orange'
        disconnectBtn['text'] = 'Desconectado'
        disconnectBtn['fg'] = 'white'
        disconnectBtn['bg'] = 'green'
        resetBtn(disconnectBtn, 'Desconectar', 2000)
    else:
        messagebox.showwarning("Aviso", "El dron debe estar en estado 'connected' para desconectar.\nEstado actual: " + dron.state)


def onArmError(msg):
    """Callback cuando el armado falla (no ready to arm, pre-arm checks, etc.)"""
    armBtn['text'] = 'Armar'
    armBtn['fg'] = 'black'
    armBtn['bg'] = 'dark orange'
    messagebox.showerror("Error al armar", "No se pudo armar el dron.\n\nMotivo: " + msg +
                         "\n\nComprueba que el dron esté listo para armar (GPS fix, pre-arm checks, etc.)")

def onArmed():
    """Callback cuando el armado se completa correctamente."""
    armBtn['text'] = 'Armado'
    armBtn['fg'] = 'white'
    armBtn['bg'] = 'green'

def arm():
    global dron
    if dron.state != 'connected':
        messagebox.showwarning("Aviso", "El dron debe estar conectado (y no armado) para armar.\nEstado actual: " + dron.state)
        return
    # Ponemos el botón en amarillo mientras espera confirmación
    armBtn['text'] = 'Armando...'
    armBtn['fg'] = 'black'
    armBtn['bg'] = 'yellow'
    result = dron.arm(blocking=False, callback=onArmed, error_callback=onArmError)
    if not result:
        armBtn['text'] = 'Armar'
        armBtn['fg'] = 'black'
        armBtn['bg'] = 'dark orange'
        messagebox.showerror("Error", "No se pudo iniciar el armado.\nEstado actual: " + dron.state)


def disarm():
    """Desarmar el dron enviando comando de desarme."""
    global dron
    if dron.state == 'armed':
        # Enviar comando de desarme directamente
        from pymavlink import mavutil
        dron.vehicle.mav.command_long_send(
            dron.vehicle.target_system, dron.vehicle.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 0, 0, 0, 0, 0, 0)
        dron.state = 'connected'
        armBtn['text'] = 'Armar'
        armBtn['fg'] = 'black'
        armBtn['bg'] = 'dark orange'
        disarmBtn['text'] = 'Desarmado'
        disarmBtn['fg'] = 'white'
        disarmBtn['bg'] = 'green'
        resetBtn(disarmBtn, 'Desarmar', 2000)
    else:
        messagebox.showwarning("Aviso", "El dron debe estar armado (sin volar) para desarmar.\nEstado actual: " + dron.state)


def inTheAir():
    """Callback cuando el dron ha alcanzado la altitud de despegue."""
    global _enTransicion
    _enTransicion = False
    # Actualizar el botón inmediatamente al completar el despegue
    takeOffBtn['text'] = 'En el aire ✈'
    takeOffBtn['fg'] = 'white'
    takeOffBtn['bg'] = 'green'


def takeoff ():
    global dron, altSldr, _enTransicion
    if _enTransicion:
        return  # Evitar doble clic durante transición
    if dron.state != 'armed':
        messagebox.showwarning("Aviso", "El dron debe estar armado para despegar.\nEstado actual: " + dron.state)
        return
    # Usamos la altitud del slider en lugar de un valor fijo
    alt = int(altSldr.get())
    _enTransicion = True  # Bloquear durante despegue
    result = dron.takeOff(alt, blocking=False, callback=inTheAir)
    if result:
        takeOffBtn['text'] = 'Despegando...'
        takeOffBtn['fg'] = 'black'
        takeOffBtn['bg'] = 'yellow'
    else:
        _enTransicion = False
        messagebox.showerror("Error", "No se pudo despegar.\nEstado actual: " + dron.state)


def onLanded():
    """Callback cuando el dron ha aterrizado."""
    global _enTransicion
    _enTransicion = True
    landBtn['text'] = 'Aterrizado ✓'
    landBtn['fg'] = 'white'
    landBtn['bg'] = 'green'
    armBtn['text'] = 'Armar'
    armBtn['fg'] = 'black'
    armBtn['bg'] = 'dark orange'
    takeOffBtn['text'] = 'Despegar'
    takeOffBtn['fg'] = 'black'
    takeOffBtn['bg'] = 'dark orange'
    resetBtn(landBtn, 'Aterrizar', 2000)


def land ():
    global dron, previousBtn, gotoBtn, _enTransicion
    if _enTransicion:
        return  # Evitar doble clic durante transición
    if dron.state not in ('flying', 'returning'):
        messagebox.showwarning("Aviso", "El dron debe estar volando para aterrizar.\nEstado actual: " + dron.state)
        return

    # Detener navegación direccional si está activa
    if previousBtn and previousBtn['bg'] == 'green':
        dron.go("Stop")

    result = dron.Land(blocking=False, callback=onLanded)
    if result:
        _enTransicion = True  # Bloquear durante aterrizaje
        landBtn['text'] = 'Aterrizando...'
        landBtn['fg'] = 'black'
        landBtn['bg'] = 'yellow'
        # Resetear el botón goto si estaba navegando
        if gotoBtn['text'] == 'Navegando...':
            gotoBtn['text'] = 'Ir a posición'
            gotoBtn['fg'] = 'black'
            gotoBtn['bg'] = 'dark orange'
        # Resetear el botón de dirección anterior si estaba activo
        if previousBtn:
            previousBtn['fg'] = 'black'
            previousBtn['bg'] = 'dark orange'
            previousBtn = None


def onRTLComplete():
    """Callback cuando el RTL ha terminado (dron en tierra)."""
    global _enTransicion
    _enTransicion = True
    RTLBtn['text'] = 'Aterrizado ✓'
    RTLBtn['fg'] = 'white'
    RTLBtn['bg'] = 'green'
    armBtn['text'] = 'Armar'
    armBtn['fg'] = 'black'
    armBtn['bg'] = 'dark orange'
    takeOffBtn['text'] = 'Despegar'
    takeOffBtn['fg'] = 'black'
    takeOffBtn['bg'] = 'dark orange'
    resetBtn(RTLBtn, 'RTL', 2000)


def RTL():
    global dron, previousBtn, gotoBtn, _enTransicion
    if _enTransicion:
        return  # Evitar doble clic durante transición
    if dron.state != 'flying':
        messagebox.showwarning("Aviso", "El dron debe estar volando para RTL.\nEstado actual: " + dron.state)
        return

    # Detener navegación direccional si está activa
    if previousBtn and previousBtn['bg'] == 'green':
        dron.go("Stop")

    result = dron.RTL(blocking=False, callback=onRTLComplete)
    if result:
        _enTransicion = True  # Bloquear durante RTL
        RTLBtn['text'] = 'Volviendo a casa...'
        RTLBtn['fg'] = 'black'
        RTLBtn['bg'] = 'yellow'
        # Resetear el botón goto si estaba navegando
        if gotoBtn['text'] == 'Navegando...':
            gotoBtn['text'] = 'Ir a posición'
            gotoBtn['fg'] = 'black'
            gotoBtn['bg'] = 'dark orange'
        # Resetear el botón de dirección anterior si estaba activo
        if previousBtn:
            previousBtn['fg'] = 'black'
            previousBtn['bg'] = 'dark orange'
            previousBtn = None

def go (direction, btn):
    global dron, previousBtn, gotoBtn
    if previousBtn:
        previousBtn['fg'] = 'black'
        previousBtn['bg'] = 'dark orange'

    dron.go(direction)
    btn['fg'] = 'white'
    btn['bg'] = 'green'
    previousBtn = btn

    # Resetear el botón goto si estaba navegando
    if gotoBtn['text'] == 'Navegando...':
        gotoBtn['text'] = 'Ir a posición'
        gotoBtn['fg'] = 'black'
        gotoBtn['bg'] = 'dark orange'


def startTelem():
    global dron
    dron.send_telemetry_info(showTelemetryInfo)

def stopTelem():
    global dron
    dron.stop_sending_telemetry_info()

def changeHeading (event):
    global dron, gradesSldr
    dron.changeHeading(int(gradesSldr.get()))

def changeNavSpeed (event):
    global dron, speedSldr
    dron.changeNavSpeed(float(speedSldr.get()))

def altitudeReached():
    changeAltBtn['text'] = 'Altitud alcanzada'
    changeAltBtn['fg'] = 'white'
    changeAltBtn['bg'] = 'green'
    resetBtn(changeAltBtn, 'Cambiar altitud', 3000)

def changeAlt():
    global dron, altSldr, changeAltBtn
    alt = int(altSldr.get())
    dron.change_altitude(alt, blocking=False, callback=altitudeReached)
    changeAltBtn['text'] = 'Cambiando altitud...'
    changeAltBtn['fg'] = 'black'
    changeAltBtn['bg'] = 'yellow'

def gotoReached():
    gotoBtn['text'] = 'Destino alcanzado'
    gotoBtn['fg'] = 'white'
    gotoBtn['bg'] = 'green'
    resetBtn(gotoBtn, 'Ir a posición', 3000)

def gotoPosition():
    global dron, gotoBtn, latEntry, lonEntry, altGotoEntry, previousBtn
    try:
        lat = float(latEntry.get())
        lon = float(lonEntry.get())
        alt = float(altGotoEntry.get())
    except ValueError:
        messagebox.showerror("Error", "Los campos Lat, Lon y Alt deben ser números válidos.")
        return

    if dron.state != 'flying':
        messagebox.showwarning("Aviso", "El dron debe estar volando para ir a una posición.\nEstado actual: " + dron.state)
        return

    dron.goto(lat, lon, alt, blocking=False, callback=gotoReached)
    gotoBtn['text'] = 'Navegando...'
    gotoBtn['fg'] = 'black'
    gotoBtn['bg'] = 'yellow'
    # Resetear el botón de dirección anterior si estaba activo
    if previousBtn:
        previousBtn['fg'] = 'black'
        previousBtn['bg'] = 'dark orange'
        previousBtn = None

def rotateFinished():
    global previousBtn
    rotateCWBtn['text'] = '↻ 90° CW'
    rotateCWBtn['fg'] = 'black'
    rotateCWBtn['bg'] = 'dark orange'
    rotateCCWBtn['text'] = '↺ 90° CCW'
    rotateCCWBtn['fg'] = 'black'
    rotateCCWBtn['bg'] = 'dark orange'
    # Si el último botón activo era uno de rotar, lo limpiamos
    if previousBtn in (rotateCWBtn, rotateCCWBtn):
        previousBtn = None

def rotateCW():
    global dron, rotateCWBtn
    if dron.state != 'flying':
        messagebox.showwarning("Aviso", "El dron debe estar volando para rotar.\nEstado actual: " + dron.state)
        return
    rotateCWBtn['text'] = 'Rotando CW...'
    rotateCWBtn['fg'] = 'white'
    rotateCWBtn['bg'] = 'green'
    dron.rotate(90, direction='cw', blocking=False, callback=rotateFinished)

def rotateCCW():
    global dron, rotateCCWBtn
    if dron.state != 'flying':
        messagebox.showwarning("Aviso", "El dron debe estar volando para rotar.\nEstado actual: " + dron.state)
        return
    rotateCCWBtn['text'] = 'Rotando CCW...'
    rotateCCWBtn['fg'] = 'white'
    rotateCCWBtn['bg'] = 'green'
    dron.rotate(90, direction='ccw', blocking=False, callback=rotateFinished)



def crear_ventana():
    global dron
    global altShowLbl, headingShowLbl, speedSldr, gradesSldr, stateShowLbl
    global speedShowLbl, flightModeShowLbl, latShowLbl, lonShowLbl
    global connectBtn, armBtn, takeOffBtn, landBtn, RTLBtn
    global disconnectBtn, disarmBtn
    global previousBtn
    global altSldr, changeAltBtn
    global latEntry, lonEntry, altGotoEntry, gotoBtn
    global rotateCWBtn, rotateCCWBtn

    dron = Dron()

    previousBtn = None

    ventana = tk.Tk()
    ventana.title("Dashboard con conexión directa")
    ventana.geometry("780x950")
    ventana.minsize(700, 850)

    # 12 filas, 4 columnas
    for i in range(12):
        ventana.rowconfigure(i, weight=1)
    for i in range(4):
        ventana.columnconfigure(i, weight=1)

    # ---- Fila 0: Conectar | Armar | Despegar | Desconectar ----
    connectBtn = tk.Button(ventana, text="Conectar", bg="dark orange", font=("Arial", 10, "bold"), command=connect)
    connectBtn.grid(row=0, column=0, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    armBtn = tk.Button(ventana, text="Armar", bg="dark orange", font=("Arial", 10, "bold"), command=arm)
    armBtn.grid(row=0, column=1, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    takeOffBtn = tk.Button(ventana, text="Despegar", bg="dark orange", font=("Arial", 10, "bold"), command=takeoff)
    takeOffBtn.grid(row=0, column=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    disconnectBtn = tk.Button(ventana, text="Desconectar", bg="dark orange", font=("Arial", 10, "bold"), command=disconnect)
    disconnectBtn.grid(row=0, column=3, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 1: Aterrizar | RTL | Rotar | Desarmar ----
    landBtn = tk.Button(ventana, text="Aterrizar", bg="dark orange", font=("Arial", 10, "bold"), command=land)
    landBtn.grid(row=1, column=0, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    RTLBtn = tk.Button(ventana, text="RTL", bg="dark orange", font=("Arial", 10, "bold"), command=RTL)
    RTLBtn.grid(row=1, column=1, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    # Rotar
    rotateFrame = tk.Frame(ventana)
    rotateFrame.grid(row=1, column=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)
    rotateFrame.columnconfigure(0, weight=1)
    rotateFrame.columnconfigure(1, weight=1)
    rotateFrame.rowconfigure(0, weight=1)

    rotateCWBtn = tk.Button(rotateFrame, text="↻ 90° CW", bg="dark orange", font=("Arial", 9), command=rotateCW)
    rotateCWBtn.grid(row=0, column=0, padx=1, sticky=tk.N + tk.S + tk.E + tk.W)

    rotateCCWBtn = tk.Button(rotateFrame, text="↺ 90° CCW", bg="dark orange", font=("Arial", 9), command=rotateCCW)
    rotateCCWBtn.grid(row=0, column=1, padx=1, sticky=tk.N + tk.S + tk.E + tk.W)

    disarmBtn = tk.Button(ventana, text="Desarmar", bg="dark orange", font=("Arial", 10, "bold"), command=disarm)
    disarmBtn.grid(row=1, column=3, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 2: Slider heading (ocupa 4 columnas) ----
    gradesSldr = tk.Scale(ventana, label="Heading (grados):", resolution=5, from_=0, to=360,
                          tickinterval=45, orient=tk.HORIZONTAL, length=400, font=("Arial", 9))
    gradesSldr.grid(row=2, column=0, columnspan=4, padx=10, pady=5, sticky=tk.E + tk.W)
    gradesSldr.bind("<ButtonRelease-1>", changeHeading)

    # ---- Fila 3: Navegación (ocupa 4 columnas) ----
    navFrame = tk.LabelFrame(ventana, text="Navegación", font=("Arial", 10, "bold"))
    navFrame.grid(row=3, column=0, columnspan=4, padx=30, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    for r in range(3):
        navFrame.rowconfigure(r, weight=1)
    for c in range(5):
        navFrame.columnconfigure(c, weight=1)

    nav_font = ("Arial", 10, "bold")
    NWBtn = tk.Button(navFrame, text="NW", bg="dark orange", font=nav_font,
                        command=lambda: go("NorthWest", NWBtn))
    NWBtn.grid(row=0, column=0, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    NoBtn = tk.Button(navFrame, text="N", bg="dark orange", font=nav_font,
                        command=lambda: go("North", NoBtn))
    NoBtn.grid(row=0, column=1, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    NEBtn = tk.Button(navFrame, text="NE", bg="dark orange", font=nav_font,
                        command=lambda: go("NorthEast", NEBtn))
    NEBtn.grid(row=0, column=2, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    # Botón subir a la derecha de la cuadrícula
    UpBtn = tk.Button(navFrame, text="▲ Subir", bg="SteelBlue1", fg="white", font=nav_font,
                        command=lambda: go("Up", UpBtn))
    UpBtn.grid(row=0, column=3, columnspan=2, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    WeBtn = tk.Button(navFrame, text="W", bg="dark orange", font=nav_font,
                        command=lambda: go("West", WeBtn))
    WeBtn.grid(row=1, column=0, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    StopBtn = tk.Button(navFrame, text="STOP", bg="red", fg="white", font=nav_font,
                        command=lambda: go("Stop", StopBtn))
    StopBtn.grid(row=1, column=1, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    EaBtn = tk.Button(navFrame, text="E", bg="dark orange", font=nav_font,
                        command=lambda: go("East", EaBtn))
    EaBtn.grid(row=1, column=2, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    SWBtn = tk.Button(navFrame, text="SW", bg="dark orange", font=nav_font,
                        command=lambda: go("SouthWest", SWBtn))
    SWBtn.grid(row=2, column=0, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    SoBtn = tk.Button(navFrame, text="S", bg="dark orange", font=nav_font,
                        command=lambda: go("South", SoBtn))
    SoBtn.grid(row=2, column=1, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    SEBtn = tk.Button(navFrame, text="SE", bg="dark orange", font=nav_font,
                        command=lambda: go("SouthEast", SEBtn))
    SEBtn.grid(row=2, column=2, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    # Botón bajar a la derecha de la cuadrícula
    DownBtn = tk.Button(navFrame, text="▼ Bajar", bg="SteelBlue3", fg="white", font=nav_font,
                        command=lambda: go("Down", DownBtn))
    DownBtn.grid(row=2, column=3, columnspan=2, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 4: Slider velocidad de navegación (4 columnas) ----
    speedSldr = tk.Scale(ventana, label="Velocidad nav. (m/s):", resolution=1, from_=0, to=20,
                         tickinterval=5, orient=tk.HORIZONTAL, length=400, font=("Arial", 9))
    speedSldr.grid(row=4, column=0, columnspan=4, padx=10, pady=5, sticky=tk.E + tk.W)
    speedSldr.bind("<ButtonRelease-1>", changeNavSpeed)

    # ---- Fila 5: Slider altitud objetivo + botón cambiar altitud ----
    altSldr = tk.Scale(ventana, label="Altitud objetivo (m):", resolution=1, from_=1, to=50,
                       tickinterval=10, orient=tk.HORIZONTAL, length=300, font=("Arial", 9))
    altSldr.grid(row=5, column=0, columnspan=3, padx=10, pady=5, sticky=tk.E + tk.W)
    altSldr.set(5)

    changeAltBtn = tk.Button(ventana, text="Cambiar altitud", bg="dark orange", font=("Arial", 10, "bold"),
                             command=changeAlt)
    changeAltBtn.grid(row=5, column=3, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 6: Telemetría botones ----
    StartTelemBtn = tk.Button(ventana, text="▶ Iniciar telemetría", bg="dark orange", font=("Arial", 10),
                              command=startTelem)
    StartTelemBtn.grid(row=6, column=0, columnspan=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    StopTelemBtn = tk.Button(ventana, text="■ Parar telemetría", bg="dark orange", font=("Arial", 10),
                             command=stopTelem)
    StopTelemBtn.grid(row=6, column=2, columnspan=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 7: Panel de telemetría (4 columnas) ----
    telemetryFrame = tk.LabelFrame(ventana, text="Telemetría", font=("Arial", 10, "bold"))
    telemetryFrame.grid(row=7, column=0, columnspan=4, padx=10, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    for r in range(4):
        telemetryFrame.rowconfigure(r, weight=1)
    for c in range(4):
        telemetryFrame.columnconfigure(c, weight=1)

    lbl_font = ("Arial", 9, "bold")
    val_font = ("Arial", 11)

    # Fila 0/1: Altitud | Heading | Estado | Velocidad
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

    # Fila 2/3: Modo vuelo | Latitud | Longitud
    tk.Label(telemetryFrame, text='Modo vuelo', font=lbl_font).grid(row=2, column=0, padx=4, pady=2)
    tk.Label(telemetryFrame, text='Latitud', font=lbl_font).grid(row=2, column=1, padx=4, pady=2)
    tk.Label(telemetryFrame, text='Longitud', font=lbl_font).grid(row=2, column=2, padx=4, pady=2)

    flightModeShowLbl = tk.Label(telemetryFrame, text='--', font=val_font, fg='blue')
    flightModeShowLbl.grid(row=3, column=0, padx=4, pady=2)
    latShowLbl = tk.Label(telemetryFrame, text='--', font=val_font, fg='blue')
    latShowLbl.grid(row=3, column=1, padx=4, pady=2)
    lonShowLbl = tk.Label(telemetryFrame, text='--', font=val_font, fg='blue')
    lonShowLbl.grid(row=3, column=2, padx=4, pady=2)

    # ---- Fila 8: GoTo frame (lat, lon, alt) ----
    gotoFrame = tk.LabelFrame(ventana, text="Ir a posición (GoTo)", font=("Arial", 10, "bold"))
    gotoFrame.grid(row=8, column=0, columnspan=4, padx=10, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    for c in range(3):
        gotoFrame.columnconfigure(c, weight=1)

    tk.Label(gotoFrame, text='Lat:', font=("Arial", 9)).grid(row=0, column=0, padx=4, pady=2)
    latEntry = tk.Entry(gotoFrame, font=("Arial", 10))
    latEntry.grid(row=1, column=0, padx=4, pady=2, sticky=tk.E + tk.W)

    tk.Label(gotoFrame, text='Lon:', font=("Arial", 9)).grid(row=0, column=1, padx=4, pady=2)
    lonEntry = tk.Entry(gotoFrame, font=("Arial", 10))
    lonEntry.grid(row=1, column=1, padx=4, pady=2, sticky=tk.E + tk.W)

    tk.Label(gotoFrame, text='Alt:', font=("Arial", 9)).grid(row=0, column=2, padx=4, pady=2)
    altGotoEntry = tk.Entry(gotoFrame, font=("Arial", 10))
    altGotoEntry.grid(row=1, column=2, padx=4, pady=2, sticky=tk.E + tk.W)

    # ---- Fila 9: Botón Ir a posición (4 columnas) ----
    gotoBtn = tk.Button(ventana, text="Ir a posición", bg="dark orange", font=("Arial", 10, "bold"),
                        command=gotoPosition)
    gotoBtn.grid(row=9, column=0, columnspan=4, padx=5, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    return ventana


if __name__ == "__main__":
    ventana = crear_ventana()
    ventana.mainloop()
