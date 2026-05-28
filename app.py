from concurrent.futures import ThreadPoolExecutor
from statistics import mean
from threading import Lock
from flask import Flask, jsonify, render_template, request
import requests
import time
import math

app = Flask(__name__)

WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
AIR_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

ALLERGENS = {
    "birch": {
        "label": "Берёза",
        "field": "birch_pollen",
        "desc": "основной весенний аллерген",
    },
    "grass": {
        "label": "Злаки",
        "field": "grass_pollen",
        "desc": "сезонный травяной аллерген",
    },
    "ragweed": {
        "label": "Амброзия",
        "field": "ragweed_pollen",
        "desc": "высокоаллергенное растение",
    },
}

HTTP_HEADERS = {"User-Agent": "AllergyRiskMVP/1.0"}

_CACHE = {}
_CACHE_LOCK = Lock()


def normalize_allergen(value: str) -> str:
    return value if value in ALLERGENS else "birch"


def cache_get(key):
    now = time.time()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        expires_at, payload = item
        if expires_at <= now:
            del _CACHE[key]
            return None
        return payload


def cache_set(key, payload, ttl_seconds: int):
    expires_at = time.time() + ttl_seconds
    with _CACHE_LOCK:
        _CACHE[key] = (expires_at, payload)


def safe_float(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def request_json(url: str, params: dict):
    response = requests.get(url, params=params, timeout=15, headers=HTTP_HEADERS)
    response.raise_for_status()
    return response.json()


def risk_bundle(score: int):
    if score < 25:
        return {"level": "Низкий", "color": "#53B97C", "marker_value": 1, "css": "low"}
    if score < 50:
        return {"level": "Средний", "color": "#A8C94A", "marker_value": 2, "css": "medium"}
    if score < 75:
        return {"level": "Высокий", "color": "#E8A23A", "marker_value": 3, "css": "high"}
    return {"level": "Очень высокий", "color": "#D65A63", "marker_value": 4, "css": "very-high"}


def calc_score(allergen_value, pm25, aqi, wind_speed, humidity, temperature) -> int:
    allergen_value = safe_float(allergen_value, 0.0) or 0.0
    pm25 = safe_float(pm25, None)
    aqi = safe_float(aqi, None)
    wind_speed = safe_float(wind_speed, None)
    humidity = safe_float(humidity, None)
    temperature = safe_float(temperature, None)

    score = 0

    if allergen_value >= 80:
        score += 50
    elif allergen_value >= 40:
        score += 35
    elif allergen_value >= 15:
        score += 20
    elif allergen_value >= 5:
        score += 10

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

    if wind_speed is not None:
        if wind_speed >= 8:
            score += 8
        elif wind_speed >= 5:
            score += 4
        elif wind_speed <= 2:
            score -= 2

    if humidity is not None:
        if humidity < 40:
            score += 6
        elif humidity >= 75:
            score -= 4

    if temperature is not None:
        if temperature > 15:
            score += 6
        elif temperature < 8:
            score -= 2

    return max(0, min(int(round(score)), 100))


def get_point_current_source(lat: float, lon: float):
    cache_key = ("point-current", round(lat, 4), round(lon, 4))
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    weather_params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "timezone": "auto",
    }
    air_params = {
        "latitude": lat,
        "longitude": lon,
        "current": "european_aqi,pm2_5,birch_pollen,grass_pollen,ragweed_pollen",
        "timezone": "auto",
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        weather_future = executor.submit(request_json, WEATHER_API_URL, weather_params)
        air_future = executor.submit(request_json, AIR_API_URL, air_params)
        payload = {
            "weather": weather_future.result(),
            "air": air_future.result(),
        }

    cache_set(cache_key, payload, ttl_seconds=300)
    return payload


def point_payload(lat: float, lon: float, allergen_key: str, with_forecast: bool = True):
    allergen_key = normalize_allergen(allergen_key)
    allergen_info = ALLERGENS[allergen_key]
    allergen_field = allergen_info["field"]

    source = get_point_current_source(lat, lon)
    weather_json = source["weather"]
    air_json = source["air"]

    weather_current = weather_json.get("current", {}) or {}
    air_current = air_json.get("current", {}) or {}

    allergen_value = safe_float(air_current.get(allergen_field), 0.0) or 0.0
    aqi = safe_float(air_current.get("european_aqi"), None)
    pm25 = safe_float(air_current.get("pm2_5"), None)
    wind_speed = safe_float(weather_current.get("wind_speed_10m"), None)
    humidity = safe_float(weather_current.get("relative_humidity_2m"), None)
    temperature = safe_float(weather_current.get("temperature_2m"), None)

    score = calc_score(
        allergen_value=allergen_value,
        pm25=pm25,
        aqi=aqi,
        wind_speed=wind_speed,
        humidity=humidity,
        temperature=temperature,
    )

    bundle = risk_bundle(score)

    return {
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "temperature": temperature,
        "humidity": humidity,
        "wind_speed": wind_speed,
        "aqi": aqi,
        "pm25": pm25,
        "allergen": allergen_key,
        "allergen_label": allergen_info["label"],
        "allergen_desc": allergen_info["desc"],
        "allergen_value": round(allergen_value, 1),
        "risk": bundle["level"],
        "score": score,
        "color": bundle["color"],
        "marker_value": bundle["marker_value"],
        "risk_css": bundle["css"],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/risk", methods=["POST"])
def api_risk():
    data = request.get_json(silent=True) or {}
    lat = data.get("lat")
    lon = data.get("lon")
    allergen = normalize_allergen(data.get("allergen", "birch"))

    if lat is None or lon is None:
        return jsonify({"error": "Нужно передать lat и lon"}), 400

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return jsonify({"error": "lat и lon должны быть числами"}), 400

    try:
        return jsonify(point_payload(lat, lon, allergen, with_forecast=False))
    except requests.RequestException as e:
        return jsonify({"error": f"Не удалось получить данные Open-Meteo: {str(e)}"}), 502
    except Exception as exc:
        return jsonify({"error": f"Внутренняя ошибка сервера: {exc}"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)