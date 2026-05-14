let myMap;
let currentRoute = null;
let activePlacemark = null;
let markerObjects = [];
let currentAllergen = "birch";

const centerCoords = [55.7558, 37.6176];

function riskCssClass(risk) {
    if (risk === "Низкий") return "low";
    if (risk === "Средний") return "medium";
    if (risk === "Высокий") return "high";
    return "very-high";
}

function setPointInfo(data) {
    const riskBox = document.getElementById("point-risk");
    riskBox.textContent = data.risk;
    riskBox.className = `risk-badge risk-${riskCssClass(data.risk)}`;

    document.getElementById("point-temp").textContent =
        data.temperature !== null && data.temperature !== undefined ? `${data.temperature}°C` : "—";

    document.getElementById("point-wind").textContent =
        data.wind_speed !== null && data.wind_speed !== undefined ? `${data.wind_speed} м/с` : "—";

    document.getElementById("point-humidity").textContent =
        data.humidity !== null && data.humidity !== undefined ? `${data.humidity}%` : "—";

    document.getElementById("point-allergen-value").textContent =
        data.allergen_value !== null && data.allergen_value !== undefined ? data.allergen_value : "—";

    document.getElementById("point-allergen").textContent = data.allergen_label;
    document.getElementById("point-score").textContent = data.score;
    document.getElementById("forecast-text").textContent = data.forecast;
}

async function fetchRisk(lat, lon) {
    const response = await fetch("/api/risk", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            lat,
            lon,
            allergen: currentAllergen
        })
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || "Ошибка загрузки данных");
    }

    return data;
}

async function fetchMapMarkers() {
    const response = await fetch(`/api/map-markers?allergen=${currentAllergen}`);
    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || "Ошибка загрузки карты");
    }

    return data.markers;
}

function clearMarkers() {
    markerObjects.forEach(obj => myMap.geoObjects.remove(obj));
    markerObjects = [];
}

function markerLayout() {
    return ymaps.templateLayoutFactory.createClass(`
        <div class="custom-pin-wrap">
            <div class="custom-pin-head" style="background: {{ properties.iconColor }};">
                <div class="custom-pin-text">{{ properties.iconText }}</div>
            </div>
        </div>
    `);
}

async function loadMarkers() {
    clearMarkers();

    const PinLayout = markerLayout();
    const markers = await fetchMapMarkers();

    markers.forEach(marker => {
        const placemark = new ymaps.Placemark(
            [marker.lat, marker.lon],
            {
                hintContent: `${marker.name}: ${marker.risk}`,
                balloonContent: `
                    <strong>${marker.name}</strong><br>
                    Аллерген: ${marker.allergen_label}<br>
                    Уровень риска: ${marker.risk}<br>
                    Индекс: ${marker.score}
                `,
                iconText: marker.marker_value,
                iconColor: marker.color
            },
            {
                iconLayout: PinLayout,
                iconShape: {
                    type: "Rectangle",
                    coordinates: [[-26, -52], [26, 4]]
                },
                hideIconOnBalloonOpen: false
            }
        );

        placemark.events.add("click", async () => {
            const fullData = await fetchRisk(marker.lat, marker.lon);
            setPointInfo(fullData);

            if (activePlacemark) {
                myMap.geoObjects.remove(activePlacemark);
            }

            activePlacemark = new ymaps.Placemark(
                [marker.lat, marker.lon],
                {},
                {
                    preset: "islands#redDotIcon"
                }
            );

            myMap.geoObjects.add(activePlacemark);
        });

        myMap.geoObjects.add(placemark);
        markerObjects.push(placemark);
    });
}

function geocodeToCoords(address) {
    return new Promise((resolve, reject) => {
        ymaps.geocode(address).then(
            function (result) {
                const first = result.geoObjects.get(0);
                if (!first) {
                    reject(new Error("Адрес не найден"));
                    return;
                }
                resolve(first.geometry.getCoordinates());
            },
            function (error) {
                reject(error);
            }
        );
    });
}

function buildYRoute(points) {
    return new Promise((resolve, reject) => {
        ymaps.route(points).then(resolve, reject);
    });
}

