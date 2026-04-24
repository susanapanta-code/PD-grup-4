import cv2
import glob
import os

# ================= CONFIGURACION =================
CARPETA_BASE = "dataset"
CARPETA_ENTRADA = os.path.join(CARPETA_BASE, "images")
CARPETA_SALIDA = os.path.join(CARPETA_BASE, "labels")
CLASE_DRON = 0
EXTENSIONES = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp")
VENTANA = "Etiquetador de Drones (YOLO)"
MIN_LADO_CAJA_PX = 4
MAX_VIEW_WIDTH = 1600
MAX_VIEW_HEIGHT = 900


def clamp(valor, minimo, maximo):
    return max(minimo, min(valor, maximo))


def normalizar_caja(x1, y1, x2, y2, ancho_img, alto_img):
    x1, x2 = sorted((clamp(x1, 0, ancho_img - 1), clamp(x2, 0, ancho_img - 1)))
    y1, y2 = sorted((clamp(y1, 0, alto_img - 1), clamp(y2, 0, alto_img - 1)))

    ancho = x2 - x1
    alto = y2 - y1
    if ancho < MIN_LADO_CAJA_PX or alto < MIN_LADO_CAJA_PX:
        return None

    x_centro = ((x1 + x2) / 2.0) / ancho_img
    y_centro = ((y1 + y2) / 2.0) / alto_img
    w = ancho / ancho_img
    h = alto / alto_img
    return x_centro, y_centro, w, h


def yolo_a_pixels(xc, yc, w, h, ancho_img, alto_img):
    x_c = xc * ancho_img
    y_c = yc * alto_img
    ancho = w * ancho_img
    alto = h * alto_img
    x1 = int(clamp(x_c - ancho / 2, 0, ancho_img - 1))
    y1 = int(clamp(y_c - alto / 2, 0, alto_img - 1))
    x2 = int(clamp(x_c + ancho / 2, 0, ancho_img - 1))
    y2 = int(clamp(y_c + alto / 2, 0, alto_img - 1))
    return x1, y1, x2, y2


