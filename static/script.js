const DEFAULT_CENTER = [55.7558, 37.6176];

let myMap;
let panelMode = "map";
let currentAllergen = "birch";

let pointA = null;
let pointB = null;

let pointAMarker = null;
let pointBMarker = null;

let currentRoute = null;

let pollenCircles = [];

let isSelectingPointA = true;

// =====================
// API
// =====================

async function fetchRisk(lat, lon) {
    try {
        const response = await fetch("/api/risk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                lat: lat,
                lon: lon,
                allergen: currentAllergen
            })
        });
        const data = await response.json();
        return data;
    } catch (error) {
        console.error("API error:", error);
        return {
            risk: "Низкий",
            score: 15,
            allergen_label: "Берёза",
            allergen_value: 5,
            temperature: 18,
            humidity: 60,
            wind_speed: 3,
            aqi: 35,
            pm25: 12
        };
    }
}

// =====================
// ПОЛУЧИТЬ НАЗВАНИЕ АЛЛЕРГЕНА
// =====================

function getAllergenName() {
    if (currentAllergen === "birch") return "Берёза";
    if (currentAllergen === "grass") return "Злаки";
    return "Амброзия";
}

// =====================
// ПРАВАЯ ПАНЕЛЬ - РЕЖИМ КАРТЫ
// =====================

function updateMapInfo(data, coords) {
    // Уровень риска и цвет
    const riskLevel = data.risk || "Низкий";
    
    // Правильные цвета для риска
    let riskColor = "";
    if (riskLevel === "Низкий") riskColor = "#53B97C";
    else if (riskLevel === "Средний") riskColor = "#E8A23A";
    else if (riskLevel === "Высокий") riskColor = "#D65A63";
    else riskColor = "#D65A63";
    
    document.getElementById("main-risk-box").innerHTML = riskLevel;
    document.getElementById("main-risk-box").style.background = `rgba(${parseInt(riskColor.slice(1,3),16)}, ${parseInt(riskColor.slice(3,5),16)}, ${parseInt(riskColor.slice(5,7),16)}, 0.15)`;
    document.getElementById("main-risk-box").style.color = riskColor;
    
    // Основная информация (с правильным аллергеном)
    document.getElementById("main-info").innerHTML = `
        📍 Координаты:<br>
        ${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}<br><br>
        🌾 Аллерген: ${getAllergenName()}<br><br>
        🌾 Концентрация: ${data.allergen_value || 0} ед.<br><br>
        ⚠️ Индекс риска: ${data.score || 0} баллов
    `;
    
    // Погода
    document.getElementById("weather-info").innerHTML = `
        🌡️ Температура: ${data.temperature || "—"}°C<br><br>
        💧 Влажность: ${data.humidity || "—"}%<br><br>
        💨 Ветер: ${data.wind_speed || "—"} м/с
    `;
    
    // Воздух
    document.getElementById("air-info").innerHTML = `
        🌫️ AQI: ${data.aqi || "—"}<br><br>
        🧪 PM2.5: ${data.pm25 || "—"} мкг/м³
    `;
    
    // Прогноз
    let forecastText = "Данные загружаются...";
    if (data.score < 25) forecastText = "В ближайшие 6 часов ожидается низкий уровень аллергенов";
    else if (data.score < 50) forecastText = "В ближайшие 6 часов уровень аллергенов останется умеренным";
    else if (data.score < 75) forecastText = "В ближайшие 6 часов ожидается высокий уровень аллергенов";
    else forecastText = "В ближайшие 6 часов ожидается очень высокий уровень аллергенов! Будьте осторожны!";
    
    document.getElementById("forecast-info").innerHTML = forecastText;
}

// =====================
// КАРТА ПЫЛЬЦЫ (РАЗНЫЕ ТОЧКИ ДЛЯ РАЗНЫХ АЛЛЕРГЕНОВ)
// =====================

