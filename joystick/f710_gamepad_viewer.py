#!/usr/bin/env python3
"""Interfaz independiente para visualizar un Logitech F710.

Este script no usa ROS. Lee el gamepad directamente desde /dev/input/js*
usando la API de joystick de Linux y muestra el estado en una ventana Tkinter.
"""

from __future__ import annotations

import array
import glob
import os
import struct
import tkinter as tk
from dataclasses import dataclass, field
from typing import Optional


JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80
JS_EVENT_FORMAT = "IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FORMAT)

JSIOCGAXES = 0x80016A11
JSIOCGBUTTONS = 0x80016A12

BACKGROUND = "#101418"
PANEL = "#172029"
PANEL_2 = "#223140"
LINE = "#314658"
TEXT = "#E9F0F4"
MUTED = "#91A5B2"
GREEN = "#24C36B"
YELLOW = "#F2C94C"
RED = "#EB5757"
BLUE = "#2D9CDB"

DEADZONE = 0.08

XINPUT_AXIS_LABELS = {
    0: "LX",
    1: "LY",
    2: "LT",
    3: "RX",
    4: "RY",
    5: "RT",
    6: "DPad X",
    7: "DPad Y",
}

DINPUT_AXIS_LABELS = {
    0: "LX",
    1: "LY",
    2: "RX",
    3: "RY",
    4: "DPad X",
    5: "DPad Y",
}

XINPUT_BUTTON_LABELS = {
    0: "A",
    1: "B",
    2: "X",
    3: "Y",
    4: "LB",
    5: "RB",
    6: "Back",
    7: "Start",
    8: "Guide",
    9: "LS",
    10: "RS",
}

DINPUT_BUTTON_LABELS = {
    0: "X",
    1: "A",
    2: "B",
    3: "Y",
    4: "LB",
    5: "RB",
    6: "LT",
    7: "RT",
    8: "Back",
    9: "Start",
    10: "LS",
    11: "RS",
}


def jsiocgname(length: int) -> int:
    return 0x80006A13 + (length << 16)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_axis(value: int) -> float:
    normalized = clamp(value / 32767.0, -1.0, 1.0)
    return 0.0 if abs(normalized) < DEADZONE else normalized


@dataclass
class JoystickState:
    path: str = ""
    name: str = ""
    connected: bool = False
    message: str = "Esperando control Logitech F710..."
    axes_count: int = 0
    buttons_count: int = 0
    axes: dict[int, float] = field(default_factory=dict)
    buttons: dict[int, bool] = field(default_factory=dict)
    last_button: str = "Ninguno"
    last_axis: str = "Ninguno"

    def reset(self, message: str) -> None:
        self.path = ""
        self.name = ""
        self.connected = False
        self.message = message
        self.axes_count = 0
        self.buttons_count = 0
        self.axes.clear()
        self.buttons.clear()
        self.last_button = "Ninguno"
        self.last_axis = "Ninguno"


def is_direct_input(state: JoystickState) -> bool:
    name = state.name.lower()
    return state.axes_count == 6 or "rumblepad" in name or "dual action" in name


def axis_labels_for(state: JoystickState) -> dict[int, str]:
    return DINPUT_AXIS_LABELS if is_direct_input(state) else XINPUT_AXIS_LABELS


def button_labels_for(state: JoystickState) -> dict[int, str]:
    return DINPUT_BUTTON_LABELS if is_direct_input(state) else XINPUT_BUTTON_LABELS


def axis_label(index: int, state: JoystickState) -> str:
    return axis_labels_for(state).get(index, f"Eje {index}")


def button_label(index: int, state: JoystickState) -> str:
    return button_labels_for(state).get(index, f"Boton {index}")


def index_for_label(labels: dict[int, str], label: str) -> Optional[int]:
    for index, current_label in labels.items():
        if current_label == label:
            return index
    return None


