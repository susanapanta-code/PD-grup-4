# proxyWebRTC.py
# Servidor de señalización WebRTC (SOLO reenvía mensajes)

import asyncio
import json
from websockets import serve

receptores = []
wsEmisor = None


async def handler(ws):
    global wsEmisor, receptores

    print("Nueva conexión")

    try:
        async for raw in ws:
            data = json.loads(raw)

            print("Recibo:", data.get("type"), data.get("role"))

            # REGISTRO EMISOR
            if data.get("type") == "registro" and data.get("role") == "emisor":
                print("Emisor registrado")
                wsEmisor = ws

                # Avisar a receptores existentes
                for i, receptor in enumerate(receptores):
                    await wsEmisor.send(json.dumps({
                        "type": "receptor",
                        "id": i
                    }))

            # NUEVO RECEPTOR
            elif data.get("type") == "peticion":
                print("Nuevo receptor")

                receptores.append(ws)
                rid = len(receptores) - 1

                if wsEmisor:
                    await wsEmisor.send(json.dumps({
                        "type": "receptor",
                        "id": rid
                    }))

            # SDP DEL EMISOR → RECEPTOR
            elif data.get("type") == "sdp" and data.get("role") == "emisor":
                rid = data.get("id")
                print("Oferta para receptor:", rid)

                if rid < len(receptores):
                    await receptores[rid].send(raw)

            # SDP DEL RECEPTOR → EMISOR
            elif data.get("type") == "sdp" and data.get("role") == "receptor":
                print("Answer del receptor")

                if wsEmisor:
                    await wsEmisor.send(raw)

            # ICE (REENVÍO DIRECTO 🔥)
            elif data.get("type") == "ice":
                print("Reenviando ICE")

                # receptor → emisor
                if data.get("role") == "receptor":
                    if wsEmisor:
                        await wsEmisor.send(raw)

                # emisor → receptores
                elif data.get("role") == "emisor":
                    for r in receptores:
                        await r.send(raw)

    except Exception as e:
        print("Error:", e)

    finally:
        print("Cliente desconectado")

        # limpiar conexiones
        if ws in receptores:
            receptores.remove(ws)

        if ws == wsEmisor:
            wsEmisor = None


async def main():
    host = "0.0.0.0"
    port = 8108

    print(f"Proxy en marcha en {host}:{port}")

    async with serve(handler, host, port):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())