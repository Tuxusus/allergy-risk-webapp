from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from flask_cors import CORS
import mysql.connector
import bcrypt
import secrets
import requests
import time
import math
from datetime import timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=7)
CORS(app, supports_credentials=True)

# =====================
# НАСТРОЙКА БАЗЫ ДАННЫХ
# =====================

DB_CONFIG = {
    'host': 'localhost',
    'user': 'allergy_user',
    'password': 'allergy_password',
    'database': 'allergy_db'
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def init_db():
    """Инициализация базы данных MySQL (создание таблиц)"""
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password']
        )
        cursor = conn.cursor()
        
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        cursor.execute(f"USE {DB_CONFIG['database']}")
        
        # Таблица пользователей с is_blocked
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(30) DEFAULT 'user',
                is_blocked TINYINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица аллергенов пользователя
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
        
        # Таблица опасных зон
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS danger_zones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                lat DECIMAL(10,6) NOT NULL,
                lon DECIMAL(10,6) NOT NULL,
                radius INT DEFAULT 1500,
                allergen_type VARCHAR(30) NOT NULL,
                severity INT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица истории маршрутов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS route_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                start_lat DECIMAL(10,6),
                start_lon DECIMAL(10,6),
                end_lat DECIMAL(10,6),
                end_lon DECIMAL(10,6),
                risk_score INT,
                allergen_type VARCHAR(30),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Таблица системных логов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                username VARCHAR(50),
                action VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица статей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                content TEXT NOT NULL,
                category VARCHAR(50) DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица избранных мест
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorite_places (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                name VARCHAR(100),
                lat DECIMAL(10,6) NOT NULL,
                lon DECIMAL(10,6) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ База данных MySQL успешно инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации MySQL: {e}")

init_db()

# =====================
# ООП КЛАССЫ
# =====================

class User:
    def __init__(self, id, username, email, role, is_blocked=0):
        self.id = id
        self.username = username
        self.email = email
        self.role = role
        self.is_blocked = is_blocked
    
    @staticmethod
    def get_by_id(user_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, email, role, is_blocked FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        if user_data:
            return User(user_data['id'], user_data['username'], user_data['email'], user_data['role'], user_data['is_blocked'])
        return None

class DangerZone:
    def __init__(self, id, name, lat, lon, radius, allergen_type, severity, created_at=None):
        self.id = id
        self.name = name
        self.lat = lat
        self.lon = lon
        self.radius = radius
        self.allergen_type = allergen_type
        self.severity = severity
        self.created_at = created_at
    
    @staticmethod
    def get_all(allergen_type=None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if allergen_type:
            cursor.execute("SELECT id, name, lat, lon, radius, allergen_type, severity, created_at FROM danger_zones WHERE allergen_type = %s", (allergen_type,))
        else:
            cursor.execute("SELECT id, name, lat, lon, radius, allergen_type, severity, created_at FROM danger_zones")
        zones = cursor.fetchall()
        cursor.close()
        conn.close()
        return [DangerZone(**z) for z in zones]
    
    def save(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO danger_zones (name, lat, lon, radius, allergen_type, severity)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (self.name, self.lat, self.lon, self.radius, self.allergen_type, self.severity))
        conn.commit()
        self.id = cursor.lastrowid
        cursor.close()
        conn.close()
        return self.id

class RouteHistory:
    @staticmethod
    def save(user_id, start_lat, start_lon, end_lat, end_lon, risk_score, allergen_type):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO route_history (user_id, start_lat, start_lon, end_lat, end_lon, risk_score, allergen_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, start_lat, start_lon, end_lat, end_lon, risk_score, allergen_type))
        conn.commit()
        cursor.close()
        conn.close()
    
    @staticmethod
    def get_user_history(user_id, limit=20):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM route_history 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT %s
        """, (user_id, limit))
        history = cursor.fetchall()
        cursor.close()
        conn.close()
        return history

# =====================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================

def get_current_user_obj():
    if 'user_id' in session:
        return User.get_by_id(session['user_id'])
    return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Не авторизован"}), 401
        return f(*args, **kwargs)
    return decorated_function

def add_log(user_id, username, action):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO system_logs (user_id, username, action) VALUES (%s, %s, %s)", 
                       (user_id, username, action))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Лог не записан: {e}")

# =====================
# API ДЛЯ ПОГОДЫ И РИСКА
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
# API АВТОРИЗАЦИИ
# =====================

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not username or not email or not password:
        return jsonify({"error": "Заполните все поля"}), 400
    if len(username) < 3:
        return jsonify({"error": "Имя пользователя минимум 3 символа"}), 400
    if len(password) < 4:
        return jsonify({"error": "Пароль минимум 4 символа"}), 400
    
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'user')",
            (username, email, password_hash.decode('utf-8'))
        )
        conn.commit()
        user_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username
        add_log(user_id, username, "Регистрация нового пользователя")
        
        return jsonify({"success": True, "user_id": user_id, "username": username, "message": "Регистрация успешна"})
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
        
        if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            
            add_log(user['id'], user['username'], "Вход в систему")
            
            return jsonify({"success": True, "user_id": user['id'], "username": user['username'], "message": "Вход выполнен успешно"})
        else:
            return jsonify({"error": "Неверный пароль"}), 401
    except Exception as e:
        return jsonify({"error": f"Ошибка: {str(e)}"}), 500

@app.route("/api/logout", methods=["POST"])
def logout():
    if 'user_id' in session and 'username' in session:
        add_log(session['user_id'], session['username'], "Выход из системы")
    session.clear()
    return jsonify({"success": True, "message": "Вы вышли из системы"})

@app.route("/api/user/me", methods=["GET"])
def get_current_user_api():
    if 'user_id' in session:
        user = get_current_user_obj()
        role = user.role if user else 'user'
        return jsonify({"authenticated": True, "user_id": session['user_id'], "username": session['username'], "role": role})
    return jsonify({"authenticated": False})

@app.route("/api/user/allergens", methods=["GET"])
def get_user_allergens():
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
        
        return jsonify({"success": True, "allergens": [a['allergen_type'] for a in allergens]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user/allergens", methods=["POST"])
def add_user_allergen():
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
        
        return jsonify({"success": True, "message": f"Аллерген добавлен"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user/allergens/<allergen_type>", methods=["DELETE"])
def remove_user_allergen(allergen_type):
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
        return jsonify({"error": f"Не удалось получить данные: {str(e)}"}), 502
    except Exception as exc:
        return jsonify({"error": f"Внутренняя ошибка: {exc}"}), 500

@app.route("/api/route/save", methods=["POST"])
@login_required
def save_route():
    data = request.get_json()
    RouteHistory.save(
        session['user_id'],
        data.get("start_lat"),
        data.get("start_lon"),
        data.get("end_lat"),
        data.get("end_lon"),
        data.get("risk_score", 0),
        data.get("allergen_type", "birch")
    )
    return jsonify({"success": True, "message": "Маршрут сохранён"})

@app.route("/api/route/history", methods=["GET"])
@login_required
def get_route_history():
    limit = request.args.get("limit", 20, type=int)
    history = RouteHistory.get_user_history(session['user_id'], limit)
    return jsonify({"success": True, "history": history, "count": len(history)})

# =====================
# ДОПОЛНИТЕЛЬНЫЕ API
# =====================

@app.route("/api/articles", methods=["GET"])
def get_articles():
    category = request.args.get("category", "")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if category:
        cursor.execute("SELECT id, title, content, category, created_at FROM articles WHERE category = %s ORDER BY created_at DESC", (category,))
    else:
        cursor.execute("SELECT id, title, content, category, created_at FROM articles ORDER BY created_at DESC")
    
    articles = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return jsonify({"success": True, "articles": articles})

@app.route("/api/favorites", methods=["GET"])
@login_required
def get_favorites():
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, lat, lon, created_at FROM favorite_places WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    favorites = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return jsonify({"success": True, "favorites": favorites})

@app.route("/api/favorites", methods=["POST"])
@login_required
def add_favorite():
    data = request.get_json()
    name = data.get("name", "")
    lat = data.get("lat")
    lon = data.get("lon")
    user_id = session['user_id']
    
    if lat is None or lon is None:
        return jsonify({"error": "Не указаны координаты"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO favorite_places (user_id, name, lat, lon) VALUES (%s, %s, %s, %s)",
        (user_id, name, lat, lon)
    )
    conn.commit()
    favorite_id = cursor.lastrowid
    cursor.close()
    conn.close()
    
    return jsonify({"success": True, "id": favorite_id, "message": "Место добавлено в избранное"})

@app.route("/api/favorites/<int:favorite_id>", methods=["DELETE"])
@login_required
def delete_favorite(favorite_id):
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM favorite_places WHERE id = %s AND user_id = %s", (favorite_id, user_id))
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    
    if affected:
        return jsonify({"success": True, "message": "Место удалено из избранного"})
    return jsonify({"error": "Место не найдено"}), 404

@app.route("/api/statistics", methods=["GET"])
def get_statistics():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT AVG(risk_score) as avg_risk FROM route_history")
    avg_risk = cursor.fetchone()['avg_risk'] or 0
    
    cursor.execute("SELECT COUNT(*) as total FROM route_history")
    total_routes = cursor.fetchone()['total']
    
    cursor.execute("SELECT MAX(risk_score) as max_risk FROM route_history")
    max_risk = cursor.fetchone()['max_risk'] or 0
    
    cursor.execute("""
        SELECT allergen_type, COUNT(*) as cnt 
        FROM route_history 
        GROUP BY allergen_type 
        ORDER BY cnt DESC 
        LIMIT 1
    """)
    top_allergen_row = cursor.fetchone()
    top_allergen = top_allergen_row['allergen_type'] if top_allergen_row else 'birch'
    
    cursor.close()
    conn.close()
    
    allergen_names = {"birch": "Берёза", "grass": "Злаки", "ragweed": "Амброзия"}
    
    return jsonify({
        "success": True,
        "statistics": {
            "avg_risk": round(avg_risk, 1),
            "total_routes": total_routes,
            "max_risk": max_risk,
            "top_allergen": allergen_names.get(top_allergen, top_allergen)
        }
    })

# =====================
# АДМИН-ПАНЕЛЬ
# =====================

@app.route("/admin/global")
def admin_global():
    user = get_current_user_obj()
    if not user or user.role != 'global_admin':
        return "Доступ запрещён", 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role != 'guest'")
    auth_users = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM route_history")
    total_routes = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM danger_zones")
    total_zones = cursor.fetchone()['count']
    
    cursor.execute("SELECT id, username, email, role FROM users WHERE role IN ('allergen_admin', 'user_admin')")
    admins = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template("admin/global_admin.html", 
                          username=user.username, 
                          role=user.role,
                          total_users=total_users,
                          auth_users=auth_users,
                          total_routes=total_routes,
                          total_zones=total_zones,
                          admins=admins)

@app.route("/admin/allergen")
def admin_allergen():
    user = get_current_user_obj()
    if not user or user.role not in ['global_admin', 'allergen_admin']:
        return "Доступ запрещён", 403
    
    zones = DangerZone.get_all()
    
    return render_template("admin/allergen_admin.html",
                          username=user.username,
                          role=user.role,
                          zones=zones)

@app.route("/admin/allergen/add-zone", methods=["POST"])
def add_zone():
    user = get_current_user_obj()
    if not user or user.role not in ['global_admin', 'allergen_admin']:
        return "Доступ запрещён", 403
    
    zone = DangerZone(
        id=None,
        name=request.form.get("name"),
        lat=float(request.form.get("lat")),
        lon=float(request.form.get("lon")),
        radius=int(request.form.get("radius")),
        allergen_type=request.form.get("allergen_type"),
        severity=1
    )
    zone.save()
    add_log(user.id, user.username, f"Добавлена зона: {zone.name}")
    return redirect("/admin/allergen")
@app.route("/admin/allergen/stats")
def allergen_stats():
    user = get_current_user_obj()
    if not user or user.role not in ['global_admin', 'allergen_admin']:
        return "Доступ запрещён", 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            allergen_type,
            COUNT(*) as count
        FROM danger_zones
        GROUP BY allergen_type
    """)
    stats = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # Перевод названий аллергенов
    allergen_names = {
        "birch": "Берёза",
        "grass": "Злаки",
        "ragweed": "Амброзия"
    }
    
    for s in stats:
        s['allergen_label'] = allergen_names.get(s['allergen_type'], s['allergen_type'])
    
    return render_template("admin/allergen_stats.html", 
                          username=user.username, 
                          role=user.role, 
                          stats=stats)

@app.route("/admin/allergen/delete-zone", methods=["POST"])
def delete_zone():
    user = get_current_user_obj()
    if not user or user.role not in ['global_admin', 'allergen_admin']:
        return "Доступ запрещён", 403
    
    zone_id = request.form.get("zone_id")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM danger_zones WHERE id = %s", (zone_id,))
    zone_result = cursor.fetchone()
    zone_name = zone_result[0] if zone_result else f"ID={zone_id}"
    
    cursor.execute("DELETE FROM danger_zones WHERE id = %s", (zone_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    add_log(user.id, user.username, f"Удалена зона: {zone_name}")
    return redirect("/admin/allergen")

@app.route("/admin/users-list")
def admin_users_list():
    user = get_current_user_obj()
    if not user or user.role != 'global_admin':
        return "Доступ запрещён", 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email, role, created_at FROM users ORDER BY id")
    all_users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template("admin/users_list.html", 
                          username=user.username, 
                          role=user.role, 
                          users=all_users)

@app.route("/admin/user")
def admin_user():
    user = get_current_user_obj()
    if not user or user.role not in ['global_admin', 'user_admin']:
        return "Доступ запрещён", 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email, role, is_blocked FROM users")
    users = cursor.fetchall()
    
    cursor.execute("""
        SELECT rh.*, u.username 
        FROM route_history rh 
        JOIN users u ON rh.user_id = u.id 
        ORDER BY rh.created_at DESC 
        LIMIT 50
    """)
    routes = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template("admin/user_admin.html",
                          username=user.username,
                          role=user.role,
                          users=users,
                          routes=routes)

@app.route("/admin/global/add-admin", methods=["POST"])
def add_admin():
    user = get_current_user_obj()
    if not user or user.role != 'global_admin':
        return "Доступ запрещён", 403
    
    email = request.form.get("email")
    role = request.form.get("role")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = %s WHERE email = %s", (role, email))
    conn.commit()
    cursor.close()
    conn.close()
    
    add_log(user.id, user.username, f"Назначен администратор {email} с ролью {role}")
    return redirect("/admin/global")

@app.route("/admin/user/block", methods=["POST"])
def block_user():
    user = get_current_user_obj()
    if not user or (user.role not in ['global_admin', 'user_admin']):
        return "Доступ запрещён", 403
    
    user_id = request.form.get("user_id")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    target_user = cursor.fetchone()
    target_username = target_user[0] if target_user else str(user_id)
    
    cursor.execute("UPDATE users SET is_blocked = 1 WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    add_log(user.id, user.username, f"Заблокирован пользователь: {target_username}")
    return redirect("/admin/user")

@app.route("/admin/user/unblock", methods=["POST"])
def unblock_user():
    user = get_current_user_obj()
    if not user or (user.role not in ['global_admin', 'user_admin']):
        return "Доступ запрещён", 403
    
    user_id = request.form.get("user_id")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    target_user = cursor.fetchone()
    target_username = target_user[0] if target_user else str(user_id)
    
    cursor.execute("UPDATE users SET is_blocked = 0 WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    add_log(user.id, user.username, f"Разблокирован пользователь: {target_username}")
    return redirect("/admin/user")

@app.route("/admin/user-stats")
def admin_user_stats():
    user = get_current_user_obj()
    if not user or user.role not in ['global_admin', 'user_admin']:
        return "Доступ запрещён", 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.id, u.username, u.email, u.role, COUNT(rh.id) as routes_count
        FROM users u
        LEFT JOIN route_history rh ON u.id = rh.user_id
        GROUP BY u.id
        ORDER BY routes_count DESC
    """)
    stats = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template("admin/user_stats.html", 
                          username=user.username, 
                          role=user.role, 
                          stats=stats)

@app.route("/admin/logs")
def admin_logs():
    user = get_current_user_obj()
    if not user or user.role != 'global_admin':
        return "Доступ запрещён", 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM system_logs ORDER BY created_at DESC LIMIT 100")
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template("admin/logs.html", username=user.username, role=user.role, logs=logs)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)