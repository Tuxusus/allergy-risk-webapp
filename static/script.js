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

let currentUser = null;

// =====================
// API ВЫЗОВЫ
// =====================

async function fetchRisk(lat, lon) {
    try {
        const response = await fetch("/api/risk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
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

function getAllergenName() {
    if (currentAllergen === "birch") return "Берёза";
    if (currentAllergen === "grass") return "Злаки";
    return "Амброзия";
}

function getRiskColorClass(riskLevel) {
    if (riskLevel === "Низкий") return "risk-low";
    if (riskLevel === "Средний") return "risk-medium";
    if (riskLevel === "Высокий") return "risk-high";
    if (riskLevel === "Очень высокий") return "risk-very-high";
    return "risk-low";
}

function updateRiskBadge(element, riskLevel) {
    element.innerHTML = riskLevel;
    element.classList.remove("risk-low", "risk-medium", "risk-high", "risk-very-high");
    element.classList.add(getRiskColorClass(riskLevel));
}

function getDangerZones() {
    if (currentAllergen === "birch") {
        return [
            { name: "ВДНХ", coords: [55.7800, 37.6000], radius: 1500 },
            { name: "Лосиный остров", coords: [55.8300, 37.6500], radius: 2000 },
            { name: "Нескучный сад", coords: [55.7400, 37.5500], radius: 1200 },
            { name: "Битцевский лес", coords: [55.6700, 37.5800], radius: 1800 },
            { name: "Измайловский парк", coords: [55.7900, 37.7800], radius: 1500 },
            { name: "Царицыно", coords: [55.7000, 37.6500], radius: 1300 },
            { name: "Сокольники", coords: [55.8000, 37.6800], radius: 1400 }
        ];
    } else if (currentAllergen === "grass") {
        return [
            { name: "Воробьёвы горы", coords: [55.7100, 37.5500], radius: 1200 },
            { name: "Капотня", coords: [55.6900, 37.7000], radius: 1300 },
            { name: "Гольяново", coords: [55.8000, 37.8000], radius: 1200 },
            { name: "Солнцево", coords: [55.7300, 37.3800], radius: 1100 },
            { name: "Мнёвники", coords: [55.7600, 37.5000], radius: 1200 },
            { name: "Алтуфьево", coords: [55.9000, 37.5900], radius: 1000 }
        ];
    } else {
        return [
            { name: "Марьино", coords: [55.6500, 37.6500], radius: 1300 },
            { name: "Братеево", coords: [55.6300, 37.7200], radius: 1200 },
            { name: "Северное Бутово", coords: [55.5700, 37.5500], radius: 1100 },
            { name: "Южное Бутово", coords: [55.5400, 37.5800], radius: 1200 },
            { name: "Зябликово", coords: [55.6200, 37.7500], radius: 1000 },
            { name: "Тимирязевский", coords: [55.8200, 37.5800], radius: 1200 },
            { name: "Гольяново", coords: [55.8000, 37.8000], radius: 1200 }
        ];
    }
}

function isPointInDangerZone(lat, lon) {
    const dangerZones = getDangerZones();
    for (const zone of dangerZones) {
        const dx = lat - zone.coords[0];
        const dy = lon - zone.coords[1];
        const distance = Math.sqrt(dx * dx + dy * dy) * 111000;
        if (distance < zone.radius) {
            return true;
        }
    }
    return false;
}

async function findSafeWaypoint(fromCoords, toCoords) {
    const candidates = [];
    const offsets = [
        { name: "север", lat: 0.03, lon: 0 },
        { name: "юг", lat: -0.03, lon: 0 },
        { name: "восток", lat: 0, lon: 0.03 },
        { name: "запад", lat: 0, lon: -0.03 },
        { name: "северо-восток", lat: 0.025, lon: 0.025 },
        { name: "северо-запад", lat: 0.025, lon: -0.025 },
        { name: "юго-восток", lat: -0.025, lon: 0.025 },
        { name: "юго-запад", lat: -0.025, lon: -0.025 }
    ];
    
    const midLat = (fromCoords[0] + toCoords[0]) / 2;
    const midLon = (fromCoords[1] + toCoords[1]) / 2;
    
    for (const offset of offsets) {
        const candidateLat = midLat + offset.lat;
        const candidateLon = midLon + offset.lon;
        const isSafe = !isPointInDangerZone(candidateLat, candidateLon);
        candidates.push({
            coords: [candidateLat, candidateLon],
            name: offset.name,
            isSafe: isSafe
        });
    }
    
    let bestPoint = null;
    let lowestRisk = Infinity;
    
    for (const candidate of candidates) {
        try {
            const riskData = await fetchRisk(candidate.coords[0], candidate.coords[1]);
            const riskScore = riskData.score || 0;
            const finalScore = candidate.isSafe ? riskScore : riskScore + 30;
            if (finalScore < lowestRisk) {
                lowestRisk = finalScore;
                bestPoint = {
                    coords: candidate.coords,
                    riskData: riskData,
                    name: candidate.name,
                    isSafe: candidate.isSafe
                };
            }
        } catch (error) {
            console.error("Ошибка при проверке кандидата:", error);
        }
    }
    return bestPoint;
}

async function buildRoute() {
    if (!pointA || !pointB) return;
    
    if (currentRoute) {
        myMap.geoObjects.remove(currentRoute);
    }
    
    document.getElementById("route-status").textContent = "Поиск безопасного маршрута...";
    document.getElementById("route-details").innerHTML = "Анализируем опасные зоны для " + getAllergenName() + "...";
    
    try {
        const safeWaypoint = await findSafeWaypoint(pointA, pointB);
        const startDanger = isPointInDangerZone(pointA[0], pointA[1]);
        const endDanger = isPointInDangerZone(pointB[0], pointB[1]);
        const needDetour = startDanger || endDanger || (safeWaypoint && !safeWaypoint.isSafe);
        
        let routePoints;
        let detourInfo = "";
        
        if (needDetour && safeWaypoint && safeWaypoint.riskData.score < 50) {
            routePoints = [pointA, safeWaypoint.coords, pointB];
            detourInfo = "Маршрут изменён для " + getAllergenName() + "! Объезд через " + safeWaypoint.name + ". Риск: " + (safeWaypoint.riskData.risk || "Низкий") + " (" + safeWaypoint.riskData.score + " баллов)";
        } else {
            routePoints = [pointA, pointB];
            if (startDanger || endDanger) {
                detourInfo = "Внимание! Точки находятся в опасной зоне для " + getAllergenName() + ". Рекомендуется выбрать другие точки.";
            } else {
                detourInfo = "Прямой маршрут безопасен для " + getAllergenName() + ". Опасные зоны не пересекаются.";
            }
        }
        
        currentRoute = new ymaps.multiRouter.MultiRoute({
            referencePoints: routePoints,
            params: { routingMode: "pedestrian", results: 1 }
        }, { boundsAutoApply: true });
        
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
            const riskA = await fetchRisk(pointA[0], pointA[1]);
            const riskB = await fetchRisk(pointB[0], pointB[1]);
            const maxRisk = Math.max(riskA.score || 0, riskB.score || 0);
            
            let riskLevel = "Низкий";
            if (maxRisk >= 75) riskLevel = "Очень высокий";
            else if (maxRisk >= 50) riskLevel = "Высокий";
            else if (maxRisk >= 25) riskLevel = "Средний";
            
            updateRiskBadge(document.getElementById("route-risk"), riskLevel);
            
            document.getElementById("route-details").innerHTML = `
                <div class="info-line">Маршрут для ` + getAllergenName() + ` построен</div>
                <div class="info-line">Длина: ` + distance + `</div>
                <div class="info-line">Время: ` + duration + `</div>
                <div class="info-line">` + detourInfo + `</div>
                <div class="info-line">Макс. риск: ` + maxRisk + ` баллов (` + riskLevel + `)</div>
            `;
            
            let comparisonHtml = `<div class="info-line">Анализ для ` + getAllergenName() + `:</div>`;
            const dangerZones = getDangerZones();
            if (dangerZones.length > 0) {
                comparisonHtml += `<div class="info-line">Избегаемые зоны:</div>`;
                for (const zone of dangerZones.slice(0, 3)) {
                    comparisonHtml += `<div class="info-line">- ` + zone.name + `</div>`;
                }
                comparisonHtml += `<div class="info-line"></div>`;
            }
            comparisonHtml += `<div class="info-line">` + (needDetour ? "Маршрут оптимизирован для объезда опасных зон." : "Прямой маршрут безопасен.") + `</div>`;
            document.getElementById("comparison").innerHTML = comparisonHtml;
            document.getElementById("route-status").textContent = "Маршрут готов";
            
            if (currentUser && currentUser.role === 'user') {
                try {
                    await fetch("/api/route/save", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            start_lat: pointA[0],
                            start_lon: pointA[1],
                            end_lat: pointB[0],
                            end_lon: pointB[1],
                            risk_score: maxRisk,
                            allergen_type: currentAllergen
                        })
                    });
                } catch(e) {
                    console.log("Не удалось сохранить маршрут");
                }
            }
        });
        
        currentRoute.model.events.add("requestfail", function() {
            document.getElementById("route-details").innerHTML = "Не удалось построить маршрут. Попробуйте другие точки.";
            document.getElementById("route-status").textContent = "Ошибка";
        });
        
    } catch (error) {
        console.error("Ошибка построения маршрута:", error);
        document.getElementById("route-details").innerHTML = "Ошибка построения маршрута";
        document.getElementById("route-status").textContent = "Ошибка";
    }
}

