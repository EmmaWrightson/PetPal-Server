import paho.mqtt.client as mqtt
import json
from datetime import datetime
from collections import deque
import numpy as np
import requests
from dotenv import load_dotenv
import os

load_dotenv()

# MQTT Broker settings
#BROKER = "broker.hivemq.com"
BROKER = "broker.emqx.io"
PORT = 1883

BASE_TOPIC = os.environ['BASE_TOPIC']
TOPIC = BASE_TOPIC + "/#"

if BASE_TOPIC == "blueberries/ece140/sensors":
    print("Please enter a unique topic for your server")
    exit()


def on_connect(client, userdata, flags, rc):
    """Callback for when the client connects to the broker."""
    if rc == 0:
        print("Successfully connected to MQTT broker")
        client.subscribe(TOPIC)
        print(f"Subscribed to {TOPIC}")
    else:
        print(f"Failed to connect with result code {rc}")

def on_message(client, userdata, msg):
    """Callback for when a message is received."""
    #print("Message recieved")
    try:
        # Parse JSON message
        payload = json.loads(msg.payload.decode())
        current_time = datetime.now()
        
        # check the topic if it is the base topic + /readings
        # if it is, print the payload
        print(payload)
    


        #Post the temperature and the pressure to our FASTAPI
        #url = "http://localhost:8000/api/temperature"
        #url = "http://localhost:6543/sensor_data"
        url = "https://tech-assignment-final-project-emma-and-obr3.onrender.com/sensor_data"
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        topic = msg.topic[len(BASE_TOPIC) + 1:]
        data = {"temp": payload['temperature'], "timestamp": time, "topic": topic}
        #print(data)
        mypost = requests.post(url,json=data)


            
    except json.JSONDecodeError:
        #print(f"\nReceived non-JSON message on {msg.topic}:")

        payload = msg.payload.decode()

        print(f"Payload: {payload}")

        # url = "http://localhost:8000/api/temperature"
        # #url = "http://localhost:6543/api/temperature"
        # time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # data = {"value": str(payload['temperature']), "unit": "Celsius", "timestamp": str(time)}
        # print(data)
        # mypost = requests.post(url,json=data)



def main():
    # Create MQTT client
    print("Creating MQTT client...")
    client = mqtt.Client()
    # Set the callback functions onConnect and onMessage
    print("Setting callback functions...")
    client.on_message = on_message
    client.on_connect = on_connect
    try:
        # Connect to broker
        print("Connecting to broker...")
        client.connect(BROKER)
        # Start the MQTT loop
        print("Starting MQTT loop...")
        client.loop_forever()
    
    except KeyboardInterrupt:
        print("\nDisconnecting from broker...")
        # make sure to stop the loop and disconnect from the broker
        client.loop_stop()
        client.disconnect()
        print("Exited successfully")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()