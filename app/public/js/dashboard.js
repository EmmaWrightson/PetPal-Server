document.addEventListener("DOMContentLoaded", async () => {
 
    async function fetchSensorData(sensorType) {
        try {
            const response = await fetch(`/api/${sensorType}`);
            const data = await response.json();
            return data;
        } catch (error) {
            console.error(`Error fetching ${sensorType} data:`, error);
            return [];
        }
    }

    async function graphData() {
     
        const tempData = await fetchSensorData("temperature");
        const humiData = await fetchSensorData("humidity");
        const lightData = await fetchSensorData("light");

        if (tempData.length === 0 || humiData.length === 0 || lightData.length === 0) {
            console.error("One or more datasets are empty. Check API response.");
            return;
        }

        
        const labels = tempData.map(entry => new Date(entry.timestamp).toLocaleTimeString());

        
        function createChart(canvasId, label, data, borderColor, backgroundColor, yAxisLabel) {
            const ctx = document.getElementById(canvasId).getContext('2d');
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: label,
                        data: data.map(entry => entry.value),
                        borderColor: borderColor,
                        backgroundColor: backgroundColor,
                        borderWidth: 2,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        title: {
                            display: true,
                            text: label,  
                            font: { size: 16 }
                        }
                    },
                    scales: {
                        x: {
                            title: {
                                display: true,
                                text: 'Time'  
                            }
                        },
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: yAxisLabel  
                            }
                        }
                    }
                }
            });
        }

        createChart('temperatureChart', 'Temperature Readings in Celsius', tempData, 'red', 'rgba(255, 0, 0, 0.2)', 'Temperature (°C)');
        createChart('humidityChart', 'Humidity Readings in Percentage', humiData, 'blue', 'rgba(0, 0, 255, 0.2)', 'Humidity (%)');
        createChart('lightChart', 'Light Readings in Lux', lightData, 'yellow', 'rgba(255, 255, 0, 0.2)', 'Light (lux)');
    }


    await graphData();

});