function updateMapInfo(data, coords) {
    const riskLevel = data.risk || "Низкий";
    updateRiskBadge(document.getElementById("main-risk-box"), riskLevel);
    
    document.getElementById("main-info").innerHTML = `
        <div class="info-line">Координаты: ${coords[0].toFixed(4)}°, ${coords[1].toFixed(4)}°</div>
        <div class="info-line">Аллерген: ${getAllergenName()}</div>
        <div class="info-line">Концентрация: ${data.allergen_value || 0} ед.</div>
        <div class="info-line">Индекс риска: ${data.score || 0} баллов</div>
    `;
    
    document.getElementById("weather-info").innerHTML = `
        <div class="info-line">Температура: ${data.temperature || "—"}°C</div>
        <div class="info-line">Влажность: ${data.humidity || "—"}%</div>
        <div class="info-line">Ветер: ${data.wind_speed || "—"} м/с</div>
    `;
    
    document.getElementById("air-info").innerHTML = `
        <div class="info-line">AQI: ${data.aqi || "—"}</div>
        <div class="info-line">PM2.5: ${data.pm25 || "—"} мкг/м³</div>
    `;
    
    let forecastText = "Данные загружаются...";
    if (data.score < 25) forecastText = "В ближайшие 6 часов ожидается низкий уровень аллергенов";
    else if (data.score < 50) forecastText = "В ближайшие 6 часов уровень аллергенов останется умеренным";
    else if (data.score < 75) forecastText = "В ближайшие 6 часов ожидается высокий уровень аллергенов";
    else forecastText = "В ближайшие 6 часов ожидается очень высокий уровень аллергенов! Будьте осторожны!";
    
    document.getElementById("forecast-info").innerHTML = forecastText;
}

