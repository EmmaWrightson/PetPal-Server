package main

import (
	"bytes"
	"encoding/base64"
	"log"
	"net/http"
	"os/exec"
	"sync"

	"github.com/gorilla/websocket"
)

var (
	upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
	return true // Allow all origins for testing
	},
	}

	// Client management
	videoClients = make(map[*websocket.Conn]bool)
	audioClients = make(map[*websocket.Conn]bool)
	clientsMutex sync.Mutex

	// Stream control
	streamActive = false
	streamMutex sync.Mutex
)

// HTML page with video player and controls
const htmlPage = `
<!DOCTYPE html>
<html>
<head>
 <title>RPi Camera & Audio Stream</title>
 <style>
 body {
 font-family: Arial, sans-serif;
 max-width: 800px;
 margin: 0 auto;
 padding: 20px;
 background-color: #f0f0f0;
 }
 #videoContainer {
 background-color: #000;
 width: 640px;
 height: 480px;
 margin: 20px auto;
 display: flex;
 align-items: center;
 justify-content: center;
 position: relative;
 }
 #video {
 max-width: 100%;
 max-height: 100%;
 }
 #controls {
 text-align: center;
 margin: 20px;
 }
 button {
 font-size: 18px;
 padding: 10px 20px;
 margin: 10px;
 cursor: pointer;
 }
 #debug {
 background-color: #333;
 color: #0f0;
 padding: 10px;
 font-family: monospace;
 font-size: 12px;
 height: 200px;
 overflow-y: auto;
 margin-top: 20px;
 }
 .indicator {
 display: inline-block;
 width: 10px;
 height: 10px;
 border-radius: 50%;
 margin-left: 10px;
 }
 .active { background-color: #0f0; }
 .inactive { background-color: #f00; }
 </style>
</head>
<body>
 <h1>Raspberry Pi Camera & Audio Stream</h1>

 <div id="controls">
 <button id="startBtn" onclick="startStream()">Start Stream</button>
 <button id="stopBtn" onclick="stopStream()" disabled>Stop Stream</button>
 <span>Video: <span id="videoStatus" class="indicator inactive"></span></span>
 <span>Audio: <span id="audioStatus" class="indicator inactive"></span></span>
 </div>

 <div id="videoContainer">
 <img id="video" style="display:none;" />
 <div id="placeholder">Click "Start Stream" to begin</div>
 </div>

 <div id="debug"></div>

 <script>
 let videoWs = null;
 let audioWs = null;
 let audioContext = null;
 let isStreaming = false;

 function log(msg) {
 const debug = document.getElementById('debug');
 const timestamp = new Date().toLocaleTimeString();
 debug.innerHTML += timestamp + ' - ' + msg + '\n';
 debug.scrollTop = debug.scrollHeight;
 console.log(msg);
 }

 async function startStream() {
 if (isStreaming) return;

 log('Starting stream...');
 document.getElementById('startBtn').disabled = true;
 document.getElementById('stopBtn').disabled = false;
 document.getElementById('placeholder').style.display = 'none';
 document.getElementById('video').style.display = 'block';

 // Initialize audio context
 if (!audioContext) {
 audioContext = new (window.AudioContext || window.webkitAudioContext)();
 log('Audio context created, sample rate: ' + audioContext.sampleRate);
 }

 // Start video WebSocket
 try {
 videoWs = new WebSocket('ws://' + window.location.host + '/video');

 videoWs.onopen = () => {
 log('Video WebSocket connected');
 document.getElementById('videoStatus').className = 'indicator active';
 };

 videoWs.onmessage = (event) => {
 // Update video frame
 const video = document.getElementById('video');
 video.src = 'data:image/jpeg;base64,' + event.data;
 };

 videoWs.onerror = (error) => {
 log('Video WebSocket error: ' + error);
 };

 videoWs.onclose = () => {
 log('Video WebSocket closed');
 document.getElementById('videoStatus').className = 'indicator inactive';
 };
 } catch (error) {
 log('Failed to connect video WebSocket: ' + error);
 }

 // Start audio WebSocket
 try {
 audioWs = new WebSocket('ws://' + window.location.host + '/audio');

 audioWs.onopen = () => {
 log('Audio WebSocket connected');
 document.getElementById('audioStatus').className = 'indicator active';
 };

 let nextPlayTime = 0;

audioWs.onmessage = async (event) => {
  try {
    const arrayBuffer = await event.data.arrayBuffer();
    const int16Array = new Int16Array(arrayBuffer);

    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768;
    }

    const sampleRate = 44100;
    const audioBuffer = audioContext.createBuffer(1, float32Array.length, sampleRate);
    audioBuffer.copyToChannel(float32Array, 0);

    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);

    // Schedule playback sequentially
    if (nextPlayTime < audioContext.currentTime) {
      nextPlayTime = audioContext.currentTime + 0.1; // small offset to avoid glitches
    }

    source.start(nextPlayTime);
    nextPlayTime += audioBuffer.duration;
  } catch (error) {
    log('Audio playback error: ' + error);
  }
};

 audioWs.onerror = (error) => {
 log('Audio WebSocket error: ' + error);
 };

 audioWs.onclose = () => {
 log('Audio WebSocket closed');
 document.getElementById('audioStatus').className = 'indicator inactive';
 };
 } catch (error) {
 log('Failed to connect audio WebSocket: ' + error);
 }

 // Tell server to start streaming
 fetch('/control/start', { method: 'POST' })
 .then(() => {
 log('Stream started');
 isStreaming = true;
 })
 .catch(error => log('Failed to start stream: ' + error));
 }

 function stopStream() {
 log('Stopping stream...');

 document.getElementById('startBtn').disabled = false;
 document.getElementById('stopBtn').disabled = true;
 document.getElementById('video').style.display = 'none';
 document.getElementById('placeholder').style.display = 'block';

 if (videoWs) {
 videoWs.close();
 videoWs = null;
 }

 if (audioWs) {
 audioWs.close();
 audioWs = null;
 }

 // Tell server to stop streaming
 fetch('/control/stop', { method: 'POST' })
 .then(() => {
 log('Stream stopped');
 isStreaming = false;
 })
 .catch(error => log('Failed to stop stream: ' + error));
 }
 </script>
</body>
</html>
`

