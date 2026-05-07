from flask import Flask, render_template, jsonify, request

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/risk", methods=["POST"])
def get_risk():
    data = request.get_json()

    lat = data.get("lat")
    lon = data.get("lon")

    return jsonify({
        "lat": lat,
        "lon": lon,
        "risk": "Средний",
        "forecast": "Повышение риска в ближайшие часы",
        "route_risk": "Средний"
    })


if __name__ == "__main__":
    app.run(debug=True)