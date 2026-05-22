# prueba3.py - Seguimiento Leader-Follower con Detección Visual YOLO

## Descripción

`prueba3.py` es una versión mejorada del seguimiento leader-follower que integra:
- **Seguimiento por GPS**: El follower sigue los movimientos del líder
- **Heading hacia líder**: El follower siempre apunta su cámara/heading hacia el líder
- **Detección visual YOLO**: Ajusta el heading mediante detección de drones por cámara en tiempo real

## Requisitos

- 2 drones SITL ejecutándose
- Python 3.8+ con:
  - `pymavlink`
  - `dronLink` (módulo local)
  - `tkinter`
  - `cv2` (OpenCV)
  - `ultralytics` (YOLO)

## Lanzar SITL (2 instancias)

**Terminal 1 - Leader (UDP 14551):**
```bash
cd C:\ruta\a\ardupilot\ArduCopter
python .\Tools\autotest\sim_vehicle.py -v ArduCopter -f quad --console --map --out=udp:127.0.0.1:14551
```

**Terminal 2 - Follower (UDP 14561):**
```bash
cd C:\ruta\a\ardupilot\ArduCopter
python .\Tools\autotest\sim_vehicle.py -v ArduCopter -f quad --console --map --out=udp:127.0.0.1:14561 --instance 1
```

## Ejecutar prueba3.py

```bash
python "Versión 3 y 4\prueba3.py"
```

## Flujo de Uso

### 1. Conectar Drones
- Botón: "Conectar ambos"
- Espera a que apareezca "Conexión: lista"

### 2. Activar Telemetría
- Botón: "Activar telemetría"
- Espera a mensaje: `Telemetría recibida. Listo para armar y despegar.`

### 3. Armar y Despegar
- Ajusta "Altitud despegue" si lo necesitas (default: 5.0m)
- Botón: "Armar y Despegar"
- Espera a que ambos drones alcancen la altitud

### 4. Activar Seguimiento
- Botón: "Activar seguimiento"
- El follower se calibra y comienza a seguir
- La cámara detecta el dron y ajusta el heading

### 5. Ajustar PIDs (opcional)
- Deslizadores para Kp, Ki, Kd de X/Y (posición)
- Deslizadores para Kp, Ki, Kd de Z (altitud)

### 6. Parar
- Botón: "Parar seguimiento"

## Funcionalidades Integradas

### Seguimiento GPS
- PID de 3 ejes (N/E/Z)
- Offset geográfico entre drones
- Tolerancia de 1m

### Heading Hacia Líder (Primario)
- Cálculo del ángulo usando `atan2`
- Apunta siempre hacia la posición del líder

### Detección Visual YOLO (Secundaria)
- Ejecuta en thread separado
- Detecta drones en tiempo real
- Ajusta el heading **incrementalmente** basado en la posición del dron en la imagen
- **Deadzone**: 2° (evita ajustes innecesarios)
- **Cooldown**: 0.5s entre ajustes
- **Max step**: 20° por comando

### Debug en Terminal
```
Disp líder: N=2.50 E=1.20 | Error: N=0.50 E=-0.30 | Vels: N=0.10 E=-0.06 | Yaw: 45.2° | 📷 Dron detectado
```

Útil para verificar:
- Desplazamientos del líder
- Errores de posición
- Velocidades generadas
- Ángulo del heading
- Estado de la detección visual (`📷 Dron detectado` o `📷 --`)

## Configuración YOLO

En el código (líneas ~42-49):
```python
MODEL_PATH = "./Entrenamiento_Red_Neuronal/runs/dron_yolov8n/weights/best.pt"
VIDEO_SOURCE = "0"  # 0 = webcam, o URL (ej: "http://192.168.1.100:8080/video")
CONFIDENCE = 0.5    # Confianza mínima
FOV_X_DEG = 78.0    # Field of view horizontal (ajusta según tu cámara)
```

## Solución de Problemas

### "Error cargando modelo YOLO"
- Verifica que `best.pt` existe en:
  - `Entrenamiento_Red_Neuronal/runs/dron_yolov8n/weights/best.pt`
- O pasa la ruta correcta modificando `MODEL_PATH`

### "No se pudo abrir la fuente de video"
- Verifica que la webcam está disponible
- Si usas URL, verifica conectividad

### Drones se arman pero no despegan
- Verifica SITL está corriendo en los puertos correctos (14551/14561)
- Reinicia SITL

### Heading no se mueve
- Verifica telemetría está activada
- Verifica que `follower_telemetry` recibe datos de "heading"

## Notas de Diseño

### Por qué dos métodos de heading
1. **GPS-based**: Fiable, preciso, siempre activo
2. **Vision-based**: Complementario, solo si detecta dron, evita oclusiones

El sistema prioriza GPS pero ajusta incrementalmente si hay detección visual.

### Thread Safety
- `detected_yaw_error`: Protegido por `vision_lock`
- `leader/follower_telemetry`: Updates desde callbacks
- `follow_enabled`: Event para sincronización

### Performance
- Vision loop: Independiente (no bloquea control)
- Control loop: 20 Hz (50ms)
- GUI: Actualiza status cada 500ms