class LinuxJoystick:
    def __init__(self) -> None:
        self.state = JoystickState()
        self.fd: Optional[int] = None

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def scan(self) -> list[tuple[str, str]]:
        devices = []
        for path in sorted(glob.glob("/dev/input/js*")):
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                try:
                    name = self._read_name(fd)
                finally:
                    os.close(fd)
            except PermissionError:
                devices.append((path, "Sin permisos de lectura"))
                continue
            except OSError:
                continue
            devices.append((path, name))
        return devices

    def connect(self) -> None:
        if self.fd is not None:
            return

        devices = self.scan()
        if not devices:
            self.state.reset("No hay controles en /dev/input/js*")
            return

        path, _name = self._select_device(devices)
        try:
            self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            name = self._read_name(self.fd)
            axes_count = self._read_count(self.fd, JSIOCGAXES)
            buttons_count = self._read_count(self.fd, JSIOCGBUTTONS)
        except PermissionError:
            self.close()
            self.state.reset(
                f"Sin permisos para {path}. Prueba: sudo usermod -a -G input $USER"
            )
            return
        except OSError as exc:
            self.close()
            self.state.reset(f"No se pudo abrir {path}: {exc}")
            return

        self.state.path = path
        self.state.name = name
        self.state.connected = True
        self.state.message = "Conectado"
        self.state.axes_count = axes_count
        self.state.buttons_count = buttons_count
        self.state.axes = {index: 0.0 for index in range(axes_count)}
        self.state.buttons = {index: False for index in range(buttons_count)}

    def poll(self) -> None:
        if self.fd is None:
            self.connect()
            return

        while True:
            try:
                data = os.read(self.fd, JS_EVENT_SIZE)
            except BlockingIOError:
                break
            except OSError:
                self.close()
                self.state.reset("Control desconectado")
                break

            if len(data) != JS_EVENT_SIZE:
                self.close()
                self.state.reset("Control desconectado")
                break

            _time_ms, value, event_type, number = struct.unpack(JS_EVENT_FORMAT, data)
            is_init = bool(event_type & JS_EVENT_INIT)
            event_type &= ~JS_EVENT_INIT

            if event_type == JS_EVENT_AXIS:
                axis_value = normalize_axis(value)
                self.state.axes[number] = axis_value
                if not is_init and abs(axis_value) > DEADZONE:
                    label = axis_label(number, self.state)
                    self.state.last_axis = f"{label}: {axis_value:+.2f}"
            elif event_type == JS_EVENT_BUTTON:
                pressed = bool(value)
                self.state.buttons[number] = pressed
                if not is_init and pressed:
                    label = button_label(number, self.state)
                    self.state.last_button = f"{label} ({number})"

    def _select_device(self, devices: list[tuple[str, str]]) -> tuple[str, str]:
        def score(device: tuple[str, str]) -> int:
            name = device[1].lower()
            if "f710" in name and "logitech" in name:
                return 3
            if "rumblepad" in name and "logitech" in name:
                return 3
            if "f710" in name:
                return 2
            if "rumblepad" in name:
                return 2
            if "logitech" in name:
                return 1
            return 0

        return max(devices, key=score)

    def _read_name(self, fd: int) -> str:
        buffer = array.array("B", [0] * 128)
        import fcntl

        fcntl.ioctl(fd, jsiocgname(len(buffer)), buffer)
        raw = bytes(buffer).split(b"\x00", 1)[0]
        return raw.decode(errors="replace") or "Joystick"

    def _read_count(self, fd: int, request: int) -> int:
        buffer = array.array("B", [0])
        import fcntl

        fcntl.ioctl(fd, request, buffer)
        return int(buffer[0])


