from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _list_images(images_dir: Path) -> list[Path]:
    return sorted([p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS])


def _ensure_dirs(dataset_dir: Path) -> None:
    for sub in ("images/train", "images/val", "images/test", "labels/train", "labels/val", "labels/test"):
        (dataset_dir / sub).mkdir(parents=True, exist_ok=True)


def _clear_previous_splits(dataset_dir: Path) -> None:
    for split in ("train", "val", "test"):
        for kind in ("images", "labels"):
            split_dir = dataset_dir / kind / split
            if split_dir.exists():
                for f in split_dir.iterdir():
                    if f.is_file():
                        f.unlink()


def _split_counts(total: int, val_ratio: float, test_ratio: float) -> tuple[int, int, int]:
    if total <= 0:
        return 0, 0, 0

    val_count = int(total * val_ratio)
    test_count = int(total * test_ratio)

    if total >= 3 and val_count == 0:
        val_count = 1
    if total >= 6 and test_ratio > 0 and test_count == 0:
        test_count = 1

    if val_count + test_count >= total:
        overflow = (val_count + test_count) - (total - 1)
        if overflow > 0:
            test_count = max(0, test_count - overflow)
        if val_count + test_count >= total:
            val_count = max(1, total - test_count - 1)

    train_count = total - val_count - test_count
    return train_count, val_count, test_count


def _copy_item(image_path: Path, src_labels_dir: Path, dst_images_dir: Path, dst_labels_dir: Path) -> None:
    label_src = src_labels_dir / f"{image_path.stem}.txt"
    label_dst = dst_labels_dir / f"{image_path.stem}.txt"

    shutil.copy2(image_path, dst_images_dir / image_path.name)

    if label_src.exists():
        shutil.copy2(label_src, label_dst)
    else:
        # Negativa: YOLO acepta .txt vacio.
        label_dst.write_text("", encoding="utf-8")


def split_dataset(dataset_dir: Path, val_ratio: float, test_ratio: float, seed: int) -> None:
    images_dir = dataset_dir / "images"
    labels_dir = dataset_dir / "labels"

    if not images_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta de imagenes: {images_dir}")
    if not labels_dir.exists():
        labels_dir.mkdir(parents=True, exist_ok=True)

    images = _list_images(images_dir)
    if not images:
        raise RuntimeError("No hay imagenes para hacer split en dataset/images")

    _ensure_dirs(dataset_dir)
    _clear_previous_splits(dataset_dir)

    rng = random.Random(seed)
    rng.shuffle(images)

    train_count, val_count, test_count = _split_counts(len(images), val_ratio, test_ratio)

    train_items = images[:train_count]
    val_items = images[train_count:train_count + val_count]
    test_items = images[train_count + val_count:train_count + val_count + test_count]

    for img in train_items:
        _copy_item(img, labels_dir, dataset_dir / "images/train", dataset_dir / "labels/train")
    for img in val_items:
        _copy_item(img, labels_dir, dataset_dir / "images/val", dataset_dir / "labels/val")
    for img in test_items:
        _copy_item(img, labels_dir, dataset_dir / "images/test", dataset_dir / "labels/test")

    print(f"Split completado: train={len(train_items)}, val={len(val_items)}, test={len(test_items)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera split train/val/test para YOLO")
    parser.add_argument("--dataset", default="dataset", help="Carpeta dataset base")
    parser.add_argument("--val-ratio", type=float, default=0.2, help="Proporcion para validacion")
    parser.add_argument("--test-ratio", type=float, default=0.1, help="Proporcion para test")
    parser.add_argument("--seed", type=int, default=42, help="Semilla de aleatoriedad")
    args = parser.parse_args()

    if not (0.0 <= args.val_ratio < 1.0):
        raise ValueError("val-ratio debe estar entre 0 y 1")
    if not (0.0 <= args.test_ratio < 1.0):
        raise ValueError("test-ratio debe estar entre 0 y 1")
    if args.val_ratio + args.test_ratio >= 1.0:
        raise ValueError("val-ratio + test-ratio debe ser menor que 1")

    split_dataset(Path(args.dataset), args.val_ratio, args.test_ratio, args.seed)


if __name__ == "__main__":
    main()