async function renderPollenMap() {
    clearPollen();
    document.getElementById("page-title").textContent = "Карта пыльцы";
    document.getElementById("page-subtitle").textContent = "Аллерген: " + getAllergenName();
    
    let points = [];
    if (currentAllergen === "birch") {
        points = [
            [55.7558, 37.6176], [55.7800, 37.6000], [55.8300, 37.6500],
            [55.7400, 37.5500], [55.7200, 37.6800], [55.6700, 37.5800],
            [55.8500, 37.4800], [55.7900, 37.7800], [55.7000, 37.6500],
            [55.8100, 37.5500]
        ];
    } else if (currentAllergen === "grass") {
        points = [
            [55.7558, 37.6176], [55.7100, 37.5500], [55.6500, 37.6000],
            [55.6900, 37.7000], [55.7600, 37.6800], [55.8000, 37.8000],
            [55.6700, 37.4800], [55.7300, 37.3800], [55.8200, 37.5800]
        ];
    } else {
        points = [
            [55.7558, 37.6176], [55.6500, 37.6500], [55.6300, 37.7200],
            [55.6800, 37.5000], [55.6700, 37.5800], [55.5700, 37.5500],
            [55.7800, 37.6000], [55.8200, 37.5800], [55.8200, 37.8000]
        ];
    }
    
    for (const point of points) {
        const risk = await fetchRisk(point[0], point[1]);
        const score = risk.score || 0;
        let color = "#53B97C";
        if (score >= 75) color = "#D65A63";
        else if (score >= 50) color = "#D65A63";
        else if (score >= 25) color = "#E8A23A";
        
        const circle = new ymaps.Circle(
            [point, 2000],
            {
                hintContent: getAllergenName() + "\nРиск: " + (risk.risk || "Низкий") + " (" + score + " баллов)\nПыльца: " + (risk.allergen_value || 0) + " ед."
            },
            {
                fillColor: color + "66",
                strokeColor: color,
                strokeWidth: 3,
                fillOpacity: 0.5,
                interactive: false
            }
        );
        pollenCircles.push(circle);
        myMap.geoObjects.add(circle);
    }
}

