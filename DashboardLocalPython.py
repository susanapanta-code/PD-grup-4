##########  INSTALAR ##########
# pymavlink
###############################

import tkinter as tk
from dronLink.Dron import Dron



def showTelemetryInfo (telemetry_info):
    global heading, altitude, groundSpeed, state
    global altShowLbl, headingShowLbl, stateShowLbl
    global speedShowLbl, flightModeShowLbl, latShowLbl, lonShowLbl
    altShowLbl['text'] = round (telemetry_info['alt'],2)
    headingShowLbl['text'] =  round(telemetry_info['heading'],2)
    stateShowLbl['text'] = telemetry_info['state']
    speedShowLbl['text'] = round(telemetry_info['groundSpeed'], 2)
    flightModeShowLbl['text'] = telemetry_info['flightMode']
    latShowLbl['text'] = round(telemetry_info['lat'], 6)
    lonShowLbl['text'] = round(telemetry_info['lon'], 6)


def connect ():
    global dron, speedSldr
    connection_string ='tcp:127.0.0.1:5763'
    baud = 115200
    dron.connect(connection_string,baud)
    # cambiamos el color del boton
    connectBtn['text'] = 'Conectado'
    connectBtn['fg'] = 'white'
    connectBtn['bg'] = 'green'
    # fijamos la velocidad por defecto en el slider
    speedSldr.set(1)

def arm ():
    global dron
    dron.arm()
    armBtn['text'] = 'Armado'
    armBtn['fg'] = 'white'
    armBtn['bg'] = 'green'

def inTheAir ():
    # ya ha alcanzado la altura de despegue
    takeOffBtn['text'] = 'En el aire'
    takeOffBtn['fg'] = 'white'
    takeOffBtn['bg'] = 'green'


def takeoff ():
    global dron
    # despegamos a una altura de 5 metros
    # llamada no bloqueante. Cuando alcance la altura indicada ejecutará la función inTheAir
    dron.takeOff (5, blocking = False,  callback = inTheAir)
    takeOffBtn['text'] = 'Despegando...'
    takeOffBtn['fg'] = 'black'
    takeOffBtn['bg'] = 'yellow'

def land ():
    global dron
    # llamada no bloqueante
    dron.Land(blocking = False, callback = inTheAir)
    landBtn['text'] = 'En tierra'
    landBtn['fg'] = 'white'
    landBtn['bg'] = 'green'

def RTL():
    global dron
    # llamada no bloqueante
    dron.RTL(blocking = False, callback = inTheAir)
    RTLBtn['text'] = 'En tierra'
    RTLBtn['fg'] = 'white'
    RTLBtn['bg'] = 'green'

def go (direction, btn):
    global dron, previousBtn
    # cambio el color del anterior boton clicado (si lo hay)
    if previousBtn:
        previousBtn['fg'] = 'black'
        previousBtn['bg'] = 'dark orange'

    # navegamos en la dirección indicada
    dron.go (direction)
    # pongo en verde el boton clicado
    btn['fg'] = 'white'
    btn['bg'] = 'green'
    # tomo nota de que este es el último botón clicado
    previousBtn = btn


def startTelem():
    global dron
    # pedimos datos de telemetría que se procesarán en showTelemetryInfo a medida que vayan llegando
    dron.send_telemetry_info(showTelemetryInfo)

def stopTelem():
    global dron
    dron.stop_sending_telemetry_info()

def changeHeading (event):
    global dron
    global gradesSldr
    # cambiamos el heading según se haya seleccionado en el slider
    dron.changeHeading(int (gradesSldr.get()))

def changeNavSpeed (event):
    global dron
    global speedSldr
    # cambiamos la velocidad de navagación según se haya seleccionado en el slider
    dron.changeNavSpeed(float (speedSldr.get()))

def altitudeReached():
    changeAltBtn['text'] = 'Altitud alcanzada'
    changeAltBtn['fg'] = 'white'
    changeAltBtn['bg'] = 'green'

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

def gotoPosition():
    global dron, gotoBtn, latEntry, lonEntry, altEntry
    try:
        lat = float(latEntry.get())
        lon = float(lonEntry.get())
        alt = float(altEntry.get())
        dron.goto(lat, lon, alt, blocking=False, callback=gotoReached)
        gotoBtn['text'] = 'Navegando...'
        gotoBtn['fg'] = 'black'
        gotoBtn['bg'] = 'yellow'
    except ValueError:
        gotoBtn['text'] = 'Error en datos'
        gotoBtn['fg'] = 'white'
        gotoBtn['bg'] = 'red'

