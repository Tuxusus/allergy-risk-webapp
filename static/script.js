// Глобальные переменные
let myMap;
let activePlacemark;

// Инициализация карты при загрузке страницы
ymaps.ready(init);

function init() {
    // Создаём карту с центром на Москве
    myMap = new ymaps.Map("map", {
        center: [55.751574, 37.573856], // Москва
        zoom: 10,
        controls: ["zoomControl", "fullscreenControl"]
    });

    // Обработчик клика по карте
    myMap.events.add("click", function(e) {
        const coords = e.get("coords");
        const lat = coords[0].toFixed(6);
        const lon = coords[1].toFixed(6);
        
        // Вывод координат в консоль
        console.log(`Клик по карте: широта ${lat}, долгота ${lon}`);
        
        // Вывод координат на страницу
        document.getElementById("coords-info").innerHTML = `
            <p>📍 Выбрана точка: <strong>${lat}, ${lon}</strong></p>
            <p style="font-size: 12px; color: #888;">Загрузка данных о риске...</p>
        `;
        
        // Добавляем/обновляем метку на карте
        if (activePlacemark) {
            myMap.geoObjects.remove(activePlacemark);
        }
        
        activePlacemark = new ymaps.Placemark(coords, {
            hintContent: `Выбранная точка`,
            balloonContent: `<strong>Координаты:</strong><br>${lat}, ${lon}`
        }, {
            preset: "islands#redDotIcon"
        });
        
        myMap.geoObjects.add(activePlacemark);
        
        // Отправляем запрос на сервер для оценки риска
        fetchRiskData(lat, lon);
    });
}

// Функция получения данных о риске
async function fetchRiskData(lat, lon) {
    try {
        const response = await fetch("/api/risk", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ lat: parseFloat(lat), lon: parseFloat(lon) })
        });
        
        const data = await response.json();
        console.log("Получены данные:", data);
        
        // Обновляем UI с полученными данными
        updateUI(data);
        
    } catch (error) {
        console.error("Ошибка при запросе:", error);
        document.getElementById("coords-info").innerHTML = `
            <p>❌ Ошибка при получении данных</p>
            <p style="font-size: 12px; color: #888;">Проверьте подключение к интернету</p>
        `;
    }
}

// Функция обновления интерфейса
function updateUI(data) {
    // Обновляем информацию о координатах
    document.getElementById("coords-info").innerHTML = `
        <p>📍 Текущая точка: <strong>${data.lat}, ${data.lon}</strong></p>
        <p style="font-size: 12px; color: #28a745;">✅ Данные загружены</p>
    `;
    
    // Обновляем погодные данные
    document.getElementById("temp").textContent = data.temperature || "—";
    document.getElementById("wind").textContent = data.wind_speed || "—";
    document.getElementById("humidity").textContent = data.humidity || "—";
    
    // Обновляем риск
    const riskElement = document.getElementById("risk-value");
    riskElement.textContent = data.risk;
    riskElement.className = "risk-value " + getRiskClass(data.risk);
    
    // Обновляем прогноз
    document.getElementById("forecast-text").textContent = data.forecast;
    
    // Обновляем риск маршрута
    const routeElement = document.getElementById("route-value");
    routeElement.textContent = data.route_risk;
    routeElement.className = "route-value " + getRiskClass(data.route_risk);
    
    let routeDetailsText = "";
    if (data.route_risk === "Низкий") {
        routeDetailsText = "✅ Маршрут безопасен для аллергиков";
    } else if (data.route_risk === "Средний") {
        routeDetailsText = "⚠️ Рекомендуется принять меры предосторожности";
    } else {
        routeDetailsText = "🚫 Высокий риск! По возможности избегайте длительного пребывания на улице";
    }
    document.getElementById("route-details").textContent = routeDetailsText;
}

// Функция получения CSS класса для уровня риска
function getRiskClass(riskLevel) {
    switch(riskLevel) {
        case "Низкий": return "low";
        case "Средний": return "medium";
        case "Высокий": return "high";
        default: return "";
    }
}