function clearPollen() {
    pollenCircles.forEach(circle => myMap.geoObjects.remove(circle));
    pollenCircles = [];
}

function createMarker(coords, type) {
    return new ymaps.Placemark(
        coords,
        { hintContent: "Точка " + type },
        {
            preset: "islands#circleDotIcon",
            iconColor: type === "A" ? "#53B97C" : "#D65A63"
        }
    );
}

async function selectPoint(coords) {
    if (panelMode === "map") {
        const risk = await fetchRisk(coords[0], coords[1]);
        updateMapInfo(risk, coords);
        return;
    }
    
    if (isSelectingPointA) {
        if (pointAMarker) myMap.geoObjects.remove(pointAMarker);
        if (pointBMarker) myMap.geoObjects.remove(pointBMarker);
        if (currentRoute) myMap.geoObjects.remove(currentRoute);
        
        pointA = coords;
        pointAMarker = createMarker(coords, "A");
        myMap.geoObjects.add(pointAMarker);
        
        const riskA = await fetchRisk(coords[0], coords[1]);
        updateRiskBadge(document.getElementById("point-a-risk"), riskA.risk || "Низкий");
        document.getElementById("point-a-coords").innerHTML = coords[0].toFixed(4) + ", " + coords[1].toFixed(4);
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
        
        const riskB = await fetchRisk(coords[0], coords[1]);
        updateRiskBadge(document.getElementById("point-b-risk"), riskB.risk || "Низкий");
        document.getElementById("point-b-coords").innerHTML = coords[0].toFixed(4) + ", " + coords[1].toFixed(4);
        await buildRoute();
        isSelectingPointA = true;
    }
}

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

async function changeAllergen(type) {
    currentAllergen = type;
    document.querySelectorAll(".allergen-item").forEach(btn => btn.classList.remove("active"));
    document.querySelector(`[data-allergen="${type}"]`).classList.add("active");
    
    if (panelMode === "map") {
        document.getElementById("page-subtitle").textContent = "Аллерген: " + getAllergenName();
        await renderPollenMap();
    } else if (panelMode === "route") {
        if (pointA && pointB) await buildRoute();
        if (pointA) {
            const riskA = await fetchRisk(pointA[0], pointA[1]);
            updateRiskBadge(document.getElementById("point-a-risk"), riskA.risk || "Низкий");
        }
        if (pointB) {
            const riskB = await fetchRisk(pointB[0], pointB[1]);
            updateRiskBadge(document.getElementById("point-b-risk"), riskB.risk || "Низкий");
        }
    }
}

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
        document.getElementById("page-subtitle").textContent = "Аллерген: " + getAllergenName();
    } else {
        document.getElementById("mode-route").classList.add("active");
        document.getElementById("map-panel").style.display = "none";
        document.getElementById("route-panel").style.display = "block";
        clearPollen();
        document.getElementById("page-title").textContent = "Безопасный маршрут";
        document.getElementById("page-subtitle").textContent = "Выберите точки A и Б на карте";
        resetRoute();
    }
}

async function loadUserAllergensFromDB() {
    try {
        const response = await fetch("/api/user/allergens");
        const data = await response.json();
        if (data.success && data.allergens) {
            document.getElementById("user-allergen-birch").checked = false;
            document.getElementById("user-allergen-grass").checked = false;
            document.getElementById("user-allergen-ragweed").checked = false;
            
            for (const allergen of data.allergens) {
                const checkbox = document.getElementById("user-allergen-" + allergen);
                if (checkbox) checkbox.checked = true;
            }
            
            if (data.allergens.length > 0) {
                const primaryAllergen = data.allergens[0];
                if (primaryAllergen !== currentAllergen) {
                    await changeAllergen(primaryAllergen);
                }
            }
        }
    } catch (error) {
        console.error("Ошибка загрузки аллергенов пользователя:", error);
    }
}

