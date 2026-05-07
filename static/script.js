document.getElementById("test-btn").addEventListener("click", () => {
    fetch("/api/risk", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            lat: 55.75,
            lon: 37.61
        })
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById("lat").textContent = data.lat;
        document.getElementById("lon").textContent = data.lon;
        document.getElementById("risk").textContent = data.risk;
        document.getElementById("forecast").textContent = data.forecast;
        document.getElementById("route-risk").textContent = data.route_risk;
    })
    .catch(error => {
        console.error("Ошибка:", error);
    });
});