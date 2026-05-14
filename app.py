from flask import Flask, render_template, request, jsonify
import requests
from statistics import mean

app = Flask(__name__)

ALLERGENS = {
    "birch": {
        "label": "Берёза",
        "field": "birch_pollen",
        "desc": "основной весенний аллерген"
    },
    "grass": {
        "label": "Злаки",
        "field": "grass_pollen",
        "desc": "сезонный травяной аллерген"
    },
    "ragweed": {
        "label": "Амброзия",
        "field": "ragweed_pollen",
        "desc": "высокоаллергенное растение"
    }
}

MAP_POINTS = [
    {"name": "Москва", "lat": 55.7558, "lon": 37.6176},
    {"name": "Химки", "lat": 55.8970, "lon": 37.4297},
    {"name": "Красногорск", "lat": 55.8310, "lon": 37.3300},
    {"name": "Зеленоград", "lat": 55.9825, "lon": 37.1814},
    {"name": "Мытищи", "lat": 55.9105, "lon": 37.7360},
    {"name": "Балашиха", "lat": 55.7963, "lon": 37.9382},
    {"name": "Люберцы", "lat": 55.6765, "lon": 37.8982},
    {"name": "Одинцово", "lat": 55.6780, "lon": 37.2777},
    {"name": "Подольск", "lat": 55.4311, "lon": 37.5455},
    {"name": "Жуковский", "lat": 55.5992, "lon": 38.1167},
    {"name": "Ногинск", "lat": 55.8686, "lon": 38.4418},
    {"name": "Воскресенск", "lat": 55.3176, "lon": 38.6526},
    {"name": "Серпухов", "lat": 54.9226, "lon": 37.4031},
    {"name": "Дмитров", "lat": 56.3449, "lon": 37.5204}
]


def risk_bundle(score: int):
    if score < 25:
        return {
            "level": "Низкий",
            "color": "#4FD08A",
            "marker_value": 1
        }
    elif score < 50:
        return {
            "level": "Средний",
            "color": "#B8D94B",
            "marker_value": 2
        }
    elif score < 75:
        return {
            "level": "Высокий",
            "color": "#F5A623",
            "marker_value": 3
        }
    else:
        return {
            "level": "Очень высокий",
            "color": "#E8505B",
            "marker_value": 4
        }


def calc_score(allergen_value, pm25, aqi, wind_speed, humidity, temperature):
    score = 0

    # Пыльца
    if allergen_value >= 80:
        score += 50
    elif allergen_value >= 40:
        score += 35
    elif allergen_value >= 15:
        score += 20
    elif allergen_value >= 5:
        score += 10

    # Воздух
    if pm25 is not None:
        if pm25 >= 35:
            score += 15
        elif pm25 >= 15:
            score += 8

    if aqi is not None:
        if aqi >= 80:
            score += 15
        elif aqi >= 40:
            score += 8

    # Погода
    if wind_speed is not None:
        if wind_speed >= 8:
            score += 8
        elif wind_speed >= 5:
            score += 4

    if humidity is not None and humidity < 40:
        score += 6

    if temperature is not None and temperature > 15:
        score += 6

    return min(score, 100)


def current_environment(lat, lon):
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
    )

    air_url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        f"&current=european_aqi,pm2_5,birch_pollen,grass_pollen,ragweed_pollen"
    )

    weather_resp = requests.get(weather_url, timeout=12)
    air_resp = requests.get(air_url, timeout=12)

    weather_resp.raise_for_status()
    air_resp.raise_for_status()

    weather_current = weather_resp.json().get("current", {})
    air_current = air_resp.json().get("current", {})

    return {
        "temperature": weather_current.get("temperature_2m"),
        "humidity": weather_current.get("relative_humidity_2m"),
        "wind_speed": weather_current.get("wind_speed_10m"),
        "aqi": air_current.get("european_aqi"),
        "pm25": air_current.get("pm2_5"),
        "birch_pollen": air_current.get("birch_pollen") or 0,
        "grass_pollen": air_current.get("grass_pollen") or 0,
        "ragweed_pollen": air_current.get("ragweed_pollen") or 0
    }