async function saveUserAllergens() {
    if (!currentUser || currentUser.role !== 'user') {
        alert("Пожалуйста, войдите в систему как обычный пользователь");
        return;
    }
    
    const selectedAllergens = [];
    if (document.getElementById("user-allergen-birch").checked) selectedAllergens.push("birch");
    if (document.getElementById("user-allergen-grass").checked) selectedAllergens.push("grass");
    if (document.getElementById("user-allergen-ragweed").checked) selectedAllergens.push("ragweed");
    
    if (selectedAllergens.length === 0) {
        alert("Выберите хотя бы один аллерген");
        return;
    }
    
    try {
        const allergensList = ["birch", "grass", "ragweed"];
        for (const allergen of allergensList) {
            await fetch("/api/user/allergens/" + allergen, { 
                method: "DELETE",
                credentials: "include"
            });
        }
        
        for (const allergen of selectedAllergens) {
            await fetch("/api/user/allergens", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({ allergen_type: allergen, severity: 3 })
            });
        }
        
        alert("Аллергены сохранены!");
        
        if (selectedAllergens.length > 0 && selectedAllergens[0] !== currentAllergen) {
            await changeAllergen(selectedAllergens[0]);
        }
    } catch (error) {
        console.error("Ошибка сохранения аллергенов:", error);
        alert("Ошибка при сохранении");
    }
}

async function showRouteHistory() {
    if (!currentUser || currentUser.role !== 'user') {
        alert("Только зарегистрированные пользователи могут просматривать историю маршрутов");
        return;
    }
    
    try {
        const response = await fetch("/api/route/history", {
            method: "GET",
            credentials: "include"
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || "Ошибка загрузки");
        }
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || "Ошибка загрузки истории");
        }
        
        const allergenNames = {
            "birch": "Берёза",
            "grass": "Злаки",
            "ragweed": "Амброзия"
        };
        
        if (data.history && data.history.length > 0) {
            let historyHtml = '<div class="history-list">';
            for (let route of data.history.slice(0, 10)) {
                const startLat = route.start_lat;
                const startLon = route.start_lon;
                const endLat = route.end_lat;
                const endLon = route.end_lon;
                const riskScore = route.risk_score || 0;
                const allergenName = allergenNames[route.allergen_type] || route.allergen_type || "—";
                const createdDate = route.created_at ? new Date(route.created_at).toLocaleString() : "Дата неизвестна";
                
                let riskClass = "risk-low";
                if (riskScore >= 50) riskClass = "risk-high";
                else if (riskScore >= 25) riskClass = "risk-medium";
                
                historyHtml += `
                    <div class="history-item">
                        <div class="history-header">
                            <span class="history-date">${createdDate}</span>
                            <span class="history-risk ${riskClass}">Риск: ${riskScore} баллов</span>
                        </div>
                        <div class="history-route">
                            <div class="history-point">
                                <span class="history-point-label">Откуда:</span>
                                <span class="history-point-coords">${startLat ? startLat.toFixed(4) : "—"}°, ${startLon ? startLon.toFixed(4) : "—"}°</span>
                            </div>
                            <div class="history-arrow">→</div>
                            <div class="history-point">
                                <span class="history-point-label">Куда:</span>
                                <span class="history-point-coords">${endLat ? endLat.toFixed(4) : "—"}°, ${endLon ? endLon.toFixed(4) : "—"}°</span>
                            </div>
                        </div>
                        <div class="history-allergen">Аллерген: ${allergenName}</div>
                    </div>
                `;
            }
            historyHtml += '</div>';
            document.getElementById("route-details").innerHTML = historyHtml;
        } else {
            document.getElementById("route-details").innerHTML = '<div class="empty-history">У вас пока нет сохранённых маршрутов</div>';
        }
    } catch(e) {
        console.error("Ошибка:", e);
        document.getElementById("route-details").innerHTML = '<div class="error-message">Ошибка загрузки истории: ' + e.message + '</div>';
    }
}

