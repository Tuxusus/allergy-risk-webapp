from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, send_from_directory, flash
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
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
            
            cursor.execute("""
                INSERT INTO danger_zones (name, lat, lon, radius, allergen_type, severity, created_by) 
                VALUES 
                ('Парк Горького', 55.7355, 37.6050, 1500, 'birch', 3, 1),
                ('ВДНХ', 55.8300, 37.6300, 1800, 'grass', 2, 1),
                ('Царицыно', 55.6150, 37.6800, 1200, 'ragweed', 4, 1),
                ('Сокольники', 55.8000, 37.6800, 1400, 'birch', 3, 1),
                ('Измайлово', 55.7900, 37.7600, 1300, 'grass', 2, 1),
                ('Лосиный остров', 55.8300, 37.6500, 2000, 'birch', 5, 1)
            """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("База данных MySQL успешно инициализирована")
    except Exception as e:
        print(f"Ошибка инициализации MySQL: {e}")

init_db()

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
            cursor.execute("SELECT id, name, lat, lon, radius, allergen_type, severity, created_by FROM danger_zones WHERE allergen_type = %s AND severity > 0 ORDER BY id", (allergen_type,))
        else:
            cursor.execute("SELECT id, name, lat, lon, radius, allergen_type, severity, created_by FROM danger_zones WHERE severity > 0 ORDER BY id")
        zones = cursor.fetchall()
        cursor.close()
        conn.close()
        return zones
    
    @staticmethod
    def get_all_with_inactive(allergen_type=None):
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
    
    @staticmethod
    def batch_update_radius(allergen_type, operation, value):
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if operation == "set":
            sql = "UPDATE danger_zones SET radius = %s WHERE allergen_type = %s"
            params = (int(value), allergen_type)
        elif operation == "add":
            sql = "UPDATE danger_zones SET radius = radius + %s WHERE allergen_type = %s"
            params = (int(value), allergen_type)
        elif operation == "subtract":
            sql = "UPDATE danger_zones SET radius = GREATEST(100, radius - %s) WHERE allergen_type = %s"
            params = (int(value), allergen_type)
        elif operation == "multiply":
            sql = "UPDATE danger_zones SET radius = radius * %s WHERE allergen_type = %s"
            params = (value, allergen_type)
        elif operation == "percent_increase":
            multiplier = 1 + (value / 100)
            sql = "UPDATE danger_zones SET radius = radius * %s WHERE allergen_type = %s"
            params = (multiplier, allergen_type)
        elif operation == "percent_decrease":
            multiplier = 1 - (value / 100)
            sql = "UPDATE danger_zones SET radius = GREATEST(100, radius * %s) WHERE allergen_type = %s"
            params = (multiplier, allergen_type)
        else:
            cursor.close()
            conn.close()
            return 0
        
        cursor.execute(sql, params)
        affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        return affected
    
    @staticmethod
    def batch_update_severity(allergen_type, severity):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE danger_zones SET severity = %s WHERE allergen_type = %s", (severity, allergen_type))
        affected = cursor.rowcount
        conn.commit()
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
    
    @staticmethod
    def delete_old(days=365):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM route_history WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)", (days,))
        affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        return affected
    
    @staticmethod
    def delete_by_user(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM route_history WHERE user_id = %s", (user_id,))
        affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        return affected

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
    
    @staticmethod
    def delete_old(days=90):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM system_logs WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)", (days,))
        affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        return affected
    
    @staticmethod
    def delete_by_user(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM system_logs WHERE user_id = %s", (user_id,))
        affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        return affected

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

@app.route("/api/request-password-reset", methods=["POST"])
def request_password_reset():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    
    if not email:
        return jsonify({"error": "Email обязателен"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id, username FROM users WHERE email = %s AND role = 'user'", (email,))
    user = cursor.fetchone()
    
    if not user:
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Если пользователь существует, заявка отправлена"})
    
    cursor.execute("SELECT id FROM password_reset_requests WHERE user_id = %s AND status = 'pending'", (user['id'],))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Заявка уже отправлена, ожидайте"})
    
    cursor.execute("""
        INSERT INTO password_reset_requests (user_id, status)
        VALUES (%s, 'pending')
    """, (user['id'],))
    conn.commit()
    cursor.close()
    conn.close()
    
    SystemLog.add(user['id'], user['username'], "Отправил заявку на сброс пароля")
    
    return jsonify({"success": True, "message": "Заявка отправлена администратору"})

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

@app.route("/admin/global")
@global_admin_required
def admin_global():
    user = get_current_user_obj()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'user'")
    regular_users_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM route_history")
    total_routes = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM danger_zones")
    total_zones = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM system_logs")
    total_logs = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'global_admin'")
    global_admins_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'allergen_admin'")
    allergen_admins_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'user_admin'")
    user_admins_count = cursor.fetchone()['count']
    
    cursor.execute("""
        SELECT id, username, email, role,
               CASE 
                   WHEN role = 'allergen_admin' THEN 'Аллерген-администратор'
                   WHEN role = 'user_admin' THEN 'Пользователь-администратор'
                   ELSE role
               END as role_name
        FROM users 
        WHERE role IN ('allergen_admin', 'user_admin')
        ORDER BY id
    """)
    admins = cursor.fetchall()
    
    cursor.execute("SELECT id, username, email FROM users WHERE role = 'user' ORDER BY username")
    users = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template("admin/global_admin.html", 
                          username=user.username, 
                          role=user.role,
                          total_users=total_users,
                          regular_users=regular_users_count,
                          total_routes=total_routes,
                          total_zones=total_zones,
                          total_logs=total_logs,
                          global_admins_count=global_admins_count,
                          allergen_admins_count=allergen_admins_count,
                          user_admins_count=user_admins_count,
                          admins=admins,
                          users=users)

@app.route("/admin/global/add-admin", methods=["POST"])
@global_admin_required
def add_admin():
    admin_user = get_current_user_obj()
    user_id = request.form.get("user_id")
    role = request.form.get("role")
    
    if not user_id:
        flash("Не выбран пользователь", "error")
        return redirect("/admin/global")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id, username, email, role FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.close()
        conn.close()
        flash("Пользователь не найден", "error")
        return redirect("/admin/global")
    
    if user['role'] != 'user':
        cursor.close()
        conn.close()
        flash("Этот пользователь уже является администратором", "error")
        return redirect("/admin/global")
    
    cursor.execute("UPDATE users SET role = %s WHERE id = %s", (role, user['id']))
    conn.commit()
    cursor.close()
    conn.close()
    
    SystemLog.add(admin_user.id, admin_user.username, f"Назначил {role} пользователю {user['username']} ({user['email']})")
    
    flash(f"Пользователь {user['username']} назначен администратором по { 'аллергенам' if role == 'allergen_admin' else 'пользователям' }", "success")
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
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email FROM users ORDER BY username")
    all_users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template("admin/logs.html", username=user.username, role=user.role, logs=logs, all_users=all_users)

@app.route("/admin/users-list")
@global_admin_required
def admin_users_list():
    user = get_current_user_obj()
    users = User.get_all_users()
    return render_template("admin/users_list.html", username=user.username, role=user.role, users=users)

@app.route("/admin/global/cleanup-logs", methods=["POST"])
@global_admin_required
def cleanup_logs():
    admin_user = get_current_user_obj()
    days = request.form.get("days", 90, type=int)
    
    if days < 30:
        days = 30
    
    affected = SystemLog.delete_old(days)
    
    SystemLog.add(admin_user.id, admin_user.username, f"Очистил системные логи старше {days} дней. Удалено записей: {affected}")
    
    flash(f"Успешно удалено {affected} записей логов старше {days} дней", "success")
    return redirect("/admin/logs")

@app.route("/admin/global/cleanup-user-logs", methods=["POST"])
@global_admin_required
def cleanup_user_logs():
    admin_user = get_current_user_obj()
    user_id = request.form.get("user_id")
    
    if not user_id:
        flash("Не указан пользователь", "error")
        return redirect("/admin/logs")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    target_user = cursor.fetchone()
    
    if not target_user:
        cursor.close()
        conn.close()
        flash("Пользователь не найден", "error")
        return redirect("/admin/logs")
    
    affected = SystemLog.delete_by_user(user_id)
    conn.commit()
    cursor.close()
    conn.close()
    
    SystemLog.add(admin_user.id, admin_user.username, f"Очистил все логи пользователя {target_user['username']}. Удалено записей: {affected}")
    
    flash(f"Успешно удалено {affected} записей логов пользователя {target_user['username']}", "success")
    return redirect("/admin/logs")

@app.route("/admin/global/cleanup-routes", methods=["POST"])
@global_admin_required
def cleanup_routes():
    admin_user = get_current_user_obj()
    days = request.form.get("days", 365, type=int)
    
    if days < 90:
        days = 90
    
    affected = RouteHistory.delete_old(days)
    
    SystemLog.add(admin_user.id, admin_user.username, f"Очистил историю маршрутов старше {days} дней. Удалено записей: {affected}")
    
    flash(f"Успешно удалено {affected} записей истории маршрутов старше {days} дней", "success")
    return redirect("/admin/logs")

@app.route("/admin/global/cleanup-user-routes", methods=["POST"])
@global_admin_required
def cleanup_user_routes():
    admin_user = get_current_user_obj()
    user_id = request.form.get("user_id")
    
    if not user_id:
        flash("Не указан пользователь", "error")
        return redirect("/admin/logs")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    target_user = cursor.fetchone()
    
    if not target_user:
        cursor.close()
        conn.close()
        flash("Пользователь не найден", "error")
        return redirect("/admin/logs")
    
    affected = RouteHistory.delete_by_user(user_id)
    conn.commit()
    cursor.close()
    conn.close()
    
    SystemLog.add(admin_user.id, admin_user.username, f"Очистил все маршруты пользователя {target_user['username']}. Удалено записей: {affected}")
    
    flash(f"Успешно удалено {affected} маршрутов пользователя {target_user['username']}", "success")
    return redirect("/admin/logs")

@app.route("/admin/global/delete-user", methods=["POST"])
@global_admin_required
def delete_user_account():
    admin_user = get_current_user_obj()
    user_id = request.form.get("user_id")
    
    if not user_id:
        flash("Не указан пользователь", "error")
        return redirect("/admin/users-list")
    
    if int(user_id) == admin_user.id:
        flash("Нельзя удалить свой собственный аккаунт", "error")
        return redirect("/admin/users-list")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id, username, email, role FROM users WHERE id = %s", (user_id,))
    target_user = cursor.fetchone()
    
    if not target_user:
        cursor.close()
        conn.close()
        flash("Пользователь не найден", "error")
        return redirect("/admin/users-list")
    
    username = target_user['username']
    email = target_user['email']
    role = target_user['role']
    
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    SystemLog.add(admin_user.id, admin_user.username, f"Удалил аккаунт пользователя {username} ({email}), роль: {role}")
    
    flash(f"Аккаунт пользователя {username} успешно удалён", "success")
    return redirect("/admin/users-list")

@app.route("/admin/user")
@user_admin_required
def admin_user():
    user = get_current_user_obj()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email, role, is_blocked, created_at FROM users WHERE role = 'user'")
    users = cursor.fetchall()
    
    routes = RouteHistory.get_all_history(50)
    
    cursor.execute("""
        SELECT pr.id, pr.user_id, pr.status, pr.created_at, u.username, u.email
        FROM password_reset_requests pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.status = 'pending'
        ORDER BY pr.created_at DESC
    """)
    reset_requests = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template("admin/user_admin.html", 
                          username=user.username, 
                          role=user.role, 
                          users=users, 
                          routes=routes,
                          reset_requests=reset_requests)

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
        flash(f"Пользователь {target_user['username']} заблокирован", "success")
    
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
        flash(f"Пользователь {target_user['username']} разблокирован", "success")
    
    return redirect("/admin/user")

@app.route("/admin/user/cleanup-routes", methods=["POST"])
@user_admin_required
def user_cleanup_routes():
    admin_user = get_current_user_obj()
    days = request.form.get("days", 365, type=int)
    
    if days < 90:
        days = 90
    
    affected = RouteHistory.delete_old(days)
    
    SystemLog.add(admin_user.id, admin_user.username, f"Очистил историю маршрутов старше {days} дней. Удалено записей: {affected}")
    
    flash(f"Успешно удалено {affected} записей истории маршрутов старше {days} дней", "success")
    return redirect("/admin/user")

@app.route("/admin/user/cleanup-user-routes", methods=["POST"])
@user_admin_required
def user_cleanup_user_routes():
    admin_user = get_current_user_obj()
    user_id = request.form.get("user_id")
    
    if not user_id:
        flash("Не указан пользователь", "error")
        return redirect("/admin/user")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    target_user = cursor.fetchone()
    
    if not target_user:
        cursor.close()
        conn.close()
        flash("Пользователь не найден", "error")
        return redirect("/admin/user")
    
    affected = RouteHistory.delete_by_user(user_id)
    conn.commit()
    cursor.close()
    conn.close()
    
    SystemLog.add(admin_user.id, admin_user.username, f"Очистил все маршруты пользователя {target_user['username']}. Удалено записей: {affected}")
    
    flash(f"Успешно удалено {affected} маршрутов пользователя {target_user['username']}", "success")
    return redirect("/admin/user")

@app.route("/admin/user/approve-reset-request", methods=["POST"])
@user_admin_required
def approve_reset_request():
    admin_user = get_current_user_obj()
    request_id = request.form.get("request_id")
    
    if not request_id:
        flash("Не указана заявка", "error")
        return redirect("/admin/user")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT pr.*, u.username, u.email
        FROM password_reset_requests pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.id = %s AND pr.status = 'pending'
    """, (request_id,))
    req = cursor.fetchone()
    
    if not req:
        cursor.close()
        conn.close()
        flash("Заявка не найдена или уже обработана", "error")
        return redirect("/admin/user")
    
    new_password = "123456"
    password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash.decode('utf-8'), req['user_id']))
    cursor.execute("UPDATE password_reset_requests SET status = 'approved' WHERE id = %s", (request_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    SystemLog.add(admin_user.id, admin_user.username, f"Одобрил сброс пароля для {req['username']}. Новый пароль: {new_password}")
    
    flash(f"Пароль пользователя {req['username']} сброшен на '{new_password}'. Сообщите пользователю!", "success")
    return redirect("/admin/user")

@app.route("/admin/user/reject-reset-request", methods=["POST"])
@user_admin_required
def reject_reset_request():
    admin_user = get_current_user_obj()
    request_id = request.form.get("request_id")
    
    if not request_id:
        flash("Не указана заявка", "error")
        return redirect("/admin/user")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT u.username FROM password_reset_requests pr JOIN users u ON pr.user_id = u.id WHERE pr.id = %s", (request_id,))
    req = cursor.fetchone()
    
    cursor.execute("UPDATE password_reset_requests SET status = 'rejected' WHERE id = %s", (request_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    if req:
        SystemLog.add(admin_user.id, admin_user.username, f"Отклонил заявку на сброс пароля от {req['username']}")
    
    flash("Заявка отклонена", "success")
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

def get_allergen_label(allergen_type):
    labels = {"birch": "Берёза", "grass": "Злаки", "ragweed": "Амброзия"}
    return labels.get(allergen_type, allergen_type)

@app.route("/admin/allergen")
@allergen_admin_required
def admin_allergen():
    user = get_current_user_obj()
    zones = DangerZone.get_all_with_inactive()
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
            severity=3,
            created_by=user.id
        )
        zone.save()
        SystemLog.add(user.id, user.username, f"Добавил опасную зону: {zone.name}")
        flash(f"Зона '{zone.name}' успешно добавлена", "success")
    except Exception as e:
        print(f"Ошибка при добавлении зоны: {e}")
        flash(f"Ошибка при добавлении зоны: {str(e)}", "error")
    
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
            flash(f"Зона '{zone['name']}' успешно удалена", "success")
    
    return redirect("/admin/allergen")

@app.route("/admin/allergen/batch-update-radius", methods=["POST"])
@allergen_admin_required
def batch_update_radius():
    admin_user = get_current_user_obj()
    
    allergen_type = request.form.get("allergen_type")
    operation = request.form.get("operation")
    value = request.form.get("value")
    
    if not allergen_type or not operation or value is None:
        flash("Необходимо указать аллерген, операцию и значение", "error")
        return redirect("/admin/allergen")
    
    try:
        value = float(value)
    except ValueError:
        flash("Значение должно быть числом", "error")
        return redirect("/admin/allergen")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute(
        "SELECT COUNT(*) as count, AVG(radius) as avg_radius FROM danger_zones WHERE allergen_type = %s",
        (allergen_type,)
    )
    stats = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if stats['count'] == 0:
        flash(f"Нет зон для аллергена {get_allergen_label(allergen_type)}", "warning")
        return redirect("/admin/allergen")
    
    affected = DangerZone.batch_update_radius(allergen_type, operation, value)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT MIN(radius) as min_radius, MAX(radius) as max_radius, AVG(radius) as avg_radius FROM danger_zones WHERE allergen_type = %s",
        (allergen_type,)
    )
    new_stats = cursor.fetchone()
    cursor.close()
    conn.close()
    
    allergen_label = get_allergen_label(allergen_type)
    operation_labels = {
        "set": f"установил радиус = {int(value)}м",
        "add": f"прибавил {int(value)}м к радиусу",
        "subtract": f"вычел {int(value)}м из радиуса",
        "multiply": f"умножил радиус на {value}",
        "percent_increase": f"увеличил радиус на {value}%",
        "percent_decrease": f"уменьшил радиус на {value}%"
    }
    operation_desc = operation_labels.get(operation, operation)
    
    SystemLog.add(
        admin_user.id, 
        admin_user.username, 
        f"Массовое изменение радиуса для {allergen_label}: {operation_desc}. "
        f"Затронуто зон: {stats['count']}. "
        f"Было: в среднем {stats['avg_radius']:.0f}м. Стало: мин={new_stats['min_radius']:.0f}м, "
        f"макс={new_stats['max_radius']:.0f}м, среднее={new_stats['avg_radius']:.0f}м"
    )
    
    flash(f"Успешно обновлены радиусы для {affected} зон ({allergen_label})", "success")
    return redirect("/admin/allergen")

@app.route("/admin/allergen/batch-update-severity", methods=["POST"])
@allergen_admin_required
def batch_update_severity():
    admin_user = get_current_user_obj()
    
    allergen_type = request.form.get("allergen_type")
    severity = request.form.get("severity")
    
    if not allergen_type or severity is None:
        flash("Необходимо указать аллерген и уровень опасности", "error")
        return redirect("/admin/allergen")
    
    try:
        severity = int(severity)
        if severity < 0 or severity > 5:
            raise ValueError("Severity должен быть от 0 до 5")
    except ValueError:
        flash("Уровень опасности должен быть числом от 0 до 5", "error")
        return redirect("/admin/allergen")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute(
        "SELECT COUNT(*) as count, severity FROM danger_zones WHERE allergen_type = %s GROUP BY severity",
        (allergen_type,)
    )
    old_distribution = cursor.fetchall()
    
    cursor.execute(
        "SELECT COUNT(*) as total FROM danger_zones WHERE allergen_type = %s",
        (allergen_type,)
    )
    total_zones = cursor.fetchone()['total']
    cursor.close()
    conn.close()
    
    if total_zones == 0:
        flash(f"Нет зон для аллергена {get_allergen_label(allergen_type)}", "warning")
        return redirect("/admin/allergen")
    
    affected = DangerZone.batch_update_severity(allergen_type, severity)
    
    allergen_label = get_allergen_label(allergen_type)
    
    severity_labels = {
        0: "Деактивирована",
        1: "Низкая",
        2: "Ниже среднего",
        3: "Средняя",
        4: "Высокая",
        5: "Критическая"
    }
    severity_label = severity_labels.get(severity, str(severity))
    
    old_distribution_str = ", ".join([f"severity={s['severity']}: {s['count']} зон" for s in old_distribution])
    
    SystemLog.add(
        admin_user.id,
        admin_user.username,
        f"Массовое изменение severity для {allergen_label}: установлен уровень {severity_label} ({severity}). "
        f"Затронуто зон: {affected}. "
        f"Предыдущее распределение: {old_distribution_str}"
    )
    
    if severity == 0:
        flash(f"Успешно деактивированы {affected} зон ({allergen_label}). Они больше не будут отображаться на карте.", "success")
    else:
        flash(f"Успешно обновлен уровень опасности для {affected} зон ({allergen_label}) до {severity_label}", "success")
    
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
            COUNT(*) as total_zones,
            AVG(radius) as avg_radius,
            MIN(radius) as min_radius,
            MAX(radius) as max_radius,
            SUM(CASE WHEN severity = 0 THEN 1 ELSE 0 END) as inactive_zones,
            SUM(CASE WHEN severity > 0 THEN 1 ELSE 0 END) as active_zones,
            AVG(CASE WHEN severity > 0 THEN severity ELSE NULL END) as avg_severity
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