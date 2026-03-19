###########  INSTALAR #########################
# opencv-python
# aiortc
# aiohttp
# aiohttp_cors
###############################################

import argparse
import asyncio
import json
import logging
import os
import platform
import ssl

from aiohttp import web
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaPlayer, MediaRelay
from av import VideoFrame
import cv2
import fractions
import time

ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = set()
relay = None

class CameraVideoStreamTrack(VideoStreamTrack):
    """
    Un track de video que lee de la cámara usando OpenCV
    """
    def __init__(self, camera_id=0):
        super().__init__()
        self.camera_id = camera_id
        self.cap = cv2.VideoCapture(camera_id)
        # Configurar resolución si es necesario (opcional)
        # self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        # self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.pts = 0

    async def recv(self):
        self.pts += 1
        ret, frame = self.cap.read()

        if not ret:
            # Si falla la lectura, enviamos un frame negro o reintentamos
            # Para simplificar, generamos error o frame vacio
            # print("Error leyendo cámara")
            # Idealmente manejar reconexión
            pass

        # Convertir BGR (OpenCV) a RGB
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Crear VideoFrame
        new_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        new_frame.pts = self.pts
        new_frame.time_base = fractions.Fraction(1, 30)

        # Simular delay de frame rate (30fps aprox) si el bucle es muy rápido
        # await asyncio.sleep(0.01)

        return new_frame

    def stop(self):
        if self.cap.isOpened():
            self.cap.release()

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    # Abrir cámara. Nota: Esto abre la cámara CADA VEZ que alguien conecta.
    # Si queremos compartir la misma cámara entre varios, necesitamos un mecanismo de relay/proxy,
    # pero para V2 monousuario esto vale.
    video = CameraVideoStreamTrack(0)
    pc.addTrack(video)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )

async def on_shutdown(app):
    # Cerrar conexiones activas
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC Webcam Demo")
    parser.add_argument("--port", type=int, default=8080, help="Port for HTTP server (default: 8080)")
    args = parser.parse_args()

    app = web.Application()
    app.on_shutdown.append(on_shutdown)

    # Configurar rutas
    app.router.add_post("/offer", offer)

    # Configurar CORS para permitir acceso desde la WebApp (puerto distinto)
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })

    for route in list(app.router.routes()):
        cors.add(route)

    print(f"CameraService escuchando en http://0.0.0.0:{args.port}")
    web.run_app(app, access_log=None, port=args.port)

