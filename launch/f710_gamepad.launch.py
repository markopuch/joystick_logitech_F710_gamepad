from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    device = LaunchConfiguration('device')
    cmd_vel_topic = LaunchConfiguration('cmd_vel_topic')
    face_topic_legacy = LaunchConfiguration('face_topic_legacy')
    face_topic_web = LaunchConfiguration('face_topic_web')
    max_linear_speed = LaunchConfiguration('max_linear_speed')
    max_angular_speed = LaunchConfiguration('max_angular_speed')
    deadzone = LaunchConfiguration('deadzone')
    publish_rate_hz = LaunchConfiguration('publish_rate_hz')
    initial_speed_percent = LaunchConfiguration('initial_speed_percent')
    speed_step_percent = LaunchConfiguration('speed_step_percent')
    face_a = LaunchConfiguration('face_a')
    face_b = LaunchConfiguration('face_b')
    face_x = LaunchConfiguration('face_x')
    face_y = LaunchConfiguration('face_y')

    return LaunchDescription([
        DeclareLaunchArgument('device', default_value=''),
        DeclareLaunchArgument('cmd_vel_topic', default_value='cmd_vel'),
        DeclareLaunchArgument('face_topic_legacy', default_value='face_coms_topic'),
        DeclareLaunchArgument('face_topic_web', default_value='/face/expression'),
        DeclareLaunchArgument('max_linear_speed', default_value='0.50'),
        DeclareLaunchArgument('max_angular_speed', default_value='1.40'),
        DeclareLaunchArgument('deadzone', default_value='0.08'),
        DeclareLaunchArgument('publish_rate_hz', default_value='20.0'),
        DeclareLaunchArgument('initial_speed_percent', default_value='35'),
        DeclareLaunchArgument('speed_step_percent', default_value='10'),
        DeclareLaunchArgument('face_a', default_value='smile'),
        DeclareLaunchArgument('face_b', default_value='fire'),
        DeclareLaunchArgument('face_x', default_value='music'),
        DeclareLaunchArgument('face_y', default_value='heart'),
        Node(
            package='joystick_logitech_f710_gamepad',
            executable='f710_gamepad_node',
            name='f710_gamepad_node',
            output='screen',
            parameters=[{
                'device': device,
                'cmd_vel_topic': cmd_vel_topic,
                'face_topic_legacy': face_topic_legacy,
                'face_topic_web': face_topic_web,
                'max_linear_speed': ParameterValue(max_linear_speed, value_type=float),
                'max_angular_speed': ParameterValue(max_angular_speed, value_type=float),
                'deadzone': ParameterValue(deadzone, value_type=float),
                'publish_rate_hz': ParameterValue(publish_rate_hz, value_type=float),
                'initial_speed_percent': ParameterValue(initial_speed_percent, value_type=int),
                'speed_step_percent': ParameterValue(speed_step_percent, value_type=int),
                'face_a': face_a,
                'face_b': face_b,
                'face_x': face_x,
                'face_y': face_y,
            }],
        ),
    ])
