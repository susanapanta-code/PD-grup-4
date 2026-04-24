# Etiquetador YOLO de Drones

Este etiquetador genera archivos `.txt` en formato YOLO para entrenamiento de deteccion de drones.

## Caracteristicas

- Multiples cajas por imagen.
- Reanudacion: si existe etiqueta previa, se carga al abrir la imagen.
- Muestras negativas: guarda `.txt` vacio con la tecla `n`.
- Atajos de productividad: deshacer (`u`), limpiar (`c`), navegar (`a`/`d`).
- Validacion de cajas pequenas para evitar ruido en el dataset.

## Uso

```powershell
python "C:\Users\angel\OneDrive\Escritorio\8vo cuatri\PD-grup-4\Versión 3 y 4\InterfazEtiquetación.py"
```

## Smoke test rapido

```powershell
python "C:\Users\angel\OneDrive\Escritorio\8vo cuatri\PD-grup-4\Versión 3 y 4\test_interfaz_etiquetacion.py"
```

