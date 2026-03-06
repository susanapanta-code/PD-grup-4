## Implementación de funcionalidades extra
Para la versión de python nuevas funcionalidades han sido añadidas, incluyendo botones y datos de telemetría. 

Nuevos Botones: 
- Girar "clockwise" y "counterclockwise" 90º.
- Desarmar.

Nuevos datos de telemetría:
- Velocidad.
- Latitud y longitud.
- Modo de Vuelo.

Nuevas funcionalidades:
- Ir a posición [lat, lon].
- Ir a altura [alt].

Para la versión de C# se ha implementado un botón nuevo que permite poner el dron en modo guiado.

En el reconocimiento de objetos se ha implementado el reconocimiento de teléfonos móviles, perros y paraguas. Además, se ha establecido el procesamiento de 1 de cada 25 frames para encontrar un equilibrio entre fluidez de la cámara y la velocidad de detección del objeto.
