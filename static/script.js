const DEFAULT_CENTER = [55.7558, 37.6176];
const DEFAULT_FROM = "Москва, Красная площадь";
const DEFAULT_TO = "Москва, Парк Горького";

let myMap = null;
let currentAllergen = "birch";
let currentRoute = null;
let detailPlacemark = null;
let clusterer = null;
let pinLayoutClass = null;
let clusterLayoutClass = null;
let lastDetailCoords = DEFAULT_CENTER.slice();

function riskCssClass(level) {
    if (level === "Низкий") return "low";
    if (level === "Средний") return "medium";
    if (level === "Высокий") return "high";
    return "very-high";
}

function formatMetric(value, suffix = "", digits = 1) {
    if (value === null || value === undefined || value === "") {
        return "—";
    }
    const numeric = Number(value);
    if (Number.isNaN(numeric)) {
        return "—";
    }
    return `${numeric.toFixed(digits).replace(".0", "")}${suffix}`;
}

function showMapLoading(text) {
    const block = document.getElementById("map-loading");
    block.textContent = text || "Загрузка…";
    block.classList.remove("hidden");
}

function hideMapLoading() {
    document.getElementById("map-loading").classList.add("hidden");
}

function setMarkerStatus(text) {
    document.getElementById("marker-status").textContent = text;
}

function setPointInfo(data) {
    const riskBox = document.getElementById("point-risk");
    riskBox.textContent = data.risk || "—";
    riskBox.className = `risk-badge risk-${riskCssClass(data.risk)}`;

    document.getElementById("point-temp").textContent = formatMetric(data.temperature, "°C");
    document.getElementById("point-wind").textContent = formatMetric(data.wind_speed, " м/с");
    document.getElementById("point-humidity").textContent = formatMetric(data.humidity, "%", 0);
    document.getElementById("point-allergen-value").textContent = formatMetric(data.allergen_value, "", 1);
    document.getElementById("point-allergen").textContent = data.allergen_label || "—";
    document.getElementById("point-score").textContent = data.score ?? "—";
    document.getElementById("point-aqi").textContent = formatMetric(data.aqi, "", 0);
    document.getElementById("point-pm25").textContent = formatMetric(data.pm25, " мкг/м³", 1);
    document.getElementById("forecast-text").textContent = data.forecast || "Нет данных прогноза";
}

async function fetchRisk(lat, lon, options = {}) {
    const withForecast = options.withForecast !== false;

    const response = await fetch("/api/risk", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            lat: Number(lat),
            lon: Number(lon),
            allergen: currentAllergen,
            with_forecast: withForecast
        })
    });

    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || "Ошибка загрузки данных точки");
    }

    return data;
}

function getCurrentBoundsPayload() {
    const bounds = myMap.getBounds();
    return {
        south: bounds[0][0],
        west: bounds[0][1],
        north: bounds[1][0],
        east: bounds[1][1],
        zoom: myMap.getZoom()
    };
}

async function fetchMapMarkers() {
    const payload = getCurrentBoundsPayload();
    const url = new URL("/api/map-markers", window.location.origin);

    url.searchParams.set("allergen", currentAllergen);
    url.searchParams.set("south", payload.south);
    url.searchParams.set("west", payload.west);
    url.searchParams.set("north", payload.north);
    url.searchParams.set("east", payload.east);
    url.searchParams.set("zoom", payload.zoom);

    const response = await fetch(url.toString());
    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || "Ошибка загрузки маркеров");
    }

    return data;
}

function getPinLayout() {
    if (!pinLayoutClass) {
        pinLayoutClass = ymaps.templateLayoutFactory.createClass(`
            <div class="custom-pin">
                <div class="custom-pin__shape" style="background: {{ properties.iconColor }};"></div>
                <div class="custom-pin__label">{{ properties.iconText }}</div>
            </div>
        `);
    }
    return pinLayoutClass;
}

function getClusterLayout() {
    if (!clusterLayoutClass) {
        clusterLayoutClass = ymaps.templateLayoutFactory.createClass(`
            <div class="cluster-badge">{{ properties.geoObjects.length }}</div>
        `);
    }
    return clusterLayoutClass;
}

function ensureClusterer() {
    if (clusterer) return;

    clusterer = new ymaps.Clusterer({
        clusterDisableClickZoom: false,
        groupByCoordinates: false,
        clusterOpenBalloonOnClick: true,
        clusterBalloonPanelMaxMapArea: 0,
        clusterIconLayout: getClusterLayout(),
        clusterIconShape: {
            type: "Circle",
            coordinates: [28, 28],
            radius: 28
        }
    });

    myMap.geoObjects.add(clusterer);
}

function clearMarkers() {
    ensureClusterer();
    clusterer.removeAll();
}

