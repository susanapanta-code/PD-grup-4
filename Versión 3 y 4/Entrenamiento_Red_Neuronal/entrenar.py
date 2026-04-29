from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    import torch
    default_device = "0" if torch.cuda.is_available() else "cpu"
    parser = argparse.ArgumentParser(description="Entrenamiento YOLO profesional para deteccion de dron")
    parser.add_argument("--model", default="yolov8n.pt", help="Checkpoint base de YOLO")
    parser.add_argument("--data", default="data.yaml", help="Archivo YAML del dataset")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default=default_device, help="cpu, 0, 0,1...")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--name", default="dron_yolov8n")
    parser.add_argument("--project", default="runs")
    parser.add_argument("--exist-ok", action="store_true", help="Permite sobrescribir nombre de experimento")
    return parser.parse_args()


def validar_dataset_simple(dataset_dir: Path) -> None:
    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"

    if not images_dir.exists():
        raise SystemExit(f"No existe la carpeta: {images_dir}")
    if not labels_dir.exists():
        raise SystemExit(f"No existe la carpeta: {labels_dir}")

    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images = [p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in image_exts]

    if not images:
        raise SystemExit("No hay imagenes en dataset/images")

    labels_missing = []
    for img in images:
        txt = labels_dir / f"{img.stem}.txt"
        if not txt.exists():
            labels_missing.append(img.name)

    print(f"Resumen dataset: imagenes={len(images)}, faltan_labels={len(labels_missing)}")
    if labels_missing:
        print("Aviso: faltan labels para estas imagenes (se consideran negativas si creas .txt vacio):")
        for name in labels_missing[:10]:
            print(f"- {name}")
        if len(labels_missing) > 10:
            print(f"... y {len(labels_missing) - 10} mas")


def main() -> None:
    from multiprocessing import freeze_support
    freeze_support()
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    dataset_dir = base_dir / "dataset"
    data_yaml = base_dir / args.data

    print("Validando dataset (distribucion simple)...")
    validar_dataset_simple(dataset_dir)

    print("Iniciando entrenamiento...")
    model = YOLO(args.model)

    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        seed=args.seed,
        deterministic=True,
        project=str(base_dir / args.project),
        name=args.name,
        exist_ok=args.exist_ok,
        plots=True,
    )

    save_dir = getattr(results, "save_dir", "(no disponible)")
    print(f"Entrenamiento finalizado. Resultados en: {save_dir}")


if __name__ == "__main__":
    main()