class EtiquetadorYOLO:
    def __init__(self):
        os.makedirs(CARPETA_SALIDA, exist_ok=True)

        self.imagenes = self._listar_imagenes()
        if not self.imagenes:
            raise FileNotFoundError(f"No se encontraron imagenes en '{CARPETA_ENTRADA}'.")

        self.idx = 0
        self.img = None
        self.img_base = None
        self.ancho = 0
        self.alto = 0
        self.cajas = []

        self.dibujando = False
        self.inicio = (0, 0)
        self.fin = (0, 0)

        # Escala de visualizacion (la etiqueta siempre se guarda en resolucion original).
        self.view_scale = 1.0
        self.view_width = 0
        self.view_height = 0

    def _listar_imagenes(self):
        rutas = []
        for ext in EXTENSIONES:
            rutas.extend(glob.glob(os.path.join(CARPETA_ENTRADA, ext)))
        rutas = sorted(rutas)
        return rutas

    def _ruta_txt_actual(self):
        base = os.path.splitext(os.path.basename(self.imagenes[self.idx]))[0]
        return os.path.join(CARPETA_SALIDA, f"{base}.txt")

    def _cargar_etiquetas_existentes(self, ruta_txt):
        cajas = []
        if not os.path.exists(ruta_txt):
            return cajas

        with open(ruta_txt, "r", encoding="utf-8") as f:
            for linea in f:
                partes = linea.strip().split()
                if len(partes) != 5:
                    continue
                try:
                    clase = int(partes[0])
                    xc, yc, w, h = map(float, partes[1:])
                except ValueError:
                    continue

                if clase != CLASE_DRON:
                    continue
                cajas.append(yolo_a_pixels(xc, yc, w, h, self.ancho, self.alto))
        return cajas

    def _guardar_etiquetas(self, cajas):
        ruta_txt = self._ruta_txt_actual()
        with open(ruta_txt, "w", encoding="utf-8") as f:
            for x1, y1, x2, y2 in cajas:
                norm = normalizar_caja(x1, y1, x2, y2, self.ancho, self.alto)
                if norm is None:
                    continue
                xc, yc, w, h = norm
                f.write(f"{CLASE_DRON} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
        return ruta_txt

    def _guardar_negativa(self):
        ruta_txt = self._ruta_txt_actual()
        with open(ruta_txt, "w", encoding="utf-8"):
            pass
        return ruta_txt

    def _update_view_scale(self):
        scale_w = MAX_VIEW_WIDTH / self.ancho
        scale_h = MAX_VIEW_HEIGHT / self.alto
        self.view_scale = min(1.0, scale_w, scale_h)
        self.view_width = max(1, int(self.ancho * self.view_scale))
        self.view_height = max(1, int(self.alto * self.view_scale))

    def _to_view_point(self, x, y):
        vx = int(clamp(round(x * self.view_scale), 0, self.view_width - 1))
        vy = int(clamp(round(y * self.view_scale), 0, self.view_height - 1))
        return vx, vy

    def _from_view_point(self, x, y):
        if self.view_scale <= 0:
            return 0, 0
        ox = int(clamp(round(x / self.view_scale), 0, self.ancho - 1))
        oy = int(clamp(round(y / self.view_scale), 0, self.alto - 1))
        return ox, oy

    def _cargar_imagen_actual(self):
        ruta = self.imagenes[self.idx]
        self.img_base = cv2.imread(ruta)
        if self.img_base is None:
            raise RuntimeError(f"No se pudo abrir la imagen: {ruta}")
        self.alto, self.ancho = self.img_base.shape[:2]
        self._update_view_scale()
        self.cajas = self._cargar_etiquetas_existentes(self._ruta_txt_actual())
        cv2.resizeWindow(VENTANA, self.view_width, self.view_height)

    def _dibujar_hud(self, canvas):
        total = len(self.imagenes)
        nombre = os.path.basename(self.imagenes[self.idx])
        linea1 = f"Imagen {self.idx + 1}/{total}: {nombre}"
        linea2 = "s=guardar | n=negativa | u=deshacer | c=limpiar | a=anterior | d=siguiente | q=salir"
        linea3 = f"Cajas actuales: {len(self.cajas)} | Escala vista: {self.view_scale:.2f}x"

        cv2.rectangle(canvas, (0, 0), (self.view_width, 72), (20, 20, 20), -1)
        cv2.putText(canvas, linea1, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, linea2, (10, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 230, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, linea3, (10, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 255, 120), 1, cv2.LINE_AA)

    def _redibujar(self):
        if self.view_scale < 1.0:
            self.img = cv2.resize(self.img_base, (self.view_width, self.view_height), interpolation=cv2.INTER_AREA)
        else:
            self.img = self.img_base.copy()

        for i, (x1, y1, x2, y2) in enumerate(self.cajas, start=1):
            vx1, vy1 = self._to_view_point(x1, y1)
            vx2, vy2 = self._to_view_point(x2, y2)
            cv2.rectangle(self.img, (vx1, vy1), (vx2, vy2), (0, 220, 0), 2)
            cv2.putText(self.img, f"dron {i}", (vx1, max(15, vy1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1, cv2.LINE_AA)

        if self.dibujando:
            v_inicio = self._to_view_point(*self.inicio)
            v_fin = self._to_view_point(*self.fin)
            cv2.rectangle(self.img, v_inicio, v_fin, (0, 255, 255), 1)

        self._dibujar_hud(self.img)

    def _mouse(self, event, x, y, _flags, _param):
        ox, oy = self._from_view_point(x, y)

        if event == cv2.EVENT_LBUTTONDOWN:
            self.dibujando = True
            self.inicio = (ox, oy)
            self.fin = (ox, oy)
        elif event == cv2.EVENT_MOUSEMOVE and self.dibujando:
            self.fin = (ox, oy)
        elif event == cv2.EVENT_LBUTTONUP and self.dibujando:
            self.dibujando = False
            self.fin = (ox, oy)
            x1, y1 = self.inicio
            x2, y2 = self.fin
            if normalizar_caja(x1, y1, x2, y2, self.ancho, self.alto) is not None:
                x1, x2 = sorted((int(x1), int(x2)))
                y1, y2 = sorted((int(y1), int(y2)))
                self.cajas.append((x1, y1, x2, y2))

    def run(self):
        cv2.namedWindow(VENTANA, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(VENTANA, self._mouse)

        print("--- INSTRUCCIONES ---")
        print("- Dibuja una o varias cajas por imagen (arrastrar con click izquierdo).")
        print("- s: guarda etiquetas y avanza.")
        print("- n: guarda muestra negativa (.txt vacio) y avanza.")
        print("- u: deshace la ultima caja.")
        print("- c: borra todas las cajas de la imagen actual.")
        print("- a: imagen anterior (sin guardar automatico).")
        print("- d: siguiente imagen (sin guardar automatico).")
        print("- q: salir.")
        print("---------------------")

        while 0 <= self.idx < len(self.imagenes):
            try:
                self._cargar_imagen_actual()
            except RuntimeError as e:
                print(f"[WARN] {e}")
                self.idx += 1
                continue

            while True:
                self._redibujar()
                cv2.imshow(VENTANA, self.img)
                tecla = cv2.waitKey(15) & 0xFF

                if tecla == ord("u"):
                    if self.cajas:
                        self.cajas.pop()

                elif tecla == ord("c"):
                    self.cajas = []

                elif tecla == ord("s"):
                    ruta_txt = self._guardar_etiquetas(self.cajas)
                    print(f"Guardado: {os.path.basename(self.imagenes[self.idx])} -> {ruta_txt}")
                    self.idx += 1
                    break

                elif tecla == ord("n"):
                    ruta_txt = self._guardar_negativa()
                    print(f"Negativa: {os.path.basename(self.imagenes[self.idx])} -> {ruta_txt}")
                    self.idx += 1
                    break

                elif tecla == ord("a"):
                    self.idx = max(0, self.idx - 1)
                    break

                elif tecla == ord("d"):
                    self.idx += 1
                    break

                elif tecla == ord("q"):
                    cv2.destroyAllWindows()
                    print("Saliendo del etiquetador...")
                    return

        cv2.destroyAllWindows()
        print("Etiquetado finalizado.")


if __name__ == "__main__":
    try:
        app = EtiquetadorYOLO()
        app.run()
    except FileNotFoundError as e:
        print(e)