function setDetailPlacemark(coords) {
    if (detailPlacemark) {
        myMap.geoObjects.remove(detailPlacemark);
    }

    detailPlacemark = new ymaps.Placemark(coords, {}, {
        preset: "islands#redCircleDotIcon"
    });

    myMap.geoObjects.add(detailPlacemark);
}

function createMarker(marker) {
    const placemark = new ymaps.Placemark(
        [marker.lat, marker.lon],
        {
            hintContent: `${marker.name}: ${marker.risk}`,
            balloonContent: `
                <strong>${marker.name}</strong><br>
                Аллерген: ${marker.allergen_label}<br>
                Уровень риска: ${marker.risk}<br>
                Индекс: ${marker.score}<br>
                Значение пыльцы: ${marker.allergen_value}
            `,
            iconText: marker.marker_value,
            iconColor: marker.color
        },
        {
            iconLayout: getPinLayout(),
            iconOffset: [-22, -56],
            iconShape: {
                type: "Rectangle",
                coordinates: [[-22, -56], [22, 0]]
            },
            hideIconOnBalloonOpen: false,
            openBalloonOnClick: true
        }
    );

    placemark.events.add("click", async function (event) {
        if (event && typeof event.stopPropagation === "function") {
            event.stopPropagation();
        }
        await selectPoint(marker.lat, marker.lon, { pan: false });
    });

    return placemark;
}

let markerReloadTimer = null;

function scheduleMarkersReload(delay = 280) {
    if (markerReloadTimer) {
        clearTimeout(markerReloadTimer);
    }

    markerReloadTimer = setTimeout(() => {
        loadMarkers();
    }, delay);
}

async function loadMarkers() {
    showMapLoading("Загрузка маркеров…");
    setMarkerStatus("Загрузка карты аллергенов…");
    clearMarkers();

    try {
        const payload = await fetchMapMarkers();
        const markers = payload.markers || [];
        const geoObjects = markers.map(createMarker);

        ensureClusterer();
        clusterer.add(geoObjects);

        setMarkerStatus(`Загружено точек: ${markers.length}. Аллерген: ${payload.allergen_label}. Zoom: ${payload.zoom}.`);
    } catch (error) {
        console.error(error);
        setMarkerStatus("Не удалось загрузить маркеры карты.");
    } finally {
        hideMapLoading();
    }
}

async function selectPoint(lat, lon, options = {}) {
    try {
        const data = await fetchRisk(lat, lon, { withForecast: true });
        lastDetailCoords = [Number(lat), Number(lon)];
        setPointInfo(data);
        setDetailPlacemark([Number(lat), Number(lon)]);

        if (options.pan) {
            myMap.panTo([Number(lat), Number(lon)], {
                delay: 0,
                duration: 250
            });
        }
    } catch (error) {
        console.error(error);
        document.getElementById("forecast-text").textContent = "Не удалось загрузить подробности по выбранной точке";
    }
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
        ymaps.route(points, {
            mapStateAutoApply: true
        }).then(resolve, reject);
    });
}

function styleRoute(route) {
    try {
        route.getPaths().options.set({
            strokeWidth: 5,
            opacity: 0.9,
            strokeColor: "#2f6cf6"
        });
    } catch (error) {
        console.warn("Не удалось применить стиль маршрута", error);
    }
}

async function chooseSaferWaypoint(fromCoords, toCoords) {
    const midLat = (fromCoords[0] + toCoords[0]) / 2;
    const midLon = (fromCoords[1] + toCoords[1]) / 2;
    const offsetLat = 0.08;
    const offsetLon = 0.08;

    const candidates = [
        { name: "center", coords: [midLat, midLon] },
        { name: "north", coords: [midLat + offsetLat, midLon] },
        { name: "south", coords: [midLat - offsetLat, midLon] },
        { name: "east", coords: [midLat, midLon + offsetLon] },
        { name: "west", coords: [midLat, midLon - offsetLon] }
    ];

    const results = await Promise.all(
        candidates.map(async (candidate) => {
            try {
                const data = await fetchRisk(candidate.coords[0], candidate.coords[1], {
                    withForecast: false
                });

                return {
                    ...candidate,
                    score: data.score,
                    risk: data.risk
                };
            } catch (error) {
                console.error("Ошибка при расчёте кандидата маршрута:", error);
                return {
                    ...candidate,
                    score: Number.POSITIVE_INFINITY,
                    risk: "—"
                };
            }
        })
    );

    const valid = results.filter((item) => Number.isFinite(item.score));
    if (!valid.length) {
        return null;
    }

    const centerCandidate = valid.find((item) => item.name === "center") || valid[0];
    const bestCandidate = [...valid].sort((a, b) => a.score - b.score)[0];

    return {
        center: centerCandidate,
        best: bestCandidate,
        shouldUse: bestCandidate.name !== "center" && bestCandidate.score + 5 < centerCandidate.score
    };
}

