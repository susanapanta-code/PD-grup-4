from __future__ import annotations

import argparse
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS


def _check_label_file(label_path: Path, nc: int) -> list[str]:
    errors: list[str] = []

    if not label_path.exists():
        errors.append(f"Falta label: {label_path.name}")
        return errors

    content = label_path.read_text(encoding="utf-8").strip()
    if not content:
        return errors

    for i, line in enumerate(content.splitlines(), start=1):
        parts = line.split()
        if len(parts) != 5:
            errors.append(f"{label_path.name}:{i} formato invalido (esperado 5 columnas)")
            continue

        try:
            cls = int(parts[0])
            x, y, w, h = map(float, parts[1:])
        except ValueError:
            errors.append(f"{label_path.name}:{i} contiene valores no numericos")
            continue

        if not (0 <= cls < nc):
            errors.append(f"{label_path.name}:{i} clase fuera de rango: {cls}")

        for name, value in (("x", x), ("y", y), ("w", w), ("h", h)):
            if not (0.0 <= value <= 1.0):
                errors.append(f"{label_path.name}:{i} {name} fuera de [0,1]: {value}")

        if w <= 0.0 or h <= 0.0:
            errors.append(f"{label_path.name}:{i} ancho/alto deben ser > 0")

    return errors


def validate_dataset(dataset_dir: Path, nc: int = 1) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    stats = {
        "images_train": 0,
        "images_val": 0,
        "images_test": 0,
        "labels_empty": 0,
    }

    for split in ("train", "val", "test"):
        img_dir = dataset_dir / "images" / split
        lbl_dir = dataset_dir / "labels" / split

        if split in ("train", "val"):
            if not img_dir.exists():
                errors.append(f"No existe carpeta requerida: {img_dir}")
            if not lbl_dir.exists():
                errors.append(f"No existe carpeta requerida: {lbl_dir}")

        if not img_dir.exists() or not lbl_dir.exists():
            continue

        images = [p for p in img_dir.iterdir() if _is_image(p)]
        stats[f"images_{split}"] = len(images)

        for image in images:
            label_path = lbl_dir / f"{image.stem}.txt"
            label_errors = _check_label_file(label_path, nc)
            errors.extend(label_errors)

            if label_path.exists() and not label_path.read_text(encoding="utf-8").strip():
                stats["labels_empty"] += 1

        for label in lbl_dir.glob("*.txt"):
            expected_image = None
            for ext in IMAGE_EXTS:
                candidate = img_dir / f"{label.stem}{ext}"
                if candidate.exists():
                    expected_image = candidate
                    break
            if expected_image is None:
                errors.append(f"Label huerfano sin imagen: {label}")

    if stats["images_train"] == 0:
        errors.append("No hay imagenes en train")
    if stats["images_val"] == 0:
        errors.append("No hay imagenes en val")

    return errors, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida estructura y etiquetas YOLO del dataset")
    parser.add_argument("--dataset", default="dataset", help="Carpeta dataset base")
    parser.add_argument("--nc", type=int, default=1, help="Numero de clases")
    args = parser.parse_args()

    errors, stats = validate_dataset(Path(args.dataset), nc=args.nc)

    print("Resumen dataset:")
    for key, value in stats.items():
        print(f"- {key}: {value}")

    if errors:
        print("\nErrores encontrados:")
        for err in errors:
            print(f"- {err}")
        raise SystemExit(1)

    print("\nDataset valido para entrenamiento.")


if __name__ == "__main__":
    main()

