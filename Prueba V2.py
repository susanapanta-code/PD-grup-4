"""
DashboardV2.py - Dashboard unificado (version 2)

Integra:
  - Servicio de autopiloto (modo Local o modo Global)
  - Servicio de camara (WebRTC, receptor local)

Modo LOCAL  -> comandos directos al dron a traves de dronLink (Dron)
Modo GLOBAL -> comandos publicados via MQTT al AutopilotService
"""

import atexit
import asyncio
import concurrent.futures
import json
import math
import threading
import tkinter as tk
from tkinter import messagebox
import os
import subprocess
import sys
import time
import uuid
import tempfile
import socket

from typing import Optional, Tuple

import cv2
from aiortc import MediaStreamTrack, RTCPeerConnection
from aiortc.contrib.signaling import TcpSocketSignaling
from pymavlink import mavutil

try:
    import torch
except ImportError:
    torch = None

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from dronLink.Dron import Dron

try:
    import tkintermapview
except ImportError:
    tkintermapview = None


# ============================================================================
# CONSTANTES
# ============================================================================

COLOR_DISPONIBLE = "dark orange"
COLOR_NO_DISPONIBLE = "#4682B4"
COLOR_EN_PROCESO = "yellow"
COLOR_ACTIVO = "green"
COLOR_STOP = "red"
FG_NORMAL = "black"
FG_ACTIVO = "white"
FG_NO_DISPONIBLE = "#D0D0D0"

# Broker MQTT (modo Global)
BROKER_ADDRESS = "dronseetac.upc.edu"
BROKER_PORT = 8000
BROKER_USER = "dronsEETAC"
BROKER_PASS = "mimara1456."
MQTT_CLIENT_ID = "InterfazGlobalV2"
MQTT_ORIGIN_PREFIX = "interfazGlobalV2"
MQTT_SERVICE_NAME = "autopilotService04"
# Conexion local por defecto (modo Local)
LOCAL_CONNECTION_STRING = "tcp:127.0.0.1:5763"
LOCAL_BAUD = 115200

# WebRTC - servicio de camara (CameraService.py actua como servidor)
CAMERA_SERVER_IP = "localhost"
CAMERA_SERVER_PORT = 9999
CAMERA_SERVER_IP_LOCAL = "127.0.0.1"
CAMERA_MAX_SESSION_S = 3600
CAMERA_CONNECT_RETRIES = 6
CAMERA_RETRY_WAIT_S = 1.0

MODE_LOCAL = "local"
MODE_GLOBAL = "global"

MAP_DEFAULT_LAT = 41.3874
MAP_DEFAULT_LON = 2.1686
MAP_DEFAULT_ZOOM = 16
MAP_RECENTER_INTERVAL_S = 2.5
MAP_MARKER_MIN_INTERVAL_S = 0.5
MAP_MARKER_MIN_MOVE_M = 0.5

DETECTION_INFER_EVERY_N_FRAMES = 12
DETECTION_MIN_CONF = 0.35
COCO_DETECTION_SUBSET = [
    "person",
    "car",
    "bicycle",
    "dog",
    "cat",
    "bottle",
    "cell phone",
    "backpack",
]

LOCAL_INSTANCE_LOCK_PATH = os.path.join(tempfile.gettempdir(), "dashboard_v2_local.lock")
AUTOPILOT_SERVICE_LOCK_PATH = os.path.join(tempfile.gettempdir(), "dashboard_v2_autopilot.lock")
CAMERA_SERVICE_LOCK_PATH = os.path.join(tempfile.gettempdir(), "dashboard_v2_camera.lock")
# Descriptor del lock de instancia Local (solo una instancia local permitida).
_local_lock_fd = None


def _pid_alive(pid):
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # En Windows puede pasar con procesos de otro usuario; lo consideramos vivo.
        return True
    except OSError:
        return False
    return True


def _read_lock_pid(lock_path):
    try:
        with open(lock_path, "r", encoding="ascii", errors="ignore") as fh:
            raw = fh.read().strip()
        return int(raw) if raw else None
    except Exception:
        return None


def _acquire_pid_lock(lock_path):
    """Intenta adquirir lock exclusivo; si esta huerfano, lo recupera."""
    for _ in range(2):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
            return True, fd, False
        except FileExistsError:
            owner_pid = _read_lock_pid(lock_path)
            if owner_pid is not None and _pid_alive(owner_pid):
                return False, None, False
            try:
                os.unlink(lock_path)
                continue
            except Exception:
                return False, None, False
    return False, None, True


def _release_pid_lock(fd, lock_path):
    if fd is not None:
        try:
            os.close(fd)
        except Exception:
            pass
    try:
        if os.path.exists(lock_path):
            os.unlink(lock_path)
    except Exception:
        pass


class CameraServiceManager:
    """Gestiona CameraService.py como proceso hijo del dashboard."""

    def __init__(self, status_cb=None):
        self._proc = None
        self._status_cb = status_cb
        self._lock_fd = None
        self._owns_service = False

    def _status(self, msg):
        if self._status_cb:
            self._status_cb(msg)
        print(msg)

    @property
    def owns_service(self):
        return self._owns_service

    @property
    def is_running(self):
        return bool(self._proc and self._proc.poll() is None)

    def _acquire_service_lock(self):
        if self._lock_fd is not None:
            return True
        ok, fd, recovered = _acquire_pid_lock(CAMERA_SERVICE_LOCK_PATH)
        if ok:
            self._lock_fd = fd
            if recovered:
                self._status("[CamaraService] Lock huerfano recuperado")
            return True
        return False

    def _release_service_lock(self):
        if self._lock_fd is None:
            return
        _release_pid_lock(self._lock_fd, CAMERA_SERVICE_LOCK_PATH)
        self._lock_fd = None

    def start(self):
        if self.is_running:
            self._status("[CamaraService] Ya activo")
            return True

        # Si otra instancia ya lo levanto, se reutiliza.
        if not self._acquire_service_lock():
            self._owns_service = False
            self._status("[CamaraService] Ya activo en otra instancia; reutilizando.")
            return True

        script_path = os.path.join(os.path.dirname(__file__), "CameraService.py")
        if not os.path.exists(script_path):
            self._status("[CamaraService] No se encuentra CameraService.py")
            self._release_service_lock()
            return False

        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            self._proc = subprocess.Popen(
                [sys.executable, script_path],
                # Modificado para redirigir trazas a stdout/stderr del proceso padre
                # para poder diagnosticar errores (ej. WinError 1225)
                # stdout=subprocess.DEVNULL,
                # stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            # Si el proceso cae nada mas arrancar, lo detectamos aqui.
            time.sleep(0.5)
            if self._proc.poll() is not None:
                code = self._proc.returncode
                self._status(f"[CamaraService] Se cerro al iniciar (codigo {code}).")
                self._proc = None
                self._owns_service = False
                self._release_service_lock()
                return False

            self._owns_service = True
            self._status("[CamaraService] Iniciado")
            return True
        except Exception as exc:
            self._status(f"[CamaraService] Error al iniciar: {exc}")
            self._owns_service = False
            self._release_service_lock()
            return False

    def stop(self):
        if not self._owns_service:
            return
        if not self.is_running:
            self._release_service_lock()
            self._owns_service = False
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=3)
            self._status("[CamaraService] Detenido")
        except Exception:
            try:
                self._proc.kill()
                self._proc.wait(timeout=2)
            except Exception:
                pass
        finally:
            self._proc = None
            self._owns_service = False
            self._release_service_lock()


class AutopilotServiceManager:
    """Gestiona AutopilotService.py como proceso hijo del dashboard."""

    def __init__(self, status_cb=None):
        self._proc = None
        self._status_cb = status_cb
        self._lock_fd = None
        self._owns_service = False

    def _status(self, msg):
        if self._status_cb:
            self._status_cb(msg)
        print(msg)

    @property
    def is_running(self):
        return bool(self._proc and self._proc.poll() is None)

    @property
    def owns_service(self):
        return self._owns_service

    def _acquire_service_lock(self):
        if self._lock_fd is not None:
            return True
        ok, fd, recovered = _acquire_pid_lock(AUTOPILOT_SERVICE_LOCK_PATH)
        if ok:
            self._lock_fd = fd
            if recovered:
                self._status("[AutopilotService] Lock huerfano recuperado")
            return True
        return False

    def _release_service_lock(self):
        if self._lock_fd is None:
            return
        _release_pid_lock(self._lock_fd, AUTOPILOT_SERVICE_LOCK_PATH)
        self._lock_fd = None

    def start(self, show_console=False):
        if self.is_running:
            self._status("[AutopilotService] Ya activo")
            return True

        # Si otra instancia ya levanto el servicio, lo reutilizamos.
        if not self._acquire_service_lock():
            self._owns_service = False
            self._status("[AutopilotService] Ya activo en otra instancia; reutilizando.")
            return True

        script_path = os.path.join(os.path.dirname(__file__), "AutopilotService.py")
        if not os.path.exists(script_path):
            self._status("[AutopilotService] No se encuentra AutopilotService.py")
            self._release_service_lock()
            return False

        try:
            creationflags = 0
            stdout = subprocess.DEVNULL
            stderr = subprocess.DEVNULL

            if os.name == "nt":
                if show_console:
                    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                    stdout = None
                    stderr = None
                else:
                    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            self._proc = subprocess.Popen(
                [sys.executable, script_path],
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
            )
            time.sleep(0.6)
            if self._proc.poll() is not None:
                code = self._proc.returncode
                self._status(f"[AutopilotService] Se cerro al iniciar (codigo {code}).")
                self._proc = None
                self._owns_service = False
                self._release_service_lock()
                return False

            self._owns_service = True
            if show_console:
                self._status("[AutopilotService] Iniciado (consola visible)")
            else:
                self._status("[AutopilotService] Iniciado")
            return True
        except Exception as exc:
            self._status(f"[AutopilotService] Error al iniciar: {exc}")
            self._owns_service = False
            self._release_service_lock()
            return False

    def stop(self):
        if not self._owns_service:
            return
        if not self.is_running:
            self._release_service_lock()
            self._owns_service = False
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=3)
            self._status("[AutopilotService] Detenido")
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        finally:
            self._proc = None
            self._owns_service = False
            self._release_service_lock()


