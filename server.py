# server.py
import os
import hmac
import hashlib
import json
import traceback
from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
import sqlite3
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "rakecase.db")
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")  # <- поставь ваш токен в переменных окружения

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app, supports_credentials=True)
app.config["JSON_SORT_KEYS"] = False

# ---------- DB ----------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS inventory(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        gift TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

init_db()

def ensure_user(user_id:int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users(user_id, balance) VALUES(?, 0)", (user_id,))
    conn.commit()
    conn.close()

def get_balance(user_id:int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row["balance"] if row else None

def change_balance(user_id:int, delta:int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (delta, user_id))
    conn.commit()
    conn.close()

def add_inventory(user_id:int, gift:str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO inventory(user_id, gift) VALUES(?,?)", (user_id, gift))
    conn.commit()
    conn.close()

def get_inventory(user_id:int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT gift, created_at FROM inventory WHERE user_id=? ORDER BY id DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [{"gift": r["gift"], "created_at": r["created_at"]} for r in rows]

# ---------- Telegram initData verification ----------
def verify_init_data(init_data_raw: str, bot_token: str):
    """
    Validate Telegram WebApp initData string and return dict of params if valid.
    init_data_raw is the raw string from Telegram.WebApp.initData.
    """
    try:
        if not init_data_raw or not bot_token:
            return None
        # parse into dict
        params = {}
        for part in init_data_raw.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = v
        # data_check_string: sorted keys excluding hash, joined by '\n'
        hash_value = params.get("hash")
        if not hash_value:
            return None
        items = []
        for k in sorted(params.keys()):
            if k == "hash":
                continue
            items.append(f"{k}={params[k]}")
        data_check_string = "\n".join(items)

        secret_key = hashlib.sha256(bot_token.encode()).digest()
        hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if hmac_hash != hash_value:
            return None

        # if valid, try to return parsed fields (some values are urlencoded/json)
        # 'user' field may contain JSON -> try to json.loads
        parsed = {}
        for k, v in params.items():
            try:
                parsed[k] = json.loads(v)
            except Exception:
                parsed[k] = v
        return parsed
    except Exception:
        traceback.print_exc()
        return None

# ---------- Helpers ----------
def extract_user_id():
    # 1) cookie
    uid = request.cookies.get("uid")
    if uid:
        try:
            return int(uid)
        except:
            pass
    # 2) JSON body user_id
    try:
        data = request.get_json(silent=True) or {}
        if isinstance(data, dict) and data.get("user_id"):
            return int(data.get("user_id"))
    except:
        pass
    # fallback test id
    return 123456789

# ---------- Routes ----------
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/static/<path:fname>")
def static_files(fname):
    return send_from_directory(os.path.join(BASE_DIR, "static"), fname)

@app.route("/api/init", methods=["POST"])
def api_init():
    try:
        data = request.get_json(silent=True) or {}
        initData = data.get("initData") or data.get("init_data") or ""
        # If front sends already parsed user_id -> accept it (dev)
        if data.get("user_id"):
            user_id = int(data.get("user_id"))
            ensure_user(user_id)
            resp = make_response(jsonify({"ok": True, "user_id": user_id}))
            resp.set_cookie("uid", str(user_id), httponly=True)
            return resp

        # verify initData from Telegram WebApp
        parsed = verify_init_data(initData, BOT_TOKEN)
        if parsed and parsed.get("user"):
            user_obj = parsed.get("user")
            # user may be a dict already
            if isinstance(user_obj, dict) and user_obj.get("id"):
                user_id = int(user_obj["id"])
                ensure_user(user_id)
                resp = make_response(jsonify({"ok": True, "user_id": user_id}))
                resp.set_cookie("uid", str(user_id), httponly=True)
                return resp

        # else: respond OK but without setting cookie
        return jsonify({"ok": True, "note": "no user in initData"})
    except Exception:
        traceback.print_exc()
        return jsonify({"ok": False, "message": "server error"}), 500

@app.route("/api/me", methods=["GET"])
def api_me():
    try:
        user_id = extract_user_id()
        ensure_user(user_id)
        bal = get_balance(user_id)
        return jsonify({"ok": True, "user_id": user_id, "balance": bal})
    except Exception:
        traceback.print_exc()
        return jsonify({"ok": False, "message": "server error"}), 500

@app.route("/api/topup", methods=["POST"])
def api_topup():
    try:
        user_id = extract_user_id()
        ensure_user(user_id)
        # demo: +10 stars
        change_balance(user_id, 10)
        return jsonify({"ok": True, "message": "Баланс пополнен на 10⭐", "balance": get_balance(user_id)})
    except Exception:
        traceback.print_exc()
        return jsonify({"ok": False, "message": "server error"}), 500

@app.route("/api/open", methods=["POST"])
def api_open():
    try:
        user_id = extract_user_id()
        ensure_user(user_id)

        data = request.get_json(silent=True) or {}
        case = data.get("case", "basic")

        CASES = {
            "basic": {"price": 10, "pool": (["Обычный NFT"]*70 + ["Редкий NFT"]*20 + ["Эпик NFT"]*8 + ["Легендарный NFT"]*2)},
            "premium": {"price": 30, "pool": (["Обычный NFT"]*40 + ["Редкий NFT"]*35 + ["Эпик NFT"]*20 + ["Легендарный NFT"]*5)}
        }
        if case not in CASES:
            return jsonify({"ok": False, "message": "Неизвестный кейс"}), 400

        price = CASES[case]["price"]
        bal = get_balance(user_id)
        if bal is None:
            return jsonify({"ok": False, "message": "Пользователь не найден"}), 404
        if bal < price:
            return jsonify({"ok": False, "message": "Недостаточно средств"}), 400

        gift = random.choice(CASES[case]["pool"])
        change_balance(user_id, -price)
        add_inventory(user_id, gift)

        return jsonify({"ok": True, "gift": gift, "balance": get_balance(user_id)})
    except Exception:
        traceback.print_exc()
        return jsonify({"ok": False, "message": "server error"}), 500

@app.route("/api/gifts", methods=["GET"])
def api_gifts():
    try:
        user_id = extract_user_id()
        ensure_user(user_id)
        items = get_inventory(user_id)
        return jsonify({"ok": True, "gifts": [i["gift"] for i in items], "detail": items})
    except Exception:
        traceback.print_exc()
        return jsonify({"ok": False, "message": "server error"}), 500

if __name__ == "__main__":
    print("Starting server on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
