# Sistema Avanzado de Seguimiento Autónomo de Drones (Leader-Follower)

Un sistema de control avanzado en Python que implementa una arquitectura **Líder-Seguidor** (Leader-Follower) combinando **Telemetría GPS**, un **Controlador PID de 3 Ejes** y **Visión Artificial (YOLOv8)** en tiempo real. 

El dron seguidor replica de forma autónoma la trayectoria del dron líder en el espacio 3D, manteniendo una distancia (*offset*) constante. Simultáneamente, emplea un hilo de visión por computadora para detectar físicamente al dron líder mediante su cámara a bordo, visualizándolo en una interfaz gráfica integrada.

---

## ✨ Características Principales

*   **Arquitectura Multithreading Real-Time:** Diseño concurrente sin bloqueos que procesa telemetría a 20Hz, Inferencia YOLO a ~30FPS y una Interfaz Gráfica de Usuario (GUI) de forma simultánea.
*   **Control Posicional Autónomo (PID):**
    *   **Eje Norte (Y):** Control predictivo del seguimiento longitudinal.
    *   **Eje Este (X):** Control del seguimiento lateral.
    *   **Altitud (Z):** Mantenimiento estricto del gradiente vertical relativo para evasión de colisiones.
    *   *Anti-Windup y Filtro Pasa-bajos (Alpha) implementados*.
*   **Control de Orientación Dinámico (Yaw):** El dron calcula dinámicamente mediante trigonometría el ángulo de cabeceo (*Yaw*) necesario para mantener su "mirada" siempre fija hacia las coordenadas del líder.
*   **Detección Visual (Inteligencia Artificial):** Integración nativa de Ultralytics YOLOv8. Captura el vídeo de la cámara, clasifica al dron líder y proyecta los metadatos directamente en el panel de control.
*   **Interfaz de Ajuste Rápido (GUI):** UI desarrollada en *Tkinter* que embebe la vista de la cámara y permite afinar ('tuning') de los coeficientes Kp, Ki y Kd en pleno vuelo, así como comandos rápidos de Armado/Despegue.

---

## 🛠️ Requisitos del Sistema

*   **Python:** 3.9 o superior.
*   **Simulador / Hardware:** 
    *   Entorno SITL (ArduPilot) o hardware real que soporte el protocolo MAVLink.
*   **Cámara:** Webcam conectada, flux IP, o dispositivo virtual (configurable en el script).

### Dependencias de Python
Instala las dependencias necesarias a través de `pip`:

```bash
pip install pymavlink opencv-python pillow ultralytics
```
*(Nota: El archivo depende estructuralmente del módulo `dronLink` personalizado incluido en el repositorio).*

---

## 🚀 Arquitectura y Conexión de Puertos

Estructurado de fábrica para interceptar y gestionar dos instancias SITL conjuntas:

*   **Dron Líder (Leader):** `udp:127.0.0.1:14561`
*   **Dron Seguidor (Follower):** `udp:127.0.0.1:14551`
*   **Baudrate base:** `57600`
*   **Conexión de Cámara Dron Seguidor:** Canal de Vídeo OpenCV (Defecto: Puerto local `0`).

---

## 💻 Instrucciones de Uso

1.  **Levantar Simulación (SITL):** 
    Inicializa dos instancias de ArduPilot SITL en tu terminal apuntando a los puertos estipulados en la configuración.
2.  **Carga del Modelo YOLO:**
    Asegúrate de que el path de `YOLO_MODEL_PATH` apunte a tu modelo de red neuronal entrenado (`best.pt`).
3.  **Ejecutar el Controlador:**
    ```bash
    python "SeguimientoDron V2.py"
    ```
4.  **Uso de la Interfaz:**
    1.  Pulsa **Conectar Ambos** y espera el flag visual de conexión exitosa.
    2.  Pulsa **Activar telemetría** para iniciar los *listeners* asíncronos.
    3.  Ajusta la "Altitud despegue" en el Slider.
    4.  Pulsa **Armar y Despegar**, ambos drones elevarán vuelo coordinadamente.
    5.  Por último, haz clic en **Activar seguimiento**. El dron seguidor se posicionará e interceptará el control hacia el dron líder en el espacio tridimensional.

---

## 🛡️ Mecanismos de Seguridad "Failsafe" incorporados

El sistema posee auditoría interna para prevenir fly-aways (fugas) o caídas en la vida real:

*   **Bloqueo de Velocidad Integral:** Los comandos MAVLink están acotados por hardware a máximos estrictos (ej. 3.0 m/s longitudinal, 1.0 m/s vertical).
*   **Detección de Aterrizaje del Líder:** Si el dron principal disminuye su umbral de altura o entra en modo `LAND`/`RTL`, el seguidor abortará la ruta y aplicará aterrizaje de inmediato.
*   **TimeOut de Telemetría:** Cese inmediato del control vectorial si la latencia del paquete MAVLink del Líder supera el umbral de desconexión (MAX_TELEMETRY_AGE).
