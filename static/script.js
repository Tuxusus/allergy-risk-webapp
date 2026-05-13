// Глобальные переменные
let myMap;
let activePlacemark;

// Инициализация карты
ymaps.ready(init);

function init() {
    myMap = new ymaps.Map("map", {
        center: [55.751574, 37.573856],
        zoom: 11,
        controls: ["zoomControl", "fullscreenControl"]
    });

    // Стилизация карты (немного темнее для современного вида)
    myMap.setType("yandex#dark");

    myMap.events.add("click", function(e) {
        const coords = e.get("coords");
        const lat = coords[0].toFixed(6);
        const lon = coords[1].toFixed(6);
        
        console.log(`Клик: ${lat}, ${lon}`);
        
        document.getElementById("coords-info").innerHTML = `
            <span>📍</span> Загрузка данных для ${lat}, ${lon}...
        `;
        
        if (activePlacemark) {
            myMap.geoObjects.remove(activePlacemark);
        }
        
        activePlacemark = new ymaps.Placemark(coords, {
            hintContent: `Выбрано: ${lat}, ${lon}`,
            balloonContent: `<strong>Координаты:</strong><br>${lat}, ${lon}`
        }, {
            preset: "islands#greenDotIcon"
        });
        
        myMap.geoObjects.add(activePlacemark);
        fetchRiskData(lat, lon);
    });

    // Обработчик маршрутов
    document.getElementById("build-route-btn").addEventListener("click", buildRoute);
}

async function fetchRiskData(lat, lon) {
    try {
        const response = await fetch("/api/risk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lat: parseFloat(lat), lon: parseFloat(lon) })
        });
        
        const data = await response.json();
        console.log("Данные получены:", data);
        updateUI(data);
        
        document.getElementById("coords-info").innerHTML = `
            <span>📍</span> ${lat}, ${lon} — данные обновлены
        `;
        
    } catch (error) {
        console.error("Ошибка:", error);
        document.getElementById("coords-info").innerHTML = `
            <span>⚠️</span> Ошибка получения данных
        `;
    }
}

function updateUI(data) {
    // Погода
    document.getElementById("temp").textContent = data.temperature !== null ? data.temperature + "°C" : "—";
    document.getElementById("wind").textContent = data.wind_speed !== null ? data.wind_speed + " м/с" : "—";
    document.getElementById("humidity").textContent = data.humidity !== null ? data.humidity + "%" : "—";
    
    // Риск
    const riskElement = document.getElementById("risk-value");
    riskElement.textContent = data.risk;
    riskElement.className = "risk-value " + getRiskClass(data.risk);
    
    // Прогноз
    document.getElementById("forecast-text").textContent = data.forecast;
    
    // Риск маршрута
    const routeElement = document.getElementById("route-value");
    routeElement.textContent = data.route_risk;
    routeElement.className = "route-value " + getRiskClass(data.route_risk);
    
    let routeMsg = "";
    if (data.route_risk === "Низкий") routeMsg = "✅ Маршрут безопасен";
    else if (data.route_risk === "Средний") routeMsg = "⚠️ Рекомендованы меры предосторожности";
    else routeMsg = "🚫 Высокий риск! По возможности избегайте";
    document.getElementById("route-details").textContent = routeMsg;
}

function getRiskClass(risk) {
    if (risk === "Низкий") return "low";
    if (risk === "Средний") return "medium";
    if (risk === "Высокий") return "high";
    return "";
}

function buildRoute() {
    const from = document.getElementById("route-from").value;
    const to = document.getElementById("route-to").value;
    
    if (!from || !to) {
        alert("Введите обе точки маршрута");
        return;
    }
    
    document.getElementById("route-details").innerHTML = "⏳ Построение маршрута...";
    
    ymaps.route([from, to]).then(
        route => {
            myMap.geoObjects.add(route);
            
            const wayPoints = route.getWayPoints();
            const length = route.getHumanLength();
            const time = route.getHumanTime();
            
            // TODO: Рассчитать риск вдоль маршрута (когда будут данные)
            document.getElementById("route-value").textContent = "Низкий";
            document.getElementById("route-value").className = "route-value low";
            document.getElementById("route-details").innerHTML = `
                📏 ${length} | ⏱️ ${time}<br>
                🟢 Предварительная оценка риска: низкая
            `;
        },
        error => {
            console.error(error);
            document.getElementById("route-details").innerHTML = 
                "❌ Не удалось построить маршрут. Проверьте названия мест";
        }
    );
}