async function chooseSaferWaypoint(fromCoords, toCoords) {
    const midLat = (fromCoords[0] + toCoords[0]) / 2;
    const midLon = (fromCoords[1] + toCoords[1]) / 2;
    const offset = 0.08;

    const candidates = [
        [midLat, midLon],
        [midLat + offset, midLon],
        [midLat - offset, midLon],
        [midLat, midLon + offset],
        [midLat, midLon - offset]
    ];

    let bestPoint = null;

    for (const coords of candidates) {
        try {
            const data = await fetchRisk(coords[0], coords[1]);
            if (!bestPoint || data.score < bestPoint.score) {
                bestPoint = {
                    coords,
                    score: data.score,
                    risk: data.risk
                };
            }
        } catch (e) {
            console.error("Ошибка точки маршрута:", e);
        }
    }

    return bestPoint;
}

async function buildRoute() {
    const from = document.getElementById("route-from").value.trim();
    const to = document.getElementById("route-to").value.trim();
    const routeRiskBox = document.getElementById("route-risk");
    const routeDetails = document.getElementById("route-details");

    if (!from || !to) {
        alert("Введите обе точки маршрута");
        return;
    }

    routeDetails.textContent = "Построение маршрута...";
    routeRiskBox.textContent = "—";
    routeRiskBox.className = "route-risk-box";

    if (currentRoute) {
        myMap.geoObjects.remove(currentRoute);
        currentRoute = null;
    }

    try {
        const fromCoords = await geocodeToCoords(from);
        const toCoords = await geocodeToCoords(to);
        const waypoint = await chooseSaferWaypoint(fromCoords, toCoords);

        let routePoints = [fromCoords, toCoords];
        if (waypoint && waypoint.score < 70) {
            routePoints = [fromCoords, waypoint.coords, toCoords];
        }

        currentRoute = await buildYRoute(routePoints);
        myMap.geoObjects.add(currentRoute);

        const destinationRisk = await fetchRisk(toCoords[0], toCoords[1]);

        routeRiskBox.textContent = destinationRisk.risk;
        routeRiskBox.className = `route-risk-box route-${riskCssClass(destinationRisk.risk)}`;

        let extraText = "Маршрут построен";
        if (waypoint && waypoint.score < 70) {
            extraText = "Маршрут построен через более безопасную промежуточную точку";
        }

        routeDetails.innerHTML = `
            ${extraText}<br>
            Длина: ${currentRoute.getHumanLength()}<br>
            Время: ${currentRoute.getHumanTime()}
        `;
    } catch (error) {
        console.error(error);
        routeDetails.textContent = "Не удалось построить маршрут. Проверьте адреса.";
    }
}

async function handleMapClick(coords) {
    const lat = parseFloat(coords[0].toFixed(6));
    const lon = parseFloat(coords[1].toFixed(6));

    try {
        const data = await fetchRisk(lat, lon);
        setPointInfo(data);

        if (activePlacemark) {
            myMap.geoObjects.remove(activePlacemark);
        }

        activePlacemark = new ymaps.Placemark(
            [lat, lon],
            {},
            {
                preset: "islands#redDotIcon"
            }
        );

        myMap.geoObjects.add(activePlacemark);
    } catch (error) {
        console.error(error);
    }
}

function bindAllergenButtons() {
    document.querySelectorAll(".allergen-item").forEach(btn => {
        btn.addEventListener("click", async () => {
            document.querySelectorAll(".allergen-item").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            currentAllergen = btn.dataset.allergen;
            await loadMarkers();

            const data = await fetchRisk(centerCoords[0], centerCoords[1]);
            setPointInfo(data);
        });
    });
}

function init() {
    myMap = new ymaps.Map("map", {
        center: centerCoords,
        zoom: 9,
        controls: ["zoomControl", "geolocationControl", "fullscreenControl"]
    });

    myMap.events.add("click", function (e) {
        handleMapClick(e.get("coords"));
    });

    bindAllergenButtons();

    document.getElementById("build-route-btn").addEventListener("click", buildRoute);

    loadMarkers();
    fetchRisk(centerCoords[0], centerCoords[1]).then(setPointInfo);
}

ymaps.ready(init);