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


async def display_track(track):
    print("Conectando a C#...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", 5000))

    print("Conectado a C#")

    while True:
        frame = await track.recv()

        img = frame.to_ndarray(format="bgr24")

        ret, jpeg = cv2.imencode(".jpg", img)
        data = jpeg.tobytes()

        print("FRAME ENVIADO")

        sock.sendall(struct.pack(">I", len(data)) + data)


async def run(server_url: str):
    config = RTCConfiguration(iceServers=[
        RTCIceServer(urls="stun:stun.l.google.com:19302")
    ])

    pc = RTCPeerConnection(configuration=config)

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