def rotateFinished():
    rotateCWBtn['fg'] = 'black'
    rotateCWBtn['bg'] = 'dark orange'
    rotateCCWBtn['fg'] = 'black'
    rotateCCWBtn['bg'] = 'dark orange'

def rotateCW():
    global dron, rotateCWBtn
    dron.rotate(90, direction='cw', blocking=False, callback=rotateFinished)
    rotateCWBtn['text'] = 'Rotando CW...'
    rotateCWBtn['fg'] = 'black'
    rotateCWBtn['bg'] = 'yellow'

def rotateCCW():
    global dron, rotateCCWBtn
    dron.rotate(90, direction='ccw', blocking=False, callback=rotateFinished)
    rotateCCWBtn['text'] = 'Rotando CCW...'
    rotateCCWBtn['fg'] = 'black'
    rotateCCWBtn['bg'] = 'yellow'



def crear_ventana():
    global dron
    global  altShowLbl, headingShowLbl,  speedSldr, gradesSldr, stateShowLbl
    global speedShowLbl, flightModeShowLbl, latShowLbl, lonShowLbl
    global connectBtn, armBtn, takeOffBtn, landBtn, RTLBtn
    global previousBtn # aqui guardaré el ultimo boton de navegación clicado
    global altSldr, changeAltBtn
    global latEntry, lonEntry, altEntry, gotoBtn
    global rotateCWBtn, rotateCCWBtn

    dron = Dron()

    previousBtn = None

    ventana = tk.Tk()
    ventana.title("Dashboard con conexión directa")
    ventana.geometry("750x900")
    ventana.minsize(650, 800)

    # 11 filas, 3 columnas
    for i in range(11):
        ventana.rowconfigure(i, weight=1)
    for i in range(3):
        ventana.columnconfigure(i, weight=1)

    # ---- Fila 0: Conectar | Armar | Despegar en línea ----
    connectBtn = tk.Button(ventana, text="Conectar", bg="dark orange", font=("Arial", 10, "bold"), command=connect)
    connectBtn.grid(row=0, column=0, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    armBtn = tk.Button(ventana, text="Armar", bg="dark orange", font=("Arial", 10, "bold"), command=arm)
    armBtn.grid(row=0, column=1, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    takeOffBtn = tk.Button(ventana, text="Despegar", bg="dark orange", font=("Arial", 10, "bold"), command=takeoff)
    takeOffBtn.grid(row=0, column=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 1: Aterrizar | RTL | (vacío o rotar) ----
    landBtn = tk.Button(ventana, text="Aterrizar", bg="dark orange", font=("Arial", 10, "bold"), command=land)
    landBtn.grid(row=1, column=0, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    RTLBtn = tk.Button(ventana, text="RTL", bg="dark orange", font=("Arial", 10, "bold"), command=RTL)
    RTLBtn.grid(row=1, column=1, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 1 col 2: Rotar ----
    rotateFrame = tk.Frame(ventana)
    rotateFrame.grid(row=1, column=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)
    rotateFrame.columnconfigure(0, weight=1)
    rotateFrame.columnconfigure(1, weight=1)
    rotateFrame.rowconfigure(0, weight=1)

    rotateCWBtn = tk.Button(rotateFrame, text="↻ 90° CW", bg="dark orange", font=("Arial", 9), command=rotateCW)
    rotateCWBtn.grid(row=0, column=0, padx=1, sticky=tk.N + tk.S + tk.E + tk.W)

    rotateCCWBtn = tk.Button(rotateFrame, text="↺ 90° CCW", bg="dark orange", font=("Arial", 9), command=rotateCCW)
    rotateCCWBtn.grid(row=0, column=1, padx=1, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 2: Slider heading (ocupa 3 columnas, con length para que los ticks se vean) ----
    gradesSldr = tk.Scale(ventana, label="Heading (grados):", resolution=5, from_=0, to=360,
                          tickinterval=45, orient=tk.HORIZONTAL, length=350, font=("Arial", 9))
    gradesSldr.grid(row=2, column=0, columnspan=3, padx=10, pady=5, sticky=tk.E + tk.W)
    gradesSldr.bind("<ButtonRelease-1>", changeHeading)

    # ---- Fila 3: Navegación (ocupa 3 columnas) ----
    navFrame = tk.LabelFrame(ventana, text="Navegación", font=("Arial", 10, "bold"))
    navFrame.grid(row=3, column=0, columnspan=3, padx=30, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    for r in range(3):
        navFrame.rowconfigure(r, weight=1)
    for c in range(3):
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

    WeBtn = tk.Button(navFrame, text="W", bg="dark orange", font=nav_font,
                        command=lambda: go("West", WeBtn))
    WeBtn.grid(row=1, column=0, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    StopBtn = tk.Button(navFrame, text="STOP", bg="red", fg="white", font=nav_font,
                        command=lambda: go("Stop", StopBtn))
    StopBtn.grid(row=1, column=1, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    EaBtn = tk.Button(navFrame, text="E", bg="dark orange", font=nav_font,
                        command=lambda: go("East", EaBtn))
    EaBtn.grid(row=1, column=2, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    SWBtn = tk.Button(navFrame, text="SW ↓", bg="dark orange", font=nav_font,
                        command=lambda: go("Down", SWBtn))
    SWBtn.grid(row=2, column=0, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    SoBtn = tk.Button(navFrame, text="S", bg="dark orange", font=nav_font,
                        command=lambda: go("South", SoBtn))
    SoBtn.grid(row=2, column=1, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    SEBtn = tk.Button(navFrame, text="SE ↑", bg="dark orange", font=nav_font,
                        command=lambda: go("Up", SEBtn))
    SEBtn.grid(row=2, column=2, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 4: Slider velocidad de navegación (3 columnas) ----
    speedSldr = tk.Scale(ventana, label="Velocidad nav. (m/s):", resolution=1, from_=0, to=20,
                         tickinterval=5, orient=tk.HORIZONTAL, length=350, font=("Arial", 9))
    speedSldr.grid(row=4, column=0, columnspan=3, padx=10, pady=5, sticky=tk.E + tk.W)
    speedSldr.bind("<ButtonRelease-1>", changeNavSpeed)

    # ---- Fila 5: Slider altitud objetivo + botón cambiar altitud ----
    altSldr = tk.Scale(ventana, label="Altitud objetivo (m):", resolution=1, from_=1, to=50,
                       tickinterval=10, orient=tk.HORIZONTAL, length=250, font=("Arial", 9))
    altSldr.grid(row=5, column=0, columnspan=2, padx=10, pady=5, sticky=tk.E + tk.W)

    changeAltBtn = tk.Button(ventana, text="Cambiar altitud", bg="dark orange", font=("Arial", 10, "bold"),
                             command=changeAlt)
    changeAltBtn.grid(row=5, column=2, padx=5, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 6: Telemetría botones ----
    StartTelemBtn = tk.Button(ventana, text="▶ Iniciar telemetría", bg="dark orange", font=("Arial", 10),
                              command=startTelem)
    StartTelemBtn.grid(row=6, column=0, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    StopTelemBtn = tk.Button(ventana, text="■ Parar telemetría", bg="dark orange", font=("Arial", 10),
                             command=stopTelem)
    StopTelemBtn.grid(row=6, column=1, columnspan=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    # ---- Fila 7: Panel de telemetría (3 columnas) ----
    telemetryFrame = tk.LabelFrame(ventana, text="Telemetría", font=("Arial", 10, "bold"))
    telemetryFrame.grid(row=7, column=0, columnspan=3, padx=10, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    for r in range(4):
        telemetryFrame.rowconfigure(r, weight=1)
    for c in range(4):
        telemetryFrame.columnconfigure(c, weight=1)

    lbl_font = ("Arial", 9, "bold")
    val_font = ("Arial", 10)

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
    gotoFrame.grid(row=8, column=0, columnspan=3, padx=10, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    for c in range(3):
        gotoFrame.columnconfigure(c, weight=1)

    tk.Label(gotoFrame, text='Lat:', font=("Arial", 9)).grid(row=0, column=0, padx=4, pady=2)
    latEntry = tk.Entry(gotoFrame, font=("Arial", 10))
    latEntry.grid(row=1, column=0, padx=4, pady=2, sticky=tk.E + tk.W)

    tk.Label(gotoFrame, text='Lon:', font=("Arial", 9)).grid(row=0, column=1, padx=4, pady=2)
    lonEntry = tk.Entry(gotoFrame, font=("Arial", 10))
    lonEntry.grid(row=1, column=1, padx=4, pady=2, sticky=tk.E + tk.W)

    tk.Label(gotoFrame, text='Alt:', font=("Arial", 9)).grid(row=0, column=2, padx=4, pady=2)
    altEntry = tk.Entry(gotoFrame, font=("Arial", 10))
    altEntry.grid(row=1, column=2, padx=4, pady=2, sticky=tk.E + tk.W)

    # ---- Fila 9: Botón Ir a posición (3 columnas) ----
    gotoBtn = tk.Button(ventana, text="Ir a posición", bg="dark orange", font=("Arial", 10, "bold"),
                        command=gotoPosition)
    gotoBtn.grid(row=9, column=0, columnspan=3, padx=5, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    return ventana


if __name__ == "__main__":
    ventana = crear_ventana()
    ventana.mainloop()
