# Proyecto de Drones — Grup 4

Sistema de control y monitorización de drones desarrollado como proyecto de capstone del 8.º cuatrimestre en la **EETAC (UPC)**. El proyecto evoluciona a lo largo de cuatro versiones, desde un control básico local hasta un sistema autónomo de seguimiento dron-a-dron con visión artificial e inteligencia artificial.

---

## Índice

1. [Descripción general](#descripción-general)
2. [Estructura del repositorio](#estructura-del-repositorio)
3. [Tecnologías y herramientas](#tecnologías-y-herramientas)
4. [Versión 1 — Control local básico](#versión-1--control-local-básico)
5. [Versión 2 — Sistema integrado y distribuido](#versión-2--sistema-integrado-y-distribuido)
6. [Versiones 3 y 4 — Seguimiento autónomo con IA](#versiones-3-y-4--seguimiento-autónomo-con-ia)
7. [Librería DronLink](#librería-dronlink)
8. [Dashboard en C#](#dashboard-en-c)
9. [Instalación y puesta en marcha](#instalación-y-puesta-en-marcha)
10. [Conexión al dron real](#conexión-al-dron-real)

---

## Descripción general

El proyecto implementa una aplicación completa de control de drones cuatrimotores con ArduPilot. Se trabaja en paralelo con el simulador **ArduPilot SITL** y con hardware real en el **DroneLab del Campus del Baix Llobregat**.

Las capacidades finales del sistema incluyen:

- Control manual desde dashboards de escritorio (Python y C#) y desde aplicaciones web
- Comunicación distribuida mediante **MQTT** y streaming de vídeo en tiempo real con **WebRTC**
- Reconocimiento de objetos con redes neuronales preentrenadas (COCO dataset)
- Control por voz en castellano
- **Seguimiento autónomo líder-seguidor** con control PID de 3 ejes y detección visual mediante **YOLOv8**

---

## Estructura del repositorio

```
PD-grup-4/
├── Versión 1 y 2/               # Versiones fundacionales
│   ├── DashboardLocalPython.py  # Dashboard local en Tkinter
│   ├── DashboardGlobalPython.py # Dashboard global vía MQTT
│   ├── AutopilotService.py      # Servicio de autopiloto (MQTT)
│   ├── CameraService.py         # Servicio de cámara (WebRTC)
│   ├── serverHTTP.py            # WebApp Flask (HTTP)
│   ├── serverMQTT.py            # WebApp Flask (HTTPS + MQTT)
│   ├── GUIAPROYECTO.md          # Guía completa del proyecto
│   └── requirements.txt
├── Versión 3 y 4/               # Sistema autónomo avanzado
│   ├── SeguimientoDron V2.py    # Sistema líder-seguidor (pieza principal)
│   ├── sitl_leader_follower.py  # Lanzador de simulación dual SITL
│   ├── simulation.py            # Simulación 2D del PID con Pygame
│   ├── entrenar.py              # Entrenamiento del modelo YOLOv8
│   ├── InterfazEtiquetación.py  # Herramienta de anotación de imágenes
│   ├── reconocimiento_camara.py # Detección en tiempo real
│   └── requirements.txt
├── DashboardLocalCsharp/        # Dashboard de escritorio en C#
│   ├── Form1.cs                 # Formulario principal
│   ├── GaleriaForm.cs           # Galería de capturas de pantalla
│   └── map.html                 # Mapa Leaflet embebido
├── dronLink/                    # Librería Python de control del dron
│   ├── Dron.py                  # Clase principal
│   ├── dron_*.py                # Módulos funcionales
│   └── tests/                   # Suite de tests (19+ ficheros)
├── templates/                   # HTML de las WebApps
│   ├── indexHTTP.html
│   └── indexMQTT.html
└── Antiguo/                     # Código legado de iteraciones previas
```

---

## Tecnologías y herramientas

| Categoría | Herramientas |
|---|---|
| **Lenguajes** | Python 3.9+, C#, JavaScript, HTML/CSS |
| **Protocolo dron** | MAVLink (pymavlink) |
| **Mensajería** | MQTT (paho-mqtt, MQTTnet) |
| **Vídeo** | WebRTC (aiortc), OpenCV |
| **IA / Visión** | YOLOv8 (ultralytics), PyTorch |
| **Web** | Flask, Bootstrap 5 |
| **GUIs** | Tkinter, tkintermapview, Windows Forms |
| **Simulador** | ArduPilot SITL + MAVProxy |
| **Otros** | Newtonsoft.Json, Microsoft WebView2 |

---

## Versión 1 — Control local básico

Objetivo: aprender los componentes de forma individual.

### Dashboard local en Python (`DashboardLocalPython.py`)

Interfaz Tkinter que se conecta directamente al simulador SITL mediante la librería DronLink. Permite:

- Conectar, armar, despegar, aterrizar y RTL
- Navegar en 8 direcciones cardinales
- Visualizar telemetría (altitud, velocidad, latitud/longitud, modo de vuelo)
- Girar 90° en sentido horario/antihorario

Las llamadas al dron son **no bloqueantes** con callbacks, por lo que la interfaz permanece operativa durante las operaciones.

### Dashboard local en C# (`DashboardLocalCsharp/`)

Aplicación Windows Forms con funcionalidad equivalente. Incorpora un slider para configurar la altitud de despegue, un botón de modo guiado y muestra la posición GPS del dron.

### WebApp HTTP (`serverHTTP.py` + `indexHTTP.html`)

Servidor Flask en el puerto 5000. El cliente web realiza peticiones HTTP POST para enviar comandos y GET periódicos para obtener telemetría.

### WebApp MQTT (`serverMQTT.py` + `indexMQTT.html`)

Servidor Flask con HTTPS (puerto 5002). El navegador se conecta directamente al broker MQTT, lo que reduce la latencia respecto a la versión HTTP. Incluye tres pestañas: Control, Mapa (Leaflet) y Vídeo.

---

## Versión 2 — Sistema integrado y distribuido

Objetivo: integrar todos los módulos en un sistema cohesionado con comunicación global.

### Arquitectura

```
[Dashboard Python/C#/WebApp]
          |
          | MQTT (pub/sub)
          |
   [MQTT Broker]  ←→  [AutopilotService.py]  ←→  [Dron / SITL]
                                ↑
                       [CameraService.py]  ←→  WebRTC  ←→  [Clientes]
```

### AutopilotService (`AutopilotService.py`)

Servicio central que se conecta al dron y escucha comandos del broker MQTT con el patrón de topic:
```
+/autopilotServiceDemo/#
```
Publica telemetría y estados en respuesta a los clientes conectados.

### CameraService (`CameraService.py`)

Captura el stream de vídeo con OpenCV y lo emite por WebRTC a todos los clientes que lo soliciten.

### Control por voz

Disponible en la WebApp MQTT. Comandos reconocidos (Web Speech API en castellano):

| Voz | Acción |
|---|---|
| "despega" | Despegue |
| "aterriza" / "tierra" | Aterrizaje |
| "regresa" / "rtl" | Return to Launch |
| "norte" / "adelante" | Volar al norte |
| "sur" / "atrás" | Volar al sur |
| "este" / "derecha" | Volar al este |
| "oeste" / "izquierda" | Volar al oeste |
| "para" / "stop" | Detener movimiento |

### Reconocimiento de objetos

Se usa YOLOv8 preentrenado con el dataset COCO para detectar objetos (teléfonos, perros, paraguas, bananas, etc.) en el stream de vídeo. El procesamiento se aplica a 1 de cada 25 frames para equilibrar fluidez y velocidad de detección.

---

## Versiones 3 y 4 — Seguimiento autónomo con IA

Pieza principal: `Versión 3 y 4/SeguimientoDron V2.py`

### Sistema Líder-Seguidor

El dron seguidor replica de forma autónoma la trayectoria del dron líder en el espacio 3D, manteniendo una distancia (*offset*) constante y orientando siempre su cabeceo hacia él.

```
[Dron Líder]  ──telemetría MAVLink──▶  [SeguimientoDron V2.py]
                                               │
                                    ┌──────────┼──────────┐
                                    │          │          │
                               Thread PID  Thread YOLO  Thread GUI
                                    │          │
                               [Dron Seguidor]
```

### Control PID de 3 ejes

| Eje | Descripción |
|---|---|
| **Norte (Y)** | Seguimiento longitudinal |
| **Este (X)** | Seguimiento lateral |
| **Altitud (Z)** | Mantenimiento vertical y evasión de colisiones |

Implementaciones adicionales: anti-windup de integral, filtro pasa-bajos en derivativo (α = 0.2), saturación de velocidad (3.0 m/s lateral, 1.0 m/s vertical).

### Control de orientación (Yaw)

El ángulo de cabeceo se calcula dinámicamente mediante `atan2` para que el seguidor mire siempre hacia las coordenadas GPS del líder.

### Detección visual con YOLOv8

Un hilo de visión independiente captura fotogramas de la cámara a bordo a ~30 FPS, detecta el dron líder con el modelo entrenado (`best.pt`) y ajusta el heading del seguidor según el error angular calculado.

### GUI de ajuste en vuelo

Interfaz Tkinter que embebe la vista de la cámara en directo y permite afinar los coeficientes Kp, Ki y Kd con sliders durante el vuelo.

### Failsafes de seguridad

| Failsafe | Comportamiento |
|---|---|
| Aterrizaje del líder | El seguidor aterriza automáticamente si el líder entra en modo `LAND`/`RTL` o baja de la altitud mínima |
| Timeout de telemetría | Cese del control vectorial si el paquete MAVLink supera `MAX_TELEMETRY_AGE = 2.0 s` |
| Saturación de velocidad | Los comandos MAVLink están acotados a velocidades máximas estrictas |

### Entrenamiento del modelo YOLO

```
InterfazEtiquetación.py  →  split_dataset.py  →  entrenar.py  →  best.pt
```

La herramienta de etiquetado permite anotar bounding boxes con atajos de teclado (`a`/`d` para navegar, `u` para deshacer, `n` para muestras negativas) y retoma desde la última anotación guardada.

---

## Librería DronLink

`dronLink/` contiene la librería Python que abstrae el protocolo MAVLink. La clase `Dron` agrupa 19 módulos:

| Módulo | Funcionalidad |
|---|---|
| `dron_connect` | Conexión y telemetría |
| `dron_arm` | Armado y modos de vuelo |
| `dron_takeOff` | Despegue |
| `dron_RTL_Land` | RTL y aterrizaje |
| `dron_nav` | Navegación en 8 direcciones |
| `dron_heading` | Control de yaw |
| `dron_goto` | Ir a posición GPS |
| `dron_move` | Movimiento por distancia |
| `dron_mission` | Planes de vuelo y misiones |
| `dron_altitude` | Cambio de altitud |
| `dron_drop` | Liberación de carga |
| `dron_RC_override` | Control manual RC |
| `dron_parameters` | Lectura/escritura de parámetros |
| `dron_geofence` | Geofencing y escenarios |
| `dron_telemetry` | Stream de telemetría global |
| `dron_local_telemetry` | Telemetría en frame NED |
| `dron_minAltitude` | Protección de altitud mínima |
| `dron_inDoor` | Escenarios indoor (NED) |
| `message_handler` | Escucha asíncrona de mensajes |

El modelo de programación es **no bloqueante**: todas las operaciones largas aceptan un callback que se ejecuta al completarse.

La suite de tests en `dronLink/tests/` cubre todas las funcionalidades con 19+ ficheros de test.

---

## Dashboard en C#

`DashboardLocalCsharp/` es una aplicación Windows Forms que opera en modo global vía MQTT. Características:

- Conexión al broker `dronseetac.upc.edu:8000/mqtt`
- Mapa Leaflet embebido con WebView2 para visualización GPS en tiempo real
- Slider para configurar la altitud de despegue
- Galería de fotos capturadas del stream de vídeo
- Indicador visual de estado de conexión

---

## Instalación y puesta en marcha

### Requisitos previos

- Python 3.9+
- [Mission Planner](https://ardupilot.org/planner/docs/mission-planner-installation.html) (incluye el simulador SITL)
- [MAVProxy](https://ardupilot.org/mavproxy/) (para conexión simultánea con Mission Planner)
- Visual Studio (para el dashboard en C#)

### Versiones 1 y 2

```bash
cd "Versión 1 y 2"
pip install -r requirements.txt
```

**Escenario local (SITL):**
1. Iniciar Mission Planner y lanzar SITL
2. Ejecutar `python DashboardLocalPython.py`

**Escenario global:**
1. Iniciar SITL
2. `python AutopilotService.py`
3. `python DashboardGlobalPython.py` (en el mismo equipo o en otro conectado a Internet)

**WebApp:**
```bash
python serverMQTT.py   # HTTPS, puerto 5002
# Acceder desde el móvil a https://<IP-del-servidor>:5002
```

### Versiones 3 y 4

```bash
cd "Versión 3 y 4"
pip install -r requirements.txt
```

1. Lanzar dos instancias SITL (líder en puerto 14561, seguidor en 14551)
2. Asegurarse de que `YOLO_MODEL_PATH` en el script apunta al modelo entrenado (`best.pt`)
3. Ejecutar el sistema:
   ```bash
   python "SeguimientoDron V2.py"
   ```
4. En la GUI: **Conectar Ambos** → **Activar telemetría** → **Armar y Despegar** → **Activar seguimiento**

---

## Conexión al dron real

Sustituir la cadena de conexión SITL por el puerto COM de la radio de telemetría:

```python
# SITL
connection_string = "tcp:127.0.0.1:5763"
vehicle = connect(connection_string, wait_ready=True, baud=115200)

# Dron real (ajustar COM según Administrador de dispositivos)
connection_string = "COM12"
vehicle = connect(connection_string, wait_ready=True, baud=57600)
```

Para conectar **simultáneamente** Mission Planner y la aplicación al dron real, usar MAVProxy como proxy:

```bash
mavproxy --master=com12 --out=udp:127.0.0.1:14550 --out=udp:127.0.0.1:14551
```

Mission Planner se conecta al puerto 14550 y la aplicación al 14551.

---

*Proyecto desarrollado en el Campus del Baix Llobregat, EETAC — Universitat Politècnica de Catalunya.*
