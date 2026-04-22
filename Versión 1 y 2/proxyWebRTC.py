# signaling_server.py
import asyncio
import json
import logging
#from websockets import serve, WebSocketServerProtocol
from websockets import serve


receptores = []
wsEmisor = None

async def handler(ws):
    global wsEmisor, receptores

    print("Nueva conexión ")

    try:
        async for raw in ws:
                print("Recibo algo")
                data = json.loads(raw)
                print(data)
                # print("Recibo:", data.get("type"), data.get("role"))

                # Registro emisor
                if data.get("type") == "registro" and data.get("role") == "emisor":
                    print ("Es el emisor que se registra")
                    wsEmisor = ws
                    # Avisar a receptores existentes
                    if len (receptores) > 0:
                        print ("Hay receptores esperando")
                        for indice, receptor in enumerate(receptores):
                            print("Aviso al emisor para que prepare una oferta para este cliente: ", indice)
                            await wsEmisor.send(json.dumps({
                                "type": "receptor",
                                "id": indice
                            }))

                # Nuevo receptor
                if data.get("type") == "peticion":
                    print ("Es una petición de recepción")
                    receptores.append(ws)
                    # rid = len(receptores) - 1
                    if wsEmisor:
                        print ("El emisor ya está registrado")
                        indice = len(receptores)-1
                        print ("Aviso al emisor para que prepare una oferta para este cliente: ", indice)
                        await wsEmisor.send(json.dumps({
                            "type": "receptor",
                            "id": indice
                        }))
                    else:
                        print ("El emisor aun no se ha conectado")

                # SDP DEL EMISOR → RECEPTOR
                if data.get("type") == "sdp" and data.get("role") == "emisor":
                    id = data.get("id")
                    # print("Oferta para receptor:", id)
                    print ("Recibo una oferta para el cliente: ",data.get("id") )
                    cliente = receptores[id]
                    # if id < len(receptores):
                    await cliente.send (raw)
                    print("He re-enviado la oferta al cliente implicado")

                # SDP DEL RECEPTOR → EMISOR
                elif data.get("type") == "sdp" and data.get("role") == "receptor":
                    # print("Answer del receptor")
                    id = receptores.index (ws)
                    print ("Recibo aceptación del receptor: ", id)
                    print ("Agrego el id al mensaje, que re-trasmito al emisor")
                    data["id"] = id
                    await wsEmisor.send(json.dumps(data))
                    #if wsEmisor:
                        #await wsEmisor.send(raw)
                    print ("Aceptación enviada al emisor")

                elif data.get("type") == "ice" and data.get("role") == "receptor":
                    id = receptores.index(ws)
                    print("Recibo ice del receptor: ", id)
                    print("Agrego el id al mensaje, que re-trasmito al emisor")
                    data["id"] = id
                    await wsEmisor.send(json.dumps(data))
                    print("ICE enviado al emisor")
                elif data.get("type") == "ice" and data.get("role") == "emisor":
                    print("Recibo ice del emisor. Se lo envio a todos los receptores ")
                    for receptor in receptores:
                        print("Aviso al emisor para que prepare una oferta para este cliente: ", indice)
                        await receptor.send(raw)

                # ----------ICE (REENVÍO DIRECTO )----------
                #elif data.get("type") == "ice":
                    #print("Reenviando ICE")
                    # receptor → emisor
                    #if data.get("role") == "receptor":
                        #if wsEmisor:
                            #await wsEmisor.send(raw)
                    # emisor → receptores
                    #elif data.get("role") == "emisor":
                        #for r in receptores:
                            #await r.send(raw)
                #------------------------------------------------
    except Exception as e:
        print("Error:", e)

    #----------------------------------------
    finally:
        print("Cliente desconectado")

        # limpiar conexiones
        if ws in receptores:
            receptores.remove(ws)

        if ws == wsEmisor:
            wsEmisor = None

    #----------------------------------------

async def main():
    host = "0.0.0.0"
    port = 8108
    async with serve(handler, host, port):
        print ("Proxy en marcha en:", host, port)
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