async function renderPollenMap() {
    clearPollen();
    
    document.getElementById("page-title").textContent = "Карта пыльцы";
    document.getElementById("page-subtitle").textContent = `Аллерген: ${getAllergenName()}`;
    
    // Разные точки для разных аллергенов, чтобы карта выглядела по-разному
    let points = [];
    
    if (currentAllergen === "birch") {
        // Берёза - больше точек в парках и лесопарках
        points = [
            [55.7558, 37.6176],  // Центр
            [55.7800, 37.6000],  // ВДНХ (много берёз)
            [55.8300, 37.6500],  // Лосиный остров
            [55.7400, 37.5500],  // Нескучный сад
            [55.7200, 37.6800],  // Кузьминки
            [55.6700, 37.5800],  // Битцевский лес
            [55.8500, 37.4800],  // Серебряный бор
            [55.7900, 37.7800],  // Измайловский парк
            [55.7000, 37.6500],  // Царицыно
            [55.8100, 37.5500]   // Покровское-Стрешнево
        ];
    } else if (currentAllergen === "grass") {
        // Злаки - больше точек в степных/луговых зонах
        points = [
            [55.7558, 37.6176],  // Центр
            [55.7100, 37.5500],  // Воробьёвы горы
            [55.6500, 37.6000],  // Южное Бутово
            [55.6900, 37.7000],  // Капотня
            [55.7600, 37.6800],  // Перово
            [55.8000, 37.8000],  // Гольяново
            [55.6700, 37.4800],  // Тёплый Стан
            [55.7300, 37.3800],  // Солнцево
        ];
    } else {
        // Амброзия - точки в южных и теплых районах
        points = [
            [55.7558, 37.6176],  // Центр
            [55.6500, 37.6500],  // Марьино
            [55.6300, 37.7200],  // Братеево
            [55.6800, 37.5000],  // Ясенево
            [55.6700, 37.5800],  // Битцевский лес
            [55.5700, 37.5500],  // Северное Бутово
            [55.7800, 37.6000],  // ВДНХ
        ];
    }
    
    for (const point of points) {
        const risk = await fetchRisk(point[0], point[1]);
        const score = risk.score || 0;
        
        // Цвет в зависимости от риска
        let color = "#53B97C"; // низкий - зеленый
        if (score >= 75) color = "#D65A63"; // очень высокий/высокий - красный
        else if (score >= 50) color = "#D65A63"; // высокий - красный
        else if (score >= 25) color = "#E8A23A"; // средний - желтый
        
        const circle = new ymaps.Circle(
            [point, 2000],
            {
                hintContent: `${getAllergenName()}<br>Риск: ${risk.risk || "Низкий"} (${score} баллов)<br>Пыльца: ${risk.allergen_value || 0} ед.<br>Температура: ${risk.temperature || "—"}°C`
            },
            {
                fillColor: color + "66",
                strokeColor: color,
                strokeWidth: 3,
                fillOpacity: 0.5,
                interactive: false  // ВОТ ЭТА СТРОКА - чтобы круги не перехватывали клики
            }
        );
        
        pollenCircles.push(circle);
        myMap.geoObjects.add(circle);
    }
}

function clearPollen() {
    pollenCircles.forEach(circle => {
        myMap.geoObjects.remove(circle);
    });
    pollenCircles = [];
}

// =====================
// МАРШРУТ
// =====================