async function buildRoute() {
    let from = document.getElementById("route-from").value.trim();
    let to = document.getElementById("route-to").value.trim();

    const routeRiskBox = document.getElementById("route-risk");
    const routeDetails = document.getElementById("route-details");

    if (!from) {
        from = DEFAULT_FROM;
        document.getElementById("route-from").value = from;
    }

    if (!to) {
        to = DEFAULT_TO;
        document.getElementById("route-to").value = to;
    }

    routeRiskBox.textContent = "—";
    routeRiskBox.className = "route-risk-box";
    routeDetails.textContent = "Построение маршрута…";

    if (currentRoute) {
        myMap.geoObjects.remove(currentRoute);
        currentRoute = null;
    }

    try {
        const [fromCoords, toCoords] = await Promise.all([
            geocodeToCoords(from),
            geocodeToCoords(to)
        ]);

        const [destinationRisk, waypointPlan] = await Promise.all([
            fetchRisk(toCoords[0], toCoords[1], { withForecast: false }),
            chooseSaferWaypoint(fromCoords, toCoords)
        ]);

        let routePoints = [fromCoords, toCoords];
        let usedWaypoint = null;

        if (waypointPlan && waypointPlan.shouldUse && waypointPlan.best) {
            routePoints = [
                fromCoords,
                { type: "viaPoint", point: waypointPlan.best.coords },
                toCoords
            ];
            usedWaypoint = waypointPlan.best;
        }

        try {
            currentRoute = await buildYRoute(routePoints);
        } catch (routeError) {
            console.warn("Маршрут с промежуточной точкой не построился, пробуем прямой.", routeError);
            currentRoute = await buildYRoute([fromCoords, toCoords]);
            usedWaypoint = null;
        }

        styleRoute(currentRoute);
        myMap.geoObjects.add(currentRoute);

        routeRiskBox.textContent = destinationRisk.risk;
        routeRiskBox.className = `route-risk-box route-${riskCssClass(destinationRisk.risk)}`;

        let detailsHtml = `
            Длина: ${currentRoute.getHumanLength()}<br>
            Время: ${currentRoute.getHumanTime()}<br>
            Оценка маршрута показана по точке назначения.
        `;

        if (usedWaypoint) {
            detailsHtml = `
                Маршрут построен через более безопасную промежуточную зону.<br>
                Промежуточный риск: ${usedWaypoint.risk} (индекс ${usedWaypoint.score}).<br>
                ${detailsHtml}
            `;
        } else if (waypointPlan && waypointPlan.center) {
            detailsHtml = `
                Прямой маршрут оставлен без обхода: безопасный путь не дал заметного выигрыша по индексу.<br>
                ${detailsHtml}
            `;
        }

        routeDetails.innerHTML = detailsHtml;
    } catch (error) {
        console.error(error);
        routeDetails.textContent = "Не удалось построить маршрут. Проверьте адреса и повторите попытку.";
    }
}

function bindAllergenButtons() {
    document.querySelectorAll(".allergen-item").forEach((button) => {
        button.addEventListener("click", async function () {
            if (button.dataset.allergen === currentAllergen) {
                return;
            }

            document.querySelectorAll(".allergen-item").forEach((item) => item.classList.remove("active"));
            button.classList.add("active");

            currentAllergen = button.dataset.allergen;

            await loadMarkers();
            await selectPoint(lastDetailCoords[0], lastDetailCoords[1], { pan: false });
        });
    });
}

function init() {
    myMap = new ymaps.Map("map", {
        center: DEFAULT_CENTER,
        zoom: 9,
        controls: ["zoomControl", "geolocationControl", "fullscreenControl"]
    });

    ensureClusterer();

    myMap.events.add("click", function (event) {
        const coords = event.get("coords");
        selectPoint(coords[0], coords[1], { pan: false });
    });

    myMap.events.add("boundschange", function (event) {
        if (event.get("newZoom") !== event.get("oldZoom")) {
            scheduleMarkersReload(250);
        }
    });

    bindAllergenButtons();
    document.getElementById("build-route-btn").addEventListener("click", buildRoute);

    Promise.all([
        loadMarkers(),
        selectPoint(DEFAULT_CENTER[0], DEFAULT_CENTER[1], { pan: false })
    ]).catch((error) => {
        console.error("Ошибка первичной загрузки:", error);
        setMarkerStatus("Первичная загрузка завершилась с ошибкой. Попробуйте обновить страницу.");
    });
}

ymaps.ready(init);