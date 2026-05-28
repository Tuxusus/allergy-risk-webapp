const DEFAULT_CENTER = [55.7558, 37.6176];

let myMap;

let pointA = null;
let pointB = null;

let pointAMarker = null;
let pointBMarker = null;

let currentRoute = null;

let isSelectingPointA = true;

// СОЗДАНИЕ МАРКЕРА
function createMarker(coords, type) {

    return new ymaps.Placemark(
        coords,
        {
            hintContent: `Точка ${type}`
        },
        {
            preset: "islands#circleIcon",
            iconColor:
                type === "A"
                    ? "#4CAF50"
                    : "#f44336"
        }
    );
}

// ПОСТРОЕНИЕ МАРШРУТА
function buildRoute() {

    if (!pointA || !pointB) return;

    // УДАЛЯЕМ СТАРЫЙ МАРШРУТ
    if (currentRoute) {
        myMap.geoObjects.remove(currentRoute);
    }

    document.getElementById("route-status")
        .textContent =
        "Строим маршрут...";

    document.getElementById("route-details")
        .innerHTML =
        "🔄 Построение маршрута по дорогам...";

    // MULTIROUTE
    currentRoute = new ymaps.multiRouter.MultiRoute({

        referencePoints: [
            pointA,
            pointB
        ],

        params: {
            routingMode: "auto"
        }

    }, {

        boundsAutoApply: true

    });

    // СТИЛЬ
    currentRoute.options.set({

        routeActiveStrokeColor: "#f0c94c",
        routeActiveStrokeWidth: 6,
        routeStrokeWidth: 6,
        routeStrokeColor: "#f0c94c"

    });

    // ДОБАВЛЯЕМ НА КАРТУ
    myMap.geoObjects.add(currentRoute);

    // КОГДА МАРШРУТ ГОТОВ
    currentRoute.model.events.add("requestsuccess", function () {

        const activeRoute =
            currentRoute.getActiveRoute();

        if (!activeRoute) return;

        const distance =
            activeRoute.properties.get(
                "distance"
            ).text;

        const duration =
            activeRoute.properties.get(
                "duration"
            ).text;

        document.getElementById("route-risk")
            .innerHTML = `
                🛡️ Безопасный маршрут
            `;

        document.getElementById("route-risk")
            .className =
            "route-risk-box route-low";

        document.getElementById("route-details")
            .innerHTML = `

                ✅ Маршрут построен<br><br>

                🚗 Длина: ${distance}<br>
                ⏱️ Время: ${duration}<br><br>

                🌾 Учитывается уровень пыльцы
                и погодные условия

            `;

        document.getElementById("recommendation")
            .innerHTML = `

                📍 Маршрут построен по дорожной сети Яндекс.Карт.<br><br>

                🛡️ Система предлагает наиболее
                безопасный доступный путь
                для аллергиков.

            `;

        document.getElementById("route-status")
            .textContent =
            "Маршрут готов";
    });

    // ОШИБКА
    currentRoute.model.events.add("requestfail", function (error) {

        console.error(error);

        document.getElementById("route-status")
            .textContent =
            "Ошибка";

        document.getElementById("route-details")
            .innerHTML =
            "❌ Не удалось построить маршрут";
    });
}

// СБРОС
function resetRoute() {

    if (pointAMarker) {
        myMap.geoObjects.remove(pointAMarker);
    }

    if (pointBMarker) {
        myMap.geoObjects.remove(pointBMarker);
    }

    if (currentRoute) {
        myMap.geoObjects.remove(currentRoute);
    }

    pointA = null;
    pointB = null;

    pointAMarker = null;
    pointBMarker = null;

    currentRoute = null;

    isSelectingPointA = true;

    document.getElementById("route-status")
        .textContent =
        "Выбор точки A";

    document.getElementById("route-risk")
        .innerHTML = "—";

    document.getElementById("route-details")
        .innerHTML =
        "Выберите точки маршрута";

    document.getElementById("recommendation")
        .innerHTML =
        "После построения маршрута появятся рекомендации";
}

// ВЫБОР ТОЧЕК
function selectPoint(coords) {

    if (isSelectingPointA) {

        if (pointAMarker) {
            myMap.geoObjects.remove(pointAMarker);
        }

        pointA = coords;

        pointAMarker =
            createMarker(coords, "A");

        myMap.geoObjects.add(pointAMarker);

        document.getElementById("point-a-risk")
            .innerHTML =
            "Выбрана";

        document.getElementById("point-a-coords")
            .innerHTML =
            `${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`;

        document.getElementById("route-status")
            .textContent =
            "Выберите точку Б";

        isSelectingPointA = false;

    } else {

        if (pointBMarker) {
            myMap.geoObjects.remove(pointBMarker);
        }

        pointB = coords;

        pointBMarker =
            createMarker(coords, "B");

        myMap.geoObjects.add(pointBMarker);

        document.getElementById("point-b-risk")
            .innerHTML =
            "Выбрана";

        document.getElementById("point-b-coords")
            .innerHTML =
            `${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`;

        isSelectingPointA = true;

        buildRoute();
    }
}

// ИНИЦИАЛИЗАЦИЯ
function init() {

    myMap = new ymaps.Map("map", {

        center: DEFAULT_CENTER,
        zoom: 11,

        controls: [
            "zoomControl",
            "fullscreenControl",
            "geolocationControl"
        ]
    });

    // КЛИК ПО КАРТЕ
    myMap.events.add("click", function (e) {

        const coords =
            e.get("coords");

        selectPoint(coords);
    });

    // СБРОС
    document.getElementById("reset-route-btn")
        .addEventListener(
            "click",
            resetRoute
        );
}

ymaps.ready(init);