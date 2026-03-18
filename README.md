## Dashboard V2 — Interfaz unificada (autopiloto + cámara)

`DashboardV2.py` es el punto de entrada único de la versión 2. Integra el **servicio de autopiloto** y el **servicio de cámara** en una sola interfaz y permite elegir entre dos modos de operación:

| Modo | Descripción |
|------|-------------|
| **Local** | Controla el dron directamente a través de `dronLink` (sin intermediario). El receptor de cámara WebRTC se inicia automáticamente. |
| **Global** | Publica comandos vía MQTT al `AutopilotService.py`. La telemetría y los eventos de estado llegan de vuelta por MQTT. |

### Dependencias

```bash
pip install paho-mqtt aiortc opencv-python pymavlink
```

### Cómo ejecutar en modo Local

1. Arranca el simulador de dron (p. ej. SITL en `tcp:127.0.0.1:5763`).
2. (Opcional) Arranca el servicio de cámara en otra terminal:
   ```bash
   python CameraService.py
   ```
3. Lanza el dashboard:
   ```bash
   python DashboardV2.py
   ```
4. En la interfaz, selecciona **Local** y pulsa **Iniciar**.
5. Usa los botones para Conectar → Armar → Despegar → Navegar → Aterrizar/RTL.
6. La ventana de cámara WebRTC se cierra pulsando la tecla **Q** en esa ventana.

### Cómo ejecutar en modo Global

1. Asegúrate de tener acceso a internet (se conecta a `broker.hivemq.com`).
2. Arranca el servicio de autopiloto en otra terminal (junto al dron real o simulador):
   ```bash
   python AutopilotService.py
   ```
3. Lanza el dashboard:
   ```bash
   python DashboardV2.py
   ```
4. En la interfaz, selecciona **Global** y pulsa **Iniciar**.
5. Los comandos se envían por MQTT y la telemetría se recibe automáticamente.

> **Nota:** Los dashboards anteriores (`DashboardLocalPython.py`, `DashboardLocalConVideoStream.py`, `DashboardLocalConDeteccion.py`, `DashboardGlobalPython.py`) siguen funcionando sin cambios.

---

## Implementación de funcionalidades extra
Para la versión de python nuevas funcionalidades han sido añadidas, incluyendo botones y datos de telemetría. 

Nuevos Botones: 
- Girar "clockwise" y "counterclockwise" 90º.
- Desarmar.

Nuevos datos de telemetría:
- Velocidad.
- Latitud y longitud.
- Modo de Vuelo.

Nuevas funcionalidades:
- Ir a posición [lat, lon].
- Ir a altura [alt].

Para la versión de C# se ha implementado un botón nuevo que permite poner el dron en modo guiado.

En el reconocimiento de objetos se ha implementado el reconocimiento de teléfonos móviles, perros y paraguas. Además, se ha establecido el procesamiento de 1 de cada 25 frames para encontrar un equilibrio entre fluidez de la cámara y la velocidad de detección del objeto.