// =====================
// АДМИН-МОДАЛЬНОЕ ОКНО
// =====================

const adminModal = document.getElementById("admin-modal");
const adminModalClose = document.getElementById("admin-modal-close");

function openAdminModal() {
    adminModal.style.display = "flex";
}

function closeAdminModal() {
    adminModal.style.display = "none";
    document.getElementById("admin-modal-content").innerHTML = "";
}

async function loadAdminModal(url, title) {
    try {
        document.getElementById("admin-modal-content").innerHTML = `
            <div style="text-align: center; padding: 40px;">
                <div class="loading-spinner"></div>
                <p>Загрузка...</p>
            </div>
        `;
        openAdminModal();
        
        const response = await fetch(url, { credentials: "include" });
        const html = await response.text();
        
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        
        const allCards = doc.querySelectorAll('.admin-card');
        let allContent = '';
        
        if (allCards.length > 0) {
            allCards.forEach(card => {
                allContent += card.outerHTML;
            });
        } else {
            let content = doc.querySelector('.container');
            if (!content) content = doc.body;
            allContent = content.innerHTML;
        }
        
        allContent = allContent.replace(/<button[^>]*close-btn[^>]*>.*?<\/button>/gi, '');
        allContent = allContent.replace(/<button[^>]*Закрыть[^>]*>.*?<\/button>/gi, '');
        
        document.getElementById("admin-modal-content").innerHTML = `
            <h3 style="margin-bottom: 20px; color: #2ecc71;">` + title + `</h3>
            <div style="max-height: 500px; overflow-y: auto;">
                ` + allContent + `
            </div>
        `;
        
        const forms = document.querySelectorAll("#admin-modal-content form");
        forms.forEach(form => {
            form.addEventListener("submit", async (e) => {
                e.preventDefault();
                const formData = new FormData(form);
                const action = form.action;
                
                try {
                    const response = await fetch(action, {
                        method: "POST",
                        body: formData,
                        credentials: "include"
                    });
                    
                    if (response.redirected) {
                        closeAdminModal();
                        showToast("Операция выполнена успешно");
                        setTimeout(() => location.reload(), 1500);
                    } else {
                        const result = await response.json();
                        showToast(result.message || "Операция выполнена");
                        closeAdminModal();
                        setTimeout(() => location.reload(), 1000);
                    }
                } catch (error) {
                    showToast("Ошибка при выполнении операции", "error");
                }
            });
        });
        
    } catch(e) {
        document.getElementById("admin-modal-content").innerHTML = `<div style="color: red;">Ошибка загрузки: ` + e.message + `</div>`;
    }
}

function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = "toast-message toast-" + type;
    toast.innerHTML = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: ` + (type === "success" ? "#2ecc71" : "#e74c3c") + `;
        color: white;
        padding: 12px 24px;
        border-radius: 12px;
        z-index: 10000;
        animation: fadeInOut 3s ease;
        font-weight: 500;
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

adminModal.addEventListener("click", (e) => {
    if (e.target === adminModal) closeAdminModal();
});
if (adminModalClose) adminModalClose.addEventListener("click", closeAdminModal);

// =====================
// АВТОРИЗАЦИЯ
// =====================

