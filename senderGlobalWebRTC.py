# sender.py
# Emisor: captura cámara y envía vídeo por WebRTC

import asyncio
import json
import cv2
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCIceCandidate
from aiortc import RTCConfiguration, RTCIceServer
from av import VideoFrame
from websockets import connect

ofertas = []

class CameraVideoTrack(VideoStreamTrack):
    def __init__(self, device=0):
        super().__init__()
        self.cap = cv2.VideoCapture(device)

        if not self.cap.isOpened():
            print("ERROR: No se pudo abrir la cámara")

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        ret, frame = self.cap.read()

        if not ret:
            print("No frame desde cámara")
            await asyncio.sleep(0.1)
            return await self.recv()

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base

        return video_frame


async def run(server_url: str):
    global ofertas, cameraTrack

    async with connect(server_url) as ws:
        print("Ya estoy conectado al proxy")

        await ws.send(json.dumps({
            "type": "registro",
            "role": "emisor"
        }))

        print("Ya me he registrado")

        async for raw in ws:
            print("Recibo algo del proxy")
            data = json.loads(raw)

            # NUEVO RECEPTOR
            if data.get("type") == "receptor":
                print("Un receptor necesita oferta")
                rid = data.get("id")

                config = RTCConfiguration(iceServers=[
                    RTCIceServer(urls="stun:stun.l.google.com:19302")
                ])

                pc = RTCPeerConnection(configuration=config)

                # ICE saliente
                @pc.on("icecandidate")
                async def on_ice(candidate):
                    if candidate:
                        print("Enviando ICE al receptor")

                        await ws.send(json.dumps({
                            "type": "ice",
                            "role": "emisor",
                            "id": rid,
                            "candidate": candidate.to_dict()
                        }))

                # Estado conexión
                @pc.on("connectionstatechange")
                async def on_state():
                    print("STATE:", pc.connectionState)

                pc.addTrack(cameraTrack)

                offer = await pc.createOffer()
                await pc.setLocalDescription(offer)

                ofertas.append({
                    "id": rid,
                    "pc": pc
                })

                await ws.send(json.dumps({
                    "type": "sdp",
                    "role": "emisor",
                    "id": rid,
                    "sdp": pc.localDescription.sdp,
                    "sdp_type": pc.localDescription.type
                }))

                print("Oferta enviada")

            # ANSWER
            elif data.get("type") == "sdp":
                rid = data.get("id")

                print("Respuesta del receptor:", rid)

                pc = next(o["pc"] for o in ofertas if o["id"] == rid)

                desc = RTCSessionDescription(
                    sdp=data["sdp"],
                    type=data["sdp_type"]
                )

                await pc.setRemoteDescription(desc)

            # ICE entrante
            elif data.get("type") == "ice" and data.get("role") == "receptor":
                rid = data.get("id")

                print("Recibo ICE del receptor")

                pc = next(o["pc"] for o in ofertas if o["id"] == rid)

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
    cameraTrack = CameraVideoTrack()

    asyncio.run(run("ws://127.0.0.1:8108"))
   # asyncio.run(run("ws://dronseetac.upc.edu:8108"))