class F710Viewer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Logitech F710 - Visualizador")
        self.geometry("1120x760")
        self.minsize(980, 700)
        self.configure(bg=BACKGROUND)
        self.joystick = LinuxJoystick()

        self.canvas = tk.Canvas(self, bg=BACKGROUND, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(20, self._tick)

    def _close(self) -> None:
        self.joystick.close()
        self.destroy()

    def _tick(self) -> None:
        self.joystick.poll()
        self._draw()
        self.after(20, self._tick)

    def _draw(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 980)
        height = max(self.canvas.winfo_height(), 700)
        state = self.joystick.state

        self._text(34, 28, "Logitech F710 Gamepad", 28, TEXT, "nw", bold=True)
        subtitle = "Sin ROS - lectura directa desde /dev/input/js*"
        self._text(36, 66, subtitle, 12, MUTED, "nw")

        status_color = GREEN if state.connected else RED
        status = state.message
        if state.connected:
            status = f"{state.message}: {state.name}  ({state.path})"
        self._status_pill(width - 36, 34, status, status_color)

        panel_height = 158
        data_top = height - panel_height - 30
        controller_top = 122
        controller_bottom = data_top - 30
        controller_h = min(330, max(300, controller_bottom - controller_top))
        controller_w = min(740, width - 120)
        controller_cy = controller_top + controller_h / 2

        self._draw_controller(width * 0.50, controller_cy, controller_w, controller_h, state)
        self._draw_data_panel(36, data_top, width - 72, panel_height, state)

    def _draw_controller(self, cx: float, cy: float, body_w: float, body_h: float, state: JoystickState) -> None:
        left = cx - body_w / 2
        top = cy - body_h / 2
        right = cx + body_w / 2
        bottom = cy + body_h / 2

        self._rounded_rect(left, top + 35, right, bottom - 10, 95, PANEL, LINE, 3)
        self._rounded_rect(left + 132, top, right - 132, bottom - 28, 70, PANEL, LINE, 3)
        mode = "DirectInput" if is_direct_input(state) else "XInput"
        self._text(cx, top + 34, "F710", 24, TEXT, "center", bold=True)
        self._text(cx, top + 64, f"modo detectado: {mode}", 10, MUTED, "center")

        self._draw_shoulder(left + 110, top + 16, "LB", self._button_pressed("LB", state))
        self._draw_shoulder(right - 110, top + 16, "RB", self._button_pressed("RB", state))
        self._draw_trigger(left + 110, top - 8, "LT", self._trigger_value("LT", state))
        self._draw_trigger(right - 110, top - 8, "RT", self._trigger_value("RT", state))

        controls_y = top + body_h * 0.62
        left_buttons_x = left + 125
        left_stick_x = cx - 90
        right_stick_x = cx + 90
        right_buttons_x = right - 125

        self._draw_dpad(left_buttons_x, controls_y + 4, self._axis_named("DPad X", state), self._axis_named("DPad Y", state))
        self._draw_stick(left_stick_x, controls_y, self._axis_named("LX", state), self._axis_named("LY", state), "L")
        self._draw_stick(right_stick_x, controls_y, self._axis_named("RX", state), self._axis_named("RY", state), "R")

        button_positions = {
            "Y": (right_buttons_x, controls_y - 58),
            "B": (right_buttons_x + 52, controls_y),
            "X": (right_buttons_x - 52, controls_y),
            "A": (right_buttons_x, controls_y + 58),
        }
        colors = {"A": GREEN, "B": RED, "X": BLUE, "Y": YELLOW}
        for label, (x_pos, y_pos) in button_positions.items():
            self._round_button(x_pos, y_pos, 22, label, colors[label], self._button_pressed(label, state))

        self._center_button(cx - 82, top + body_h * 0.38, "Back", self._button_pressed("Back", state))
        self._center_button(cx, top + body_h * 0.34, "Guide", self._button_pressed("Guide", state))
        self._center_button(cx + 82, top + body_h * 0.38, "Start", self._button_pressed("Start", state))

        self._text(left_stick_x, bottom - 24, self._axis_pair_text("LX", "LY", state), 10, MUTED, "center")
        self._text(right_stick_x, bottom - 24, self._axis_pair_text("RX", "RY", state), 10, MUTED, "center")

    def _draw_data_panel(self, x_pos: float, y_pos: float, width: float, height: float, state: JoystickState) -> None:
        self._rounded_rect(x_pos, y_pos, x_pos + width, y_pos + height, 16, PANEL, LINE, 2)
        self._text(x_pos + 22, y_pos + 18, "Datos actuales", 16, TEXT, "nw", bold=True)
        left_width = width * 0.48
        right_x = x_pos + width * 0.54
        self._text(x_pos + 22, y_pos + 50, f"Ultimo boton: {state.last_button}", 13, TEXT, "nw", max_width=left_width)
        self._text(x_pos + 22, y_pos + 80, f"Ultimo eje: {state.last_axis}", 13, TEXT, "nw", max_width=left_width)

        active_buttons = [
            button_label(index, state)
            for index, pressed in sorted(state.buttons.items())
            if pressed
        ]
        active_text = ", ".join(active_buttons) if active_buttons else "Ninguno"
        self._text(
            x_pos + 22,
            y_pos + 110,
            f"Botones presionados: {active_text}",
            13,
            TEXT,
            "nw",
            max_width=left_width,
        )

        axis_lines = []
        for index in range(max(len(axis_labels_for(state)), state.axes_count)):
            label = axis_label(index, state)
            axis_lines.append(f"{label}={self._axis(index, state):+.2f}")
        self._text(right_x, y_pos + 50, "  ".join(axis_lines[:4]), 12, MUTED, "nw", max_width=width * 0.42)
        self._text(right_x, y_pos + 80, "  ".join(axis_lines[4:8]), 12, MUTED, "nw", max_width=width * 0.42)
        counts = f"Ejes: {state.axes_count}   Botones: {state.buttons_count}"
        mode = "DirectInput" if is_direct_input(state) else "XInput"
        self._text(right_x, y_pos + 110, f"{counts}   Modo: {mode}", 12, MUTED, "nw", max_width=width * 0.42)

    def _draw_stick(self, cx: float, cy: float, x_axis: float, y_axis: float, label: str) -> None:
        radius = 58
        knob_radius = 22
        self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=PANEL_2, outline=LINE, width=3)
        self.canvas.create_line(cx - radius + 8, cy, cx + radius - 8, cy, fill=LINE, width=1)
        self.canvas.create_line(cx, cy - radius + 8, cx, cy + radius - 8, fill=LINE, width=1)
        knob_x = cx + x_axis * 32
        knob_y = cy + y_axis * 32
        active = abs(x_axis) > DEADZONE or abs(y_axis) > DEADZONE
        fill = GREEN if active else "#526779"
        self.canvas.create_oval(
            knob_x - knob_radius,
            knob_y - knob_radius,
            knob_x + knob_radius,
            knob_y + knob_radius,
            fill=fill,
            outline=TEXT,
            width=2,
        )
        self._text(cx, cy + radius + 22, f"Stick {label}", 12, TEXT, "center", bold=True)

    def _draw_dpad(self, cx: float, cy: float, x_axis: float, y_axis: float) -> None:
        size = 30
        gap = 2
        directions = {
            "U": (cx, cy - size - gap, y_axis < -0.5),
            "D": (cx, cy + size + gap, y_axis > 0.5),
            "L": (cx - size - gap, cy, x_axis < -0.5),
            "R": (cx + size + gap, cy, x_axis > 0.5),
            "": (cx, cy, False),
        }
        for label, (x_pos, y_pos, active) in directions.items():
            fill = GREEN if active else PANEL_2
            self._rounded_rect(x_pos - size / 2, y_pos - size / 2, x_pos + size / 2, y_pos + size / 2, 7, fill, LINE, 2)
            if label:
                self._text(x_pos, y_pos, label, 11, TEXT, "center", bold=True)
        self._text(cx, cy + 74, "DPad", 12, TEXT, "center", bold=True)

    def _round_button(self, cx: float, cy: float, radius: float, label: str, color: str, pressed: bool) -> None:
        fill = GREEN if pressed else PANEL_2
        outline = color if not pressed else TEXT
        self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=fill, outline=outline, width=3)
        self._text(cx, cy, label, 14, TEXT, "center", bold=True)

    def _draw_shoulder(self, cx: float, cy: float, label: str, pressed: bool) -> None:
        fill = GREEN if pressed else PANEL_2
        self._rounded_rect(cx - 64, cy - 19, cx + 64, cy + 19, 14, fill, LINE, 2)
        self._text(cx, cy, label, 13, TEXT, "center", bold=True)

    def _draw_trigger(self, cx: float, cy: float, label: str, value: float) -> None:
        fill_amount = clamp((value + 1.0) / 2.0, 0.0, 1.0)
        self._rounded_rect(cx - 54, cy - 16, cx + 54, cy + 16, 10, PANEL_2, LINE, 1)
        self._rounded_rect(cx - 50, cy - 12, cx - 50 + 100 * fill_amount, cy + 12, 8, GREEN, GREEN, 0)
        self._text(cx, cy, label, 11, TEXT, "center", bold=True)

    def _center_button(self, cx: float, cy: float, label: str, pressed: bool) -> None:
        fill = GREEN if pressed else PANEL_2
        self._rounded_rect(cx - 35, cy - 14, cx + 35, cy + 14, 11, fill, LINE, 2)
        self._text(cx, cy, label, 9, TEXT, "center", bold=True)

    def _status_pill(self, x_pos: float, y_pos: float, text: str, color: str) -> None:
        max_chars = 68
        display = text if len(text) <= max_chars else text[: max_chars - 3] + "..."
        pill_width = max(190, min(560, 16 + len(display) * 7))
        self._rounded_rect(x_pos - pill_width, y_pos - 16, x_pos, y_pos + 16, 16, PANEL, color, 2)
        self.canvas.create_oval(x_pos - pill_width + 12, y_pos - 5, x_pos - pill_width + 22, y_pos + 5, fill=color, outline=color)
        self._text(x_pos - pill_width + 32, y_pos, display, 10, TEXT, "w")

    def _rounded_rect(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        radius: float,
        fill: str,
        outline: str,
        width: int,
    ) -> None:
        radius = min(radius, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        self.canvas.create_polygon(points, smooth=True, fill=fill, outline=outline, width=width)

    def _text(
        self,
        x_pos: float,
        y_pos: float,
        text: str,
        size: int,
        color: str,
        anchor: str,
        bold: bool = False,
        max_width: Optional[float] = None,
    ) -> None:
        weight = "bold" if bold else "normal"
        kwargs = {
            "text": text,
            "fill": color,
            "anchor": anchor,
            "font": ("DejaVu Sans", size, weight),
        }
        if max_width is not None:
            kwargs["width"] = max_width
        self.canvas.create_text(x_pos, y_pos, **kwargs)

    def _axis(self, index: int, state: JoystickState) -> float:
        return state.axes.get(index, 0.0)

    def _axis_named(self, label: str, state: JoystickState) -> float:
        index = index_for_label(axis_labels_for(state), label)
        return self._axis(index, state) if index is not None else 0.0

    def _button_pressed(self, label: str, state: JoystickState) -> bool:
        index = index_for_label(button_labels_for(state), label)
        return bool(state.buttons.get(index, False)) if index is not None else False

    def _trigger_value(self, label: str, state: JoystickState) -> float:
        axis_index = index_for_label(axis_labels_for(state), label)
        if axis_index is not None:
            return self._axis(axis_index, state)
        button_index = index_for_label(button_labels_for(state), label)
        if button_index is not None:
            return 1.0 if state.buttons.get(button_index, False) else -1.0
        return -1.0

    def _axis_pair_text(self, x_label: str, y_label: str, state: JoystickState) -> str:
        return f"{x_label} {self._axis_named(x_label, state):+.2f} / {y_label} {self._axis_named(y_label, state):+.2f}"


def main() -> None:
    app = F710Viewer()
    app.mainloop()


if __name__ == "__main__":
    main()
