import pygame
import math
import random

# Constantes del entorno
WIDTH = 800
SIM_HEIGHT = 600
UI_HEIGHT = 150
HEIGHT = SIM_HEIGHT + UI_HEIGHT
FPS = 60

# Colores
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
GRAY = (200, 200, 200)

class PIDController:
    def __init__(self, kp, ki, kd):
        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.integral = 0
        self.previous_error = 0

    def compute(self, setpoint, current_value, dt):
        """Calcula la respuesta del controlador PID."""
        if dt <= 0.0:
            return 0.0

        error = setpoint - current_value
        self.integral += error * dt
        derivative = (error - self.previous_error) / dt

        output = (self.kp * error) + (self.ki * self.integral) + (self.kd * derivative)

        self.previous_error = error
        return output

class Drone:
    def __init__(self, x, y, color, speed=200):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.color = color
        self.speed = speed
        self.radius = 15

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.radius)

class Slider:
    def __init__(self, x, y, w, h, min_val, max_val, start_val, text):
        self.rect = pygame.Rect(x, y, w, h)
        self.min_val = min_val
        self.max_val = max_val
        self.val = start_val
        self.text = text
        self.dragging = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.dragging = True
                self.update_val(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                self.update_val(event.pos[0])

    def update_val(self, x):
        rel_x = x - self.rect.x
        rel_x = max(0, min(rel_x, self.rect.width))
        percentage = rel_x / self.rect.width
        self.val = self.min_val + percentage * (self.max_val - self.min_val)

    def draw(self, surface, font):
        # Dibujar fondo
        pygame.draw.rect(surface, GRAY, self.rect)
        # Dibujar barra
        percentage = (self.val - self.min_val) / (self.max_val - self.min_val) if self.max_val != self.min_val else 0
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, int(self.rect.width * percentage), self.rect.height)
        pygame.draw.rect(surface, BLUE, fill_rect)
        # Dibujar borde
        pygame.draw.rect(surface, BLACK, self.rect, 2)
        # Dibujar texto
        if "Vel" in self.text:
            txt_surface = font.render(f"{self.text}: {int(self.val)}", True, BLACK)
        else:
            txt_surface = font.render(f"{self.text}: {self.val:.2f}", True, BLACK)
        surface.blit(txt_surface, (self.rect.x + self.rect.width + 10, self.rect.y))