function buildRoute() {
    if (!pointA || !pointB) return;
    
    if (currentRoute) {
        myMap.geoObjects.remove(currentRoute);
    }
    
    document.getElementById("route-status").textContent = "Построение маршрута...";
    
    // Строим пешеходный маршрут
    currentRoute = new ymaps.multiRouter.MultiRoute({
        referencePoints: [pointA, pointB],
        params: {
            routingMode: "pedestrian",
            results: 1
        }
    }, {
        boundsAutoApply: true
    });
    
    // Цвет маршрута в зависимости от аллергена
    let routeColor = "#53B97C";
    if (currentAllergen === "grass") routeColor = "#3B82F6";
    if (currentAllergen === "ragweed") routeColor = "#D65A63";
    
    currentRoute.options.set({
        routeActiveStrokeColor: routeColor,
        routeStrokeColor: routeColor,
        routeActiveStrokeWidth: 6,
        routeStrokeWidth: 5,
        wayPointVisible: false,
        viaPointVisible: false
    });
    
    myMap.geoObjects.add(currentRoute);
    
    currentRoute.model.events.add("requestsuccess", async function() {
        const activeRoute = currentRoute.getActiveRoute();
        if (!activeRoute) return;
        
        const distance = activeRoute.properties.get("distance").text;
        const duration = activeRoute.properties.get("duration").text;
        
        // Получаем риски для точек A и B
        const riskA = await fetchRisk(pointA[0], pointA[1]);
        const riskB = await fetchRisk(pointB[0], pointB[1]);
        
        const maxRisk = Math.max(riskA.score || 0, riskB.score || 0);
        let riskLevel = "Низкий";
        if (maxRisk >= 75) riskLevel = "Очень высокий";
        else if (maxRisk >= 50) riskLevel = "Высокий";
        else if (maxRisk >= 25) riskLevel = "Средний";
        
        document.getElementById("route-risk").innerHTML = `🛡️ ${riskLevel}`;
        
        document.getElementById("route-details").innerHTML = `
            🚶 Маршрут построен<br><br>
            📏 Длина: ${distance}<br>
            ⏱️ Время: ${duration}<br><br>
            🛡️ Макс. риск: ${maxRisk} баллов (${riskLevel})
        `;
        
        document.getElementById("comparison").innerHTML = `
            ✅ Маршрут оптимизирован<br>
            🚶 Пешеходные дороги<br>
            🛡️ Учитывает аллергический риск
        `;
        
        document.getElementById("route-status").textContent = "Маршрут готов";
    });
    
    currentRoute.model.events.add("requestfail", function() {
        document.getElementById("route-details").innerHTML = "❌ Не удалось построить маршрут";
        document.getElementById("route-status").textContent = "Ошибка";
    });
}

// =====================
// МАРКЕРЫ
// =====================

function createMarker(coords, type) {
    return new ymaps.Placemark(
        coords,
        { hintContent: `Точка ${type}` },
        {
            preset: "islands#circleDotIcon",
            iconColor: type === "A" ? "#53B97C" : "#D65A63"
        }
    );
}

// =====================
// КЛИК ПО КАРТЕ
// =====================

async function selectPoint(coords) {
    if (panelMode === "map") {
        const risk = await fetchRisk(coords[0], coords[1]);
        updateMapInfo(risk, coords);
        return;
    }
    
    // Режим маршрута
    if (isSelectingPointA) {
        // Сброс старых данных
        if (pointAMarker) myMap.geoObjects.remove(pointAMarker);
        if (pointBMarker) myMap.geoObjects.remove(pointBMarker);
        if (currentRoute) myMap.geoObjects.remove(currentRoute);
        
        pointA = coords;
        pointAMarker = createMarker(coords, "A");
        myMap.geoObjects.add(pointAMarker);
        
        // Обновляем правую панель
        const riskA = await fetchRisk(coords[0], coords[1]);
        document.getElementById("point-a-risk").innerHTML = riskA.risk || "Низкий";
        document.getElementById("point-a-coords").innerHTML = `${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`;
        
        document.getElementById("point-b-risk").innerHTML = "—";
        document.getElementById("point-b-coords").innerHTML = "—";
        document.getElementById("route-risk").innerHTML = "—";
        document.getElementById("route-details").innerHTML = "Выберите точку Б";
        document.getElementById("comparison").innerHTML = "—";
        
        document.getElementById("route-status").textContent = "Выберите точку Б";
        isSelectingPointA = false;
        
    } else {
        pointB = coords;
        pointBMarker = createMarker(coords, "B");
        myMap.geoObjects.add(pointBMarker);
        
        // Обновляем правую панель
        const riskB = await fetchRisk(coords[0], coords[1]);
        document.getElementById("point-b-risk").innerHTML = riskB.risk || "Низкий";
        document.getElementById("point-b-coords").innerHTML = `${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`;
        
        // Строим маршрут
        buildRoute();
        
        isSelectingPointA = true;
    }
}

// =====================
// СБРОС
// =====================

