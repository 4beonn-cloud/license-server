from flask import Flask, request, jsonify, render_template_string
from datetime import datetime, timedelta, timezone
import sqlite3
import secrets
import string
import hashlib
import os

app = Flask(__name__)

# ==================================================
# 설정
# ==================================================

DB_NAME = "licenses.db"

# Render 환경변수 ADMIN_PASSWORD가 있으면 그 값을 사용합니다.
# 없으면 로컬 테스트용으로 1234를 사용합니다.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")

PORT = int(os.environ.get("PORT", 5000))


# ==================================================
# 시간
# ==================================================

def now_utc():
    return datetime.now(timezone.utc)


# ==================================================
# HWID
# ==================================================

def hash_hwid(hwid):
    """HWID 원문을 서버 DB에 저장하지 않고 SHA-256 해시로 저장합니다."""
    return hashlib.sha256(str(hwid).strip().encode("utf-8")).hexdigest()


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
            active INTEGER NOT NULL DEFAULT 1,
            hwid TEXT
        )
    """)

    # 기존 DB에 hwid 컬럼이 없는 경우 자동 추가
    columns = conn.execute("PRAGMA table_info(licenses)").fetchall()
    column_names = {row["name"] for row in columns}

    if "hwid" not in column_names:
        conn.execute("ALTER TABLE licenses ADD COLUMN hwid TEXT")

    conn.commit()
    conn.close()


# ==================================================
# 라이선스 키 생성
# ==================================================

def generate_key():
    chars = string.ascii_uppercase + string.digits

    while True:
        key = "-".join(
            "".join(secrets.choice(chars) for _ in range(4))
            for _ in range(3)
        )

        conn = get_db()
        try:
            exists = conn.execute(
                "SELECT id FROM licenses WHERE license_key = ?",
                (key,)
            ).fetchone()
        finally:
            conn.close()

        if not exists:
            return key


# ==================================================
# 관리자 페이지
# ==================================================

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>License Admin</title>

<style>
body {
    background: #111;
    color: white;
    font-family: Arial, sans-serif;
    text-align: center;
    padding: 40px 15px;
}

.box {
    width: 1150px;
    max-width: 100%;
    margin: auto;
    background: #1c1c1c;
    padding: 30px;
    border-radius: 12px;
    box-sizing: border-box;
}

input {
    padding: 12px;
    width: 280px;
    max-width: 90%;
    margin: 8px;
    border-radius: 6px;
    border: 0;
}

button {
    padding: 12px 18px;
    margin: 5px;
    border: 0;
    border-radius: 8px;
    cursor: pointer;
}

button:hover {
    opacity: 0.85;
}

#result {
    margin: 20px 0;
    word-break: break-all;
}

.table-wrap {
    overflow-x: auto;
    margin-top: 20px;
}

table {
    width: 100%;
    border-collapse: collapse;
    min-width: 900px;
}

th, td {
    border-bottom: 1px solid #333;
    padding: 12px;
}

th {
    background: #252525;
}

.active {
    color: #7CFF7C;
    font-weight: bold;
}

.inactive {
    color: #FF7777;
    font-weight: bold;
}

.mono {
    font-family: monospace;
    font-size: 12px;
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

<button onclick="createLicense(1)">1일권 생성</button>
<button onclick="createLicense(7)">7일권 생성</button>
<button onclick="createLicense(30)">30일권 생성</button>

<div id="result"></div>

<button onclick="loadLicenses()">
    라이선스 목록 새로고침
</button>

<div class="table-wrap">
<table>
<thead>
<tr>
    <th>KEY</th>
    <th>기간</th>
    <th>상태</th>
    <th>HWID</th>
    <th>만료</th>
    <th>관리</th>
</tr>
</thead>

<tbody id="licenseTable">
<tr>
    <td colspan="6">
        관리자 비밀번호를 입력하고 새로고침하세요.
    </td>
</tr>
</tbody>
</table>
</div>

</div>

<script>

async function post(url, body) {
    const response = await fetch(
        url,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(body)
        }
    );

    return await response.json();
}


function esc(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function keyArg(value) {
    return JSON.stringify(String(value));
}


async function createLicense(days) {

    const password =
        document.getElementById("password").value;

    const result =
        document.getElementById("result");

    if (!password) {
        result.innerHTML =
            "관리자 비밀번호를 입력하세요.";
        return;
    }

    result.innerHTML = "생성 중...";

    try {

        const data = await post(
            "/api/admin/create",
            {
                password: password,
                days: days
            }
        );

        if (data.success) {

            result.innerHTML =
                "생성된 키:<br><br>" +
                "<b>" + esc(data.key) + "</b>" +
                "<br><br>" +
                "기간: " + data.days + "일" +
                "<br>" +
                "만료: " + esc(data.expires);

            loadLicenses();

        } else {

            result.innerHTML =
                "오류: " + esc(data.message);
        }

    } catch (error) {

        result.innerHTML =
            "서버 오류가 발생했습니다.";
    }
}


async function loadLicenses() {

    const password =
        document.getElementById("password").value;

    const table =
        document.getElementById("licenseTable");

    if (!password) {

        table.innerHTML =
            '<tr><td colspan="6">' +
            '관리자 비밀번호를 입력하세요.' +
            '</td></tr>';

        return;
    }

    table.innerHTML =
        '<tr><td colspan="6">불러오는 중...</td></tr>';

    try {

        const data = await post(
            "/api/admin/list",
            {
                password: password
            }
        );

        if (!data.success) {

            table.innerHTML =
                '<tr><td colspan="6">' +
                '오류: ' + esc(data.message) +
                '</td></tr>';

            return;
        }

        if (!data.licenses.length) {

            table.innerHTML =
                '<tr><td colspan="6">' +
                '발급된 라이선스가 없습니다.' +
                '</td></tr>';

            return;
        }

        table.innerHTML = data.licenses.map(function (x) {

            const status =
                x.active
                ? '<span class="active">활성</span>'
                : '<span class="inactive">중지</span>';

            const hwid =
                x.hwid
                ? '<span class="mono">' +
                  esc(x.hwid) +
                  '</span>'
                : '미등록';

            const activeButton =
                x.active
                ? '<button onclick="setActive(' +
                  keyArg(x.key) +
                  ', false)">중지</button>'
                : '<button onclick="setActive(' +
                  keyArg(x.key) +
                  ', true)">재활성화</button>';

            return (
                '<tr>' +
                '<td class="mono">' +
                esc(x.key) +
                '</td>' +

                '<td>' +
                esc(x.days) +
                '일</td>' +

                '<td>' +
                status +
                '</td>' +

                '<td>' +
                hwid +
                '</td>' +

                '<td>' +
                esc(x.expires) +
                '</td>' +

                '<td>' +
                activeButton +

                '<button onclick="resetHwid(' +
                keyArg(x.key) +
                ')">' +
                'HWID 초기화' +
                '</button>' +

                '</td>' +
                '</tr>'
            );

        }).join("");

    } catch (error) {

        table.innerHTML =
            '<tr><td colspan="6">' +
            '서버 오류가 발생했습니다.' +
            '</td></tr>';
    }
}


async function setActive(key, active) {

    const password =
        document.getElementById("password").value;

    const message =
        active
        ? "이 키를 재활성화할까요?"
        : "이 키를 중지할까요?";

    if (!confirm(message)) {
        return;
    }

    const data = await post(
        "/api/admin/set-active",
        {
            password: password,
            key: key,
            active: active
        }
    );

    if (!data.success) {
        alert(data.message);
    }

    loadLicenses();
}


async function resetHwid(key) {

    const password =
        document.getElementById("password").value;

    if (!confirm("이 키의 HWID를 초기화할까요?")) {
        return;
    }

    const data = await post(
        "/api/admin/reset-hwid",
        {
            password: password,
            key: key
        }
    );

    if (!data.success) {
        alert(data.message);
    }

    loadLicenses();
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
    return render_template_string(ADMIN_HTML)


# ==================================================
# 서버 상태
# ==================================================

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ==================================================
# 라이선스 생성
# ==================================================

@app.route("/api/admin/create", methods=["POST"])
def admin_create():

    data = request.get_json(silent=True) or {}

    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({
            "success": False,
            "message": "관리자 비밀번호가 틀렸습니다."
        }), 403

    try:
        days = int(data.get("days"))
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

    now = now_utc()
    expires = now + timedelta(days=days)
    key = generate_key()

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
                active,
                hwid
            )
            VALUES (?, ?, ?, ?, 1, NULL)
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
# 라이선스 목록
# ==================================================

@app.route("/api/admin/list", methods=["POST"])
def admin_list():

    data = request.get_json(silent=True) or {}

    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({
            "success": False,
            "message": "관리자 비밀번호가 틀렸습니다."
        }), 403

    conn = get_db()

    try:
        rows = conn.execute(
            """
            SELECT
                license_key,
                days,
                active,
                hwid,
                expires_at
            FROM licenses
            ORDER BY id DESC
            """
        ).fetchall()

    finally:
        conn.close()

    return jsonify({
        "success": True,
        "licenses": [
            {
                "key": row["license_key"],
                "days": row["days"],
                "active": bool(row["active"]),
                "hwid": row["hwid"],
                "expires": row["expires_at"]
            }
            for row in rows
        ]
    })


# ==================================================
# 라이선스 활성 / 중지
# ==================================================

@app.route("/api/admin/set-active", methods=["POST"])
def admin_set_active():

    data = request.get_json(silent=True) or {}

    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({
            "success": False,
            "message": "관리자 비밀번호가 틀렸습니다."
        }), 403

    key = str(
        data.get("key", "")
    ).strip().upper()

    active = data.get("active")

    if not key or active not in [True, False]:
        return jsonify({
            "success": False,
            "message": "잘못된 요청입니다."
        }), 400

    conn = get_db()

    try:
        cursor = conn.execute(
            """
            UPDATE licenses
            SET active = ?
            WHERE license_key = ?
            """,
            (
                1 if active else 0,
                key
            )
        )

        conn.commit()

        changed = cursor.rowcount

    finally:
        conn.close()

    if changed == 0:
        return jsonify({
            "success": False,
            "message": "존재하지 않는 라이선스입니다."
        }), 404

    return jsonify({"success": True})


# ==================================================
# HWID 초기화
# ==================================================

@app.route("/api/admin/reset-hwid", methods=["POST"])
def admin_reset_hwid():

    data = request.get_json(silent=True) or {}

    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({
            "success": False,
            "message": "관리자 비밀번호가 틀렸습니다."
        }), 403

    key = str(
        data.get("key", "")
    ).strip().upper()

    if not key:
        return jsonify({
            "success": False,
            "message": "라이선스 키가 없습니다."
        }), 400

    conn = get_db()

    try:
        cursor = conn.execute(
            """
            UPDATE licenses
            SET hwid = NULL
            WHERE license_key = ?
            """,
            (key,)
        )

        conn.commit()

        changed = cursor.rowcount

    finally:
        conn.close()

    if changed == 0:
        return jsonify({
            "success": False,
            "message": "존재하지 않는 라이선스입니다."
        }), 404

    return jsonify({"success": True})


# ==================================================
# C++ 라이선스 인증
# ==================================================

@app.route("/api/license/verify", methods=["POST"])
def verify_license():

    data = request.get_json(silent=True) or {}

    key = data.get("key")
    hwid = data.get("hwid")

    if not key:
        return jsonify({
            "valid": False,
            "message": "라이선스 키가 없습니다."
        }), 400

    if not hwid:
        return jsonify({
            "valid": False,
            "message": "HWID가 없습니다."
        }), 400

    key = str(key).strip().upper()
    hwid_hash = hash_hwid(hwid)

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

        try:
            expires = datetime.fromisoformat(
                license_data["expires_at"]
            )
        except ValueError:
            return jsonify({
                "valid": False,
                "message": "라이선스 데이터가 잘못되었습니다."
            }), 500

        if now_utc() >= expires:
            return jsonify({
                "valid": False,
                "message": "라이선스가 만료되었습니다."
            })

        stored_hwid = license_data["hwid"]

        # 첫 사용이면 현재 PC를 등록
        if not stored_hwid:

            conn.execute(
                """
                UPDATE licenses
                SET hwid = ?
                WHERE license_key = ?
                """,
                (
                    hwid_hash,
                    key
                )
            )

            conn.commit()

        # 다른 PC에서 사용하면 거부
        elif stored_hwid != hwid_hash:

            return jsonify({
                "valid": False,
                "message": "등록된 PC와 다른 PC입니다."
            })

    finally:
        conn.close()

    return jsonify({
        "valid": True,
        "days": license_data["days"],
        "expires": license_data["expires_at"]
    })


# ==================================================
# DB 초기화
# ==================================================

init_db()


# ==================================================
# 로컬 실행
# ==================================================

if __name__ == "__main__":

    print("================================")
    print("       License Server")
    print("================================")
    print(
        "Admin: http://127.0.0.1:" +
        str(PORT)
    )

    app.run(
        host="0.0.0.0",
        port=PORT
    )