def forecast_environment(lat, lon):
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m"
        f"&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m"
        f"&forecast_days=1"
    )

    air_url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=european_aqi,pm2_5,birch_pollen,grass_pollen,ragweed_pollen"
        f"&forecast_days=1"
    )

    weather_resp = requests.get(weather_url, timeout=12)
    air_resp = requests.get(air_url, timeout=12)

    weather_resp.raise_for_status()
    air_resp.raise_for_status()

    weather_json = weather_resp.json()
    air_json = air_resp.json()

    weather_hourly = weather_json.get("hourly", {})
    air_hourly = air_json.get("hourly", {})

    times = weather_hourly.get("time", [])
    start_index = 0

    current_time = weather_json.get("current", {}).get("time")
    if current_time in times:
        start_index = times.index(current_time)

    end_index = min(start_index + 6, len(times))

    return {
        "temperature": weather_hourly.get("temperature_2m", [])[start_index:end_index],
        "humidity": weather_hourly.get("relative_humidity_2m", [])[start_index:end_index],
        "wind_speed": weather_hourly.get("wind_speed_10m", [])[start_index:end_index],
        "aqi": air_hourly.get("european_aqi", [])[start_index:end_index],
        "pm25": air_hourly.get("pm2_5", [])[start_index:end_index],
        "birch_pollen": air_hourly.get("birch_pollen", [])[start_index:end_index],
        "grass_pollen": air_hourly.get("grass_pollen", [])[start_index:end_index],
        "ragweed_pollen": air_hourly.get("ragweed_pollen", [])[start_index:end_index]
    }


def build_forecast_text(current_score, future_scores, allergen_label):
    if not future_scores:
        return f"{allergen_label}: недостаточно данных для прогноза"

    future_avg = round(mean(future_scores))
    future_max = max(future_scores)

    if future_max >= current_score + 15:
        future_level = risk_bundle(future_max)["level"]
        return f"{allergen_label}: в ближайшие 6 часов ожидается рост риска до уровня «{future_level}»"
    elif future_avg <= current_score - 10:
        return f"{allergen_label}: в ближайшие 6 часов ожидается снижение риска"
    else:
        return f"{allergen_label}: в ближайшие 6 часов значительных изменений не ожидается"


def point_payload(lat, lon, allergen_key, with_forecast=True):
    allergen_info = ALLERGENS.get(allergen_key, ALLERGENS["birch"])
    allergen_field = allergen_info["field"]
    allergen_label = allergen_info["label"]

    env = current_environment(lat, lon)

    allergen_value = env.get(allergen_field, 0)
    current_score = calc_score(
        allergen_value=allergen_value,
        pm25=env.get("pm25"),
        aqi=env.get("aqi"),
        wind_speed=env.get("wind_speed"),
        humidity=env.get("humidity"),
        temperature=env.get("temperature")
    )

    rb = risk_bundle(current_score)

    forecast_text = f"{allergen_label}: расчёт прогноза недоступен"
    if with_forecast:
        future = forecast_environment(lat, lon)
        future_scores = []

        allergen_forecast_values = future.get(allergen_field, [])

        for i in range(len(allergen_forecast_values)):
            score = calc_score(
                allergen_value=allergen_forecast_values[i],
                pm25=future.get("pm25", [None] * len(allergen_forecast_values))[i] if i < len(future.get("pm25", [])) else None,
                aqi=future.get("aqi", [None] * len(allergen_forecast_values))[i] if i < len(future.get("aqi", [])) else None,
                wind_speed=future.get("wind_speed", [None] * len(allergen_forecast_values))[i] if i < len(future.get("wind_speed", [])) else None,
                humidity=future.get("humidity", [None] * len(allergen_forecast_values))[i] if i < len(future.get("humidity", [])) else None,
                temperature=future.get("temperature", [None] * len(allergen_forecast_values))[i] if i < len(future.get("temperature", [])) else None
            )
            future_scores.append(score)

        forecast_text = build_forecast_text(current_score, future_scores, allergen_label)

    return {
        "lat": lat,
        "lon": lon,
        "temperature": env.get("temperature"),
        "humidity": env.get("humidity"),
        "wind_speed": env.get("wind_speed"),
        "aqi": env.get("aqi"),
        "pm25": env.get("pm25"),
        "allergen": allergen_key,
        "allergen_label": allergen_label,
        "allergen_desc": allergen_info["desc"],
        "allergen_value": allergen_value,
        "risk": rb["level"],
        "score": current_score,
        "color": rb["color"],
        "marker_value": rb["marker_value"],
        "forecast": forecast_text
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/risk", methods=["POST"])
def api_risk():
    data = request.get_json(force=True)
    lat = float(data.get("lat"))
    lon = float(data.get("lon"))
    allergen = data.get("allergen", "birch")

    try:
        result = point_payload(lat, lon, allergen, with_forecast=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/map-markers")
def api_map_markers():
    allergen = request.args.get("allergen", "birch")

    markers = []
    errors = []

    for point in MAP_POINTS:
        try:
            data = point_payload(point["lat"], point["lon"], allergen, with_forecast=False)
            markers.append({
                "name": point["name"],
                "lat": point["lat"],
                "lon": point["lon"],
                "risk": data["risk"],
                "score": data["score"],
                "color": data["color"],
                "marker_value": data["marker_value"],
                "allergen_label": data["allergen_label"],
                "allergen_value": data["allergen_value"]
            })
        except Exception as e:
            errors.append({"name": point["name"], "error": str(e)})

    return jsonify({
        "allergen": allergen,
        "markers": markers,
        "errors": errors
    })


if __name__ == "__main__":
    app.run(debug=True)