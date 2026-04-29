
import cv2
import argparse
from pathlib import Path
from ultralytics import YOLO

def parse_args():
    parser = argparse.ArgumentParser(description="Detección en tiempo real usando el modelo entrenado")
    parser.add_argument("--model", default="runs/dron_yolov8n/weights/best.pt", help="Ruta al modelo entrenado (ej. best.pt)")
    parser.add_argument("--source", default="http://10.154.255.106:8080/video", help="Fuente de video (0 para webcam, URL para cámara web o ruta a archivo)")
    parser.add_argument("--conf", type=float, default=0.5, help="Nivel de confianza mínimo para mostrar detecciones")
    return parser.parse_args()

def main():
    args = parse_args()

    # Intentar parsear el origen a entero si es un número (para la webcam)
    source = args.source
    if str(source).isdigit():
        source = int(source)

    print(f"Cargando modelo desde {args.model}...")
    try:
        model = YOLO(args.model)
    except Exception as e:
        print(f"Error al cargar el modelo: {e}")
        return

    print("Iniciando captura de video...")
    cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        print(f"Error: No se pudo abrir la fuente de video {source}")
        return

    print("Presiona 'q' para salir.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("No se pudo leer el frame del video. Terminando...")
            break

        # Realizar la predicción sobre el frame actual
        results = model.predict(frame, conf=args.conf, verbose=False)

        # Obtener el frame con las detecciones dibujadas ("annotated_frame")
        annotated_frame = results[0].plot()

        # Mostrar el resultado por pantalla
        cv2.imshow("Deteccion de dron", annotated_frame)

        # Romper el bucle si se presiona la tecla 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Liberar recursos
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

