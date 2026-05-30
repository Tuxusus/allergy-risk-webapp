import mysql.connector
import random
from datetime import datetime, timedelta

# Подключение
conn = mysql.connector.connect(
    host='localhost',
    user='allergy_user',
    password='allergy_password',
    database='allergy_db'
)
cursor = conn.cursor()

# Получаем всех пользователей
cursor.execute("SELECT id FROM users")
users = cursor.fetchall()
user_ids = [u[0] for u in users]

allergens = ['birch', 'grass', 'ragweed']

# Генерируем 3000+ записей истории маршрутов
print("Генерация 3000 записей истории маршрутов...")

for i in range(3100):
    user_id = random.choice(user_ids)
    start_lat = 55.6 + random.uniform(0, 0.5)
    start_lon = 37.4 + random.uniform(0, 0.8)
    end_lat = start_lat + random.uniform(-0.1, 0.1)
    end_lon = start_lon + random.uniform(-0.1, 0.1)
    risk_score = random.randint(5, 95)
    allergen = random.choice(allergens)
    
    # Случайная дата за последние 30 дней
    days_ago = random.randint(0, 30)
    created_at = datetime.now() - timedelta(days=days_ago)
    
    cursor.execute("""
        INSERT INTO route_history (user_id, start_lat, start_lon, end_lat, end_lon, risk_score, allergen_type, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (user_id, start_lat, start_lon, end_lat, end_lon, risk_score, allergen, created_at))
    
    if i % 500 == 0:
        print(f"Создано {i} записей...")
        conn.commit()

conn.commit()
print("✅ Готово! Добавлено 3100 записей")

# Проверка
cursor.execute("SELECT COUNT(*) FROM route_history")
count = cursor.fetchone()[0]
print(f"Всего записей в route_history: {count}")

cursor.close()
conn.close()