func main() {
	log.Println("Starting Raspberry Pi AV Streamer...")

	// HTTP routes
	http.HandleFunc("/", serveHTML)
	http.HandleFunc("/video", handleVideoWebSocket)
	http.HandleFunc("/audio", handleAudioWebSocket)
	http.HandleFunc("/control/start", handleStart)
	http.HandleFunc("/control/stop", handleStop)

	port := ":8080"
	log.Printf("Server starting on http://localhost%s", port)
	log.Fatal(http.ListenAndServe(port, nil))
}

func serveHTML(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html")
	w.Write([]byte(htmlPage))
}

func handleVideoWebSocket(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
	log.Printf("Video WebSocket upgrade failed: %v", err)
	return
	}
	defer conn.Close()

	clientsMutex.Lock()
	videoClients[conn] = true
	clientsMutex.Unlock()

	log.Printf("Video client connected. Total clients: %d", len(videoClients))

	// Keep connection alive
	for {
	if _, _, err := conn.ReadMessage(); err != nil {
	break
	}
	}

	clientsMutex.Lock()
	delete(videoClients, conn)
	clientsMutex.Unlock()

	log.Printf("Video client disconnected. Remaining clients: %d", len(videoClients))
}

func handleAudioWebSocket(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
	log.Printf("Audio WebSocket upgrade failed: %v", err)
	return
	}
	defer conn.Close()

	clientsMutex.Lock()
	audioClients[conn] = true
	clientsMutex.Unlock()

	log.Printf("Audio client connected. Total clients: %d", len(audioClients))

	// Keep connection alive
	for {
	if _, _, err := conn.ReadMessage(); err != nil {
	break
	}
	}

	clientsMutex.Lock()
	delete(audioClients, conn)
	clientsMutex.Unlock()

	log.Printf("Audio client disconnected. Remaining clients: %d", len(audioClients))
}

func handleStart(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
	http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	return
	}

	streamMutex.Lock()
	if !streamActive {
	streamActive = true
	go captureVideo()
	go captureAudio()
	log.Println("Stream started")
	}
	streamMutex.Unlock()

	w.WriteHeader(http.StatusOK)
}

func handleStop(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
	http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	return
	}

	streamMutex.Lock()
	streamActive = false
	streamMutex.Unlock()

	log.Println("Stream stopped")
	w.WriteHeader(http.StatusOK)
}

