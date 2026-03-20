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

HOST = "0.0.0.0"
PORT = 9999
CAMERA_ID = 0
TARGET_FPS = 20


class OpenCVCameraTrack(VideoStreamTrack):
    """Captura de camara compartida para todos los clientes WebRTC."""

    def __init__(self, camera_id):
        super().__init__()
        # En Windows, usar DSHOW suele ser mas rapido y compatible para webcams
        if platform.system() == "Windows":
            self._cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
        else:
            self._cap = cv2.VideoCapture(camera_id)

        if not self._cap.isOpened():
            # Intentar fallback sin backend especifico si falla
            self._cap = cv2.VideoCapture(camera_id)

        if not self._cap.isOpened():
            raise RuntimeError(f"No se pudo abrir la camara {camera_id}")

        self._frame_period_s = 1.0 / float(TARGET_FPS)
        self._last_frame_ts = 0.0

    async def recv(self):
        # Limita FPS para no saturar CPU con multiples consumidores.
        now = time.time()
        delta = now - self._last_frame_ts
        if delta < self._frame_period_s:
            await asyncio.sleep(self._frame_period_s - delta)

        pts, time_base = await self.next_timestamp()
        ok, frame = self._cap.read()
        if not ok:
            await asyncio.sleep(0.03)
            ok, frame = self._cap.read()
            if not ok:
                raise RuntimeError("Fallo leyendo frame de camara")

        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        self._last_frame_ts = time.time()
        return video_frame

    def close(self):
        try:
            self._cap.release()
        except Exception:
            pass


class WebRTCCameraHub:
    """Acepta multiples clientes de señalizacion TCP y crea una sesion por cliente."""

    def __init__(self, host, port, camera_id):
        self._host = host
        self._port = int(port)
        self._camera_track = OpenCVCameraTrack(camera_id)
        self._relay = MediaRelay()
        self._pcs = set()

    async def _recv_description(self, reader):
        line = await asyncio.wait_for(reader.readline(), timeout=20.0)
        if not line:
            return None
        payload = json.loads(line.decode("utf-8", errors="ignore"))
        sdp = payload.get("sdp")
        sdp_type = payload.get("type")
        if not sdp or not sdp_type:
            return None
        return RTCSessionDescription(sdp=sdp, type=sdp_type)

    async def _send_description(self, writer, description):
        payload = {"sdp": description.sdp, "type": description.type}
        writer.write((json.dumps(payload) + "\n").encode("utf-8"))
        await writer.drain()

    async def _handle_client(self, reader, writer):
        addr = writer.get_extra_info("peername")
        print(f"[CameraService] Cliente conectado: {addr}")

        pc = RTCPeerConnection()
        self._pcs.add(pc)
        pc.addTrack(self._relay.subscribe(self._camera_track))

        finished = asyncio.Event()

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"[CameraService] {addr} estado={pc.connectionState}")
            if pc.connectionState in ("failed", "closed", "disconnected"):
                finished.set()

        try:
            # Modo compatible con receptores actuales: el servicio envia oferta.
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            await self._send_description(writer, pc.localDescription)

            answer = await self._recv_description(reader)
            if answer is None or answer.type != "answer":
                raise RuntimeError("Respuesta WebRTC invalida")

            await pc.setRemoteDescription(answer)
            print(f"[CameraService] Streaming activo para {addr}")

            while not finished.is_set():
                if reader.at_eof():
                    await asyncio.sleep(0.5)
                else:
                    await asyncio.sleep(0.25)
        except Exception as exc:
            print(f"[CameraService] Error con {addr}: {exc}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            await pc.close()
            self._pcs.discard(pc)
            print(f"[CameraService] Cliente liberado: {addr}")

    async def run(self):
        server = await asyncio.start_server(self._handle_client, self._host, self._port)
        print(f"[CameraService] Escuchando en {self._host}:{self._port}")
        async with server:
            await server.serve_forever()

    async def shutdown(self):
        for pc in list(self._pcs):
            try:
                await pc.close()
            except Exception:
                pass
        self._pcs.clear()
        self._camera_track.close()


async def main():
    hub = WebRTCCameraHub(HOST, PORT, CAMERA_ID)
    try:
        await hub.run()
    finally:
        await hub.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[CameraService] Finalizado")
