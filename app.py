from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, send_from_directory
from flask_cors import CORS
import mysql.connector
import bcrypt
import secrets
import requests
import time
import math
from datetime import timedelta
from functools import wraps
import os

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
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password']
        )
        cursor = conn.cursor()
        
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        cursor.execute(f"USE {DB_CONFIG['database']}")
        
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS danger_zones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                lat DECIMAL(10,6) NOT NULL,
                lon DECIMAL(10,6) NOT NULL,
                radius INT DEFAULT 1500,
                allergen_type VARCHAR(30) NOT NULL,
                severity INT DEFAULT 1,
                created_by INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                username VARCHAR(50),
                action VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
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
        
        # Создание тестового глобального администратора
        test_admin_email = "admin@allergy.com"
        test_admin_password = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())
        cursor.execute("SELECT id FROM users WHERE email = %s", (test_admin_email,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, role) 
                VALUES (%s, %s, %s, 'global_admin')
            """, ("GlobalAdmin", test_admin_email, test_admin_password.decode('utf-8')))
            
            test_password = bcrypt.hashpw("user123".encode('utf-8'), bcrypt.gensalt())
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, role) 
                VALUES (%s, %s, %s, 'user')
            """, ("TestUser1", "user1@test.com", test_password.decode('utf-8')))
            
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, role) 
                VALUES (%s, %s, %s, 'user')
            """, ("TestUser2", "user2@test.com", test_password.decode('utf-8')))
            
            cursor.execute("SELECT id FROM users WHERE email = 'user1@test.com'")
            user1 = cursor.fetchone()
            if user1:
                cursor.execute("""
                    INSERT INTO user_allergens (user_id, allergen_type, severity) 
                    VALUES (%s, 'birch', 3), (%s, 'grass', 2)
                """, (user1[0], user1[0]))
            
            cursor.execute("SELECT id FROM users WHERE email = 'user2@test.com'")
            user2 = cursor.fetchone()
            if user2:
                cursor.execute("""
                    INSERT INTO user_allergens (user_id, allergen_type, severity) 
                    VALUES (%s, 'ragweed', 3)
                """, (user2[0],))
            
            # Добавление тестовых опасных зон
            cursor.execute("""
                INSERT INTO danger_zones (name, lat, lon, radius, allergen_type, created_by) 
                VALUES 
                ('Парк Горького', 55.7355, 37.6050, 1500, 'birch', 1),
                ('ВДНХ', 55.8300, 37.6300, 1800, 'grass', 1),
                ('Царицыно', 55.6150, 37.6800, 1200, 'ragweed', 1),
                ('Сокольники', 55.8000, 37.6800, 1400, 'birch', 1),
                ('Измайлово', 55.7900, 37.7600, 1300, 'grass', 1),
                ('Лосиный остров', 55.8300, 37.6500, 2000, 'birch', 1)
            """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("База данных MySQL успешно инициализирована")
    except Exception as e:
        print(f"Ошибка инициализации MySQL: {e}")

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
    
    @staticmethod
    def get_all_users():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, email, role, is_blocked, created_at FROM users ORDER BY id")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        return users
    
    @staticmethod
    def update_role(user_id, new_role):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        conn.close()
        return affected
    
    @staticmethod
    def toggle_block(user_id, block_status):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = %s WHERE id = %s", (block_status, user_id))
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        conn.close()
        return affected

class DangerZone:
    def __init__(self, id=None, name=None, lat=None, lon=None, radius=None, allergen_type=None, severity=1, created_by=None):
        self.id = id
        self.name = name
        self.lat = lat
        self.lon = lon
        self.radius = radius
        self.allergen_type = allergen_type
        self.severity = severity
        self.created_by = created_by
    
    @staticmethod
    def get_all(allergen_type=None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if allergen_type:
            cursor.execute("SELECT id, name, lat, lon, radius, allergen_type, severity, created_by FROM danger_zones WHERE allergen_type = %s ORDER BY id", (allergen_type,))
        else:
            cursor.execute("SELECT id, name, lat, lon, radius, allergen_type, severity, created_by FROM danger_zones ORDER BY id")
        zones = cursor.fetchall()
        cursor.close()
        conn.close()
        return zones
    
    def save(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO danger_zones (name, lat, lon, radius, allergen_type, severity, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (self.name, self.lat, self.lon, self.radius, self.allergen_type, self.severity, self.created_by))
        conn.commit()
        self.id = cursor.lastrowid
        cursor.close()
        conn.close()
        return self.id
    
    @staticmethod
    def delete(zone_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM danger_zones WHERE id = %s", (zone_id,))
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        conn.close()
        return affected

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
            SELECT id, start_lat, start_lon, end_lat, end_lon, risk_score, allergen_type, created_at
            FROM route_history 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT %s
        """, (user_id, limit))
        history = cursor.fetchall()
        cursor.close()
        conn.close()
        return history
    
    @staticmethod
    def get_all_history(limit=100):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT rh.*, u.username 
            FROM route_history rh 
            JOIN users u ON rh.user_id = u.id 
            ORDER BY rh.created_at DESC 
            LIMIT %s
        """, (limit,))
        history = cursor.fetchall()
        cursor.close()
        conn.close()
        return history
    
    @staticmethod
    def get_count():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM route_history")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

class SystemLog:
    @staticmethod
    def add(user_id, username, action):
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
    
    @staticmethod
    def get_all(limit=100):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM system_logs ORDER BY id DESC LIMIT %s", (limit,))
        logs = cursor.fetchall()
        cursor.close()
        conn.close()
        return logs
    
    @staticmethod
    def get_count():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM system_logs")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

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

def regular_user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Не авторизован"}), 401
        user = get_current_user_obj()
        if not user or user.role != 'user':
            return jsonify({"error": "Доступ только для обычных пользователей"}), 403
        return f(*args, **kwargs)
    return decorated_function

def global_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Не авторизован"}), 401
        user = get_current_user_obj()
        if not user or user.role != 'global_admin':
            return jsonify({"error": "Доступ только для глобального администратора"}), 403
        return f(*args, **kwargs)
    return decorated_function

def allergen_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Не авторизован"}), 401
        user = get_current_user_obj()
        if not user or user.role not in ['global_admin', 'allergen_admin']:
            return jsonify({"error": "Доступ только для администратора по аллергенам"}), 403
        return f(*args, **kwargs)
    return decorated_function

def user_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Не авторизован"}), 401
        user = get_current_user_obj()
        if not user or user.role not in ['global_admin', 'user_admin']:
            return jsonify({"error": "Доступ только для администратора по пользователям"}), 403
        return f(*args, **kwargs)
    return decorated_function

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
        SystemLog.add(user_id, username, "Зарегистрировался в системе")
        
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
        
        if user['is_blocked']:
            return jsonify({"error": "Ваш аккаунт заблокирован"}), 401
        
        if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            
            SystemLog.add(user['id'], user['username'], "Выполнен вход в систему")
            
            return jsonify({"success": True, "user_id": user['id'], "username": user['username'], "role": user['role'], "message": "Вход выполнен успешно"})
        else:
            return jsonify({"error": "Неверный пароль"}), 401
    except Exception as e:
        return jsonify({"error": f"Ошибка: {str(e)}"}), 500

@app.route("/api/logout", methods=["POST"])
def logout():
    if 'user_id' in session and 'username' in session:
        SystemLog.add(session['user_id'], session['username'], "Выполнен выход из системы")
    session.clear()
    return jsonify({"success": True, "message": "Вы вышли из системы"})

@app.route("/logout")
def logout_get():
    session.clear()
    return redirect("/")

@app.route("/api/user/me", methods=["GET"])
def get_current_user_api():
    if 'user_id' in session:
        user = get_current_user_obj()
        if user:
            return jsonify({"authenticated": True, "user_id": session['user_id'], "username": session['username'], "role": user.role})
    return jsonify({"authenticated": False})

@app.route("/api/user/allergens", methods=["GET"])
@login_required
def get_user_allergens():
    user = get_current_user_obj()
    if user.role != 'user':
        return jsonify({"success": True, "allergens": []})
    
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
@regular_user_required
def add_user_allergen():
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
        
        SystemLog.add(user_id, session['username'], f"Добавил аллерген: {allergen_type}")
        
        return jsonify({"success": True, "message": f"Аллерген добавлен"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user/allergens/<allergen_type>", methods=["DELETE"])
@regular_user_required
def remove_user_allergen(allergen_type):
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
        
        SystemLog.add(user_id, session['username'], f"Удалил аллерген: {allergen_type}")
        
        return jsonify({"success": True, "message": "Аллерген удалён"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =====================
# ОСНОВНЫЕ МАРШРУТЫ
# =====================

@app.route("/")
def index():
    return render_template("index.html")

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route("/api/risk", methods=["POST"])
def api_risk():
    data = request.get_json(silent=True) or {}
    lat = data.get("lat")
    lon = data.get("lon")
    
    allergen = data.get("allergen", "birch")
    if 'user_id' in session:
        user = get_current_user_obj()
        if user and user.role == 'user':
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT allergen_type FROM user_allergens WHERE user_id = %s", (session['user_id'],))
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
@regular_user_required
def save_route():
    try:
        data = request.get_json()
        user_id = session['user_id']
        
        start_lat = data.get("start_lat")
        start_lon = data.get("start_lon")
        end_lat = data.get("end_lat")
        end_lon = data.get("end_lon")
        risk_score = data.get("risk_score", 0)
        allergen_type = data.get("allergen_type", "birch")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO route_history (user_id, start_lat, start_lon, end_lat, end_lon, risk_score, allergen_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, start_lat, start_lon, end_lat, end_lon, risk_score, allergen_type))
        conn.commit()
        cursor.close()
        conn.close()
        
        SystemLog.add(user_id, session['username'], f"Сохранён маршрут (риск: {risk_score})")
        
        return jsonify({"success": True, "message": "Маршрут сохранён"})
    except Exception as e:
        print(f"Ошибка сохранения маршрута: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/route/history", methods=["GET"])
@regular_user_required
def get_route_history():
    try:
        limit = request.args.get("limit", 20, type=int)
        user_id = session['user_id']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, start_lat, start_lon, end_lat, end_lon, risk_score, allergen_type, created_at
            FROM route_history 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT %s
        """, (user_id, limit))
        history = cursor.fetchall()
        cursor.close()
        conn.close()
        
        for route in history:
            if route['start_lat'] is not None:
                route['start_lat'] = float(route['start_lat'])
            if route['start_lon'] is not None:
                route['start_lon'] = float(route['start_lon'])
            if route['end_lat'] is not None:
                route['end_lat'] = float(route['end_lat'])
            if route['end_lon'] is not None:
                route['end_lon'] = float(route['end_lon'])
            if route['created_at'] is not None:
                route['created_at'] = route['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({"success": True, "history": history, "count": len(history)})
    except Exception as e:
        print(f"Ошибка получения истории: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# =====================
# АДМИН-ПАНЕЛЬ (ГЛОБАЛЬНЫЙ АДМИН)
# =====================

@app.route("/admin/global")
@global_admin_required
def admin_global():
    user = get_current_user_obj()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'user'")
    regular_users = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM route_history")
    total_routes = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM danger_zones")
    total_zones = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM system_logs")
    total_logs = cursor.fetchone()['count']
    
    cursor.execute("""
        SELECT id, username, email, role 
        FROM users 
        WHERE role IN ('allergen_admin', 'user_admin')
        ORDER BY id
    """)
    admins = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template("admin/global_admin.html", 
                          username=user.username, 
                          role=user.role,
                          total_users=total_users,
                          regular_users=regular_users,
                          total_routes=total_routes,
                          total_zones=total_zones,
                          total_logs=total_logs,
                          admins=admins)

@app.route("/admin/global/add-admin", methods=["POST"])
@global_admin_required
def add_admin():
    admin_user = get_current_user_obj()
    email = request.form.get("email")
    role = request.form.get("role")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id, username, role FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    
    if not user:
        cursor.close()
        conn.close()
        return "Пользователь с таким email не найден", 404
    
    if user['role'] != 'user':
        cursor.close()
        conn.close()
        return "Этот пользователь уже является администратором", 400
    
    cursor.execute("UPDATE users SET role = %s WHERE id = %s", (role, user['id']))
    conn.commit()
    cursor.close()
    conn.close()
    
    SystemLog.add(admin_user.id, admin_user.username, f"Назначил {role} пользователю {user['username']} ({email})")
    
    return redirect("/admin/global")

@app.route("/admin/global/remove-admin", methods=["POST"])
@global_admin_required
def remove_admin():
    admin_user = get_current_user_obj()
    user_id = request.form.get("user_id")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id, username, role FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.close()
        conn.close()
        return "Пользователь не найден", 404
    
    if user['role'] == 'global_admin':
        cursor.close()
        conn.close()
        return "Нельзя снять права с глобального администратора", 400
    
    cursor.execute("UPDATE users SET role = 'user' WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    SystemLog.add(admin_user.id, admin_user.username, f"Снял права администратора с {user['username']}")
    
    return redirect("/admin/global")

@app.route("/admin/logs")
@global_admin_required
def admin_logs():
    user = get_current_user_obj()
    logs = SystemLog.get_all(200)
    return render_template("admin/logs.html", username=user.username, role=user.role, logs=logs)

@app.route("/admin/users-list")
@global_admin_required
def admin_users_list():
    user = get_current_user_obj()
    users = User.get_all_users()
    return render_template("admin/users_list.html", username=user.username, role=user.role, users=users)

# =====================
# АДМИН-ПАНЕЛЬ (АЛЛЕРГЕН-АДМИН)
# =====================

@app.route("/admin/allergen")
@allergen_admin_required
def admin_allergen():
    user = get_current_user_obj()
    zones = DangerZone.get_all()
    return render_template("admin/allergen_admin.html", username=user.username, role=user.role, zones=zones)

@app.route("/admin/allergen/add-zone", methods=["POST"])
@allergen_admin_required
def add_zone():
    user = get_current_user_obj()
    
    try:
        zone = DangerZone(
            id=None,
            name=request.form.get("name"),
            lat=float(request.form.get("lat")),
            lon=float(request.form.get("lon")),
            radius=int(request.form.get("radius", 1500)),
            allergen_type=request.form.get("allergen_type"),
            severity=1,
            created_by=user.id
        )
        zone.save()
        SystemLog.add(user.id, user.username, f"Добавил опасную зону: {zone.name}")
    except Exception as e:
        print(f"Ошибка при добавлении зоны: {e}")
    
    return redirect("/admin/allergen")

@app.route("/admin/allergen/delete-zone", methods=["POST"])
@allergen_admin_required
def delete_zone():
    user = get_current_user_obj()
    zone_id = request.form.get("zone_id")
    
    if zone_id:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name FROM danger_zones WHERE id = %s", (zone_id,))
        zone = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if zone:
            DangerZone.delete(zone_id)
            SystemLog.add(user.id, user.username, f"Удалил опасную зону: {zone['name']}")
    
    return redirect("/admin/allergen")

@app.route("/admin/allergen/stats")
@allergen_admin_required
def allergen_stats():
    user = get_current_user_obj()
    
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
    
    allergen_names = {"birch": "Берёза", "grass": "Злаки", "ragweed": "Амброзия"}
    for s in stats:
        s['allergen_label'] = allergen_names.get(s['allergen_type'], s['allergen_type'])
    
    return render_template("admin/allergen_stats.html", username=user.username, role=user.role, stats=stats)

# =====================
# АДМИН-ПАНЕЛЬ (ПОЛЬЗОВАТЕЛЬ-АДМИН)
# =====================

@app.route("/admin/user")
@user_admin_required
def admin_user():
    user = get_current_user_obj()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email, role, is_blocked, created_at FROM users WHERE role = 'user'")
    users = cursor.fetchall()
    
    routes = RouteHistory.get_all_history(50)
    
    cursor.close()
    conn.close()
    
    return render_template("admin/user_admin.html", username=user.username, role=user.role, users=users, routes=routes)

@app.route("/admin/user/block", methods=["POST"])
@user_admin_required
def block_user():
    admin_user = get_current_user_obj()
    user_id = request.form.get("user_id")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT username FROM users WHERE id = %s AND role = 'user'", (user_id,))
    target_user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if target_user:
        User.toggle_block(user_id, 1)
        SystemLog.add(admin_user.id, admin_user.username, f"Заблокировал пользователя: {target_user['username']}")
    
    return redirect("/admin/user")

@app.route("/admin/user/unblock", methods=["POST"])
@user_admin_required
def unblock_user():
    admin_user = get_current_user_obj()
    user_id = request.form.get("user_id")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    target_user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if target_user:
        User.toggle_block(user_id, 0)
        SystemLog.add(admin_user.id, admin_user.username, f"Разблокировал пользователя: {target_user['username']}")
    
    return redirect("/admin/user")

@app.route("/admin/user-stats")
@user_admin_required
def admin_user_stats():
    user = get_current_user_obj()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.id, u.username, u.email, u.role, COUNT(rh.id) as routes_count,
               GROUP_CONCAT(DISTINCT rh.allergen_type) as allergens_used
        FROM users u
        LEFT JOIN route_history rh ON u.id = rh.user_id
        WHERE u.role = 'user'
        GROUP BY u.id
        ORDER BY u.id
    """)
    stats = cursor.fetchall()
    cursor.close()
    conn.close()
    
    allergen_names = {"birch": "Берёза", "grass": "Злаки", "ragweed": "Амброзия"}
    for s in stats:
        if s['allergens_used']:
            allergens_list = s['allergens_used'].split(',')
            s['allergens_used_ru'] = ', '.join([allergen_names.get(a, a) for a in allergens_list])
        else:
            s['allergens_used_ru'] = '—'
    
    return render_template("admin/user_stats.html", username=user.username, role=user.role, stats=stats)

# =====================
# ДОПОЛНИТЕЛЬНЫЕ API
# =====================

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

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)