async function checkAuth() {
    try {
        const response = await fetch("/api/user/me");
        const data = await response.json();
        
        if (data.authenticated) {
            currentUser = data;
            const isGlobalAdmin = data.role === 'global_admin';
            const isAllergenAdmin = data.role === 'allergen_admin';
            const isUserAdmin = data.role === 'user_admin';
            const isRegularUser = data.role === 'user';
            
            document.getElementById("user-guest-panel").style.display = "none";
            document.getElementById("user-authed-panel").style.display = "none";
            document.getElementById("user-admin-panel").style.display = "none";
            document.getElementById("global-admin-panel").style.display = "none";
            document.getElementById("allergen-admin-panel").style.display = "none";
            document.getElementById("user-management-panel").style.display = "none";
            
            document.getElementById("allergen-select-card").style.display = "block";
            
            if (isGlobalAdmin) {
                document.getElementById("user-admin-panel").style.display = "block";
                document.getElementById("global-admin-panel").style.display = "block";
                document.getElementById("allergen-admin-panel").style.display = "block";
                document.getElementById("user-management-panel").style.display = "block";
                document.getElementById("admin-name-display").innerHTML = data.username;
                document.getElementById("user-badge").innerHTML = data.username;
                document.getElementById("user-allergens-card").style.display = "none";
            } 
            else if (isAllergenAdmin) {
                document.getElementById("user-admin-panel").style.display = "block";
                document.getElementById("allergen-admin-panel").style.display = "block";
                document.getElementById("admin-name-display").innerHTML = data.username;
                document.getElementById("user-badge").innerHTML = data.username;
                document.getElementById("user-allergens-card").style.display = "none";
            }
            else if (isUserAdmin) {
                document.getElementById("user-admin-panel").style.display = "block";
                document.getElementById("user-management-panel").style.display = "block";
                document.getElementById("admin-name-display").innerHTML = data.username;
                document.getElementById("user-badge").innerHTML = data.username;
                document.getElementById("user-allergens-card").style.display = "none";
            }
            else if (isRegularUser) {
                document.getElementById("user-authed-panel").style.display = "block";
                document.getElementById("user-allergens-card").style.display = "block";
                document.getElementById("username-display").innerHTML = data.username;
                document.getElementById("user-badge").innerHTML = data.username;
                await loadUserAllergensFromDB();
            }
        } else {
            currentUser = null;
            document.getElementById("user-guest-panel").style.display = "block";
            document.getElementById("user-authed-panel").style.display = "none";
            document.getElementById("user-admin-panel").style.display = "none";
            document.getElementById("global-admin-panel").style.display = "none";
            document.getElementById("allergen-admin-panel").style.display = "none";
            document.getElementById("user-management-panel").style.display = "none";
            document.getElementById("allergen-select-card").style.display = "block";
            document.getElementById("user-allergens-card").style.display = "none";
            document.getElementById("user-badge").innerHTML = "Гость";
            
            currentAllergen = "birch";
            document.querySelectorAll(".allergen-item").forEach(btn => btn.classList.remove("active"));
            document.querySelector(`[data-allergen="birch"]`).classList.add("active");
        }
    } catch (error) {
        console.error("Ошибка проверки авторизации:", error);
    }
}

async function login(email, password) {
    try {
        const response = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ email, password })
        });
        const data = await response.json();
        if (data.success) {
            await checkAuth();
            closeModal();
            showToast("Вход выполнен успешно!");
            return true;
        } else {
            showToast(data.error, "error");
            return false;
        }
    } catch (error) {
        showToast("Ошибка при входе", "error");
        return false;
    }
}

async function register(username, email, password) {
    try {
        const response = await fetch("/api/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ username, email, password })
        });
        const data = await response.json();
        if (data.success) {
            await checkAuth();
            closeModal();
            showToast("Регистрация успешна!");
            return true;
        } else {
            showToast(data.error, "error");
            return false;
        }
    } catch (error) {
        showToast("Ошибка при регистрации", "error");
        return false;
    }
}

async function logout() {
    try {
        const response = await fetch("/api/logout", { 
            method: "POST", 
            credentials: "include" 
        });
        
        if (response.ok) {
            currentUser = null;
            await checkAuth();
            
            if (pointAMarker) myMap.geoObjects.remove(pointAMarker);
            if (pointBMarker) myMap.geoObjects.remove(pointBMarker);
            if (currentRoute) myMap.geoObjects.remove(currentRoute);
            
            pointA = null;
            pointB = null;
            pointAMarker = null;
            pointBMarker = null;
            currentRoute = null;
            isSelectingPointA = true;
            
            document.getElementById("route-status").textContent = "Выберите точку A";
            document.getElementById("point-a-risk").innerHTML = "—";
            document.getElementById("point-b-risk").innerHTML = "—";
            document.getElementById("point-a-coords").innerHTML = "—";
            document.getElementById("point-b-coords").innerHTML = "—";
            document.getElementById("route-risk").innerHTML = "—";
            document.getElementById("route-details").innerHTML = "Маршрут ещё не построен";
            
            await changeAllergen("birch");
            showToast("Вы вышли из системы");
            
            // Перенаправляем на главную страницу
            setTimeout(() => {
                window.location.href = "/";
            }, 1000);
        } else {
            showToast("Ошибка при выходе", "error");
        }
    } catch (error) {
        console.error("Ошибка при выходе:", error);
        showToast("Ошибка при выходе", "error");
    }
}

