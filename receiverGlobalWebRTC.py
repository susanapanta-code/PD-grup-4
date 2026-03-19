# receiver.py
# Archivo: ./receiver.py
# Receptor: espera offer, crea answer y muestra vídeo.

import asyncio
import json
import cv2
from aiortc import RTCPeerConnection, RTCIceCandidate, RTCSessionDescription, VideoStreamTrack, RTCConfiguration, RTCIceServer
from websockets import connect

def dict_to_ice_candidate(cand: dict):
    """Convierte dict recibido (del navegador) a RTCIceCandidate de aiortc"""
    if cand is None:
        return None
    sdpMid = cand.get("sdpMid") or "0"
    sdpMLineIndex = cand.get("sdpMLineIndex") or 0
    return RTCIceCandidate(
        candidate=cand.get("candidate"),
        sdpMid=sdpMid,
        sdpMLineIndex=sdpMLineIndex
    )



async def display_track(track):
    while True:
        frame = await track.recv()
        img = frame.to_ndarray(format="bgr24")

        cv2.imshow("Receiver2", img)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cv2.destroyAllWindows()

async def run(server_url: str, stream_id: str):
    config = RTCConfiguration(iceServers=[
        RTCIceServer(urls="stun:stun.relay.metered.ca:80"),
        RTCIceServer(urls="turn:standard.relay.metered.ca:80",
                     username="337f189c0bf26e1022e19f05",
                     credential="pSwi01maZzQZTUAf")
    ])
    pc = RTCPeerConnection(config)


    print ("He creado la estructura de datos")

    @pc.on("icecandidate")
    async def on_ice(candidate):
        if candidate:
            cjson = candidate.to_dict()
            await ws.send(json.dumps({
                "type": "ice",
                "role": "receptor",
                "candidate": cjson
            }))
            print("Acabo de enviar ICE")
        else:
            # End-of-candidates
            await ws.send(json.dumps({
                "type": "ice",
                "role": "receptor",
                "candidate": None
            }))

    @pc.on("track")
    def on_track(track):
        print("Track recibido:", track.kind)
        if track.kind == "video":
            asyncio.create_task(display_track(track))

    async with connect(server_url) as ws:
        print ("Ya estoy conectado al proxy")
        await ws.send(json.dumps({"type": "peticion"}))
        print("Ya he enviado mi petición de conexión. Espero oferta ....")

        async for raw in ws:
            print ("Recibo algo del server")
            data = json.loads(raw)
            if data.get("type") == "sdp":
                print ("Es la oferta del emisor")
                desc = RTCSessionDescription(sdp=data["sdp"], type=data["sdp_type"])
                await pc.setRemoteDescription(desc)
                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)
                print ("Ya tengo preparada la respuesta")
                await ws.send(json.dumps({"type": "sdp", "role": "receptor", "stream_id": stream_id, "sdp": pc.localDescription.sdp, "sdp_type": pc.localDescription.type}))
                print("Respuesta enviada")

            if data.get("type") == "ice" and data.get("role") == "emisor":
                idx = data.get("id")
                print("Recibo ice del emisor: ", idx)
                print(data)


                cand = data.get("candidate")
                if not cand:
                    try:
                        await pc.addIceCandidate(None)
                    except Exception:
                        pass
                    continue

                # Convertir dict -> RTCIceCandidate
                try:
                    rtc_cand = dict_to_ice_candidate(cand)
                    await pc.addIceCandidate(rtc_cand)
                    print(f"[ICE] candidato añadido para receptor {idx}")
                except Exception as e:
                    print("Error añadiendo candidate:", e)
                continue



if __name__ == "__main__":
    server ="ws://dronseetac.upc.edu:8108"
    #server ="ws://127.0.0.1:8108"
    sid = "mi_stream"
    asyncio.run(run(server, sid))
