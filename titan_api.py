from flask import Flask, jsonify, request
from flask_cors import CORS

from data.live_price import get_live_price

app = Flask(__name__)
CORS(app)


# =========================
# STOCK NAME MAPPING
# =========================

STOCK_ALIASES = {
    "RELIANCE": ["reliance", "ril", "jio"],
    "TCS": ["tcs", "tata consultancy"],
    "INFY": ["infosys", "infy"],
    "HDFCBANK": ["hdfc bank", "hdfcbank", "hdfc"],
    "ICICIBANK": ["icici bank", "icicibank", "icici"],
    "SBIN": ["sbi", "state bank", "state bank of india"],
    "AXISBANK": ["axis bank", "axisbank"],
    "KOTAKBANK": ["kotak bank", "kotakbank", "kotak"],
    "LT": ["larsen", "larsen and toubro", "l&t"],
    "ITC": ["itc"],
    "HINDUNILVR": ["hindustan unilever", "hul", "hindunilvr"],
    "BHARTIARTL": ["airtel", "bharti airtel", "bhartiartl"],
    "MARUTI": ["maruti"],
    "TATAMOTORS": ["tata motors", "tatamotors"],
    "BAJFINANCE": ["bajaj finance", "bajfinance"],
    "ASIANPAINT": ["asian paint", "asian paints", "asianpaint"],
}


def detect_stock(message):
    msg = message.lower()

    for symbol, names in STOCK_ALIASES.items():
        for name in names:
            if name in msg:
                return symbol

    words = msg.upper().replace(" PRICE", "").replace("PRICE", "").split()

    for word in words:
        if word in STOCK_ALIASES:
            return word

    return None


@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "message": "TITAN API RUNNING"
    })


@app.route("/status")
def status():
    return jsonify({
        "titan_status": "ONLINE",
        "voice_ui": "CONNECTED",
        "market_engine": "READY",
    })


@app.route("/price/<symbol>")
def price(symbol):
    try:
        symbol = symbol.upper()
        live_price = get_live_price(symbol)

        if live_price is None:
            return jsonify({
                "success": False,
                "symbol": symbol,
                "error": "Unable to fetch live price"
            })

        return jsonify({
            "success": True,
            "symbol": symbol,
            "price": live_price
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json or {}
        message = str(data.get("message", "")).lower().strip()

        if not message:
            return jsonify({"reply": "Please say or type something."})

        detected_symbol = detect_stock(message)

        if detected_symbol and ("price" in message or "current" in message or detected_symbol.lower() in message):
            live_price = get_live_price(detected_symbol)

            if live_price:
                return jsonify({
                    "reply": f"{detected_symbol} current price is rupees {live_price}"
                })

            return jsonify({
                "reply": f"Unable to fetch {detected_symbol} live price. Possible issue: Upstox token, internet, or symbol mapping."
            })

        if "status" in message:
            return jsonify({
                "reply": "TITAN systems are online. Assistant UI, voice mode, and backend API are connected."
            })

        if "hello" in message or "hi" in message:
            return jsonify({
                "reply": "Hello. TITAN online."
            })

        if "error" in message or "issue" in message or "problem" in message:
            return jsonify({
                "reply": "Error monitor is active. If a backend issue happens, I will report it here."
            })

        if "market" in message:
            return jsonify({
                "reply": "Market intelligence module will be connected next."
            })

        return jsonify({
            "reply": "Command received."
        })

    except Exception as e:
        return jsonify({
            "reply": f"API error: {str(e)}"
        })


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )