import os
from glob import glob

from setuptools import find_packages, setup


package_name = 'joystick_logitech_f710_gamepad'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Marko Puchuri',
    maintainer_email='mpuchuri@utec.edu.pe',
    description='ROS 2 driver for controlling a differential robot with a Logitech F710 gamepad.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'f710_gamepad_node = joystick_logitech_f710_gamepad.f710_gamepad_node:main',
        ],
    },
)
