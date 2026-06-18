from __future__ import annotations

import time

from geometry_msgs.msg import Twist
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from joystick_logitech_f710_gamepad.linux_joystick import LinuxJoystick, clamp


class F710GamepadNode(Node):
    def __init__(self) -> None:
        super().__init__('f710_gamepad_node')
        self.declare_parameter('device', '')
        self.declare_parameter('cmd_vel_topic', 'cmd_vel')
        self.declare_parameter('face_topic_legacy', 'face_coms_topic')
        self.declare_parameter('face_topic_web', '/face/expression')
        self.declare_parameter('max_linear_speed', 0.50)
        self.declare_parameter('max_angular_speed', 1.40)
        self.declare_parameter('deadzone', 0.08)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('initial_speed_percent', 35)
        self.declare_parameter('speed_step_percent', 10)
        self.declare_parameter('face_a', 'smile')
        self.declare_parameter('face_b', 'fire')
        self.declare_parameter('face_x', 'music')
        self.declare_parameter('face_y', 'heart')

        self.cmd_vel_topic = str(self.get_parameter('cmd_vel_topic').value)
        self.face_topic_legacy = str(self.get_parameter('face_topic_legacy').value)
        self.face_topic_web = str(self.get_parameter('face_topic_web').value)
        self.max_linear_speed = float(self.get_parameter('max_linear_speed').value)
        self.max_angular_speed = float(self.get_parameter('max_angular_speed').value)
        self.speed_percent = int(self.get_parameter('initial_speed_percent').value)
        self.speed_percent = int(clamp(self.speed_percent, 0, 100))
        self.speed_step_percent = max(int(self.get_parameter('speed_step_percent').value), 1)
        deadzone = float(self.get_parameter('deadzone').value)
        publish_rate_hz = max(float(self.get_parameter('publish_rate_hz').value), 1.0)

        self.face_by_button = {
            'A': str(self.get_parameter('face_a').value),
            'B': str(self.get_parameter('face_b').value),
            'X': str(self.get_parameter('face_x').value),
            'Y': str(self.get_parameter('face_y').value),
        }

        self.joystick = LinuxJoystick(
            device_path=str(self.get_parameter('device').value),
            deadzone=deadzone,
        )
        self.cmd_vel_publisher = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.face_legacy_publisher = self.create_publisher(String, self.face_topic_legacy, 10)
        self.face_web_publisher = self.create_publisher(String, self.face_topic_web, 10)

        self.previous_buttons: dict[str, bool] = {}
        self.previous_guide_pressed = False
        self.previous_dpad: set[str] = set()
        self.emergency_stop = False
        self.was_connected = False
        self.last_connection_log = 0.0
        self.last_speed_log = 0.0
        self.last_cmd = (None, None)

        self.timer = self.create_timer(1.0 / publish_rate_hz, self.update)
        self.get_logger().info(
            'F710 listo: stick derecho=lineal, stick izquierdo=rotacional, '
            'DPad=porcentaje, A/B/X/Y=rostros, Guide=emergencia.'
        )

    def update(self) -> None:
        connected = self.joystick.poll()
        if not connected:
            if self.was_connected:
                self.publish_stop('control desconectado')
            self.was_connected = False
            self.log_connection_waiting()
            return

        if not self.was_connected:
            self.was_connected = True
            self.get_logger().info(
                f'Control conectado: {self.joystick.state.name} ({self.joystick.state.path})'
            )

        self.handle_buttons()
        self.handle_dpad()
        self.publish_motion()

    def handle_buttons(self) -> None:
        current_buttons = self.joystick.button_snapshot()

        for button_label, expression in self.face_by_button.items():
            pressed = current_buttons.get(button_label, False)
            was_pressed = self.previous_buttons.get(button_label, False)
            if pressed and not was_pressed:
                self.publish_face(expression, button_label)

        guide_pressed = self.joystick.button('Guide') or self.joystick.raw_button(8)
        if guide_pressed and not self.previous_guide_pressed:
            self.emergency_stop = not self.emergency_stop
            state = 'ACTIVO' if self.emergency_stop else 'LIBERADO'
            self.get_logger().warn(f'STOP DE EMERGENCIA {state}')
            self.publish_stop('guide')

        self.previous_guide_pressed = guide_pressed
        self.previous_buttons = current_buttons

    def handle_dpad(self) -> None:
        dpad_x = self.joystick.axis('DPad X')
        dpad_y = self.joystick.axis('DPad Y')
        current_dpad = set()

        if dpad_y < -0.5:
            current_dpad.add('up')
        elif dpad_y > 0.5:
            current_dpad.add('down')

        if dpad_x < -0.5:
            current_dpad.add('left')
        elif dpad_x > 0.5:
            current_dpad.add('right')

        new_presses = current_dpad - self.previous_dpad
        if {'up', 'right'} & new_presses:
            self.adjust_speed(self.speed_step_percent)
        if {'down', 'left'} & new_presses:
            self.adjust_speed(-self.speed_step_percent)

        self.previous_dpad = current_dpad

    def publish_motion(self) -> None:
        if self.emergency_stop:
            self.publish_stop('emergencia activa', log_once=False)
            return

        # En los F710, arriba suele ser eje negativo. Se invierte para que
        # empujar hacia adelante produzca linear.x positivo.
        right_y = self.joystick.axis('RY')
        left_x = self.joystick.axis('LX')
        speed_scale = self.speed_percent / 100.0

        linear_x = -right_y * self.max_linear_speed * speed_scale
        angular_z = -left_x * self.max_angular_speed * speed_scale
        self.publish_cmd_vel(linear_x, angular_z)

    def publish_cmd_vel(self, linear_x: float, angular_z: float) -> None:
        msg = Twist()
        msg.linear.x = float(linear_x)
        msg.angular.z = float(angular_z)
        self.cmd_vel_publisher.publish(msg)

        rounded = (round(linear_x, 3), round(angular_z, 3))
        if rounded != self.last_cmd:
            self.last_cmd = rounded
            self.get_logger().info(
                f'cmd_vel linear.x={linear_x:+.2f} m/s, '
                f'angular.z={angular_z:+.2f} rad/s, velocidad={self.speed_percent}%'
            )

    def publish_stop(self, reason: str, log_once: bool = True) -> None:
        self.publish_cmd_vel(0.0, 0.0)
        now = time.monotonic()
        if not log_once or now - self.last_speed_log > 1.0:
            self.last_speed_log = now
            self.get_logger().warn(f'STOP enviado: {reason}')

    def publish_face(self, expression: str, button_label: str) -> None:
        msg = String()
        msg.data = expression
        self.face_legacy_publisher.publish(msg)
        self.face_web_publisher.publish(msg)
        self.get_logger().info(
            f'Boton {button_label}: rostro={expression} '
            f'-> {self.face_topic_legacy}, {self.face_topic_web}'
        )

    def adjust_speed(self, delta_percent: int) -> None:
        previous = self.speed_percent
        self.speed_percent = int(clamp(previous + delta_percent, 0, 100))
        if self.speed_percent != previous:
            self.get_logger().info(f'Porcentaje de velocidad: {self.speed_percent}%')
        else:
            self.get_logger().info(f'Porcentaje de velocidad mantiene limite: {self.speed_percent}%')

    def log_connection_waiting(self) -> None:
        now = time.monotonic()
        if now - self.last_connection_log < 2.0:
            return
        self.last_connection_log = now
        self.get_logger().warn(self.joystick.state.message)

    def destroy_node(self) -> bool:
        self.publish_stop('apagando nodo')
        self.joystick.close()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = F710GamepadNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
