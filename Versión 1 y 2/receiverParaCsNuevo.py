import asyncio
import json
import cv2
from aiortc import RTCPeerConnection, RTCSessionDescription
import socket
import struct
import torch
import threading
import concurrent.futures
import time

# ================= SOCKET PARA C# =================

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

# ================= DETECTOR =================

class Detector:
    def __init__(self):
        print("Cargando YOLO...")
        self.model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
        self.model.eval()

    def detect(self, frame, objectID):
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.model(img_rgb)

        for *box, conf, cls in results.xyxy[0]:
            if int(cls.item()) == objectID:
                x1, y1, x2, y2 = map(int, box)
                return True, [x1, y1, x2, y2]

        return False, None

# ================= VIDEO RECEIVER =================

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

# ================= DISPLAY =================

async def display_track(track):
    global video_receiver

    print("Conectando a C#...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", 5000))
    print("Conectado a C#")

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    while True:
        try:
            frame = await track.recv()
            img = frame.to_ndarray(format="bgr24")

            # DETECCIÓN
            if video_receiver.objectID is not None and not video_receiver.detecting:
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

                if time.time() - t < 0.5 and detectado and rect:
                    x1, y1, x2, y2 = rect
                    scale_x = img.shape[1] / 320
                    scale_y = img.shape[0] / 240

                    x1 = int(x1 * scale_x)
                    y1 = int(y1 * scale_y)
                    x2 = int(x2 * scale_x)
                    y2 = int(y2 * scale_y)

                    cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 255), 2)

            # Enviar frame a C#
            _, jpeg = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            data = jpeg.tobytes()

            sock.sendall(struct.pack(">I", len(data)) + data)

        except Exception as e:
            print("Error:", e)
            break

# ================= CONEXIÓN A CameraService =================

async def run(camera_ip="127.0.0.1", port=9999):

    pc = RTCPeerConnection()

    global video_receiver
    video_receiver = VideoReceiver()

    threading.Thread(target=socket_listener, args=(video_receiver,), daemon=True).start()

    @pc.on("track")
    def on_track(track):
        print("Track recibido:", track.kind)
        if track.kind == "video":
            asyncio.create_task(display_track(track))

    # 🔥 Conexión TCP al CameraService
    reader, writer = await asyncio.open_connection(camera_ip, port)
    print(f"Conectado a CameraService en {camera_ip}:{port}")

    # 1️⃣ Recibir OFFER
    data = await reader.readline()
    offer_json = json.loads(data.decode())

    offer = RTCSessionDescription(
        sdp=offer_json["sdp"],
        type=offer_json["type"]
    )

    await pc.setRemoteDescription(offer)

    # 2️⃣ Crear ANSWER
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # 3️⃣ Enviar ANSWER
    response = json.dumps({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }) + "\n"

    writer.write(response.encode())
    await writer.drain()

    print("Answer enviada → esperando vídeo...")

    # Mantener conexión
    while True:
        await asyncio.sleep(1)

# ================= MAIN =================

if __name__ == "__main__":
    import sys

    #usar si el CameraService se ejecuta en la misma máquina, sino poner la IP del portatil que tiene el CameraService.
    ip = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    #ip = sys.argv[1] if len(sys.argv) > 1 else "10.192.120.14"

    asyncio.run(run(ip, 9999))