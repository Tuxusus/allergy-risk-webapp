from flask import Flask, render_template, jsonify, request
import requests

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/risk", methods=["POST"])
def get_risk():
    data = request.get_json()

    lat = data.get("lat")
    lon = data.get("lon")

    weather_url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,wind_speed_10m,relative_humidity_2m"
    )

    response = requests.get(weather_url)
    weather_data = response.json()

    current = weather_data.get("current", {})

    temperature = current.get("temperature_2m")
    wind_speed = current.get("wind_speed_10m")
    humidity = current.get("relative_humidity_2m")

    risk_score = 0

    if wind_speed and wind_speed > 6:
        risk_score += 30
    if humidity and humidity < 45:
        risk_score += 30
    if temperature and temperature > 15:
        risk_score += 20

    if risk_score <= 30:
        risk_level = "Низкий"
        forecast = "Существенных изменений не ожидается"
    elif risk_score <= 60:
        risk_level = "Средний"
        forecast = "Возможен рост риска в ближайшие часы"
    else:
        risk_level = "Высокий"
        forecast = "Высокая вероятность ухудшения условий"

    return jsonify({
        "lat": lat,
        "lon": lon,
        "temperature": temperature,
        "wind_speed": wind_speed,
        "humidity": humidity,
        "risk": risk_level,
        "forecast": forecast,
        "route_risk": risk_level
    })


if __name__ == "__main__":
    app.run(debug=True)