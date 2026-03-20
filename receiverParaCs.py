# receiverParaCs.py
# Recibe vídeo WebRTC y lo envía a C# por socket

import asyncio
import json
import cv2
import socket
import struct
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc import RTCConfiguration, RTCIceServer
from websockets import connect
import torch
import numpy as np
import threading

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

    def setObject(self, objectID):
        print("Nuevo objeto:", objectID)
        self.objectID = objectID

async def display_track(track):
    global video_receiver
    print("Conectando a C#...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", 5000))

    print("Conectado a C#")
    frame_count = 0
    detectado = False
    rect = None

    while True:
        frame = await track.recv()

        img = frame.to_ndarray(format="bgr24")

        frame_count += 1

        # DETECCIÓN
        if video_receiver.objectID is not None:
            if frame_count % 10 == 0:  # no procesar todos (mejora rendimiento)
                detectado, rect = video_receiver.detector.detect(img, video_receiver.objectID)

            if detectado and rect:
                x1, y1, x2, y2 = rect
                cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 255), 2)
                cv2.putText(img, str(video_receiver.objectID),
                            (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (255, 0, 255), 2)

        # ENVIAR A C#
        ret, jpeg = cv2.imencode(".jpg", img)
        data = jpeg.tobytes()

        print("FRAME ENVIADO")

        sock.sendall(struct.pack(">I", len(data)) + data)


async def run(server_url: str):
    config = RTCConfiguration(iceServers=[
        RTCIceServer(urls="stun:stun.l.google.com:19302")
    ])

    pc = RTCPeerConnection(configuration=config)

    global video_receiver
    video_receiver = VideoReceiver()

    threading.Thread(
        target=socket_listener,
        args=(video_receiver,),
        daemon=True
    ).start()

    @pc.on("icecandidate")
    async def on_ice(candidate):
        if candidate:
            print("Enviando ICE al sender")

            await ws.send(json.dumps({
                "type": "ice",
                "role": "receptor",
                "candidate": candidate.to_dict()
            }))

    @pc.on("connectionstatechange")
    async def on_state():
        print("STATE RECEIVER:", pc.connectionState)

    @pc.on("track")
    def on_track(track):
        print("Track recibido:", track.kind)

        if track.kind == "video":
            asyncio.create_task(display_track(track))

    async with connect(server_url) as ws:
        print("Conectado al proxy")

        await ws.send(json.dumps({
            "type": "peticion"
        }))

        print("Esperando oferta...")

        async for raw in ws:
            data = json.loads(raw)

            if data.get("type") == "sdp":
                print("Oferta recibida")

                desc = RTCSessionDescription(
                    sdp=data["sdp"],
                    type=data["sdp_type"]
                )

                await pc.setRemoteDescription(desc)

                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)

                await ws.send(json.dumps({
                    "type": "sdp",
                    "role": "receptor",
                    "id": 0,  # 🔥 IMPORTANTE
                    "sdp": pc.localDescription.sdp,
                    "sdp_type": pc.localDescription.type
                }))

                print("Answer enviada")

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


if __name__ == "__main__":
    asyncio.run(run("ws://127.0.0.1:8108"))
    # asyncio.run(run("ws://dronseetac.upc.edu:8108"))