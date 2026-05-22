# prueba4.py - Sistema de Seguimiento Leader-Follower con Visión

## Requisitos
- 2 drones SITL ejecutándose (ver sección "Lanzar SITL")
- Modelo YOLO entrenado (opcional, si no está, GUI funciona sin visión)
- Python 3.8+ con dependencias: `dronLink`, `pymavlink`, `ultralytics`, `opencv-python`, `tkinter`

## Lanzar SITL (2 instancias)

**Importante:** Debes tener ArduPilot instalado. Si no está en la ruta exacta, ajusta el path.

**Terminal 1 - Leader (puerto UDP 14551):**
```bash
cd C:\ruta\a\ardupilot\ArduCopter
python .\Tools\autotest\sim_vehicle.py -v ArduCopter -f quad --console --map --out=udp:127.0.0.1:14551
```

**Terminal 2 - Follower (puerto UDP 14561):**
```bash
cd C:\ruta\a\ardupilot\ArduCopter
python .\Tools\autotest\sim_vehicle.py -v ArduCopter -f quad --console --map --out=udp:127.0.0.1:14561 --instance 1
```

## Ejecutar prueba4.py

Desde la raíz del proyecto (PD-grup-4):

```bash
python "Versión 3 y 4\prueba4.py"
```

## Flujo de uso en GUI

1. **Conectar drones**
   - Botón: "Conectar ambos"
   - Espera a que aparezca "Conexion: lista" en la GUI
   - Verás en terminal: `✓ Lider conectado.` y `✓ Seguidor conectado.`

2. **Activar telemetría**
   - Botón: "Activar telemetria"
   - Verás en terminal: `Telemetria activada.`

3. **Verificar telemetría recibida**
   - El script espera recibir posición GPS de ambos drones
   - Verás en terminal: `Telemetria recibida. Listo para armar y despegar.`

4. **Armar y despegar**
   - Adjust "Altitud despegue" si necesitas otro valor (default: 5.0m)
   - Botón: "Armar y despegar"
   - Espera a que en terminal aparezca:
     ```
     ✓ Lider armado.
     ✓ Seguidor armado.
     ✓ Lider despegó a 4.5m
     ✓ Seguidor despegó a 4.5m
     ✓ Ambos drones en vuelo.
     ```

5. **Activar seguimiento**
   - Botón: "Activar seguimiento"
   - El follower se calibra y comienza a seguir al leader
   - Verás en terminal: `Iniciando secuencia de seguimiento...`

6. **Ajustar PIDs (opcional)**
   - Deslizadores para Kp, Ki, Kd de X/Y (posición horizontal)
   - Deslizadores para Kp, Ki, Kd de Z (altitud)
   - Ajusta en tiempo real mientras el dron vuela

7. **Parar**
   - Botón: "Parar seguimiento"
   - El follower se detiene y desactiva la visión

## Parámetros CLI

```bash
python "Versión 3 y 4\prueba4.py" --help
```

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `--model` | `./Entrenamiento_Red_Neuronal/runs/dron_yolov8n/weights/best.pt` | Ruta al modelo YOLO |
| `--source` | `0` | Fuente de video (0=webcam, o URL HTTP) |
| `--conf` | `0.5` | Confianza mínima para detecciones |
| `--fov-x` | `78.0` | Field of View horizontal (grados) |
| `--dry-run` | (flag) | Solo valida config, no ejecuta |

Ejemplo con parámetros:
```bash
python "Versión 3 y 4\prueba4.py" --source "http://192.168.1.100:8080/video" --conf 0.7 --fov-x 90
```

Validar configuración:
```bash
python "Versión 3 y 4\prueba4.py" --dry-run
```

## Arquitectura

### Threads
- **GUI (Tkinter)**: Controles, botones, sliders (thread principal)
- **Vision (YOLO)**: Detección de drones, control de yaw (thread daemon)
- **Control (Main)**: PID de posición, seguimiento leader-follower (thread principal después de GUI)

### Conexiones
- **Leader**: UDP 127.0.0.1:14551 (9600 baud emulado)
- **Follower**: UDP 127.0.0.1:14561 (9600 baud emulado)

### Control
- **Posición (X/Y/Z)**: PID independientes
- **Yaw**: Control por visión (si modelo disponible) o manual

## Solución de problemas

### "No se pudo abrir la fuente de video"
- Webcam desconectada o no disponible
- Si usas URL, verifica que sea accesible

### "Timeout esperando a que despegue"
- SITL no recibe comando de despegue
- Verifica que los puertos SITL estén activos
- Reinicia SITL

### Drones conectan pero no reciben telemetría
- Verifica que SITL esté enviando `--out=udp:127.0.0.1:14551`
- Prueba con Mission Planner en el mismo puerto

### GUI abre pero botones no responden
- Verifica que no hay excepción en terminal
- Presiona botones de nuevo (pueden estar en thread)

## Notas

- **Sin modelo**: La visión está desactivada pero el control por seguimiento de posición funciona.
- **Falsos positivos IDE**: Las advertencias sobre métodos de `Dron` son normales (métodos dinámicos inyectados).
- **Modo bloqueante**: `takeOff()` ahora espera a que se alcance el 90% de la altura objetivo.
- **Telemetría**: Requiere GPS lock. En SITL se inicializa automáticamente.