func captureVideo() {
	log.Println("Starting video capture...")

	// Using libcamera-vid to capture MJPEG stream
	// Adjust parameters as needed for your camera
	cmd := exec.Command("libcamera-vid",
	"-t", "0", // Run indefinitely
	"--codec", "mjpeg", // MJPEG codec
	"--width", "640", // Width
	"--height", "480", // Height
	"--framerate", "15", // FPS
	"--nopreview", // No preview window
	"-o", "-", // Output to stdout
	)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
	log.Printf("Failed to get video stdout pipe: %v", err)
	return
	}

	stderr, err := cmd.StderrPipe()
	if err != nil {
	log.Printf("Failed to get video stderr pipe: %v", err)
	return
	}

	// Log stderr in a separate goroutine
	go func() {
	buf := make([]byte, 1024)
	for {
	n, err := stderr.Read(buf)
	if err != nil {
	break
	}
	log.Printf("Video capture stderr: %s", string(buf[:n]))
	}
	}()

	if err := cmd.Start(); err != nil {
	log.Printf("Failed to start video capture: %v", err)
	return
	}

	defer func() {
	cmd.Process.Kill()
	cmd.Wait()
	log.Println("Video capture stopped")
	}()

	// Read MJPEG frames
	buffer := make([]byte, 1024*1024) // 1MB buffer for frames
	frameBuffer := bytes.NewBuffer(nil)

	for streamActive {
	n, err := stdout.Read(buffer)
	if err != nil {
	log.Printf("Video read error: %v", err)
	break
	}

	frameBuffer.Write(buffer[:n])

	// Look for JPEG markers
	data := frameBuffer.Bytes()
	startIdx := bytes.Index(data, []byte{0xFF, 0xD8}) // JPEG start
	if startIdx >= 0 {
	endIdx := bytes.Index(data[startIdx+2:], []byte{0xFF, 0xD9}) // JPEG end
	if endIdx >= 0 {
	endIdx += startIdx + 4 // Adjust for offset and include end marker

	// Extract complete JPEG frame
	frame := data[startIdx:endIdx]

	// Send to all connected clients
	broadcastVideo(frame)

	// Remove processed data from buffer
	frameBuffer.Next(endIdx)
	}
	}

	// Prevent buffer from growing too large
	if frameBuffer.Len() > 2*1024*1024 {
	frameBuffer.Reset()
	}
	}
}

func captureAudio() {
	log.Println("Starting audio capture...")

	// Using arecord to capture audio
	// Adjust device name as needed (use 'arecord -l' to list devices)
	cmd := exec.Command("arecord",
	"-f", "S16_LE", // 16-bit signed little-endian
	"-r", "44100", // Sample rate
	"-c", "1", // Mono
	"-t", "raw", // Raw output
	"-D", "plughw:3,0", // USB microphone (adjust as needed)
	"-", // Output to stdout
	)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
	log.Printf("Failed to get audio stdout pipe: %v", err)
	return
	}

	stderr, err := cmd.StderrPipe()
	if err != nil {
	log.Printf("Failed to get audio stderr pipe: %v", err)
	return
	}

	// Log stderr in a separate goroutine
	go func() {
	buf := make([]byte, 1024)
	for {
	n, err := stderr.Read(buf)
	if err != nil {
	break
	}
	log.Printf("Audio capture stderr: %s", string(buf[:n]))
	}
	}()

	if err := cmd.Start(); err != nil {
	log.Printf("Failed to start audio capture: %v", err)
	return
	}

	defer func() {
	cmd.Process.Kill()
	cmd.Wait()
	log.Println("Audio capture stopped")
	}()

	// Read audio data in chunks
	buffer := make([]byte, 4096) // ~46ms of audio at 44.1kHz, 16-bit mono

	for streamActive {
	n, err := stdout.Read(buffer)
	if err != nil {
	log.Printf("Audio read error: %v", err)
	break
	}

	if n > 0 {
	broadcastAudio(buffer[:n])
	}
	}
}

func broadcastVideo(frame []byte) {
	clientsMutex.Lock()
	defer clientsMutex.Unlock()

	// Encode frame as base64
	encoded := base64.StdEncoding.EncodeToString(frame)

	for client := range videoClients {
	err := client.WriteMessage(websocket.TextMessage, []byte(encoded))
	if err != nil {
	log.Printf("Failed to send video frame: %v", err)
	client.Close()
	delete(videoClients, client)
	}
	}
}

func broadcastAudio(data []byte) {
	clientsMutex.Lock()
	defer clientsMutex.Unlock()

	for client := range audioClients {
	err := client.WriteMessage(websocket.BinaryMessage, data)
	if err != nil {
	log.Printf("Failed to send audio data: %v", err)
	client.Close()
	delete(audioClients, client)
	}
	}
}