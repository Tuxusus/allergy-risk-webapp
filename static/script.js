const DEFAULT_CENTER = [55.7558, 37.6176];

let myMap;

let currentMode = "route";
let currentAllergen = "birch";

let pointA = null;
let pointB = null;

let pointAMarker = null;
let pointBMarker = null;

let currentRoute = null;

let pollenCircles = [];

let isSelectingPointA = true;

// =====================
// ЦВЕТА
// =====================

const ROUTE_COLORS = {

    birch: "#53B97C",
    grass: "#3B82F6",
    ragweed: "#D65A63"

};

// =====================
// API
// =====================

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

    return await response.json();
}

// =====================
// КАРТА ПЫЛЬЦЫ
// =====================

async function renderPollenMap() {

    clearPollen();

    document.getElementById("page-title")
        .textContent =
        "Карта пыльцы";

    document.getElementById("page-subtitle")
        .textContent =
        `Аллерген: ${getAllergenName()}`;

    const points = [

        [55.75, 37.61],
        [55.78, 37.60],
        [55.72, 37.64],
        [55.80, 37.65],
        [55.70, 37.55],
        [55.74, 37.70],
        [55.83, 37.58],
        [55.68, 37.72],
        [55.76, 37.57],
        [55.73, 37.67]

    ];

    for (const point of points) {

        const risk =
            await fetchRisk(
                point[0],
                point[1]
            );

        const score =
            risk.score || 0;

        let color = "#53B97C";

        if (score >= 75)
            color = "#D65A63";

        else if (score >= 50)
            color = "#E8A23A";

        else if (score >= 25)
            color = "#A8C94A";

        const circle =
            new ymaps.Circle(

                [point, 2500],

                {
                    hintContent:
                        `${risk.allergen_label}<br>${score} баллов`
                },

                {

                    fillColor:
                        color + "88",

                    strokeColor:
                        color,

                    strokeWidth: 3,

                    fillOpacity: 0.45

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

    if (!pointA || !pointB)
        return;

    if (currentRoute) {

        myMap.geoObjects.remove(currentRoute);

    }

    document.getElementById("route-status")
        .textContent =
        "Построение маршрута...";

    currentRoute =
        new ymaps.multiRouter.MultiRoute({

            referencePoints: [

                pointA,
                pointB

            ],

            params: {

                // ВАЖНО:
                // теперь маршрут строится ПЕШКОМ,
                // а не на машине

                routingMode: "pedestrian",

                results: 1

            }

        }, {

            boundsAutoApply: true

        });

    const color =
        ROUTE_COLORS[currentAllergen];

    currentRoute.options.set({

        routeActiveStrokeColor:
            color,

        routeStrokeColor:
            color,

        routeActiveStrokeWidth: 6,

        routeStrokeWidth: 5,

        routeActiveStrokeStyle: "solid",

        routeStrokeStyle: "solid",

        wayPointVisible: false,

        viaPointVisible: false

    });

    myMap.geoObjects.add(currentRoute);

    currentRoute.model.events.add(

        "requestsuccess",

        function () {

            const activeRoute =
                currentRoute.getActiveRoute();

            if (!activeRoute) {

                document.getElementById("route-details")
                    .innerHTML =
                    "❌ Не удалось построить маршрут";

                return;
            }

            const distance =
                activeRoute.properties
                .get("distance").text;

            const duration =
                activeRoute.properties
                .get("duration").text;

            document.getElementById("route-risk")
                .innerHTML =
                "🛡️ Маршрут построен";

            document.getElementById("route-details")
                .innerHTML = `

                    🚶 Пеший маршрут<br><br>

                    📏 Длина:
                    ${distance}<br>

                    ⏱️ Время:
                    ${duration}<br><br>

                    🌾 Аллерген:
                    ${getAllergenName()}

                `;

            document.getElementById("comparison")
                .innerHTML = `

                    Маршрут построен
                    с учётом пешеходных дорог.

                `;

            document.getElementById("route-status")
                .textContent =
                "Маршрут готов";
        }

    );

    currentRoute.model.events.add(

        "requestfail",

        function () {

            document.getElementById("route-details")
                .innerHTML =
                "❌ Не удалось построить маршрут";

            document.getElementById("route-status")
                .textContent =
                "Ошибка маршрута";
        }

    );
}

// =====================
// МАРКЕР
// =====================

function createMarker(coords, type) {

    return new ymaps.Placemark(

        coords,

        {

            hintContent:
                `Точка ${type}`

        },

        {

            preset:
                "islands#circleDotIcon",

            iconColor:
                type === "A"
                    ? "#53B97C"
                    : "#D65A63"

        }

    );
}

// =====================
// ТОЧКИ
// =====================

function selectPoint(coords) {

    if (currentMode !== "route")
        return;

    if (isSelectingPointA) {

        resetRoute();

        pointA = coords;

        pointAMarker =
            createMarker(coords, "A");

        myMap.geoObjects.add(pointAMarker);

        document.getElementById("point-a-risk")
            .textContent =
            "Выбрана";

        document.getElementById("point-a-coords")
            .textContent =
            `${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`;

        document.getElementById("route-status")
            .textContent =
            "Выберите точку Б";

        isSelectingPointA = false;

    } else {

        pointB = coords;

        pointBMarker =
            createMarker(coords, "B");

        myMap.geoObjects.add(pointBMarker);

        document.getElementById("point-b-risk")
            .textContent =
            "Выбрана";

        document.getElementById("point-b-coords")
            .textContent =
            `${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`;

        buildRoute();

        isSelectingPointA = true;
    }
}

// =====================
// СБРОС
// =====================

function resetRoute() {

    if (pointAMarker) {

        myMap.geoObjects.remove(pointAMarker);

        pointAMarker = null;
    }

    if (pointBMarker) {

        myMap.geoObjects.remove(pointBMarker);

        pointBMarker = null;
    }

    if (currentRoute) {

        myMap.geoObjects.remove(currentRoute);

        currentRoute = null;
    }

    pointA = null;
    pointB = null;

    document.getElementById("point-a-risk")
        .textContent = "—";

    document.getElementById("point-b-risk")
        .textContent = "—";

    document.getElementById("point-a-coords")
        .textContent = "—";

    document.getElementById("point-b-coords")
        .textContent = "—";

    document.getElementById("route-risk")
        .innerHTML = "—";

    document.getElementById("route-details")
        .innerHTML =
        "Маршрут ещё не построен";

    document.getElementById("comparison")
        .innerHTML =
        "Выберите точки маршрута";

    document.getElementById("route-status")
        .textContent =
        "Выберите точку A";

    isSelectingPointA = true;
}

// =====================
// АЛЛЕРГЕН
// =====================

async function changeAllergen(type) {

    currentAllergen = type;

    document.querySelectorAll(".allergen-item")
        .forEach(btn =>
            btn.classList.remove("active")
        );

    document.querySelector(
        `[data-allergen="${type}"]`
    ).classList.add("active");

    if (currentMode === "map") {

        await renderPollenMap();

    } else if (pointA && pointB) {

        buildRoute();
    }
}

// =====================
// РЕЖИМ
// =====================

async function switchMode(mode) {

    currentMode = mode;

    document.querySelectorAll(".side-link")
        .forEach(btn =>
            btn.classList.remove("active")
        );

    if (mode === "map") {

        document.getElementById("mode-map")
            .classList.add("active");

        await renderPollenMap();

    } else {

        document.getElementById("mode-route")
            .classList.add("active");

        clearPollen();

        document.getElementById("page-title")
            .textContent =
            "Безопасный маршрут";

        document.getElementById("page-subtitle")
            .textContent =
            "Выберите точки A и Б";
    }
}

// =====================
// НАЗВАНИЕ
// =====================

function getAllergenName() {

    if (currentAllergen === "birch")
        return "Берёза";

    if (currentAllergen === "grass")
        return "Злаки";

    return "Амброзия";
}

// =====================
// INIT
// =====================

function init() {

    myMap = new ymaps.Map("map", {

        center: DEFAULT_CENTER,

        zoom: 10,

        controls: [

            "zoomControl",
            "fullscreenControl",
            "geolocationControl"

        ]

    });

    myMap.events.add("click", function (e) {

        const coords =
            e.get("coords");

        selectPoint(coords);

    });

    // MODE
    document.getElementById("mode-map")
        .addEventListener(

            "click",

            () => switchMode("map")

        );

    document.getElementById("mode-route")
        .addEventListener(

            "click",

            () => switchMode("route")

        );

    // RESET
    document.getElementById("reset-route-btn")
        .addEventListener(

            "click",

            resetRoute

        );

    // ALLERGENS
    document.querySelectorAll(".allergen-item")
        .forEach(button => {

            button.addEventListener(

                "click",

                async function () {

                    await changeAllergen(
                        this.dataset.allergen
                    );

                }

            );

        });
}

ymaps.ready(init);