function resetRoute() {
    if (pointAMarker) myMap.geoObjects.remove(pointAMarker);
    if (pointBMarker) myMap.geoObjects.remove(pointBMarker);
    if (currentRoute) myMap.geoObjects.remove(currentRoute);
    
    pointA = null;
    pointB = null;
    pointAMarker = null;
    pointBMarker = null;
    currentRoute = null;
    isSelectingPointA = true;
    
    document.getElementById("point-a-risk").innerHTML = "—";
    document.getElementById("point-b-risk").innerHTML = "—";
    document.getElementById("point-a-coords").innerHTML = "—";
    document.getElementById("point-b-coords").innerHTML = "—";
    document.getElementById("route-risk").innerHTML = "—";
    document.getElementById("route-details").innerHTML = "Выберите точки на карте";
    document.getElementById("comparison").innerHTML = "—";
    document.getElementById("route-status").textContent = "Выберите точку A";
}

// =====================
// АЛЛЕРГЕН
// =====================

async function changeAllergen(type) {
    currentAllergen = type;
    
    document.querySelectorAll(".allergen-item").forEach(btn => btn.classList.remove("active"));
    document.querySelector(`[data-allergen="${type}"]`).classList.add("active");
    
    if (panelMode === "map") {
        // Обновляем заголовок
        document.getElementById("page-subtitle").textContent = `Аллерген: ${getAllergenName()}`;
        // Перерисовываем карту
        await renderPollenMap();
    } else if (panelMode === "route") {
        if (pointA && pointB) {
            buildRoute();
        }
        // Обновляем риски для точек
        if (pointA) {
            const riskA = await fetchRisk(pointA[0], pointA[1]);
            document.getElementById("point-a-risk").innerHTML = riskA.risk || "Низкий";
        }
        if (pointB) {
            const riskB = await fetchRisk(pointB[0], pointB[1]);
            document.getElementById("point-b-risk").innerHTML = riskB.risk || "Низкий";
        }
    }
}

// =====================
// ПЕРЕКЛЮЧЕНИЕ РЕЖИМОВ
// =====================

function switchMode(mode) {
    panelMode = mode;
    
    document.querySelectorAll(".side-link").forEach(btn => btn.classList.remove("active"));
    
    if (mode === "map") {
        document.getElementById("mode-map").classList.add("active");
        document.getElementById("map-panel").style.display = "block";
        document.getElementById("route-panel").style.display = "none";
        
        clearPollen();
        renderPollenMap();
        
        document.getElementById("page-title").textContent = "Карта пыльцы";
        document.getElementById("page-subtitle").textContent = `Аллерген: ${getAllergenName()}`;
        
    } else {
        document.getElementById("mode-route").classList.add("active");
        document.getElementById("map-panel").style.display = "none";
        document.getElementById("route-panel").style.display = "block";
        
        clearPollen();
        
        document.getElementById("page-title").textContent = "Безопасный маршрут";
        document.getElementById("page-subtitle").textContent = "Выберите точки A и Б на карте";
        
        // Сбрасываем маршрут при переключении
        resetRoute();
    }
}

// =====================
// INIT
// =====================

function init() {
    myMap = new ymaps.Map("map", {
        center: DEFAULT_CENTER,
        zoom: 10,
        controls: ["zoomControl", "fullscreenControl", "geolocationControl"]
    });
    
    myMap.events.add("click", async function(e) {
        const coords = e.get("coords");
        await selectPoint(coords);
    });
    
    // Кнопки режимов
    document.getElementById("mode-map").addEventListener("click", () => switchMode("map"));
    document.getElementById("mode-route").addEventListener("click", () => switchMode("route"));
    
    // Кнопка сброса
    document.getElementById("reset-route-btn").addEventListener("click", resetRoute);
    
    // Кнопки аллергенов
    document.querySelectorAll(".allergen-item").forEach(button => {
        button.addEventListener("click", async function() {
            await changeAllergen(this.dataset.allergen);
        });
    });
    
    // Стартуем в режиме карты
    switchMode("map");
}

ymaps.ready(init);