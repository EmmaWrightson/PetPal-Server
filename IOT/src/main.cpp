#include "ECE140_WIFI.h"
#include "ECE140_MQTT.h"
#include <Adafruit_BMP085.h>



// //MQTT client - using descriptive client ID and topic
// #define CLIENT_ID "blueberry-esp32-sensors"
// #define TOPIC_PREFIX "puppy/blueberriesarecool"




// WiFi credentials
const char* ucsdUsername = UCSD_USERNAME;
const char* ucsdPassword = UCSD_PASSWORD;
const char* wifiSsid = WIFI_SSID;
const char* nonEnterpriseWifiPassword = NON_ENTERPRISE_WIFI_PASSWORD;
const char* clientId= CLIENT_ID;
const char* topicPrefix = TOPIC_PREFIX;


ECE140_MQTT mqtt(clientId, topicPrefix);

Adafruit_BMP085 bmp;


void setup() {
    Serial.begin(115200);
    ECE140_WIFI wifi;
    //Also new code may not work
    //wifi.connectToWiFi(wifiSsid, nonEnterpriseWifiPassword);
    wifi.connectToWPAEnterprise(wifiSsid, ucsdUsername, ucsdPassword);

    if (!bmp.begin()) {
        //std::cout << "Could not find a valid BMP180 sensor \n";
        while (1);  // Stop execution if sensor fails
    }
}

void loop() {

    int hallValue = hallRead();

    //std::cout << "Hall value is " << hallValue << "\n";

    //float temperature = temperatureRead();

    float temperature = bmp.readTemperature(); //New code may not work

    float pressure = bmp.readPressure(); //New code may not work

    //std::cout << "Pressure is " << bmp.readPressure() << "    Temp is  " << bmp.readTemperature() << "\n";


    String message = "{\"temperature\": " + String(temperature) + ", \"pressure\": " + String(pressure) + "}";


    mqtt.publishMessage("readings", message);

    //std::cout << "Message was sent, " << message << "\n";

    mqtt.loop();
    delay(5000);



}