# ============================================================================
# CONTROLADORES
# ============================================================================

class LocalController:
    """Controla el dron directamente a traves de dronLink."""

    def __init__(self):
        self.dron = Dron()
        # Inicializar propiedades que dronLink no define explicitamente en __init__ para evitar AttributeError al pedir telemetria antes de que se establezcan
        if not hasattr(self.dron, 'heading'):
            self.dron.heading = 0
        if not hasattr(self.dron, 'flightMode'):
            self.dron.flightMode = "--"

    def connect(self):
        return self.dron.connect(LOCAL_CONNECTION_STRING, LOCAL_BAUD, freq=10)

    def disconnect(self):
        return self.dron.disconnect()

    def arm(self, callback=None, error_callback=None):
        return self.dron.arm(blocking=False, callback=callback, error_callback=error_callback)

    def disarm(self):
        # dronLink no expone disarm directo; se envia MAV_CMD_COMPONENT_ARM_DISARM.
        if not getattr(self.dron, "vehicle", None):
            return False
        self.dron.vehicle.mav.command_long_send(
            self.dron.vehicle.target_system,
            self.dron.vehicle.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        self.dron.state = "connected"
        return True

    def takeoff(self, alt=5, callback=None):
        return self.dron.takeOff(int(alt), blocking=False, callback=callback)

    def land(self, callback=None):
        return self.dron.Land(blocking=False, callback=callback)

    def rtl(self, callback=None):
        return self.dron.RTL(blocking=False, callback=callback)

    def go(self, direction):
        return self.dron.go(direction)

    def start_telemetry(self, callback):
        return self.dron.send_telemetry_info(callback)

    def stop_telemetry(self):
        return self.dron.stop_sending_telemetry_info()

    def change_heading(self, degrees):
        return self.dron.changeHeading(int(degrees), blocking=False)

    def change_nav_speed(self, speed):
        return self.dron.changeNavSpeed(float(speed))

    def rotate(self, offset, direction="cw", callback=None):
        return self.dron.rotate(offset, direction=direction, blocking=False, callback=callback)

    def change_altitude(self, altitude, callback=None):
        return self.dron.change_altitude(int(altitude), blocking=False, callback=callback)

    def goto(self, lat, lon, callback=None):
        return self.dron.goto(float(lat), float(lon), blocking=False, callback=callback)

    @property
    def state(self):
        return self.dron.state


class GlobalController:
    """Controla el dron publicando comandos MQTT al AutopilotService."""

    def __init__(self, on_message_cb, on_connect_cb):
        self.origin = f"{MQTT_ORIGIN_PREFIX}-{uuid.uuid4().hex[:8]}"
        client_id = f"{MQTT_CLIENT_ID}-{uuid.uuid4().hex[:8]}"
        self.topic_send = f"{self.origin}/{MQTT_SERVICE_NAME}"
        self.topic_recv = f"{MQTT_SERVICE_NAME}/{self.origin}/#"

        self._connected_event = threading.Event()
        self._client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id,
            transport="websockets",
        )
        self._client.ws_set_options(path="/mqtt")
        self._client.username_pw_set(BROKER_USER, BROKER_PASS)
        self._client.on_message = on_message_cb
        self._client.on_connect = on_connect_cb
        self._client.on_disconnect = self._on_disconnect
        self._client.connect(BROKER_ADDRESS, BROKER_PORT)
        self._client.subscribe(self.topic_recv)
        self._client.loop_start()

        print(f"[MQTT] Instancia Global origin={self.origin}")
        print(f"[MQTT] Publica en: {self.topic_send}/<comando>")
        print(f"[MQTT] Escucha en: {self.topic_recv}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self._connected_event.clear()
        print(f"[MQTT] Desconectado del broker: {reason_code}")

    def mark_connected(self):
        self._connected_event.set()

    def _pub(self, command, payload=None):
        # Espera breve a que el cliente MQTT este realmente conectado.
        if not self._connected_event.wait(timeout=2.0):
            print(f"[MQTT] Broker no listo para comando '{command}'")
            return False

        topic = f"{self.topic_send}/{command}"
        payload_to_send = None if payload is None else str(payload)
        print(f"[MQTT] -> topic={topic} payload={payload_to_send}")

        if payload_to_send is not None:
            self._client.publish(topic, payload_to_send, qos=1)
        else:
            self._client.publish(topic, qos=1)
        return True

    def connect(self):
        return self._pub("connect")

    def arm(self):
        return self._pub("arm")

    def disarm(self):
        return self._pub("disarm")

    def takeoff(self, alt=5):
        return self._pub("takeOff", alt)

    def land(self):
        return self._pub("Land")

    def rtl(self):
        return self._pub("RTL")

    def go(self, direction):
        return self._pub("go", direction)

    def start_telemetry(self):
        return self._pub("startTelemetry")

    def stop_telemetry(self):
        return self._pub("stopTelemetry")

    def change_heading(self, degrees):
        return self._pub("changeHeading", int(degrees))

    def change_nav_speed(self, speed):
        return self._pub("changeNavSpeed", float(speed))

    def rotate(self, offset, direction="cw"):
        return self._pub("rotate", f"{direction}:{int(offset)}")

    def change_altitude(self, altitude):
        return self._pub("changeAltitude", int(altitude))

    def goto(self, lat, lon, speed=None):
        payload = {"lat": float(lat), "lon": float(lon)}
        if speed is not None:
            payload["speed"] = float(speed)
        return self._pub("goto", json.dumps(payload))

    def disconnect(self):
        self._connected_event.clear()
        self._client.loop_stop()
        self._client.disconnect()


# ============================================================================
# CAMARA WEBRTC
# ============================================================================

class _ObjectDetector:
    """Detector YOLOv5 con carga diferida para minimizar coste si no se usa."""

    def __init__(self, status_cb=None):
        self._status_cb = status_cb
        self._model = None
        self._model_lock = threading.Lock()
        self._load_error = None
        self._preload_started = False

    def preload_async(self):
        if self._preload_started:
            return
        self._preload_started = True
        threading.Thread(target=self._ensure_model, daemon=True, name="ObjectDetectorPreload").start()

    def _status(self, msg):
        if self._status_cb:
            self._status_cb(msg)
        print(msg)

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        if self._load_error is not None:
            return None
        if torch is None:
            self._load_error = "Falta dependencia 'torch'."
            self._status("[Deteccion] torch no disponible; deteccion desactivada.")
            return None

        with self._model_lock:
            if self._model is not None:
                return self._model
            if self._load_error is not None:
                return None
            try:
                weights_path = os.path.join(os.path.dirname(__file__), "yolov5s.pt")
                if os.path.exists(weights_path):
                    model = torch.hub.load(
                        "ultralytics/yolov5",
                        "custom",
                        path=weights_path,
                        force_reload=False,
                        verbose=False,
                    )
                else:
                    model = torch.hub.load(
                        "ultralytics/yolov5",
                        "yolov5s",
                        pretrained=True,
                        force_reload=False,
                        verbose=False,
                    )
                model.conf = DETECTION_MIN_CONF
                model.eval()
                self._model = model
                self._status("[Deteccion] Modelo YOLOv5 listo.")
            except Exception as exc:
                self._load_error = str(exc)
                self._status(f"[Deteccion] No se pudo cargar YOLOv5: {exc}")
                return None
        return self._model

    def detect(self, frame_bgr, requested_labels):
        if not requested_labels:
            return []
        model = self._ensure_model()
        if model is None:
            return []

        try:
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = model(frame_rgb)
            names = model.names
            detections = []
            for det in results.xyxy[0].tolist():
                x1, y1, x2, y2, conf, cls_idx = det
                cls_name = names.get(int(cls_idx), str(int(cls_idx))) if isinstance(names, dict) else names[int(cls_idx)]
                if cls_name not in requested_labels:
                    continue
                detections.append((cls_name, float(conf), int(x1), int(y1), int(x2), int(y2)))
            return detections
        except Exception as exc:
            self._status(f"[Deteccion] Error inferencia: {exc}")
            return []


class _VideoReceiver:
    """Recibe y muestra el stream de video WebRTC enviado por CameraService.py."""

    def __init__(self, stop_event, detector=None, selected_labels_cb=None):
        self.stop_event = stop_event
        self._detector = detector
        self._selected_labels_cb = selected_labels_cb
        self._frame_idx = 0
        self._last_detections = []
        self._detector_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="Detector")
        self._pending_detection = None

    def _collect_detection_result_if_ready(self):
        if self._pending_detection and self._pending_detection.done():
            try:
                self._last_detections = self._pending_detection.result(timeout=0)
            except Exception as exc:
                print(f"[Deteccion] Fallo en worker: {exc}")
                self._last_detections = []
            finally:
                self._pending_detection = None

    def _submit_detection_if_needed(self, frame_bgr, requested):
        if not self._detector or not requested:
            return
        if self._pending_detection is not None:
            return
        if self._frame_idx % DETECTION_INFER_EVERY_N_FRAMES != 0:
            return
        # Copia del frame para inferencia fuera del loop de recepcion.
        frame_copy = frame_bgr.copy()
        labels = set(requested)
        self._pending_detection = self._detector_executor.submit(self._detector.detect, frame_copy, labels)

    async def handle_track(self, track):
        try:
            while not self.stop_event.is_set():
                try:
                    frame = await asyncio.wait_for(track.recv(), timeout=5.0)
                    frame = frame.to_ndarray(format="bgr24")

                    self._frame_idx += 1
                    requested = set()
                    if self._selected_labels_cb:
                        requested = self._selected_labels_cb()

                    self._collect_detection_result_if_ready()

                    if requested:
                        self._submit_detection_if_needed(frame, requested)
                        for cls_name, conf, x1, y1, x2, y2 in self._last_detections:
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
                            cv2.putText(
                                frame,
                                f"{cls_name} {conf:.2f}",
                                (x1, max(18, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                (0, 220, 0),
                                2,
                            )
                    else:
                        self._last_detections = []

                    cv2.imshow("Camara Dashboard V2 [Q para cerrar]", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        self.stop_event.set()
                        break
                except asyncio.TimeoutError:
                    print("[Camara] Timeout esperando frame")
                except Exception as exc:
                    print(f"[Camara] Error en track: {exc}")
                    break
        finally:
            try:
                self._detector_executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass


def _camera_host():
    # En modo local forzamos IPv4 para evitar conflictos localhost (::1 vs 127.0.0.1).
    if _es_local():
        return CAMERA_SERVER_IP_LOCAL
    # Si estamos en global pero la IP es localhost, tambien forzamos IPv4.
    if CAMERA_SERVER_IP in ("localhost", "0.0.0.0", "127.0.0.1"):
        return CAMERA_SERVER_IP_LOCAL
    return CAMERA_SERVER_IP


def _is_port_open(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect((host, port))
        s.close()
        return True
    except:
        return False


async def _wait_camera_service(stop_event, status_cb=None):
    """Espera breve a que CameraService quede operativo antes de negociar WebRTC."""
    if status_cb:
        status_cb("[Camara] Preparando servicio de camara...")

    target_host = _camera_host()

    # Si el target es localhost, esperamos que el proceso levante.
    # En un escenario global real (IP remota), asumimos que ya está activo o esperamos conexión.
    waited = 0.0
    while waited < 8.0 and not stop_event.is_set():
        # Verificamos si el proceso local (si aplica) sigue vivo
        if camera_service_manager is not None and camera_service_manager.owns_service:
            if not camera_service_manager.is_running:
                if status_cb:
                    status_cb("[Camara] El servicio local se ha detenido inesperadamente.")
                return False

        # Intentamos conectar al puerto TCP para ver si ya escucha
        if _is_port_open(target_host, CAMERA_SERVER_PORT):
            return True

        await asyncio.sleep(0.5)
        waited += 0.5

    return False


async def _camera_receiver_task(stop_event, status_cb=None):
    host = _camera_host()
    last_error = None

    def _status(msg):
        if status_cb:
            status_cb(msg)
        print(msg)

    # Reutilizamos el helper de espera para evitar iniciar la negociacion demasiado pronto.
    # Ahora esperamos siempre si estamos actuando de servidor local (local o global con ip local).
    await _wait_camera_service(stop_event, status_cb=_status)

    for intento in range(1, CAMERA_CONNECT_RETRIES + 1):
        signaling = TcpSocketSignaling(host, CAMERA_SERVER_PORT)
        pc = RTCPeerConnection()
        video_receiver = _VideoReceiver(
            stop_event,
            detector=object_detector,
            selected_labels_cb=_get_selected_detection_labels,
        )
        track_task = None

        @pc.on("track")
        def on_track(track):
            nonlocal track_task
            if isinstance(track, MediaStreamTrack):
                _status("[Camara] Track de video recibido")
                track_task = asyncio.ensure_future(video_receiver.handle_track(track))

        try:
            if intento == 1:
                _status("[Camara] Conectando al CameraService...")
            else:
                _status("[Camara] Reintentando conexion de camara...")

            await signaling.connect()
            _status("[Camara] Esperando oferta WebRTC...")
            offer = await asyncio.wait_for(signaling.receive(), timeout=10.0)

            # Si llega None (o algo invalido), repetimos la conexion completa.
            if offer is None or getattr(offer, "type", None) is None:
                raise RuntimeError("Oferta WebRTC invalida (None)")

            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await signaling.send(pc.localDescription)

            while pc.connectionState != "connected" and not stop_event.is_set():
                await asyncio.sleep(0.1)

            if stop_event.is_set():
                return

            if pc.connectionState == "connected":
                _status("[Camara] Streaming activo")

            elapsed = 0
            while not stop_event.is_set() and elapsed < CAMERA_MAX_SESSION_S:
                await asyncio.sleep(0.2)
                elapsed += 0.2

            _status("[Camara] Cerrando sesion")
            return

        except OSError as exc:
            last_error = exc
            winerror = getattr(exc, "winerror", None)
            if winerror == 1225:
                _status("[Camara] Conexion rechazada por red (WinError 1225).")
            else:
                _status(f"[Camara] Error de red: {exc}")
        except Exception as exc:
            last_error = exc
            _status(f"[Camara] Error WebRTC: {exc}")
        finally:
            if track_task:
                track_task.cancel()
            await pc.close()
            cv2.destroyAllWindows()

        if stop_event.is_set():
            return

        await asyncio.sleep(CAMERA_RETRY_WAIT_S)

    _status(f"[Camara] No se pudo iniciar el streaming. Ultimo error: {last_error}")


class CameraClient:
    """Controla ciclo de vida del receptor de camara en un hilo daemon."""

    def __init__(self, status_cb):
        self._status_cb = status_cb
        self._thread = None
        self._stop_event = None

    def start(self):
        if self.is_running:
            self._status_cb("Camara ya activa")
            return

        self._stop_event = threading.Event()

        def _thread_target():
            asyncio.run(_camera_receiver_task(self._stop_event, self._status_cb))
            self._status_cb("Camara detenida")

        self._thread = threading.Thread(
            target=_thread_target,
            daemon=True,
            name="CameraReceiverThread",
        )
        self._thread.start()
        self._status_cb("Iniciando camara...")

    def stop(self):
        if not self.is_running:
            self._status_cb("Camara no activa")
            return
        self._stop_event.set()
        self._status_cb("Deteniendo camara...")

    @property
    def is_running(self):
        return bool(self._thread and self._thread.is_alive())


# ============================================================================
# VARIABLES GLOBALES UI
# ============================================================================

controller = None
previousBtn = None
_mode = None

# Estado resumido para habilitar/deshabilitar UI.
last_state = "disconnected"

# Ventana
root = None

# Widgets de telemetria
altShowLbl = headingShowLbl = stateShowLbl = None
speedShowLbl = flightModeShowLbl = latShowLbl = lonShowLbl = None

# Widgets de accion
connectBtn = disconnectBtn = armBtn = disarmBtn = None
takeOffBtn = landBtn = RTLBtn = None
rotateCWBtn = rotateCCWBtn = None
gotoBtn = applyAltBtn = None
StartTelemBtn = StopTelemBtn = None
startCamBtn = stopCamBtn = None

speedSldr = gradesSldr = altSldr = None
modoLbl = cameraStatusLbl = None
mapStatusLbl = targetInfoLbl = None

navBtns = []
StopBtn = None

# Estado del mapa / navegacion por clic.
map_widget = None
map_drone_marker = None
map_target_marker = None
selected_target: Optional[Tuple[float, float]] = None
last_live_position: Optional[Tuple[float, float]] = None
last_map_center_ts = 0.0
last_marker_update_ts = 0.0
last_marker_position: Optional[Tuple[float, float]] = None

# Reconocimiento de objetos sobre stream WebRTC (cliente).
detection_vars = {}
detectionStatusLbl = None
selected_detection_labels = set()
selected_detection_lock = threading.Lock()
object_detector = None

camera_client = None
camera_service_manager = None
autopilot_service_manager = None
broker_connected = False
global_connect_pending = False


def _acquire_local_instance_lock():
    """Garantiza que solo haya una instancia en modo Local."""
    global _local_lock_fd
    if _local_lock_fd is not None:
        return True

    ok, fd, recovered = _acquire_pid_lock(LOCAL_INSTANCE_LOCK_PATH)
    if ok:
        _local_lock_fd = fd
        if recovered:
            print("[LocalLock] Lock huerfano recuperado")
        return True
    return False


def _release_local_instance_lock():
    global _local_lock_fd
    if _local_lock_fd is None:
        return

    _release_pid_lock(_local_lock_fd, LOCAL_INSTANCE_LOCK_PATH)
    _local_lock_fd = None



# ============================================================================
# HELPERS UI
# ============================================================================

def _ui_call(fn):
    if root:
        root.after(0, fn)


def _habilitarBtn(btn, text=None, bg=None, fg=None):
    if btn is None:
        return
    btn["state"] = "normal"
    if text:
        btn["text"] = text
    btn["bg"] = bg if bg else COLOR_DISPONIBLE
    btn["fg"] = fg if fg else FG_NORMAL


def _deshabilitarBtn(btn, text=None, bg=None, fg=None):
    if btn is None:
        return
    if text:
        btn["text"] = text
    btn["bg"] = bg if bg else COLOR_NO_DISPONIBLE
    btn["fg"] = fg if fg else FG_NO_DISPONIBLE
    btn.configure(disabledforeground=fg if fg else FG_NO_DISPONIBLE)
    btn["state"] = "disabled"


def _activarBtn(btn, text=None):
    if btn is None:
        return
    if text:
        btn["text"] = text
    btn["bg"] = COLOR_ACTIVO
    btn["fg"] = FG_ACTIVO
    btn.configure(disabledforeground=FG_ACTIVO)


def _procesoBtn(btn, text=None):
    if btn is None:
        return
    if text:
        btn["text"] = text
    btn["bg"] = COLOR_EN_PROCESO
    btn["fg"] = FG_NORMAL


def _status_camara(msg):
    # No escribimos estados cambiantes en la UI para mantener el dashboard estable.
    print(msg)


def _status_autopilot(msg):
    print(msg)


def _has_map():
    return tkintermapview is not None and map_widget is not None


def _set_target_info(text):
    if targetInfoLbl:
        _ui_call(lambda: targetInfoLbl.config(text=text))


def _set_map_status(text):
    if mapStatusLbl:
        _ui_call(lambda: mapStatusLbl.config(text=text))


def _set_detection_status(text):
    # Estado de deteccion oculto: la seleccion visual vive en los checkboxes.
    return


def _ensure_map_dependencies_or_warn():
    if tkintermapview is not None:
        return True
    messagebox.showwarning(
        "Mapa no disponible",
        "Falta la dependencia 'tkintermapview'.\n"
        "Instala requirements.txt para activar el mapa interactivo.",
    )
    return False


def _set_map_target(lat, lon):
    global selected_target, map_target_marker
    selected_target = (float(lat), float(lon))
    if not _has_map():
        _set_target_info(f"Objetivo: {lat:.6f}, {lon:.6f}")
        return

    if map_target_marker is not None:
        try:
            map_target_marker.delete()
        except Exception:
            pass

    map_target_marker = map_widget.set_marker(lat, lon, text="Objetivo")
    _set_target_info(f"Objetivo: {lat:.6f}, {lon:.6f}")


def _on_map_click(*args):
    """Compatible con tkintermapview: puede recibir (lat, lon) o una tupla."""
    if len(args) == 1:
        pos = args[0]
        try:
            lat, lon = pos
        except Exception:
            return
    elif len(args) >= 2:
        lat, lon = args[0], args[1]
    else:
        return

    _set_map_target(lat, lon)


def _set_selected_detection_labels(labels):
    global selected_detection_labels
    with selected_detection_lock:
        selected_detection_labels = set(labels)


def _get_selected_detection_labels():
    with selected_detection_lock:
        return set(selected_detection_labels)


def _on_detection_selection_changed():
    labels = {name for name, var in detection_vars.items() if var.get()}
    _set_selected_detection_labels(labels)
    if labels and object_detector is not None:
        object_detector.preload_async()
    else:
        _set_detection_status("Reconocimiento desactivado")


def _meters_between_points(lat1, lon1, lat2, lon2):
    # Aproximacion ligera para decidir si merece redibujar el marcador.
    lat1r = math.radians(lat1)
    lat2r = math.radians(lat2)
    dlat = lat2r - lat1r
    dlon = math.radians(lon2 - lon1)
    x = dlon * math.cos((lat1r + lat2r) * 0.5)
    y = dlat
    return math.sqrt((x * x) + (y * y)) * 6371000.0


def _update_map_drone_position(lat, lon):
    global map_drone_marker, last_live_position, last_map_center_ts
    global last_marker_update_ts, last_marker_position

    if lat is None or lon is None:
        return
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return

    last_live_position = (lat, lon)

    if not _has_map():
        return

    now = time.time()
    if last_marker_position is not None:
        moved_m = _meters_between_points(last_marker_position[0], last_marker_position[1], lat, lon)
        # Evita refrescos excesivos sin dejar el marcador aparentemente congelado.
        if moved_m < MAP_MARKER_MIN_MOVE_M and (now - last_marker_update_ts) < MAP_MARKER_MIN_INTERVAL_S:
            return

    if map_drone_marker is None:
        map_drone_marker = map_widget.set_marker(lat, lon, text="Dron")
        map_widget.set_position(lat, lon)
        last_map_center_ts = now
        last_marker_position = (lat, lon)
        last_marker_update_ts = now
        return

    moved_ok = False
    if hasattr(map_drone_marker, "set_position"):
        try:
            map_drone_marker.set_position(lat, lon)
            moved_ok = True
        except Exception:
            moved_ok = False

    if not moved_ok:
        # Fallback para versiones de tkintermapview sin set_position fiable.
        try:
            map_drone_marker.delete()
        except Exception:
            pass
        map_drone_marker = map_widget.set_marker(lat, lon, text="Dron")

    last_marker_position = (lat, lon)
    last_marker_update_ts = now

    if now - last_map_center_ts >= MAP_RECENTER_INTERVAL_S:
        map_widget.set_position(lat, lon)
        last_map_center_ts = now


def _es_local():
    return _mode == MODE_LOCAL


def actualizarBotonesSegunEstado():
    """Replica comportamiento visual de DashboardLocalPython en modo Local."""
    state = last_state

    if _mode is None:
        return

    if _mode == MODE_GLOBAL:
        # En global habilitamos comandos disponibles por MQTT.
        _habilitarBtn(connectBtn, "Conectar")
        _habilitarBtn(armBtn, "Armar")
        _habilitarBtn(takeOffBtn, "Despegar")
        _habilitarBtn(landBtn, "Aterrizar")
        _habilitarBtn(RTLBtn, "RTL")
        _habilitarBtn(StartTelemBtn, "Iniciar telemetria")
        _habilitarBtn(StopTelemBtn, "Parar telemetria")
        for b in navBtns:
            _habilitarBtn(b, bg=COLOR_STOP if b == StopBtn else COLOR_DISPONIBLE, fg=FG_ACTIVO if b == StopBtn else FG_NORMAL)

        if state == "armed":
            _habilitarBtn(disarmBtn, "Desarmar")
        else:
            _deshabilitarBtn(disarmBtn, "Desarmar")

        if state == "flying":
            _habilitarBtn(rotateCWBtn, "90 CW")
            _habilitarBtn(rotateCCWBtn, "90 CCW")
            _habilitarBtn(applyAltBtn, "Aplicar altitud")
            _habilitarBtn(gotoBtn, "Ir al objetivo")
        else:
            _deshabilitarBtn(rotateCWBtn, "90 CW")
            _deshabilitarBtn(rotateCCWBtn, "90 CCW")
            _deshabilitarBtn(applyAltBtn, "Aplicar altitud")
            _deshabilitarBtn(gotoBtn, "Ir al objetivo")

        # Aun no soportado en Global.
        _deshabilitarBtn(disconnectBtn, "Desconectar")
        return

    # Modo Local completo.
    if state == "disconnected":
        _habilitarBtn(connectBtn, "Conectar")
    else:
        _activarBtn(connectBtn, "Conectado")

    if state == "connected":
        _habilitarBtn(disconnectBtn, "Desconectar")
        _habilitarBtn(armBtn, "Armar")
    else:
        _deshabilitarBtn(disconnectBtn, "Desconectar")
        if state in ("arming", "armed", "takingOff", "flying", "returning", "landing"):
            _activarBtn(armBtn, "Armado")
        else:
            _deshabilitarBtn(armBtn, "Armar")

    if state == "arming":
        _procesoBtn(armBtn, "Armando...")

    if state == "armed":
        _habilitarBtn(disarmBtn, "Desarmar")
        _habilitarBtn(takeOffBtn, "Despegar")
    else:
        _deshabilitarBtn(disarmBtn, "Desarmar")

    if state == "takingOff":
        _procesoBtn(takeOffBtn, "Despegando...")
    elif state in ("flying", "returning"):
        _activarBtn(takeOffBtn, "En el aire")
    elif state not in ("armed",):
        _deshabilitarBtn(takeOffBtn, "Despegar")

    if state in ("flying", "returning"):
        _habilitarBtn(landBtn, "Aterrizar")
    elif state == "landing":
        _procesoBtn(landBtn, "Aterrizando...")
    else:
        _deshabilitarBtn(landBtn, "Aterrizar")

    if state == "flying":
        _habilitarBtn(RTLBtn, "RTL")
        _habilitarBtn(rotateCWBtn, "90 CW")
        _habilitarBtn(rotateCCWBtn, "90 CCW")
        _habilitarBtn(gotoBtn, "Ir al objetivo")
        _habilitarBtn(applyAltBtn, "Aplicar altitud")
        for b in navBtns:
            _habilitarBtn(b, bg=COLOR_STOP if b == StopBtn else COLOR_DISPONIBLE, fg=FG_ACTIVO if b == StopBtn else FG_NORMAL)
    elif state == "returning":
        _procesoBtn(RTLBtn, "Retornando...")
        _deshabilitarBtn(rotateCWBtn, "90 CW")
        _deshabilitarBtn(rotateCCWBtn, "90 CCW")
        _deshabilitarBtn(gotoBtn, "Ir al objetivo")
        _deshabilitarBtn(applyAltBtn, "Aplicar altitud")
        for b in navBtns:
            _deshabilitarBtn(b)
    else:
        _deshabilitarBtn(RTLBtn, "RTL")
        _deshabilitarBtn(rotateCWBtn, "90 CW")
        _deshabilitarBtn(rotateCCWBtn, "90 CCW")
        _deshabilitarBtn(gotoBtn, "Ir al objetivo")
        _deshabilitarBtn(applyAltBtn, "Aplicar altitud")
        for b in navBtns:
            _deshabilitarBtn(b)

    if state == "disconnected":
        _deshabilitarBtn(StartTelemBtn, "Iniciar telemetria")
        _deshabilitarBtn(StopTelemBtn, "Parar telemetria")
    elif _es_local() and getattr(controller, "dron", None) and getattr(controller.dron, "sendTelemetryInfo", False):
        _deshabilitarBtn(StartTelemBtn, "Iniciar telemetria", bg=COLOR_NO_DISPONIBLE)
        _habilitarBtn(StopTelemBtn, "Parar telemetria")
    else:
        _habilitarBtn(StartTelemBtn, "Iniciar telemetria")
        _habilitarBtn(StopTelemBtn, "Parar telemetria")


# ============================================================================
# TELEMETRIA Y MQTT
# ============================================================================

def _set_state(new_state):
    global last_state
    if new_state:
        last_state = new_state
    _ui_call(actualizarBotonesSegunEstado)


def _safe_round(value, ndigits=2, fallback="--"):
    """Devuelve round(value) si es numerico; si llega None/valor invalido devuelve fallback."""
    if value is None:
        return fallback
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return fallback


def showTelemetryInfo(telemetry_info):
    """Actualiza las etiquetas de telemetria (thread-safe para Tk)."""
    global altShowLbl, headingShowLbl, stateShowLbl, speedShowLbl, flightModeShowLbl, latShowLbl, lonShowLbl

    def _ui_update():
        if altShowLbl:
            altShowLbl["text"] = _safe_round(telemetry_info.get("alt"), 2)
            headingShowLbl["text"] = _safe_round(telemetry_info.get("heading"), 2)
            stateShowLbl["text"] = telemetry_info.get("state") or "--"
            speedShowLbl["text"] = _safe_round(telemetry_info.get("groundSpeed"), 2)
            flightModeShowLbl["text"] = telemetry_info.get("flightMode") or "--"
            latShowLbl["text"] = _safe_round(telemetry_info.get("lat"), 6)
            lonShowLbl["text"] = _safe_round(telemetry_info.get("lon"), 6)

            # Evitar invocar a la logica pesada de Tkinter 4 veces por segundo si no ha cambiado.
            new_state = telemetry_info.get("state")
            if new_state and new_state != last_state:
                _set_state(new_state)

            _update_map_drone_position(telemetry_info.get("lat"), telemetry_info.get("lon"))

    _ui_call(_ui_update)


def on_mqtt_connect(client, userdata, flags, reason_code, properties):
    global broker_connected
    global global_connect_pending
    if reason_code == 0:
        broker_connected = True
        global_connect_pending = False
        print("[MQTT] Conectado al broker correctamente")
        if isinstance(controller, GlobalController):
            controller.mark_connected()
            print(f"[MQTT] Suscrito a respuestas de: {controller.topic_recv}")
    else:
        broker_connected = False
        print(f"[MQTT] Error de conexion al broker: {reason_code}")


def on_mqtt_message(client, userdata, message):
    global global_connect_pending
    topic = message.topic
    payload_txt = message.payload.decode("utf-8", errors="ignore") if message.payload else ""
    print(f"[MQTT] <- topic={topic} payload={payload_txt}")
    if topic.endswith("/telemetryInfo"):
        try:
            telemetry_info = json.loads(message.payload)
            if isinstance(telemetry_info, dict):
                showTelemetryInfo(telemetry_info)
        except Exception as exc:
            print(f"[MQTT] telemetria invalida: {exc}")
    elif topic.endswith("/connected"):
        global_connect_pending = False
        _set_state("connected")
    elif topic.endswith("/armed"):
        _set_state("armed")
    elif topic.endswith("/flying"):
        _set_state("flying")
    elif topic.endswith("/landed") or topic.endswith("/atHome"):
        _set_state("connected")
    elif topic.endswith("/connect_error"):
        global_connect_pending = False
        payload = message.payload.decode("utf-8", errors="ignore") if message.payload else ""
        reason = payload if payload else "No se pudo conectar el dron desde AutopilotService."

        def _ui_warn():
            messagebox.showerror(
                "Error de conexion Global",
                "AutopilotService no pudo conectar con el dron.\n\n"
                f"Detalle: {reason}\n\n"
                "Comprueba que el endpoint local del dron este activo (p. ej. tcp:127.0.0.1:5763).",
            )

        _ui_call(_ui_warn)
    elif topic.endswith("/disarmed"):
        _set_state("connected")
    elif topic.endswith("/rotated"):
        _set_state("flying")
        _ui_call(actualizarBotonesSegunEstado)
    elif topic.endswith("/altitudeChanged"):
        _set_state("flying")
        _ui_call(actualizarBotonesSegunEstado)
    elif topic.endswith("/gotoStarted"):
        _set_state("flying")
    elif topic.endswith("/gotoReached"):
        _set_state("flying")
        _ui_call(lambda: _activarBtn(gotoBtn, "Objetivo alcanzado"))
        _ui_call(lambda: root.after(1500, actualizarBotonesSegunEstado) if root else None)
    elif topic.endswith("/gotoError"):
        _set_state("flying")

        def _ui_goto_error():
            actualizarBotonesSegunEstado()
            reason = payload_txt if payload_txt else "AutopilotService rechazo el GoTo."
            messagebox.showwarning("GoTo", f"No se pudo iniciar GoTo.\n\nDetalle: {reason}")

        _ui_call(_ui_goto_error)


# ============================================================================
# COMANDOS UI
# ============================================================================

def _requerir_controlador():
    if controller is None:
        messagebox.showwarning("Aviso", "Primero selecciona modo y pulsa Iniciar.")
        return False
    return True


def cmd_connect():
    if not _requerir_controlador():
        return

    _ui_call(lambda: targetInfoLbl.config(text="Conectando..."))
    ok = controller.connect()
    if ok:
        _set_state("connected")
        _ui_call(lambda: targetInfoLbl.config(text="Dron conectado"))
    else:
        messagebox.showerror("Error", "No se pudo conectar (revisa consola o modo).")


def cmd_disconnect():
    if not _requerir_controlador():
        return
    if not _es_local():
        messagebox.showinfo("Modo Global", "Desconectar manual solo esta disponible en modo Local.")
        return

    if last_state != "connected":
        messagebox.showwarning("Aviso", f"Para desconectar, estado actual debe ser 'connected' (actual: {last_state}).")
        return

    def _do():
        ok = controller.disconnect()

        def _ui_update():
            if ok:
                _set_state("disconnected")
                _activarBtn(disconnectBtn, "Desconectado")
            else:
                messagebox.showerror("Error", "No se pudo desconectar.")

        _ui_call(_ui_update)

    threading.Thread(target=_do, daemon=True).start()


def _on_armed():
    _set_state("armed")


def _on_arm_error(msg):
    def _ui_update():
        _set_state("connected")
        messagebox.showerror("Error al armar", f"No se pudo armar. Motivo: {msg}")

    _ui_call(_ui_update)


def cmd_arm():
    if not _requerir_controlador():
        return

    if _es_local():
        if last_state != "connected":
            messagebox.showwarning("Aviso", f"El dron debe estar en 'connected' para armar (actual: {last_state}).")
            return
        _set_state("arming")
        ok = controller.arm(callback=_on_armed, error_callback=_on_arm_error)
        if not ok:
            _set_state("connected")
            messagebox.showerror("Error", "No se pudo iniciar el armado.")
    else:
        ok = controller.arm()
        if not ok:
            messagebox.showwarning("Modo Global", "No se pudo enviar comando de armado (broker no listo).")


def cmd_disarm():
    if not _requerir_controlador():
        return

    if last_state != "armed":
        messagebox.showwarning("Aviso", f"Solo se puede desarmar desde 'armed' (actual: {last_state}).")
        return

    ok = controller.disarm()
    if ok:
        if _es_local():
            _set_state("connected")
            _activarBtn(disarmBtn, "Desarmado")
    else:
        messagebox.showerror("Error", "No se pudo desarmar.")


def _on_in_the_air():
    _set_state("flying")


def cmd_takeoff():
    if not _requerir_controlador():
        return

    target_alt = int(altSldr.get()) if altSldr else 5

    _procesoBtn(takeOffBtn, "Despegando...")
    if _es_local():
        if last_state != "armed":
            messagebox.showwarning("Aviso", f"Para despegar, estado debe ser 'armed' (actual: {last_state}).")
            _set_state(last_state)
            return
        _set_state("takingOff")
        threading.Thread(
            target=controller.takeoff,
            kwargs={"alt": target_alt, "callback": _on_in_the_air},
            daemon=True,
        ).start()
    else:
        controller.takeoff(target_alt)


def _on_landed():
    _set_state("connected")


def cmd_land():
    if not _requerir_controlador():
        return

    if _es_local():
        if last_state not in ("flying", "returning"):
            messagebox.showwarning("Aviso", f"Solo se puede aterrizar en vuelo (actual: {last_state}).")
            return
        _set_state("landing")
        threading.Thread(target=controller.land, kwargs={"callback": _on_landed}, daemon=True).start()
    else:
        controller.land()
        _procesoBtn(landBtn, "Aterrizando...")


def _on_rtl_complete():
    _set_state("connected")


def cmd_rtl():
    if not _requerir_controlador():
        return

    if _es_local():
        if last_state != "flying":
            messagebox.showwarning("Aviso", f"Solo se puede activar RTL desde 'flying' (actual: {last_state}).")
            return
        _set_state("returning")
        threading.Thread(target=controller.rtl, kwargs={"callback": _on_rtl_complete}, daemon=True).start()
    else:
        controller.rtl()
        _procesoBtn(RTLBtn, "Retornando...")


def cmd_go(direction, btn):
    global previousBtn

    if not _requerir_controlador():
        return

    if _es_local() and last_state != "flying":
        return

    if previousBtn and previousBtn != StopBtn:
        _habilitarBtn(previousBtn)

    controller.go(direction)

    if btn == StopBtn:
        _habilitarBtn(StopBtn, bg=COLOR_STOP, fg=FG_ACTIVO)
        previousBtn = None
    else:
        _activarBtn(btn)
        previousBtn = btn


def cmd_start_telem():
    print("Iniciando telemtria...")
    if not _requerir_controlador():
        return

    if _es_local():
        controller.start_telemetry(showTelemetryInfo)
    else:
        controller.start_telemetry()
    _ui_call(lambda: _habilitarBtn(StopTelemBtn))
    _ui_call(lambda: _deshabilitarBtn(StartTelemBtn))


def cmd_stop_telem():
    if not _requerir_controlador():
        return
    controller.stop_telemetry()
    _ui_call(lambda: _habilitarBtn(StartTelemBtn))
    _ui_call(lambda: _deshabilitarBtn(StopTelemBtn))


def cmd_change_heading(event):
    if not _requerir_controlador():
        return
    if _es_local() and last_state != "flying":
        return
    controller.change_heading(gradesSldr.get())


def cmd_change_nav_speed(event):
    if not _requerir_controlador():
        return
    if _es_local() and last_state not in ("flying", "returning"):
        return
    controller.change_nav_speed(speedSldr.get())


def cmd_rotate(direction):
    if not _requerir_controlador():
        return
    if last_state != "flying":
        return

    target_btn = rotateCWBtn if direction == "cw" else rotateCCWBtn
    _procesoBtn(target_btn, "Rotando...")

    if _es_local():
        def _rot_done():
            _ui_call(actualizarBotonesSegunEstado)

        controller.rotate(90, direction=direction, callback=_rot_done)
    else:
        ok = controller.rotate(90, direction=direction)
        if not ok:
            actualizarBotonesSegunEstado()
            messagebox.showwarning("Modo Global", "No se pudo enviar rotacion (broker no listo).")


def cmd_apply_altitude():
    if not _requerir_controlador():
        return
    if last_state != "flying":
        return

    target_alt = int(altSldr.get())
    _procesoBtn(applyAltBtn, "Cambiando...")

    if _es_local():
        def _done():
            def _ui_update():
                _activarBtn(applyAltBtn, "Altitud OK")
                root.after(1800, actualizarBotonesSegunEstado)

            _ui_call(_ui_update)

        ok = controller.change_altitude(target_alt, callback=_done)
        if not ok:
            actualizarBotonesSegunEstado()
    else:
        ok = controller.change_altitude(target_alt)
        if not ok:
            actualizarBotonesSegunEstado()
            messagebox.showwarning("Modo Global", "No se pudo enviar cambio de altitud (broker no listo).")


def cmd_goto():
    if not _requerir_controlador():
        return
    if last_state != "flying":
        messagebox.showwarning("Aviso", f"Para GoTo el dron debe estar en vuelo (actual: {last_state}).")
        return

    if selected_target is None:
        messagebox.showwarning(
            "GoTo",
            "Selecciona un objetivo haciendo clic en el mapa.",
        )
        return

    lat, lon = selected_target
    target_speed = float(speedSldr.get()) if speedSldr else 1.0
    _procesoBtn(gotoBtn, "Navegando...")

    if _es_local():
        def _done():
            def _ui_update():
                _activarBtn(gotoBtn, "Objetivo alcanzado")
                root.after(2200, actualizarBotonesSegunEstado)

            _ui_call(_ui_update)

        def _send_local_goto():
            try:
                controller.change_nav_speed(target_speed)
                controller.goto(lat, lon, callback=_done)
            except Exception as exc:
                _ui_call(lambda: messagebox.showwarning("GoTo", f"No se pudo iniciar GoTo local.\n\nDetalle: {exc}"))
                _ui_call(actualizarBotonesSegunEstado)

        threading.Thread(target=_send_local_goto, daemon=True).start()
    else:
        ok = controller.goto(lat, lon, speed=target_speed)
        if not ok:
            actualizarBotonesSegunEstado()
            messagebox.showwarning("Modo Global", "No se pudo enviar GoTo (broker no listo).")


def cmd_start_camera():
    if camera_client is None:
        return

    global object_detector
    if object_detector is None:
        object_detector = _ObjectDetector(_set_detection_status)

    # Precarga del modelo fuera del loop de video para evitar bloqueos al seleccionar objetos.
    object_detector.preload_async()

    # En modo local O si estamos en global apuntando a localhost,
    # el dashboard es responsable de levantar el servicio de camara si no esta activo.
    if camera_service_manager is not None and not camera_service_manager.is_running:
        if _es_local() or _camera_host() in ("127.0.0.1", "localhost", "0.0.0.0"):
            ok = camera_service_manager.start()
            if not ok:
                messagebox.showerror("Camara", "No se pudo iniciar CameraService integrado.")
                return

    camera_client.start()


def cmd_stop_camera():
    if camera_client is None:
        return
    camera_client.stop()
    if _es_local() and camera_service_manager is not None:
        camera_service_manager.stop()


# ============================================================================
# INICIO DE MODO
# ============================================================================

def cmd_iniciar(modo_var, iniciarBtn, modoFrame):
    global controller, _mode, camera_client, camera_service_manager, autopilot_service_manager, last_state

    modo = modo_var.get()
    if not modo:
        messagebox.showwarning("Aviso", "Selecciona un modo antes de iniciar.")
        return

    _mode = modo
    last_state = "disconnected"

    if modo == MODE_LOCAL:
        if not _acquire_local_instance_lock():
            messagebox.showerror(
                "Modo Local bloqueado",
                "Ya existe otra instancia en modo Local en este equipo.\n"
                "Cierra esa instancia o usa modo Global.",
            )
            _mode = None
            return

        controller = LocalController()
        if camera_service_manager is None:
            camera_service_manager = CameraServiceManager(_status_camara)
        cam_ok = True

        modoLbl["text"] = "Modo: LOCAL (control directo al dron)"
        modoLbl["fg"] = "darkgreen"
        if cam_ok:
            messagebox.showinfo(
                "Modo Local activado",
                "Servicios locales activados.\n\n"
                "Control directo iniciado.\n"
                "CameraService se inicia al pulsar 'Iniciar cámara'.",
            )
        else:
            messagebox.showwarning(
                "Modo Local activado",
                "No se pudieron iniciar todos los servicios locales.\n"
                f"CameraService: {'OK' if cam_ok else 'FALLO'}",
            )
    else:
        # En Global tambien integramos AutopilotService; si otra instancia ya lo tiene,
        # reutilizamos ese servicio para evitar conflictos de client ID.
        _release_local_instance_lock()

        if autopilot_service_manager is None:
            autopilot_service_manager = AutopilotServiceManager(_status_autopilot)
        auto_ok = autopilot_service_manager.start(show_console=True)

        controller = GlobalController(on_mqtt_message, on_mqtt_connect)

        # En vez de detener la camara, la dejamos disponible si la IP es local.
        # if camera_service_manager is not None and camera_service_manager.is_running:
        #    camera_service_manager.stop()
        # Aseguramos que exista el manager para poder iniciarlo luego en cmd_start_camera si es necesario
        if camera_service_manager is None:
            camera_service_manager = CameraServiceManager(_status_camara)

        modoLbl["text"] = "Modo: GLOBAL (via MQTT / AutopilotService)"
        modoLbl["fg"] = "darkblue"

        if auto_ok and autopilot_service_manager.owns_service:
            messagebox.showinfo(
                "Modo Global activado",
                "Conectado al broker MQTT.\n"
                "AutopilotService integrado arrancado en una consola visible para trazas.",
            )
        elif auto_ok:
            messagebox.showinfo(
                "Modo Global activado",
                "Conectado al broker MQTT.\n"
                "AutopilotService ya estaba activo en otra instancia y se reutiliza.",
            )
        else:
            messagebox.showwarning(
                "Modo Global activado",
                "Conectado al broker MQTT, pero no se pudo arrancar/reutilizar AutopilotService.\n"
                "Revisa la consola y la conectividad MQTT.",
            )

    if camera_client is None:
        camera_client = CameraClient(_status_camara)

    iniciarBtn["state"] = "disabled"
    for child in modoFrame.winfo_children():
        if isinstance(child, tk.Radiobutton):
            child["state"] = "disabled"

    actualizarBotonesSegunEstado()


def _cleanup_services():
    try:
        if camera_client:
            camera_client.stop()
        if camera_service_manager:
            camera_service_manager.stop()
        if autopilot_service_manager:
            autopilot_service_manager.stop()
        if isinstance(controller, GlobalController):
            controller.disconnect()
        _release_local_instance_lock()
    except Exception:
        pass


def _on_close():
    try:
        _cleanup_services()
    finally:
        if root:
            root.destroy()


# ============================================================================
# CONSTRUCCION DE VENTANA
# ============================================================================

def crear_ventana():
    global root, previousBtn
    global altShowLbl, headingShowLbl, stateShowLbl
    global speedShowLbl, flightModeShowLbl, latShowLbl, lonShowLbl
    global connectBtn, disconnectBtn, armBtn, disarmBtn, takeOffBtn, landBtn, RTLBtn
    global rotateCWBtn, rotateCCWBtn, gotoBtn, applyAltBtn
    global speedSldr, gradesSldr, altSldr, modoLbl, cameraStatusLbl
    global StartTelemBtn, StopTelemBtn, startCamBtn, stopCamBtn
    global navBtns, StopBtn
    global map_widget, mapStatusLbl, targetInfoLbl
    global detectionStatusLbl

    previousBtn = None

    root = tk.Tk()
    root.title("Dashboard V2 - Autopiloto + Camara")
    root.geometry("1450x900")
    root.minsize(1180, 760)

    for r in range(14):
        root.rowconfigure(r, weight=1)
    for c in range(4):
        root.columnconfigure(c, weight=1)
    # Panel lateral del mapa (mas ancho que el panel de control).
    for c in range(4, 8):
        root.columnconfigure(c, weight=2)

    btn_font = ("Arial", 10, "bold")

    modoFrame = tk.LabelFrame(root, text="Seleccion de modo", pady=4)
    modoFrame.grid(row=0, column=0, columnspan=4, padx=10, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)

    modo_var = tk.StringVar(value=MODE_LOCAL)
    tk.Radiobutton(
        modoFrame,
        text="Local (control directo)",
        variable=modo_var,
        value=MODE_LOCAL,
        font=("Arial", 11),
    ).pack(side=tk.LEFT, padx=15, pady=5)
    tk.Radiobutton(
        modoFrame,
        text="Global (MQTT / AutopilotService)",
        variable=modo_var,
        value=MODE_GLOBAL,
        font=("Arial", 11),
    ).pack(side=tk.LEFT, padx=15, pady=5)

    iniciarBtn = tk.Button(modoFrame, text="Iniciar", bg=COLOR_DISPONIBLE, font=btn_font)
    iniciarBtn["command"] = lambda: cmd_iniciar(modo_var, iniciarBtn, modoFrame)
    iniciarBtn.pack(side=tk.RIGHT, padx=8, pady=5)

    modoLbl = tk.Label(
        root,
        text="Modo: no iniciado (pulsa Iniciar)",
        fg="gray",
        font=("Arial", 10, "italic"),
    )
    modoLbl.grid(row=1, column=0, columnspan=4, pady=2)

    connectBtn = tk.Button(root, text="Conectar", font=btn_font, command=cmd_connect)
    connectBtn.grid(row=2, column=0, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    armBtn = tk.Button(root, text="Armar", font=btn_font, command=cmd_arm)
    armBtn.grid(row=2, column=1, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    takeOffBtn = tk.Button(root, text="Despegar", font=btn_font, command=cmd_takeoff)
    takeOffBtn.grid(row=2, column=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    disconnectBtn = tk.Button(root, text="Desconectar", font=btn_font, command=cmd_disconnect)
    disconnectBtn.grid(row=2, column=3, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    landBtn = tk.Button(root, text="Aterrizar", font=btn_font, command=cmd_land)
    landBtn.grid(row=3, column=0, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    RTLBtn = tk.Button(root, text="RTL", font=btn_font, command=cmd_rtl)
    RTLBtn.grid(row=3, column=1, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    rotateFrame = tk.Frame(root)
    rotateFrame.grid(row=3, column=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)
    rotateFrame.columnconfigure(0, weight=1)
    rotateFrame.columnconfigure(1, weight=1)

    rotateCWBtn = tk.Button(rotateFrame, text="90 CW", font=("Arial", 8), command=lambda: cmd_rotate("cw"))
    rotateCWBtn.grid(row=0, column=0, padx=1, pady=1, sticky=tk.N + tk.S + tk.E + tk.W)

    rotateCCWBtn = tk.Button(rotateFrame, text="90 CCW", font=("Arial", 8), command=lambda: cmd_rotate("ccw"))
    rotateCCWBtn.grid(row=0, column=1, padx=1, pady=1, sticky=tk.N + tk.S + tk.E + tk.W)

    disarmBtn = tk.Button(root, text="Desarmar", font=btn_font, command=cmd_disarm)
    disarmBtn.grid(row=3, column=3, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    gradesSldr = tk.Scale(
        root,
        label="Heading (grados):",
        resolution=5,
        from_=0,
        to=360,
        tickinterval=45,
        orient=tk.HORIZONTAL,
    )
    gradesSldr.grid(row=4, column=0, columnspan=2, padx=8, pady=4, sticky=tk.N + tk.S + tk.E + tk.W)
    gradesSldr.bind("<ButtonRelease-1>", cmd_change_heading)

    speedSldr = tk.Scale(
        root,
        label="Velocidad nav (m/s):",
        resolution=1,
        from_=0,
        to=20,
        tickinterval=5,
        orient=tk.HORIZONTAL,
    )
    speedSldr.grid(row=4, column=2, columnspan=2, padx=8, pady=4, sticky=tk.N + tk.S + tk.E + tk.W)
    speedSldr.set(1)
    speedSldr.bind("<ButtonRelease-1>", cmd_change_nav_speed)

    navFrame = tk.LabelFrame(root, text="Navegacion", font=btn_font)
    navFrame.grid(row=5, column=0, columnspan=4, padx=40, pady=5, sticky=tk.N + tk.S + tk.E + tk.W)
    for r in range(3):
        navFrame.rowconfigure(r, weight=1)
    for c in range(3):
        navFrame.columnconfigure(c, weight=1)

    nav_grid = [
        ("NW", 0, 0, "NorthWest"),
        ("N", 0, 1, "North"),
        ("NE", 0, 2, "NorthEast"),
        ("W", 1, 0, "West"),
        ("STOP", 1, 1, "Stop"),
        ("E", 1, 2, "East"),
        ("SW", 2, 0, "SouthWest"),
        ("S", 2, 1, "South"),
        ("SE", 2, 2, "SouthEast"),
    ]

    navBtns = []
    for label, row, col, direction in nav_grid:
        btn = tk.Button(navFrame, text=label)
        btn.grid(row=row, column=col, padx=2, pady=2, sticky=tk.N + tk.S + tk.E + tk.W)
        btn["command"] = lambda d=direction, b=btn: cmd_go(d, b)
        navBtns.append(btn)
        if direction == "Stop":
            StopBtn = btn

    altSldr = tk.Scale(
        root,
        label="Altitud objetivo (m):",
        resolution=1,
        from_=1,
        to=50,
        tickinterval=10,
        orient=tk.HORIZONTAL,
    )
    altSldr.grid(row=6, column=0, columnspan=3, padx=8, pady=4, sticky=tk.N + tk.S + tk.E + tk.W)
    altSldr.set(5)

    applyAltBtn = tk.Button(root, text="Aplicar altitud", font=btn_font, command=cmd_apply_altitude)
    applyAltBtn.grid(row=6, column=3, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    StartTelemBtn = tk.Button(root, text="Iniciar telemetria", font=btn_font, command=cmd_start_telem)
    StartTelemBtn.grid(row=7, column=0, columnspan=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    StopTelemBtn = tk.Button(root, text="Parar telemetria", font=btn_font, command=cmd_stop_telem)
    StopTelemBtn.grid(row=7, column=2, columnspan=2, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    telemetryFrame = tk.LabelFrame(root, text="Telemetria", font=btn_font)
    telemetryFrame.grid(row=8, column=0, columnspan=4, padx=8, pady=4, sticky=tk.N + tk.S + tk.E + tk.W)
    for r in range(4):
        telemetryFrame.rowconfigure(r, weight=1)
    for c in range(4):
        telemetryFrame.columnconfigure(c, weight=1)

    tk.Label(telemetryFrame, text="Altitud").grid(row=0, column=0, padx=4, pady=2)
    tk.Label(telemetryFrame, text="Heading").grid(row=0, column=1, padx=4, pady=2)
    tk.Label(telemetryFrame, text="Estado").grid(row=0, column=2, padx=4, pady=2)
    tk.Label(telemetryFrame, text="Velocidad").grid(row=0, column=3, padx=4, pady=2)

    altShowLbl = tk.Label(telemetryFrame, text="--", fg="blue")
    altShowLbl.grid(row=1, column=0, padx=4, pady=2)
    headingShowLbl = tk.Label(telemetryFrame, text="--", fg="blue")
    headingShowLbl.grid(row=1, column=1, padx=4, pady=2)
    stateShowLbl = tk.Label(telemetryFrame, text="--", fg="blue")
    stateShowLbl.grid(row=1, column=2, padx=4, pady=2)
    speedShowLbl = tk.Label(telemetryFrame, text="--", fg="blue")
    speedShowLbl.grid(row=1, column=3, padx=4, pady=2)

    tk.Label(telemetryFrame, text="Modo vuelo").grid(row=2, column=0, padx=4, pady=2)
    tk.Label(telemetryFrame, text="Latitud").grid(row=2, column=1, padx=4, pady=2)
    tk.Label(telemetryFrame, text="Longitud").grid(row=2, column=2, padx=4, pady=2)

    flightModeShowLbl = tk.Label(telemetryFrame, text="--", fg="blue")
    flightModeShowLbl.grid(row=3, column=0, padx=4, pady=2)
    latShowLbl = tk.Label(telemetryFrame, text="--", fg="blue")
    latShowLbl.grid(row=3, column=1, padx=4, pady=2)
    lonShowLbl = tk.Label(telemetryFrame, text="--", fg="blue")
    lonShowLbl.grid(row=3, column=2, padx=4, pady=2)

    # Panel de mapa grande en lateral derecho.
    mapPanel = tk.LabelFrame(root, text="Mapa y GoTo", font=btn_font)
    mapPanel.grid(row=2, column=4, rowspan=11, columnspan=4, padx=8, pady=4, sticky=tk.N + tk.S + tk.E + tk.W)
    mapPanel.rowconfigure(0, weight=1)
    mapPanel.rowconfigure(1, weight=0)
    mapPanel.rowconfigure(2, weight=0)
    mapPanel.columnconfigure(0, weight=1)

    if tkintermapview is not None:
        map_widget = tkintermapview.TkinterMapView(mapPanel, corner_radius=0)
        map_widget.grid(row=0, column=0, padx=4, pady=4, sticky=tk.N + tk.S + tk.E + tk.W)
        map_widget.set_position(MAP_DEFAULT_LAT, MAP_DEFAULT_LON)
        map_widget.set_zoom(MAP_DEFAULT_ZOOM)
        map_widget.add_left_click_map_command(_on_map_click)
        mapStatusLbl = tk.Label(mapPanel, text="Mapa listo. Haz clic para fijar destino.", anchor="w")
        mapStatusLbl.grid(row=1, column=0, padx=4, pady=2, sticky=tk.E + tk.W)
    else:
        map_widget = None
        placeholder = tk.Label(
            mapPanel,
            text="Mapa no disponible (falta tkintermapview).",
            fg="red",
            anchor="center",
        )
        placeholder.grid(row=0, column=0, padx=4, pady=4, sticky=tk.N + tk.S + tk.E + tk.W)
        mapStatusLbl = tk.Label(mapPanel, text="Instala requirements.txt para activar el mapa.", anchor="w")
        mapStatusLbl.grid(row=1, column=0, padx=4, pady=2, sticky=tk.E + tk.W)

    gotoPanel = tk.Frame(mapPanel)
    gotoPanel.grid(row=2, column=0, padx=4, pady=4, sticky=tk.E + tk.W)
    gotoPanel.columnconfigure(0, weight=1)
    gotoPanel.columnconfigure(1, weight=0)

    targetInfoLbl = tk.Label(gotoPanel, text="Objetivo: no seleccionado", anchor="w")
    targetInfoLbl.grid(row=0, column=0, padx=4, pady=2, sticky=tk.E + tk.W)

    gotoBtn = tk.Button(gotoPanel, text="Ir al objetivo", font=btn_font, command=cmd_goto)
    gotoBtn.grid(row=0, column=1, padx=5, pady=2, sticky=tk.E)

    camFrame = tk.LabelFrame(root, text="Camara WebRTC", font=btn_font)
    camFrame.grid(row=12, column=0, columnspan=4, padx=8, pady=4, sticky=tk.N + tk.S + tk.E + tk.W)
    camFrame.columnconfigure(0, weight=1)
    camFrame.columnconfigure(1, weight=1)
    camFrame.columnconfigure(2, weight=2)
    camFrame.columnconfigure(3, weight=2)

    startCamBtn = tk.Button(camFrame, text="Iniciar camara", font=btn_font, command=cmd_start_camera)
    startCamBtn.grid(row=0, column=0, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    stopCamBtn = tk.Button(camFrame, text="Parar camara", font=btn_font, command=cmd_stop_camera)
    stopCamBtn.grid(row=0, column=1, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    cameraStatusLbl = tk.Label(camFrame, text="Camara", anchor="w", width=24)
    cameraStatusLbl.grid(row=0, column=2, padx=6, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    detectionFrame = tk.LabelFrame(camFrame, text="Objetos COCO", font=("Arial", 9, "bold"))
    detectionFrame.grid(row=1, column=0, columnspan=3, padx=3, pady=3, sticky=tk.N + tk.S + tk.E + tk.W)

    for idx, label in enumerate(COCO_DETECTION_SUBSET):
        var = tk.BooleanVar(value=False)
        detection_vars[label] = var
        chk = tk.Checkbutton(
            detectionFrame,
            text=label,
            variable=var,
            command=_on_detection_selection_changed,
        )
        chk.grid(row=idx // 4, column=idx % 4, padx=4, pady=2, sticky=tk.W)

    _on_detection_selection_changed()

    actualizarBotonesSegunEstado()
    root.protocol("WM_DELETE_WINDOW", _on_close)

    if _ensure_map_dependencies_or_warn():
        _set_map_status("Mapa listo. Haz clic para fijar destino.")

    return root


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    atexit.register(_cleanup_services)
    ventana = crear_ventana()
    try:
        ventana.mainloop()
    finally:
        _cleanup_services()
