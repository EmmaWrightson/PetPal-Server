let locationItems = [];  //hold the location

//fetch the location data when the page loads, using main.py get function
async function fetchItems() {
    try {
        const response = await fetch('/dashboard/location');
        if (response.ok) {
            const data = await response.json();

            if (data.location) {
                //store location
                locationItems = [data.location];
            }

            //fetch the weather if location is valid
            if (locationItems.length > 0) {
                const location = locationItems[0];
                fetchLocationWeather(location);  //get weather based on location
            } else {
                console.error("No location data available");
            }
        } else {
            console.error('Error fetching data:', response.status);
        }
    } catch (error) {
        console.error('Network error:', error);
    }
}

//get weather data based on the location from weather api
function fetchLocationWeather(location) {
    //use OpenStreetMap API to get lat and long of the city
    fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(location)}&format=json`)
        .then(response => response.json())
        .then(data => {
            //if empty then no city found at lat and long
            if (data.length === 0) {
                alert("Location not found!");
                return;
            }

            //print out to console to show lat and long
            const lat = data[0].lat;
            const lon = data[0].lon;
            console.log(lat + "," + lon);

            //Using the National Weather Service API with lat and lon
            fetch(`https://api.weather.gov/points/${lat},${lon}`)
                .then(response => response.json())
                .then(weatherData => {
                    const forecastUrl = weatherData.properties.forecast;
                    console.log(forecastUrl);

                    //fetch the forecast data at lat and long
                    fetch(forecastUrl)
                        .then(response => response.json())
                        .then(forecastData => {
                            //forecast period
                            const period = forecastData.properties.periods[0];

                            //update display with this array
                            const weatherInfo = {
                                city: location, //use the location from database
                                condition: period.shortForecast, //weather condition
                                temperature: `${period.temperature}° ${period.temperatureUnit}`, //temperature
                                weather_image_query: period.shortForecast, //use to get weather image
                                city_image_query: location //use to get city image
                            };

                            //fetch the weather image from Unsplash
                            fetch(`https://api.unsplash.com/search/photos/?query=${weatherInfo.weather_image_query}&client_id=SyPBIUKn5o-_QUrjNgiaTWTYMDauAtPcp_-Vw3ANAAI`)
                                .then((response) => response.json())
                                .then((data) => {
                                    const result = data.results;
                                    if (result.length > 0) {
                                        const imageUrl = result[0].urls.regular;
                                        console.log("Weather Image URL:", imageUrl);
                                        document.getElementById('weatherImage').src = imageUrl;  //eather image -> source
                                    } else {
                                        console.error("No weather image found");
                                    }
                                })
                                .catch(error => {
                                    console.error("Error fetching weather image:", error);
                                });

                            //fetch the city image from Unsplash
                            fetch(`https://api.unsplash.com/search/photos/?query=${weatherInfo.city_image_query}&client_id=SyPBIUKn5o-_QUrjNgiaTWTYMDauAtPcp_-Vw3ANAAI`)
                                .then((response) => response.json())
                                .then((data) => {
                                    const result = data.results;
                                    if (result.length > 0) {
                                        const cityImageUrl = result[0].urls.regular;
                                        console.log("City Image URL:", cityImageUrl);
                                        document.getElementById('cityImage').src = cityImageUrl;  //city image -> source
                                    } else {
                                        console.error("No city image found");
                                    }
                                })
                                .catch(error => {
                                    console.error("Error fetching city image:", error);
                                });

                            //update page elements with the fetched weather data from weatherinfo array
                            document.getElementById("location").textContent = `Location: ${weatherInfo.city}`;
                            document.getElementById("weatherCondition").textContent = `Weather Condition: ${weatherInfo.condition}`;
                            document.getElementById("temperature").textContent = `Temperature: ${weatherInfo.temperature}`;
                        });
                });
        })
        .catch(error => {
            console.error("Error fetching location data:", error);
        });
}

//fetch the location data when the page loads, from main.py and database
window.onload = fetchItems;