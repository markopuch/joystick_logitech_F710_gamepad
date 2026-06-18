from __future__ import annotations

import array
import glob
import os
import struct
from dataclasses import dataclass, field
from typing import Optional


JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80
JS_EVENT_FORMAT = 'IhBB'
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FORMAT)

JSIOCGAXES = 0x80016A11
JSIOCGBUTTONS = 0x80016A12

XINPUT_AXIS_LABELS = {
    0: 'LX',
    1: 'LY',
    2: 'LT',
    3: 'RX',
    4: 'RY',
    5: 'RT',
    6: 'DPad X',
    7: 'DPad Y',
}

DINPUT_AXIS_LABELS = {
    0: 'LX',
    1: 'LY',
    2: 'RX',
    3: 'RY',
    4: 'DPad X',
    5: 'DPad Y',
}

XINPUT_BUTTON_LABELS = {
    0: 'A',
    1: 'B',
    2: 'X',
    3: 'Y',
    4: 'LB',
    5: 'RB',
    6: 'Back',
    7: 'Start',
    8: 'Guide',
    9: 'LS',
    10: 'RS',
}

DINPUT_BUTTON_LABELS = {
    0: 'X',
    1: 'A',
    2: 'B',
    3: 'Y',
    4: 'LB',
    5: 'RB',
    6: 'LT',
    7: 'RT',
    8: 'Guide',
    9: 'Start',
    10: 'LS',
    11: 'RS',
}


def jsiocgname(length: int) -> int:
    return 0x80006A13 + (length << 16)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_axis(value: int, deadzone: float) -> float:
    normalized = clamp(value / 32767.0, -1.0, 1.0)
    return 0.0 if abs(normalized) < deadzone else normalized


@dataclass
class JoystickState:
    path: str = ''
    name: str = ''
    connected: bool = False
    message: str = 'Esperando Logitech F710...'
    axes_count: int = 0
    buttons_count: int = 0
    axes: dict[int, float] = field(default_factory=dict)
    buttons: dict[int, bool] = field(default_factory=dict)

    def reset(self, message: str) -> None:
        self.path = ''
        self.name = ''
        self.connected = False
        self.message = message
        self.axes_count = 0
        self.buttons_count = 0
        self.axes.clear()
        self.buttons.clear()


def is_direct_input(state: JoystickState) -> bool:
    name = state.name.lower()
    return state.axes_count == 6 or 'rumblepad' in name or 'dual action' in name


def axis_labels_for(state: JoystickState) -> dict[int, str]:
    return DINPUT_AXIS_LABELS if is_direct_input(state) else XINPUT_AXIS_LABELS


def button_labels_for(state: JoystickState) -> dict[int, str]:
    return DINPUT_BUTTON_LABELS if is_direct_input(state) else XINPUT_BUTTON_LABELS


def index_for_label(labels: dict[int, str], label: str) -> Optional[int]:
    for index, current_label in labels.items():
        if current_label == label:
            return index
    return None


class LinuxJoystick:
    def __init__(self, device_path: str = '', deadzone: float = 0.08) -> None:
        self.device_path = device_path.strip()
        self.deadzone = float(deadzone)
        self.state = JoystickState()
        self.fd: Optional[int] = None

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def scan(self) -> list[tuple[str, str]]:
        paths = [self.device_path] if self.device_path else sorted(glob.glob('/dev/input/js*'))
        devices = []
        for path in paths:
            if not path:
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                try:
                    name = self._read_name(fd)
                finally:
                    os.close(fd)
            except PermissionError:
                devices.append((path, 'Sin permisos de lectura'))
                continue
            except OSError:
                continue
            devices.append((path, name))
        return devices

    def connect(self) -> bool:
        if self.fd is not None:
            return True

        devices = self.scan()
        if not devices:
            target = self.device_path or '/dev/input/js*'
            self.state.reset(f'No hay controles en {target}')
            return False

        path, _name = self._select_device(devices)
        try:
            self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            name = self._read_name(self.fd)
            axes_count = self._read_count(self.fd, JSIOCGAXES)
            buttons_count = self._read_count(self.fd, JSIOCGBUTTONS)
        except PermissionError:
            self.close()
            self.state.reset(
                f'Sin permisos para {path}. Use: sudo usermod -a -G input $USER'
            )
            return False
        except OSError as exc:
            self.close()
            self.state.reset(f'No se pudo abrir {path}: {exc}')
            return False

        self.state.path = path
        self.state.name = name
        self.state.connected = True
        self.state.message = 'Conectado'
        self.state.axes_count = axes_count
        self.state.buttons_count = buttons_count
        self.state.axes = {index: 0.0 for index in range(axes_count)}
        self.state.buttons = {index: False for index in range(buttons_count)}
        return True

    def poll(self) -> bool:
        if self.fd is None and not self.connect():
            return False

        while True:
            try:
                data = os.read(self.fd, JS_EVENT_SIZE)
            except BlockingIOError:
                break
            except OSError:
                self.close()
                self.state.reset('Control desconectado')
                return False

            if len(data) != JS_EVENT_SIZE:
                self.close()
                self.state.reset('Control desconectado')
                return False

            _time_ms, value, event_type, number = struct.unpack(JS_EVENT_FORMAT, data)
            event_type &= ~JS_EVENT_INIT

            if event_type == JS_EVENT_AXIS:
                self.state.axes[number] = normalize_axis(value, self.deadzone)
            elif event_type == JS_EVENT_BUTTON:
                self.state.buttons[number] = bool(value)
        return self.state.connected

    def axis(self, label: str) -> float:
        index = index_for_label(axis_labels_for(self.state), label)
        if index is None:
            return 0.0
        return self.state.axes.get(index, 0.0)

    def button(self, label: str) -> bool:
        index = index_for_label(button_labels_for(self.state), label)
        if index is None:
            return False
        return bool(self.state.buttons.get(index, False))

    def raw_button(self, index: int) -> bool:
        return bool(self.state.buttons.get(index, False))

    def button_snapshot(self) -> dict[str, bool]:
        labels = button_labels_for(self.state)
        return {
            label: bool(self.state.buttons.get(index, False))
            for index, label in labels.items()
        }

    def _select_device(self, devices: list[tuple[str, str]]) -> tuple[str, str]:
        def score(device: tuple[str, str]) -> int:
            name = device[1].lower()
            if 'f710' in name and 'logitech' in name:
                return 4
            if 'rumblepad' in name and 'logitech' in name:
                return 3
            if 'f710' in name:
                return 2
            if 'logitech' in name:
                return 1
            return 0

        return max(devices, key=score)

    def _read_name(self, fd: int) -> str:
        buffer = array.array('B', [0] * 128)
        import fcntl

        fcntl.ioctl(fd, jsiocgname(len(buffer)), buffer)
        raw = bytes(buffer).split(b'\x00', 1)[0]
        return raw.decode(errors='replace') or 'Joystick'

    def _read_count(self, fd: int, request: int) -> int:
        buffer = array.array('B', [0])
        import fcntl

        fcntl.ioctl(fd, request, buffer)
        return int(buffer[0])
