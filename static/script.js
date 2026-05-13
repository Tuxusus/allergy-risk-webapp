let myMap;
let activePlacemark;
let currentRoute;

function init() {
    myMap = new ymaps.Map("map", {
        center: [55.751574, 37.573856],
        zoom: 11,
        controls: ["zoomControl", "fullscreenControl"]
    });
    
    myMap.events.add("click", function(e) {
        const coords = e.get("coords");
        const lat = coords[0].toFixed(6);
        const lon = coords[1].toFixed(6);
        
        document.getElementById("coords-info").innerHTML = '<span>⏳</span> Загрузка...';
        
        if (activePlacemark) {
            myMap.geoObjects.remove(activePlacemark);
        }
        
        activePlacemark = new ymaps.Placemark(coords, {
            hintContent: `${lat}, ${lon}`,
            balloonContent: `<strong>Координаты:</strong><br>${lat}, ${lon}`
        }, {
            preset: "islands#greenDotIcon"
        });
        
        myMap.geoObjects.add(activePlacemark);
        fetchRiskData(lat, lon);
    });
    
    const routeBtn = document.getElementById("build-route-btn");
    if (routeBtn) {
        routeBtn.addEventListener("click", buildRoute);
    }
}

async function fetchRiskData(lat, lon) {
    try {
        const response = await fetch("/api/risk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lat: parseFloat(lat), lon: parseFloat(lon) })
        });
        
        const data = await response.json();
        updateUI(data);
        
        document.getElementById("coords-info").innerHTML = 
            `<span>📍</span> ${lat}, ${lon} — риск: ${data.risk}`;
        
    } catch (error) {
        console.error(error);
        document.getElementById("coords-info").innerHTML = '<span>⚠️</span> Ошибка';
    }
}

function updateUI(data) {
    document.getElementById("temp").textContent = data.temperature ? data.temperature + "°C" : "—";
    document.getElementById("wind").textContent = data.wind_speed ? data.wind_speed + " м/с" : "—";
    document.getElementById("humidity").textContent = data.humidity ? data.humidity + "%" : "—";
    
    const riskDiv = document.getElementById("risk-value");
    riskDiv.textContent = data.risk;
    riskDiv.className = "risk-value " + getRiskClass(data.risk);
    
    document.getElementById("forecast-text").textContent = data.forecast;
    
    const routeRiskDiv = document.getElementById("route-value");
    routeRiskDiv.textContent = data.route_risk;
    routeRiskDiv.className = "route-value " + getRiskClass(data.route_risk);
}

function getRiskClass(risk) {
    if (risk === "Низкий") return "low";
    if (risk === "Средний") return "medium";
    if (risk === "Высокий") return "high";
    return "";
}

function buildRoute() {
    const from = document.getElementById("route-from").value.trim();
    const to = document.getElementById("route-to").value.trim();
    
    if (!from || !to) {
        alert("Введите обе точки");
        return;
    }
    
    const detailsDiv = document.getElementById("route-details");
    detailsDiv.innerHTML = "⏳ Построение маршрута...";
    
    if (currentRoute) {
        myMap.geoObjects.remove(currentRoute);
    }
    
    ymaps.route([from, to]).then(
        function(route) {
            currentRoute = route;
            myMap.geoObjects.add(currentRoute);
            
            document.getElementById("route-value").textContent = "Низкий";
            document.getElementById("route-value").className = "route-value low";
            detailsDiv.innerHTML = `
                📏 ${route.getHumanLength()} | ⏱️ ${route.getHumanTime()}<br>
                🟢 Оценка риска: низкий
            `;
        },
        function(error) {
            console.error(error);
            detailsDiv.innerHTML = "❌ Не удалось построить маршрут. Проверьте названия (например, 'Москва, Красная площадь')";
        }
    );
}

ymaps.ready(init);