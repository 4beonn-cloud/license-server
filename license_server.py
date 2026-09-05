from flask import Flask, request, jsonify, render_template_string
from datetime import datetime, timedelta
import sqlite3
import secrets
import string

app = Flask(__name__)

DB_NAME = "licenses.db"

# 관리자 비밀번호
ADMIN_PASSWORD = "1234"


# =========================
# DB
# =========================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            days INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()


# =========================
# 키 생성
# =========================

def generate_key():
    chars = string.ascii_uppercase + string.digits

    while True:
        key = "-".join(
            "".join(secrets.choice(chars) for _ in range(4))
            for _ in range(3)
        )

        conn = get_db()

        result = conn.execute(
            "SELECT id FROM licenses WHERE license_key = ?",
            (key,)
        ).fetchone()

        conn.close()

        if not result:
            return key


# =========================
# 관리자 페이지
# =========================

ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>License Admin</title>

    <style>
        body {
            background: #111;
            color: white;
            font-family: Arial;
            text-align: center;
            padding-top: 80px;
        }

        .box {
            width: 500px;
            margin: auto;
            background: #1c1c1c;
            padding: 30px;
            border-radius: 12px;
        }

        button {
            padding: 15px 25px;
            margin: 8px;
            border: 0;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
        }

        input {
            padding: 12px;
            width: 250px;
            margin: 10px;
        }

        #result {
            margin-top: 25px;
            font-size: 20px;
        }
    </style>
</head>

<body>

<div class="box">

    <h1>License Admin</h1>

    <input
        type="password"
        id="password"
        placeholder="관리자 비밀번호"
    >

    <br>

    <button onclick="createLicense(1)">
        1일권 생성
    </button>

    <button onclick="createLicense(7)">
        7일권 생성
    </button>

    <button onclick="createLicense(30)">
        30일권 생성
    </button>

    <div id="result"></div>

</div>


<script>

async function createLicense(days) {

    const password =
        document.getElementById("password").value;

    const response = await fetch(
        "/api/admin/create",
        {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                password: password,
                days: days
            })
        }
    );

    const data = await response.json();

    if (data.success) {

        document.getElementById("result").innerHTML =
            "생성된 키:<br><br><b>" +
            data.key +
            "</b><br><br>" +
            "만료: " +
            data.expires;

    } else {

        document.getElementById("result").innerHTML =
            "오류: " + data.message;
    }
}

</script>

</body>
</html>
"""


@app.route("/")
def admin_page():
    return render_template_string(ADMIN_HTML)


# =========================
# 관리자 라이선스 생성
# =========================

@app.route("/api/admin/create", methods=["POST"])
def admin_create():

    data = request.get_json(silent=True) or {}

    password = data.get("password")
    days = data.get("days")

    if password != ADMIN_PASSWORD:
        return jsonify({
            "success": False,
            "message": "관리자 비밀번호가 틀렸습니다."
        }), 403

    if days not in [1, 7, 30]:
        return jsonify({
            "success": False,
            "message": "잘못된 기간입니다."
        }), 400

    now = datetime.now()
    expires = now + timedelta(days=days)

    key = generate_key()

    conn = get_db()

    conn.execute("""
        INSERT INTO licenses
        (license_key, days, created_at, expires_at, active)
        VALUES (?, ?, ?, ?, 1)
    """, (
        key,
        days,
        now.isoformat(),
        expires.isoformat()
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "key": key,
        "days": days,
        "expires": expires.isoformat()
    })


# =========================
# C++ 라이선스 인증
# =========================

@app.route("/api/license/verify", methods=["POST"])
def verify_license():

    data = request.get_json(silent=True) or {}

    key = data.get("key")

    if not key:
        return jsonify({
            "valid": False,
            "message": "라이선스 키가 없습니다."
        })

    conn = get_db()

    license_data = conn.execute("""
        SELECT *
        FROM licenses
        WHERE license_key = ?
    """, (key,)).fetchone()

    conn.close()

    if not license_data:
        return jsonify({
            "valid": False,
            "message": "존재하지 않는 라이선스입니다."
        })

    if license_data["active"] != 1:
        return jsonify({
            "valid": False,
            "message": "차단된 라이선스입니다."
        })

    expires = datetime.fromisoformat(
        license_data["expires_at"]
    )

    if datetime.now() >= expires:
        return jsonify({
            "valid": False,
            "message": "라이선스가 만료되었습니다."
        })

    return jsonify({
        "valid": True,
        "days": license_data["days"],
        "expires": license_data["expires_at"]
    })


# =========================
# 실행
# =========================

if __name__ == "__main__":

    init_db()

    print("================================")
    print("       License Server")
    print("================================")
    print("Admin: http://127.0.0.1:5000")

    app.run(
        host="0.0.0.0",
        port=5000
    )