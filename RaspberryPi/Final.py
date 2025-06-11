import asyncio
import subprocess
import websockets
import json
import os
import base64
import time
import cv2
import sounddevice as sd
import numpy as np
from adafruit_servokit import ServoKit


import smbus2
import time

# PCA9685 default I2C address
PCA9685_ADDR = 0x40

# Registers
MODE1 = 0x00
PRESCALE = 0xFE
LED0_ON_L = 0x06

# Initialize the data bus which is in the raspberry pi's i2c-3
bus = smbus2.SMBus(3)  

# Set up PCA9685 into normal mode
bus.write_byte_data(PCA9685_ADDR, MODE1, 0x00)  

# Set frequency to 50Hz for servos, and send byte data to the bus to prepare for servos
freq = 50
prescale_val = int(25000000.0 / (4096 * freq) - 1)
old_mode = bus.read_byte_data(PCA9685_ADDR, MODE1)
sleep_mode = (old_mode & 0x7F) | 0x10
bus.write_byte_data(PCA9685_ADDR, MODE1, sleep_mode)
bus.write_byte_data(PCA9685_ADDR, PRESCALE, prescale_val)
bus.write_byte_data(PCA9685_ADDR, MODE1, old_mode)
time.sleep(0.005)
bus.write_byte_data(PCA9685_ADDR, MODE1, old_mode | 0xA1)

# Set servo positions
def set_pwm(channel, on, off):
    reg = LED0_ON_L + 4 * channel
    bus.write_byte_data(PCA9685_ADDR, reg, on & 0xFF)
    bus.write_byte_data(PCA9685_ADDR, reg + 1, on >> 8)
    bus.write_byte_data(PCA9685_ADDR, reg + 2, off & 0xFF)
    bus.write_byte_data(PCA9685_ADDR, reg + 3, off >> 8)
# 0 is left right, 1 is up down

def smooth_set_pwm(channel, start, end, step=1, delay=0.005):
    if start == end:
        return
    direction = 1 if end > start else -1
    for pos in range(start, end, direction * step):
        set_pwm(channel, 0, pos)
        time.sleep(delay)
    set_pwm(channel, 0, end)

#On startup these are the motor's middle position to be set when started
updown = 300 
leftright = 300

set_pwm(0, 0, leftright)   
set_pwm(1, 0, updown)   

def move_cam(direction):
    global leftright, updown

    if direction == "left" and leftright > 150:
        new_pos = max(150, leftright - 25)
        smooth_set_pwm(0, leftright, new_pos)
        leftright = new_pos

    elif direction == "right" and leftright < 600:
        new_pos = min(600, leftright + 25)
        smooth_set_pwm(0, leftright, new_pos)
        leftright = new_pos

    elif direction == "down" and updown > 150:
        new_pos = max(150, updown - 25)
        smooth_set_pwm(1, updown, new_pos)
        updown = new_pos

    elif direction == "up" and updown < 600:
        new_pos = min(600, updown + 25)
        smooth_set_pwm(1, updown, new_pos)
        updown = new_pos


kit = ServoKit(channels=16)
for i in range(6):
    kit.servo[i].set_pulse_width_range(500,2500)

#Move motor down then back up to release the treats
def run_motor(motor_num):
    kit.servo[motor_num].angle = 0
    time.sleep(2)
    kit.servo[motor_num].angle = 90

async def play_audio(data: bytes):
    process = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0",                
            "-f", "wav", "pipe:1"          
    ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE)
    aplay = subprocess.Popen(
        ["aplay"],
        stdin=process.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    process.stdin.write(data)
    process.stdin.close()
    process.wait()
    aplay.wait()


async def send_data():
    uri = "wss://petpal-3yfg.onrender.com/ws/live"

    async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as websocket:
        print("Connected to Server")
        while True:
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=0.01)
                data = json.loads(response)
                if data["type"] == "command":
                    run_motor(data["motor"])

                elif data["type"] == "cam":
                    move_cam(data["direction"])

                elif data["type"] == "audio":
                    audio_bytes = base64.b64decode(data["data"])
                    await play_audio(audio_bytes)

            except asyncio.TimeoutError:
                pass

            await asyncio.sleep(0.1)

        
asyncio.run(send_data())
                    