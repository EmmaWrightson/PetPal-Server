# ECE140-WI25-PetPal Server and RaspberryPi Code

**Server Link**: https://petpal-3yfg.onrender.com/

## Instructions:

#### Server:

To run the server, it is hosted by on render, and this repository there are two connectdb(): functions, the larger one should be commented out when running locally, and then when trying to put on the on render site, uncomment the larger function and comment out the smaller.

#### Video Streaming:

To video stream, you need to be on the same wifi as the raspberry pi, and in the feed.html, at the beginning of the script, the variable ip should be the ip adress of the raspberry pi. Then, on the raspberry pi, you need to run the audio.go file by putting in terminal `go run audio.go`.

#### Controlling the Raspberry Pi:

To control camera movement, compartments, and then also the speakers, the server must be live with on render. Then, you need to run the Final.py code on the raspberry pi so that it moniters for incoming posts on the websocket. So when you put to motor, sound or cam on the server, it gets put to the websocket that the raspberry pi is checking.

#### Raspberry Pi Code:

All the code that the pi uses is inside the RaspberryPi folder in this repository.


