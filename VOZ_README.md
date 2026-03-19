# 🎤 Control de Voz - Guía Rápida

## ¿Dónde está disponible?

**Servidor HTTP (puerto 5000)** - serverHTTP.py
- ✅ Control de voz
- ✅ Botones de control
- ✅ Telemetría

**Servidor MQTT (puerto 5002)** - serverMQTT.py
- ✅ Control de voz
- ✅ Mapa en tiempo real (Leaflet)
- ✅ Video streaming (WebRTC)
- ✅ Botones de control

## Comandos de Voz

| Comando | Palabras Clave |
|---------|---|
| ✈️ Despegar | "despega", "despegar" |
| 🛬 Aterrizar | "aterriza", "tierra" |
| 🏠 Regresar | "regresa", "vuelve", "rtl" |
| ⬆️ Norte | "norte", "adelante" |
| ⬇️ Sur | "sur", "atrás" |
| ➡️ Este | "este", "derecha" |
| ⬅️ Oeste | "oeste", "izquierda" |
| ⏹️ Parar | "para", "stop" |

## Cómo Usar

### Servidor HTTP
```bash
python serverHTTP.py
# Abre http://localhost:5000
```

### Servidor MQTT
```bash
python serverMQTT.py
# Abre http://localhost:5002
```

### En ambos:
1. Conecta con el dron
2. Ingresa altura (metros)
3. Clic en botón 🎤
4. Habla en español

## Modificado
- `templates/indexHTTP.html` - Web Speech API agregada
- `templates/indexMQTT.html` - Web Speech API agregada