// =====================
// МОДАЛЬНОЕ ОКНО АВТОРИЗАЦИИ
// =====================

const modal = document.getElementById("auth-modal");
const modalClose = document.querySelector(".modal-close");

function openLoginModal() { 
    modal.style.display = "flex";
    document.getElementById("login-form").style.display = "block";
    document.getElementById("register-form").style.display = "none";
}

function openRegisterModal() { 
    modal.style.display = "flex";
    document.getElementById("login-form").style.display = "none";
    document.getElementById("register-form").style.display = "block";
}

function closeModal() {
    modal.style.display = "none";
    document.getElementById("login-form").style.display = "block";
    document.getElementById("register-form").style.display = "none";
    document.getElementById("login-email").value = "";
    document.getElementById("login-password").value = "";
    document.getElementById("reg-username").value = "";
    document.getElementById("reg-email").value = "";
    document.getElementById("reg-password").value = "";
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
        await selectPoint(e.get("coords"));
    });
    
    document.getElementById("mode-map").addEventListener("click", () => switchMode("map"));
    document.getElementById("mode-route").addEventListener("click", () => switchMode("route"));
    document.getElementById("reset-route-btn").addEventListener("click", resetRoute);
    document.getElementById("save-allergens-btn").addEventListener("click", saveUserAllergens);
    
    document.getElementById("login-btn").addEventListener("click", openLoginModal);
    document.getElementById("register-btn").addEventListener("click", openRegisterModal);
    if (modalClose) modalClose.addEventListener("click", closeModal);
    window.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });
    
    document.getElementById("show-register")?.addEventListener("click", (e) => {
        e.preventDefault();
        document.getElementById("login-form").style.display = "none";
        document.getElementById("register-form").style.display = "block";
    });
    document.getElementById("show-login")?.addEventListener("click", (e) => {
        e.preventDefault();
        document.getElementById("register-form").style.display = "none";
        document.getElementById("login-form").style.display = "block";
    });
    
    document.getElementById("login-submit")?.addEventListener("click", async () => {
        await login(document.getElementById("login-email").value, document.getElementById("login-password").value);
    });
    document.getElementById("register-submit")?.addEventListener("click", async () => {
        await register(document.getElementById("reg-username").value, document.getElementById("reg-email").value, document.getElementById("reg-password").value);
    });
    
    // Универсальная кнопка выхода - для всех ролей
    const logoutButtons = document.querySelectorAll("#logout-btn, #logout-admin-btn");
    logoutButtons.forEach(btn => {
        if (btn) {
            btn.addEventListener("click", logout);
        }
    });
    
    document.getElementById("show-history-btn")?.addEventListener("click", showRouteHistory);
    
    document.querySelectorAll(".allergen-item").forEach(button => {
        button.addEventListener("click", async function() {
            await changeAllergen(this.dataset.allergen);
        });
    });
    
    document.getElementById("admin-users-btn")?.addEventListener("click", () => {
        loadAdminModal("/admin/users-list", "Все пользователи");
    });
    document.getElementById("admin-stats-btn")?.addEventListener("click", () => {
        loadAdminModal("/admin/global", "Системная статистика");
    });
    document.getElementById("admin-logs-btn")?.addEventListener("click", () => {
        loadAdminModal("/admin/logs", "Системные логи");
    });
    document.getElementById("allergen-zones-btn")?.addEventListener("click", () => {
        loadAdminModal("/admin/allergen", "Управление опасными зонами");
    });
    document.getElementById("allergen-stats-btn")?.addEventListener("click", () => {
        loadAdminModal("/admin/allergen/stats", "Статистика опасных зон по типам аллергенов");
    });
    document.getElementById("user-list-btn")?.addEventListener("click", () => {
        loadAdminModal("/admin/user", "Управление пользователями");
    });
    document.getElementById("user-stats-btn")?.addEventListener("click", () => {
        loadAdminModal("/admin/user-stats", "Статистика маршрутов");
    });
    
    checkAuth();
    switchMode("map");
}

ymaps.ready(init);