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

# Базовые центры вокруг Москвы и области
BASE_HUBS = [
    {"name": "Москва", "lat": 55.7558, "lon": 37.6176},
    {"name": "Химки", "lat": 55.8970, "lon": 37.4297},
    {"name": "Красногорск", "lat": 55.8310, "lon": 37.3300},
    {"name": "Мытищи", "lat": 55.9105, "lon": 37.7360},
    {"name": "Балашиха", "lat": 55.7963, "lon": 37.9382},
    {"name": "Люберцы", "lat": 55.6765, "lon": 37.8982},
    {"name": "Одинцово", "lat": 55.6780, "lon": 37.2777},
    {"name": "Подольск", "lat": 55.4311, "lon": 37.5455},
    {"name": "Жуковский", "lat": 55.5992, "lon": 38.1167},
    {"name": "Ногинск", "lat": 55.8686, "lon": 38.4418},
    {"name": "Зеленоград", "lat": 55.9825, "lon": 37.1814},
]

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


def build_forecast_text(current_score: int, future_scores: list, allergen_label: str) -> str:
    if not future_scores:
        return f"{allergen_label}: недостаточно данных для прогноза на ближайшие 6 часов"

    future_avg = round(mean(future_scores))
    future_max = max(future_scores)
    future_min = min(future_scores)

    if future_max >= current_score + 15:
        future_level = risk_bundle(future_max)["level"]
        return f"{allergen_label}: в ближайшие 6 часов ожидается рост риска до уровня «{future_level}»"
    if future_min <= current_score - 10 and future_avg <= current_score - 6:
        return f"{allergen_label}: в ближайшие 6 часов ожидается снижение риска"
    return f"{allergen_label}: в ближайшие 6 часов значительных изменений не ожидается"


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


def get_point_full_source(lat: float, lon: float):
    cache_key = ("point-full", round(lat, 4), round(lon, 4))
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    weather_params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "forecast_days": 1,
        "timezone": "auto",
    }
    air_params = {
        "latitude": lat,
        "longitude": lon,
        "current": "european_aqi,pm2_5,birch_pollen,grass_pollen,ragweed_pollen",
        "hourly": "european_aqi,pm2_5,birch_pollen,grass_pollen,ragweed_pollen",
        "forecast_days": 1,
        "timezone": "auto",
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        weather_future = executor.submit(request_json, WEATHER_API_URL, weather_params)
        air_future = executor.submit(request_json, AIR_API_URL, air_params)
        payload = {
            "weather": weather_future.result(),
            "air": air_future.result(),
        }

    cache_set(cache_key, payload, ttl_seconds=900)
    return payload


def calculate_future_scores(weather_json: dict, air_json: dict, allergen_field: str, hours: int = 6) -> list:
    weather_hourly = weather_json.get("hourly", {}) or {}
    air_hourly = air_json.get("hourly", {}) or {}

    times = weather_hourly.get("time", []) or []
    current_time = (weather_json.get("current") or {}).get("time")

    start_index = 0
    if current_time in times:
        start_index = times.index(current_time) + 1

    end_index = min(start_index + hours, len(times))
    if start_index >= end_index:
        return []

    def pick(source: dict, key: str, index: int):
        values = source.get(key, []) or []
        if index < len(values):
            return values[index]
        return None

    scores = []
    for idx in range(start_index, end_index):
        score = calc_score(
            allergen_value=pick(air_hourly, allergen_field, idx),
            pm25=pick(air_hourly, "pm2_5", idx),
            aqi=pick(air_hourly, "european_aqi", idx),
            wind_speed=pick(weather_hourly, "wind_speed_10m", idx),
            humidity=pick(weather_hourly, "relative_humidity_2m", idx),
            temperature=pick(weather_hourly, "temperature_2m", idx),
        )
        scores.append(score)

    return scores


def point_payload(lat: float, lon: float, allergen_key: str, with_forecast: bool = True):
    allergen_key = normalize_allergen(allergen_key)
    allergen_info = ALLERGENS[allergen_key]
    allergen_field = allergen_info["field"]

    source = get_point_full_source(lat, lon) if with_forecast else get_point_current_source(lat, lon)
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
    forecast_text = f"{allergen_info['label']}: прогноз отключён"

    if with_forecast:
        future_scores = calculate_future_scores(weather_json, air_json, allergen_field, hours=6)
        forecast_text = build_forecast_text(score, future_scores, allergen_info["label"])

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
        "forecast": forecast_text,
    }


def points_per_hub_by_zoom(zoom: int) -> int:
    if zoom <= 8:
        return 1
    if zoom <= 9:
        return 2
    if zoom <= 10:
        return 3
    if zoom <= 11:
        return 4
    return 5