class Simulation:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Twin Digital: Drones Leader-Follower (PID)")
        self.clock = pygame.time.Clock()
        self.running = True
        self.font = pygame.font.SysFont(None, 24)

        # Inicialización de drones
        # Líder en la mitad izquierda, Seguidor en la mitad derecha
        self.leader = Drone(WIDTH * 0.25, SIM_HEIGHT // 2, RED)
        self.follower = Drone(WIDTH * 0.75, SIM_HEIGHT // 2, BLUE)

        # Inicialización de sliders (Columna 1: PID X)
        self.slider_kp_x = Slider(20, SIM_HEIGHT + 20, 120, 20, 0.0, 10.0, 2.0, "Kp X")
        self.slider_ki_x = Slider(20, SIM_HEIGHT + 60, 120, 20, 0.0, 5.0, 0.5, "Ki X")
        self.slider_kd_x = Slider(20, SIM_HEIGHT + 100, 120, 20, 0.0, 2.0, 0.1, "Kd X")

        # Inicialización de sliders (Columna 2: PID Y)
        self.slider_kp_y = Slider(280, SIM_HEIGHT + 20, 120, 20, 0.0, 10.0, 2.0, "Kp Y")
        self.slider_ki_y = Slider(280, SIM_HEIGHT + 60, 120, 20, 0.0, 5.0, 0.5, "Ki Y")
        self.slider_kd_y = Slider(280, SIM_HEIGHT + 100, 120, 20, 0.0, 2.0, 0.1, "Kd Y")

        # Inicialización de sliders (Columna 3: Velocidad)
        self.slider_speed = Slider(530, SIM_HEIGHT + 20, 120, 20, 50, 500, 200, "Vel. Líder")

        self.sliders = [self.slider_kp_x, self.slider_ki_x, self.slider_kd_x,
                        self.slider_kp_y, self.slider_ki_y, self.slider_kd_y,
                        self.slider_speed]

        # Controladores PID para X e Y del seguidor
        self.pid_x = PIDController(kp=self.slider_kp_x.val, ki=self.slider_ki_x.val, kd=self.slider_kd_x.val)
        self.pid_y = PIDController(kp=self.slider_kp_y.val, ki=self.slider_ki_y.val, kd=self.slider_kd_y.val)

        # Destino de movimiento para el líder
        self.target_x = self.leader.x
        self.target_y = self.leader.y

        # Variables para latencia de telemetría (Fase 1)
        self.telemetry_delay = 0.2  # 200 ms de retraso de red
        self.leader_history = []    # Lista de tuplas (timestamp, x, y)
        self.current_time = 0.0     # Tiempo simulado transcurrido

    def update_pids(self):
        """Actualiza los valores de los PIDs en tiempo real."""
        self.pid_x.kp = self.slider_kp_x.val
        self.pid_x.ki = self.slider_ki_x.val
        self.pid_x.kd = self.slider_kd_x.val

        self.pid_y.kp = self.slider_kp_y.val
        self.pid_y.ki = self.slider_ki_y.val
        self.pid_y.kd = self.slider_kd_y.val

        self.leader.speed = self.slider_speed.val


    def update_leader(self, dt):
        """Actualiza la posición del dron líder."""
        keys = pygame.key.get_pressed()

        # Movimiento manual con flechas
        moving_with_keys = False
        if keys[pygame.K_LEFT]:
            self.leader.x -= self.leader.speed * dt
            moving_with_keys = True
        if keys[pygame.K_RIGHT]:
            self.leader.x += self.leader.speed * dt
            moving_with_keys = True
        if keys[pygame.K_UP]:
            self.leader.y -= self.leader.speed * dt
            moving_with_keys = True
        if keys[pygame.K_DOWN]:
            self.leader.y += self.leader.speed * dt
            moving_with_keys = True

        # Limitar al lado izquierdo y al área de simulación (SIM_HEIGHT)
        self.leader.x = max(self.leader.radius, min(self.leader.x, WIDTH // 2 - self.leader.radius))
        self.leader.y = max(self.leader.radius, min(self.leader.y, SIM_HEIGHT - self.leader.radius))

        if moving_with_keys:
            self.target_x = self.leader.x
            self.target_y = self.leader.y
        else:
            # Mover hacia el objetivo si se hizo click
            dx = self.target_x - self.leader.x
            dy = self.target_y - self.leader.y
            dist = math.hypot(dx, dy)

            if dist > 5:
                self.leader.x += (dx / dist) * self.leader.speed * dt
                self.leader.y += (dy / dist) * self.leader.speed * dt

    def update_follower(self, dt):
        """Actualiza la posición del dron seguidor usando control PID con físicas de 2º orden y latencia."""

        # 1. Simulación de latencia de telemetría (Retardo de Red)
        # Guardar la posición actual del líder con su timestamp
        self.leader_history.append((self.current_time, self.leader.x, self.leader.y))

        # Buscar la posición del líder hace 'telemetry_delay' segundos
        target_time = self.current_time - self.telemetry_delay

        # Limpiar historial viejo para no consumir memoria (dejar al menos el más cercano al target)
        while len(self.leader_history) > 1 and self.leader_history[1][0] < target_time:
            self.leader_history.pop(0)

        # El setpoint es la posición retrasada del líder
        delayed_leader_x = self.leader_history[0][1]
        delayed_leader_y = self.leader_history[0][2]

        # Como está en la otra mitad, su setpoint de X será X_lider + OFFSET (mitad de pantalla)
        setpoint_x = delayed_leader_x + (WIDTH // 2)
        setpoint_y = delayed_leader_y

        # 2. Físicas de segundo orden (Inercia)
        # Computar PID (la salida ahora se interpreta como aceleración / fuerza motriz)
        accel_x = self.pid_x.compute(setpoint_x, self.follower.x, dt)
        accel_y = self.pid_y.compute(setpoint_y, self.follower.y, dt)

        # Actualizar velocidad considerando la aceleración
        self.follower.vx += accel_x * dt
        self.follower.vy += accel_y * dt

        # Fricción / Resistencia aerodinámica (drag) para estabilidad
        friction = 0.95
        self.follower.vx *= friction
        self.follower.vy *= friction

        # Actualizar posición del seguidor base en la velocidad
        self.follower.x += self.follower.vx * dt
        self.follower.y += self.follower.vy * dt

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # Delta time en segundos
            self.current_time += dt

            self.handle_events()
            self.update_leader(dt)
            self.update_follower(dt)
            self.draw()

        pygame.quit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            # Pasar eventos a sliders
            for slider in self.sliders:
                slider.handle_event(event)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Comprobar si se hizo clic en el área de simulación (mitad izquierda)
                if event.pos[0] < WIDTH // 2 and event.pos[1] < SIM_HEIGHT:
                    self.target_x, self.target_y = event.pos

        # Actualizar variables en cada frame si los sliders cambiaron
        self.update_pids()

    def draw_hud(self):
        """Dibuja la información en pantalla."""
        # Fondo para el área de la interfaz
        ui_rect = pygame.Rect(0, SIM_HEIGHT, WIDTH, UI_HEIGHT)
        pygame.draw.rect(self.screen, GRAY, ui_rect)
        pygame.draw.line(self.screen, BLACK, (0, SIM_HEIGHT), (WIDTH, SIM_HEIGHT), 4)

        # Dibujar sliders
        for slider in self.sliders:
            slider.draw(self.screen, self.font)

        # Instrucciones de movimiento movidas a la tercera columna
        instructions1 = self.font.render("Controles del Lider:", True, BLACK)
        instructions2 = self.font.render("Clic Izq. o Flechas", True, BLACK)
        self.screen.blit(instructions1, (550, SIM_HEIGHT + 70))
        self.screen.blit(instructions2, (550, SIM_HEIGHT + 100))

    def draw(self):
        self.screen.fill(WHITE)

        # Dibujar línea separadora de mitades (sólo en la parte de simulación)
        pygame.draw.line(self.screen, GRAY, (WIDTH // 2, 0), (WIDTH // 2, SIM_HEIGHT), 2)

        # Dibujar drones
        self.leader.draw(self.screen)
        self.follower.draw(self.screen)

        # Dibujar UI
        self.draw_hud()

        pygame.display.flip()

if __name__ == "__main__":
    sim = Simulation()
    sim.run()

