# joystick_logitech_f710_gamepad

Paquete ROS 2 para controlar el robot diferencial con un mando Logitech F710.

El nodo lee directamente `/dev/input/js*`, por lo que no necesita `pygame` ni
`joy_node`. Funciona con el F710 en modo XInput y tambien con el modo
DirectInput, donde Linux puede detectarlo como `Logitech Cordless RumblePad 2`.

## Controles

| Control F710 | Funcion |
| --- | --- |
| Stick derecho vertical | Velocidad lineal `linear.x`. Arriba avanza, abajo retrocede. |
| Stick izquierdo horizontal | Velocidad rotacional `angular.z`. Izquierda gira a la izquierda, derecha gira a la derecha. |
| DPad arriba / derecha | Aumenta el porcentaje de velocidad. |
| DPad abajo / izquierda | Reduce el porcentaje de velocidad. |
| Boton `A` | Rostro `smile`. |
| Boton `B` | Rostro `fire`. |
| Boton `X` | Rostro `music`. |
| Boton `Y` | Rostro `heart`. |
| Boton `Guide` | Stop de emergencia. Presionar otra vez libera el stop. |

Los botones de rostro publican en ambos topics:

```text
face_coms_topic
/face/expression
```

Asi cambian los rostros de la pantalla HDMI y tambien de la WebApp para tablet.

## Compilar

Desde el workspace:

```bash
cd /home/utec/robot_ws
colcon build --symlink-install
source install/setup.bash
```

## Ejecutar

```bash
ros2 launch joystick_logitech_f710_gamepad f710_gamepad.launch.py
```

Si quieres fijar el dispositivo:

```bash
ros2 launch joystick_logitech_f710_gamepad f710_gamepad.launch.py device:=/dev/input/js0
```

## Parametros principales

```bash
ros2 launch joystick_logitech_f710_gamepad f710_gamepad.launch.py \
  max_linear_speed:=0.50 \
  max_angular_speed:=1.40 \
  initial_speed_percent:=35 \
  speed_step_percent:=10
```

Cambiar mapeo de rostros:

```bash
ros2 launch joystick_logitech_f710_gamepad f710_gamepad.launch.py \
  face_a:=smile \
  face_b:=fire \
  face_x:=music \
  face_y:=heart
```

Cambiar topics:

```bash
ros2 launch joystick_logitech_f710_gamepad f710_gamepad.launch.py \
  cmd_vel_topic:=cmd_vel \
  face_topic_legacy:=face_coms_topic \
  face_topic_web:=/face/expression
```

## Probar topics

Movimiento:

```bash
ros2 topic echo /cmd_vel
```

Rostros pantalla HDMI:

```bash
ros2 topic echo /face_coms_topic
```

Rostros WebApp:

```bash
ros2 topic echo /face/expression
```

## Permisos

Si aparece `Sin permisos para /dev/input/js0`, agrega el usuario al grupo
`input` y vuelve a iniciar sesion:

```bash
sudo usermod -a -G input $USER
```

## Visualizador sin ROS

Se mantiene el script de referencia:

```bash
python3 joystick/f710_gamepad_viewer.py
```

Sirve para revisar que Linux detecte correctamente botones y ejes del F710.
