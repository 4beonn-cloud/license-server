from flask import Flask, request, jsonify, render_template_string
from datetime import datetime, timedelta, timezone
import sqlite3
import secrets
import string
import os

app = Flask(__name__)

# ==================================================
# 설정
# ==================================================

DB_NAME = "licenses.db"

# Render 환경변수에서 관리자 비밀번호를 가져옴
# 로컬 테스트에서는 ADMIN_PASSWORD가 없으면 1234 사용
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "141127")

# Render가 자동으로 PORT 환경변수를 제공함
PORT = int(os.environ.get("PORT", 5000))


# ==================================================
# 시간
# ==================================================

def now_utc():
    return datetime.now(timezone.utc)


# ==================================================
# DB
# ==================================================

def get_db():
    conn = sqlite3.connect(
        DB_NAME,
        timeout=30,
        check_same_thread=False
    )

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


# ==================================================
# 라이선스 키 생성
# ==================================================

def generate_key():

    chars = string.ascii_uppercase + string.digits

    while True:

        key = "-".join(
            "".join(
                secrets.choice(chars)
                for _ in range(4)
            )
            for _ in range(3)
        )

        conn = get_db()

        result = conn.execute(
            """
            SELECT id
            FROM licenses
            WHERE license_key = ?
            """,
            (key,)
        ).fetchone()

        conn.close()

        if not result:
            return key


# ==================================================
# 관리자 페이지
# ==================================================

ADMIN_HTML = """
<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>License Admin</title>

    <style>

        body {
            background: #111;
            color: white;
            font-family: Arial, sans-serif;
            text-align: center;
            padding-top: 80px;
        }

        .box {
            width: 500px;
            max-width: 90%;
            margin: auto;
            background: #1c1c1c;
            padding: 30px;
            border-radius: 12px;
            box-sizing: border-box;
        }

        h1 {
            margin-bottom: 25px;
        }

        input {
            padding: 12px;
            width: 250px;
            max-width: 90%;
            margin: 10px;
            border-radius: 6px;
            border: none;
            box-sizing: border-box;
        }

        button {
            padding: 15px 25px;
            margin: 8px;
            border: 0;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
        }

        button:hover {
            opacity: 0.8;
        }

        #result {
            margin-top: 25px;
            font-size: 18px;
            word-break: break-all;
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

    const result =
        document.getElementById("result");


    result.innerHTML = "생성 중...";


    try {

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

            result.innerHTML =
                "생성된 키:<br><br>" +
                "<b>" +
                data.key +
                "</b>" +
                "<br><br>" +
                "기간: " +
                data.days +
                "일" +
                "<br>" +
                "만료: " +
                data.expires;

        } else {

            result.innerHTML =
                "오류: " +
                data.message;

        }

    } catch (error) {

        result.innerHTML =
            "서버 오류가 발생했습니다.";

    }

}

</script>


</body>

</html>
"""


# ==================================================
# 관리자 페이지
# ==================================================

@app.route("/")
def admin_page():

    return render_template_string(
        ADMIN_HTML
    )


# ==================================================
# 서버 상태 확인
# ==================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok"
    })


# ==================================================
# 관리자 라이선스 생성
# ==================================================

@app.route(
    "/api/admin/create",
    methods=["POST"]
)
def admin_create():

    data = request.get_json(
        silent=True
    ) or {}


    password = data.get("password")
    days = data.get("days")


    # 관리자 비밀번호 확인

    if password != ADMIN_PASSWORD:

        return jsonify({
            "success": False,
            "message": "관리자 비밀번호가 틀렸습니다."
        }), 403


    # 기간 확인

    try:

        days = int(days)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message": "잘못된 기간입니다."
        }), 400


    if days not in [1, 7, 30]:

        return jsonify({
            "success": False,
            "message": "잘못된 기간입니다."
        }), 400


    # 현재 시간

    now = now_utc()

    expires = now + timedelta(
        days=days
    )


    # 키 생성

    key = generate_key()


    # DB 저장

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT INTO licenses
            (
                license_key,
                days,
                created_at,
                expires_at,
                active
            )
            VALUES (?, ?, ?, ?, 1)
            """,
            (
                key,
                days,
                now.isoformat(),
                expires.isoformat()
            )
        )

        conn.commit()

    finally:

        conn.close()


    return jsonify({

        "success": True,

        "key": key,

        "days": days,

        "expires": expires.isoformat()

    })


# ==================================================
# C++ 라이선스 인증
# ==================================================

@app.route(
    "/api/license/verify",
    methods=["POST"]
)
def verify_license():

    data = request.get_json(
        silent=True
    ) or {}


    key = data.get("key")


    if not key:

        return jsonify({

            "valid": False,

            "message":
                "라이선스 키가 없습니다."

        }), 400


    # 공백 제거

    key = str(key).strip().upper()


    # DB 조회

    conn = get_db()

    try:

        license_data = conn.execute(
            """
            SELECT *
            FROM licenses
            WHERE license_key = ?
            """,
            (key,)
        ).fetchone()

    finally:

        conn.close()


    # 존재하지 않음

    if not license_data:

        return jsonify({

            "valid": False,

            "message":
                "존재하지 않는 라이선스입니다."

        })


    # 차단됨

    if license_data["active"] != 1:

        return jsonify({

            "valid": False,

            "message":
                "차단된 라이선스입니다."

        })


    # 만료 확인

    try:

        expires = datetime.fromisoformat(
            license_data["expires_at"]
        )

    except ValueError:

        return jsonify({

            "valid": False,

            "message":
                "라이선스 데이터가 잘못되었습니다."

        }), 500


    if now_utc() >= expires:

        return jsonify({

            "valid": False,

            "message":
                "라이선스가 만료되었습니다."

        })


    # 인증 성공

    return jsonify({

        "valid": True,

        "days":
            license_data["days"],

        "expires":
            license_data["expires_at"]

    })


# ==================================================
# DB 초기화
# ==================================================

# 중요:
# Gunicorn으로 실행하면
# if __name__ == "__main__"
# 부분이 실행되지 않는다.
#
# 따라서 서버가 import될 때 DB를 생성한다.

init_db()


# ==================================================
# 로컬 실행
# ==================================================

if __name__ == "__main__":

    print("================================")
    print("       License Server")
    print("================================")
    print(
        "Admin: http://127.0.0.1:"
        + str(PORT)
    )

    app.run(
        host="0.0.0.0",
        port=PORT
    )
