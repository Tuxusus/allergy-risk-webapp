from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS
import mysql.connector
import bcrypt
import secrets
import requests
import time
import math
from datetime import timedelta

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Секретный ключ для сессий
app.permanent_session_lifetime = timedelta(days=7)  # Сессия на 7 дней
CORS(app, supports_credentials=True)

# =====================
# НАСТРОЙКА БАЗЫ ДАННЫХ (MySQL)
# =====================

# Конфигурация MySQL (измените под ваши данные)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'allergy_user',
    'password': 'allergy_password',
    'database': 'allergy_db'
}

def init_db():
    """Инициализация базы данных MySQL"""
    try:
        # Подключаемся без базы данных сначала
        conn = mysql.connector.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password']
        )
        cursor = conn.cursor()
        
        # Создаём базу данных если её нет
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        cursor.execute(f"USE {DB_CONFIG['database']}")
        
        # Создаём таблицу пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Создаём таблицу аллергенов пользователя
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_allergens (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                allergen_type VARCHAR(50) NOT NULL,
                severity INT DEFAULT 3,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY unique_user_allergen (user_id, allergen_type)
            )
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ База данных MySQL успешно инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации MySQL: {e}")

# Функция для получения соединения с БД
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# Инициализируем БД при старте
init_db()

# =====================
# ОСТАЛЬНОЙ КОД (API, калькуляторы и т.д.)
# =====================

WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
AIR_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

ALLERGENS = {
    "birch": {"label": "Берёза", "field": "birch_pollen", "desc": "основной весенний аллерген"},
    "grass": {"label": "Злаки", "field": "grass_pollen", "desc": "сезонный травяной аллерген"},
    "ragweed": {"label": "Амброзия", "field": "ragweed_pollen", "desc": "высокоаллергенное растение"}
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
        return {"level": "Средний", "color": "#E8A23A", "marker_value": 2, "css": "medium"}
    if score < 75:
        return {"level": "Высокий", "color": "#D65A63", "marker_value": 3, "css": "high"}
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
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m", "timezone": "auto"
    }
    air_params = {
        "latitude": lat, "longitude": lon,
        "current": "european_aqi,pm2_5,birch_pollen,grass_pollen,ragweed_pollen", "timezone": "auto"
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        weather_future = executor.submit(request_json, WEATHER_API_URL, weather_params)
        air_future = executor.submit(request_json, AIR_API_URL, air_params)
        payload = {"weather": weather_future.result(), "air": air_future.result()}

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

    score = calc_score(allergen_value=allergen_value, pm25=pm25, aqi=aqi,
                       wind_speed=wind_speed, humidity=humidity, temperature=temperature)

    bundle = risk_bundle(score)

    return {
        "lat": round(lat, 6), "lon": round(lon, 6), "temperature": temperature,
        "humidity": humidity, "wind_speed": wind_speed, "aqi": aqi, "pm25": pm25,
        "allergen": allergen_key, "allergen_label": allergen_info["label"],
        "allergen_desc": allergen_info["desc"], "allergen_value": round(allergen_value, 1),
        "risk": bundle["level"], "score": score, "color": bundle["color"],
        "marker_value": bundle["marker_value"], "risk_css": bundle["css"],
    }

# =====================
# API РЕГИСТРАЦИИ И АВТОРИЗАЦИИ
# =====================

@app.route("/api/register", methods=["POST"])
def register():
    """Регистрация нового пользователя"""
    data = request.get_json()
    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    # Валидация
    if not username or not email or not password:
        return jsonify({"error": "Заполните все поля"}), 400
    
    if len(username) < 3:
        return jsonify({"error": "Имя пользователя минимум 3 символа"}), 400
    
    if len(password) < 4:
        return jsonify({"error": "Пароль минимум 4 символа"}), 400
    
    # Хэшируем пароль
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (username, email, password_hash.decode('utf-8'))
        )
        conn.commit()
        
        # Получаем ID нового пользователя
        user_id = cursor.lastrowid
        
        # Создаём сессию
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "username": username,
            "message": "Регистрация успешна"
        })
    except mysql.connector.IntegrityError as e:
        if "username" in str(e):
            return jsonify({"error": "Пользователь с таким именем уже существует"}), 400
        if "email" in str(e):
            return jsonify({"error": "Пользователь с таким email уже существует"}), 400
        return jsonify({"error": "Ошибка при регистрации"}), 400
    except Exception as e:
        return jsonify({"error": f"Ошибка: {str(e)}"}), 500

@app.route("/api/login", methods=["POST"])
def login():
    """Вход пользователя"""
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"error": "Заполните все поля"}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user:
            return jsonify({"error": "Пользователь не найден"}), 401
        
        # Проверяем пароль
        if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            
            return jsonify({
                "success": True,
                "user_id": user['id'],
                "username": user['username'],
                "message": "Вход выполнен успешно"
            })
        else:
            return jsonify({"error": "Неверный пароль"}), 401
    except Exception as e:
        return jsonify({"error": f"Ошибка: {str(e)}"}), 500

@app.route("/api/logout", methods=["POST"])
def logout():
    """Выход пользователя"""
    session.clear()
    return jsonify({"success": True, "message": "Вы вышли из системы"})

@app.route("/api/user/allergens", methods=["GET"])
def get_user_allergens():
    """Получить аллергены текущего пользователя"""
    if 'user_id' not in session:
        return jsonify({"error": "Не авторизован"}), 401
    
    user_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT allergen_type, severity FROM user_allergens WHERE user_id = %s", (user_id,))
        allergens = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "allergens": [a['allergen_type'] for a in allergens]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user/allergens", methods=["POST"])
def add_user_allergen():
    """Добавить аллерген для пользователя"""
    if 'user_id' not in session:
        return jsonify({"error": "Не авторизован"}), 401
    
    data = request.get_json()
    allergen_type = data.get("allergen_type")
    severity = data.get("severity", 3)
    
    if allergen_type not in ALLERGENS:
        return jsonify({"error": "Неверный тип аллергена"}), 400
    
    user_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_allergens (user_id, allergen_type, severity) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE severity = %s",
            (user_id, allergen_type, severity, severity)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": f"Аллерген {ALLERGENS[allergen_type]['label']} добавлен"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user/allergens/<allergen_type>", methods=["DELETE"])
def remove_user_allergen(allergen_type):
    """Удалить аллерген пользователя"""
    if 'user_id' not in session:
        return jsonify({"error": "Не авторизован"}), 401
    
    user_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM user_allergens WHERE user_id = %s AND allergen_type = %s",
            (user_id, allergen_type)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Аллерген удалён"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user/me", methods=["GET"])
def get_current_user():
    """Получить информацию о текущем пользователе"""
    if 'user_id' in session:
        return jsonify({
            "authenticated": True,
            "user_id": session['user_id'],
            "username": session['username']
        })
    return jsonify({"authenticated": False})

# =====================
# ОСНОВНЫЕ МАРШРУТЫ
# =====================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/risk", methods=["POST"])
def api_risk():
    data = request.get_json(silent=True) or {}
    lat = data.get("lat")
    lon = data.get("lon")
    
    # Если пользователь авторизован и у него есть аллергены
    allergen = data.get("allergen", "birch")
    if 'user_id' in session:
        user_id = session['user_id']
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT allergen_type FROM user_allergens WHERE user_id = %s", (user_id,))
            user_allergens = cursor.fetchall()
            cursor.close()
            conn.close()
            
            if user_allergens:
                # Используем первый аллерген пользователя
                allergen = user_allergens[0][0]
        except Exception as e:
            print(f"Ошибка получения аллергенов: {e}")

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