def natural_scattered_points(south: float, west: float, north: float, east: float, zoom: int):
    points = []
    per_hub = points_per_hub_by_zoom(zoom)

    for hub_index, hub in enumerate(BASE_HUBS):
        for idx in range(per_hub):
            angle = (hub_index * 47 + idx * 71) % 360
            rad = math.radians(angle)

            # чем больше zoom, тем меньше разлёт — выглядит естественнее
            spread = max(0.025, 0.16 - zoom * 0.01)
            radius = spread * (0.55 + 0.22 * idx)

            lat = hub["lat"] + math.sin(rad) * radius
            lon = hub["lon"] + math.cos(rad) * radius * 1.35

            if south <= lat <= north and west <= lon <= east:
                points.append({
                    "name": f"{hub['name']} {idx + 1}",
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
                })

    # если в видимой области точек мало, добавим сами центры хабов
    if len(points) < 8:
        for hub in BASE_HUBS:
            if south <= hub["lat"] <= north and west <= hub["lon"] <= east:
                points.append({
                    "name": hub["name"],
                    "lat": round(hub["lat"], 5),
                    "lon": round(hub["lon"], 5),
                })

    return points


def get_batch_map_source(points: list):
    cache_key = (
        "map-batch",
        tuple((round(point["lat"], 4), round(point["lon"], 4)) for point in points),
    )
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    latitudes = ",".join(str(point["lat"]) for point in points)
    longitudes = ",".join(str(point["lon"]) for point in points)

    weather_params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
    }
    air_params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "current": "european_aqi,pm2_5,birch_pollen,grass_pollen,ragweed_pollen",
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        weather_future = executor.submit(request_json, WEATHER_API_URL, weather_params)
        air_future = executor.submit(request_json, AIR_API_URL, air_params)
        weather_json = weather_future.result()
        air_json = air_future.result()

    weather_items = weather_json if isinstance(weather_json, list) else [weather_json]
    air_items = air_json if isinstance(air_json, list) else [air_json]

    data = []
    for index, point in enumerate(points):
        weather_item = weather_items[index] if index < len(weather_items) else {}
        air_item = air_items[index] if index < len(air_items) else {}

        data.append(
            {
                "name": point["name"],
                "lat": point["lat"],
                "lon": point["lon"],
                "temperature": ((weather_item or {}).get("current") or {}).get("temperature_2m"),
                "humidity": ((weather_item or {}).get("current") or {}).get("relative_humidity_2m"),
                "wind_speed": ((weather_item or {}).get("current") or {}).get("wind_speed_10m"),
                "aqi": ((air_item or {}).get("current") or {}).get("european_aqi"),
                "pm25": ((air_item or {}).get("current") or {}).get("pm2_5"),
                "birch_pollen": ((air_item or {}).get("current") or {}).get("birch_pollen") or 0,
                "grass_pollen": ((air_item or {}).get("current") or {}).get("grass_pollen") or 0,
                "ragweed_pollen": ((air_item or {}).get("current") or {}).get("ragweed_pollen") or 0,
            }
        )

    cache_set(cache_key, data, ttl_seconds=240)
    return data


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/risk", methods=["POST"])
def api_risk():
    data = request.get_json(silent=True) or {}
    lat = data.get("lat")
    lon = data.get("lon")
    allergen = normalize_allergen(data.get("allergen", "birch"))
    with_forecast = bool(data.get("with_forecast", True))

    if lat is None or lon is None:
        return jsonify({"error": "Нужно передать lat и lon"}), 400

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return jsonify({"error": "lat и lon должны быть числами"}), 400

    try:
        return jsonify(point_payload(lat, lon, allergen, with_forecast=with_forecast))
    except requests.RequestException:
        return jsonify({"error": "Не удалось получить данные Open-Meteo"}), 502
    except Exception as exc:
        return jsonify({"error": f"Внутренняя ошибка сервера: {exc}"}), 500


@app.route("/api/map-markers", methods=["GET"])
def api_map_markers():
    allergen = normalize_allergen(request.args.get("allergen", "birch"))

    try:
        south = safe_float(request.args.get("south"), 55.2)
        west = safe_float(request.args.get("west"), 36.8)
        north = safe_float(request.args.get("north"), 56.1)
        east = safe_float(request.args.get("east"), 38.3)
        zoom = int(float(request.args.get("zoom", 9)))

        allergen_info = ALLERGENS[allergen]
        allergen_field = allergen_info["field"]

        dynamic_points = natural_scattered_points(south, west, north, east, zoom)
        source_rows = get_batch_map_source(dynamic_points)

        markers = []
        for row in source_rows:
            allergen_value = row.get(allergen_field, 0)
            score = calc_score(
                allergen_value=allergen_value,
                pm25=row.get("pm25"),
                aqi=row.get("aqi"),
                wind_speed=row.get("wind_speed"),
                humidity=row.get("humidity"),
                temperature=row.get("temperature"),
            )
            bundle = risk_bundle(score)

            markers.append(
                {
                    "name": row["name"],
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "risk": bundle["level"],
                    "score": score,
                    "color": bundle["color"],
                    "marker_value": bundle["marker_value"],
                    "allergen": allergen,
                    "allergen_label": allergen_info["label"],
                    "allergen_value": round(safe_float(allergen_value, 0.0) or 0.0, 1),
                }
            )

        return jsonify(
            {
                "allergen": allergen,
                "allergen_label": allergen_info["label"],
                "count": len(markers),
                "zoom": zoom,
                "markers": markers,
            }
        )
    except requests.RequestException:
        return jsonify({"error": "Не удалось получить карту маркеров из Open-Meteo", "markers": []}), 502
    except Exception as exc:
        return jsonify({"error": f"Ошибка построения карты маркеров: {exc}", "markers": []}), 500


if __name__ == "__main__":
    app.run(debug=True)