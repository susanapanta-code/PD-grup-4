# receiver.py
# Archivo: ./receiver.py
# Receptor: espera offer, crea answer y muestra vídeo.

import asyncio
import json
import cv2
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from websockets import connect
import socket
import struct
import torch
import threading
import concurrent.futures
import time

#------------------------------------------------------------------------
def socket_listener(video_receiver):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 6000))
    server.listen(1)
    print("Esperando comandos de detección desde C#...")
    while True:
        client, _ = server.accept()
        data = client.recv(1024).decode()
        print("Recibido desde C#:", data)
        try:
            objectID = int(data)
            video_receiver.setObject(objectID)
        except:
            print("Error procesando objeto")
        client.close()

class Detector:
    def __init__(self):
        print("Cargando modelo YOLO...")
        self.model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
        self.model.eval()
        print("YOLO listo")

    def detect(self, frame, objectID):
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.model(img_rgb)
        for *box, conf, cls in results.xyxy[0]:
            if int(cls.item()) == objectID:
                x1, y1, x2, y2 = map(int, box)
                return True, [x1, y1, x2, y2]
        return False, None

class VideoReceiver:
    def __init__(self):
        self.detector = Detector()
        self.objectID = None

        self.last_detection = None
        self.lock = threading.Lock()

        self.detecting = False

    def setObject(self, objectID):
        print("Nuevo objeto:", objectID)
        self.objectID = objectID

    def update_detection(self, result):
        with self.lock:
            self.last_detection = (result, time.time())

    def get_detection(self):
        with self.lock:
            return self.last_detection

def detectar_async(video_receiver, img, objectID):
    video_receiver.detecting = True
    detectado, rect = video_receiver.detector.detect(img, objectID)
    video_receiver.update_detection((detectado, rect))
    video_receiver.detecting = False

#------------------------------------------------------------------------

async def display_track(track):
    global video_receiver
    print("Conectando a C#...")

    SERVER_IP = "127.0.0.1"
    SERVER_PORT = 5000

    # --- Inicializar socket ---
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_IP, SERVER_PORT))

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    print("Conectado a C#")
    frame_count = 0
    #detectado = False
    #rect = None

    while True:
        try:
            frame = await track.recv()
            img = frame.to_ndarray(format="bgr24")

            # reducir resolución SOLO para envío (opcional)
            #img = cv2.resize(img, (640, 480))

            #cv2.imshow("Receiver", img)

            frame_count += 1

            # DETECCIÓN no bloqueante
            if video_receiver.objectID is not None:
                if not video_receiver.detecting:
                #if frame_count % 10 == 0:  # no procesar todos (mejora rendimiento)
                    #detectado, rect = video_receiver.detector.detect(img, video_receiver.objectID)
                    img_small = cv2.resize(img, (320, 240))
                    executor.submit(
                        detectar_async,
                        video_receiver,
                        img_small.copy(),
                        video_receiver.objectID
                    )
            data = video_receiver.get_detection()

            if data is not None:
                (detectado, rect), t = data

                if time.time() - t < 0.5:  # si la detección es vieja, descartarla
                    if detectado and rect:
                        x1, y1, x2, y2 = rect
                        scale_x = img.shape[1] / 320
                        scale_y = img.shape[0] / 240
                        x1 = int(x1 * scale_x)
                        y1 = int(y1 * scale_y)
                        x2 = int(x2 * scale_x)
                        y2 = int(y2 * scale_y)
                        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 255), 2)
                        cv2.putText(img, str(video_receiver.objectID),
                                    (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                    (255, 0, 255), 2)

            # Enviar a C#
            #ret, jpeg = cv2.imencode(".jpg", img)
            ret, jpeg = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            data = jpeg.tobytes()
            print("Envio frame")

            # Enviar tamaño + datos
            sock.sendall(struct.pack(">I", len(data)) + data)

        except Exception as e:
            print("Error en stream:", e)
            break

            #if cv2.waitKey(1) & 0xFF == ord("q"):
                #break
    #cv2.destroyAllWindows()

async def run(server_url: str, stream_id: str):
    #config = RTCConfiguration(iceServers=[
        #RTCIceServer(urls="stun:stun.l.google.com:19302")
    #])
    #pc = RTCPeerConnection(configuration=config)
    pc = RTCPeerConnection()

    global video_receiver
    video_receiver = VideoReceiver()

    threading.Thread(target=socket_listener, args=(video_receiver,), daemon=True).start()

    #---------------------------------------------------------------------------------------------------
    @pc.on("track")
    def on_track(track):
        print("Track recibido:", track.kind)
        if track.kind == "video":
            asyncio.create_task(display_track(track))

    @pc.on("icecandidate")
    async def on_ice(candidate):
        if candidate:
            print("Enviando ICE al sender")
            await ws.send(json.dumps({"type": "ice", "role": "receptor", "candidate": candidate.to_dict()}))

    @pc.on("connectionstatechange")
    async def on_state():
        print("STATE RECEIVER:", pc.connectionState)
    #---------------------------------------------------------------------------------------------------

    async with connect(server_url) as ws:
        print("Conectado al proxy")
        # registro
        await ws.send(json.dumps({"type": "peticion"}))
        #await ws.send(json.dumps({"type": "peticion", "role": "receptor", "stream_id": stream_id}))
        print("Registrado como receiver, esperando offer...")

        async for raw in ws:
            data = json.loads(raw)

            if data.get("role") != "emisor":
                continue
            if data.get("type") == "sdp":
                print ("Ha llegado la oferta del emisor")
                # oferta llegada: aplicarla y crear answer
                desc = RTCSessionDescription(sdp=data["sdp"], type=data["sdp_type"])
                await pc.setRemoteDescription(desc)
                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)
                await ws.send(json.dumps({"type": "sdp", "role": "receptor", "stream_id": stream_id, "sdp": pc.localDescription.sdp, "sdp_type": pc.localDescription.type}))
                print("Answer enviada")

            #------------------------------------------------------------------
            elif data.get("type") == "ice" and data.get("role") == "emisor":
                print("Recibo ICE del sender")
                cand = data.get("candidate")
                if cand is None:
                    await pc.addIceCandidate(None)
                else:
                    await pc.addIceCandidate(RTCIceCandidate(
                        candidate=cand["candidate"],
                        sdpMid=cand["sdpMid"],
                        sdpMLineIndex=cand["sdpMLineIndex"]
                    ))
            #------------------------------------------------------------------



if __name__ == "__main__":
    import sys

    # Poner la IP pública de la máquina
    # en la que se ejecuta el proxy
    #server = sys.argv[1] if len(sys.argv) > 1 else "ws://dronseetac.upc.edu:8107"
    server = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8108"

    #server = sys.argv[1] if len(sys.argv) > 1 else "ws://IP_proxy:8107"
    sid = sys.argv[2] if len(sys.argv) > 2 else "mi_stream"
    asyncio.run(run(server, sid))

    #asyncio.run(run("ws://127.0.0.1:8108"))
    #asyncio.run(run("ws://85.219.31.65:8108"))
    # asyncio.run(run("ws://dronseetac.upc.edu:8108"))