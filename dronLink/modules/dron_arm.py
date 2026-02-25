import threading
from pymavlink import mavutil

def setFlightMode (self,mode):
    # Get mode ID
    mode_id = self.vehicle.mode_mapping()[mode]
    self.vehicle.mav.set_mode_send(
        self.vehicle.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id)
    msg = self.message_handler.wait_for_message('COMMAND_ACK', timeout=3)


def _arm(self, callback=None, params=None, error_callback=None):
    self.state = "arming"
    try:
        self.setFlightMode('GUIDED')
        self.vehicle.mav.command_long_send(
            self.vehicle.target_system, self.vehicle.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)

        msg = self.message_handler.wait_for_message('COMMAND_ACK', timeout=5)

        # Esperar a que los motores estén armados con un timeout de 10 segundos
        import time
        deadline = time.time() + 10
        armed = False
        while time.time() < deadline:
            if self.vehicle.motors_armed():
                armed = True
                break
            time.sleep(0.2)

        if not armed:
            raise TimeoutError("El dron no completó el armado en el tiempo esperado (pre-arm checks fallidos o no está listo)")

        self.state = "armed"
        if callback is not None:
            if self.id is None:
                callback() if params is None else callback(params)
            else:
                callback(self.id) if params is None else callback(self.id, params)

    except Exception as e:
        self.state = "connected"
        if error_callback is not None:
            error_callback(str(e))


def arm(self, blocking=True, callback=None, params=None, error_callback=None):
    if self.state == 'connected':
        if blocking:
            self._arm(callback, params, error_callback)
        else:
            armThread = threading.Thread(target=self._arm, args=[callback, params, error_callback])
            armThread.start()
        return True
    else:
        return False

