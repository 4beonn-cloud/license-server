from flask import Flask, request, jsonify, render_template_string
from datetime import datetime, timedelta, timezone
import sqlite3
import secrets
import string
import hashlib
import os

app = Flask(__name__)

DB_NAME = "licenses.db"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")
PORT = int(os.environ.get("PORT", 5000))

def now_utc():
    return datetime.now(timezone.utc)

def hash_hwid(hwid):
    return hashlib.sha256(str(hwid).strip().encode("utf-8")).hexdigest()

def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=30, check_same_thread=False)
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

    columns = conn.execute("PRAGMA table_info(licenses)").fetchall()
    column_names = {row["name"] for row in columns}

    if "hwid" not in column_names:
        conn.execute("ALTER TABLE licenses ADD COLUMN hwid TEXT")

    # 기존 DB와 호환되도록 기간 값/단위 컬럼 추가
    if "duration_value" not in column_names:
        conn.execute("ALTER TABLE licenses ADD COLUMN duration_value INTEGER")

    if "duration_unit" not in column_names:
        conn.execute("ALTER TABLE licenses ADD COLUMN duration_unit TEXT")

    conn.commit()
    conn.close()

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

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>License Admin</title>
<style>
body {
    background:#111;
    color:white;
    font-family:Arial,sans-serif;
    text-align:center;
    padding:40px 15px;
}
.box {
    width:1150px;
    max-width:100%;
    margin:auto;
    background:#1c1c1c;
    padding:30px;
    border-radius:12px;
    box-sizing:border-box;
}
input, select {
    padding:12px;
    margin:8px;
    border-radius:6px;
    border:0;
    box-sizing:border-box;
}
#password { width:280px; max-width:90%; }
#durationValue { width:120px; }
#durationUnit { width:120px; }
button {
    padding:12px 18px;
    margin:5px;
    border:0;
    border-radius:8px;
    cursor:pointer;
}
button:hover { opacity:.85; }
#result { margin:20px 0; word-break:break-all; }
.table-wrap { overflow-x:auto; margin-top:20px; }
table {
    width:100%;
    border-collapse:collapse;
    min-width:950px;
}
th,td {
    border-bottom:1px solid #333;
    padding:12px;
}
th { background:#252525; }
.active { color:#7CFF7C; font-weight:bold; }
.inactive { color:#FF7777; font-weight:bold; }
.mono {
    font-family:monospace;
    font-size:12px;
    word-break:break-all;
}
</style>
</head>

<body>
<div class="box">

<h1>License Admin</h1>

<input type="password" id="password" placeholder="관리자 비밀번호">

<br>

<div>
    <input
        type="number"
        id="durationValue"
        min="1"
        value="1"
        placeholder="기간"
    >

    <select id="durationUnit">
        <option value="minutes">분</option>
        <option value="hours">시간</option>
        <option value="days" selected>일</option>
        <option value="weeks">주</option>
        <option value="months">개월</option>
    </select>

    <button onclick="createLicense()">
        라이선스 생성
    </button>
</div>

<div style="font-size:13px;color:#aaa;">
    예: 30분 / 12시간 / 3일 / 2주 / 6개월
</div>

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
    <td colspan="6">관리자 비밀번호를 입력하고 새로고침하세요.</td>
</tr>
</tbody>
</table>
</div>

</div>

<script>
async function post(url, body) {
    const response = await fetch(url, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(body)
    });
    return await response.json();
}

function esc(value) {
    return String(value ?? "")
        .replaceAll("&","&amp;")
        .replaceAll("<","&lt;")
        .replaceAll(">","&gt;")
        .replaceAll('"',"&quot;")
        .replaceAll("'","&#039;");
}

function keyArg(value) {
    return JSON.stringify(String(value));
}

async function createLicense() {
    const password = document.getElementById("password").value;
    const value = document.getElementById("durationValue").value;
    const unit = document.getElementById("durationUnit").value;
    const result = document.getElementById("result");

    if (!password) {
        result.innerHTML = "관리자 비밀번호를 입력하세요.";
        return;
    }

    if (!value || Number(value) < 1) {
        result.innerHTML = "기간을 1 이상 입력하세요.";
        return;
    }

    result.innerHTML = "생성 중...";

    try {
        const data = await post("/api/admin/create", {
            password: password,
            value: Number(value),
            unit: unit
        });

        if (data.success) {
            result.innerHTML =
                "생성된 키:<br><br>" +
                "<b>" + esc(data.key) + "</b>" +
                "<br><br>" +
                "기간: " + esc(data.duration) +
                "<br>" +
                "만료: " + esc(data.expires);

            loadLicenses();
        } else {
            result.innerHTML = "오류: " + esc(data.message);
        }
    } catch (error) {
        result.innerHTML = "서버 오류가 발생했습니다.";
    }
}

async function loadLicenses() {
    const password = document.getElementById("password").value;
    const table = document.getElementById("licenseTable");

    if (!password) {
        table.innerHTML =
            '<tr><td colspan="6">관리자 비밀번호를 입력하세요.</td></tr>';
        return;
    }

    table.innerHTML =
        '<tr><td colspan="6">불러오는 중...</td></tr>';

    try {
        const data = await post("/api/admin/list", {
            password:password
        });

        if (!data.success) {
            table.innerHTML =
                '<tr><td colspan="6">오류: ' +
                esc(data.message) +
                '</td></tr>';
            return;
        }

        if (!data.licenses.length) {
            table.innerHTML =
                '<tr><td colspan="6">발급된 라이선스가 없습니다.</td></tr>';
            return;
        }

        table.innerHTML = data.licenses.map(function(x) {
            const status = x.active
                ? '<span class="active">활성</span>'
                : '<span class="inactive">중지</span>';

            const hwid = x.hwid
                ? '<span class="mono">' + esc(x.hwid) + '</span>'
                : '미등록';

            const activeButton = x.active
                ? '<button onclick="setActive(' +
                  keyArg(x.key) + ', false)">중지</button>'
                : '<button onclick="setActive(' +
                  keyArg(x.key) + ', true)">재활성화</button>';

            return (
                '<tr>' +
                '<td class="mono">' + esc(x.key) + '</td>' +
                '<td>' + esc(x.duration) + '</td>' +
                '<td>' + status + '</td>' +
                '<td>' + hwid + '</td>' +
                '<td>' + esc(x.expires) + '</td>' +
                '<td>' +
                activeButton +
                '<button onclick="resetHwid(' +
                keyArg(x.key) +
                ')">HWID 초기화</button>' +
                '</td>' +
                '</tr>'
            );
        }).join("");
    } catch (error) {
        table.innerHTML =
            '<tr><td colspan="6">서버 오류가 발생했습니다.</td></tr>';
    }
}

async function setActive(key, active) {
    const password = document.getElementById("password").value;

    const message = active
        ? "이 키를 재활성화할까요?"
        : "이 키를 중지할까요?";

    if (!confirm(message)) return;

    const data = await post("/api/admin/set-active", {
        password:password,
        key:key,
        active:active
    });

    if (!data.success) alert(data.message);
    loadLicenses();
}

async function resetHwid(key) {
    const password = document.getElementById("password").value;

    if (!confirm("이 키의 HWID를 초기화할까요?")) return;

    const data = await post("/api/admin/reset-hwid", {
        password:password,
        key:key
    });

    if (!data.success) alert(data.message);
    loadLicenses();
}
</script>
</body>
</html>
"""

@app.route("/")
def admin_page():
    return render_template_string(ADMIN_HTML)

@app.route("/health")
def health():
    return jsonify({"status":"ok"})

@app.route("/api/admin/create", methods=["POST"])
def admin_create():
    data = request.get_json(silent=True) or {}

    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({
            "success":False,
            "message":"관리자 비밀번호가 틀렸습니다."
        }),403

    try:
        value = int(data.get("value"))
    except (TypeError,ValueError):
        return jsonify({
            "success":False,
            "message":"잘못된 기간입니다."
        }),400

    unit = str(data.get("unit","")).strip().lower()

    if value < 1:
        return jsonify({
            "success":False,
            "message":"기간은 1 이상이어야 합니다."
        }),400

    unit_info = {
        "minutes":("분",60),
        "hours":("시간",60 * 60),
        "days":("일",60 * 60 * 24),
        "weeks":("주",60 * 60 * 24 * 7),
        # 1개월 = 30일 기준
        "months":("개월",60 * 60 * 24 * 30)
    }

    if unit not in unit_info:
        return jsonify({
            "success":False,
            "message":"지원하지 않는 기간 단위입니다."
        }),400

    unit_label, seconds_per_unit = unit_info[unit]
    duration_seconds = value * seconds_per_unit

    # 너무 긴 기간 방지: 최대 10년
    if duration_seconds > 10 * 365 * 24 * 60 * 60:
        return jsonify({
            "success":False,
            "message":"최대 기간은 10년입니다."
        }),400

    now = now_utc()
    expires = now + timedelta(seconds=duration_seconds)
    key = generate_key()

    # 기존 days 컬럼은 C++/기존 DB 호환을 위해 유지
    days = max(1, duration_seconds // (24 * 60 * 60))

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO licenses
            (
                license_key,
                days,
                created_at,
                expires_at,
                active,
                hwid,
                duration_value,
                duration_unit
            )
            VALUES (?, ?, ?, ?, 1, NULL, ?, ?)
        """, (
            key,
            days,
            now.isoformat(),
            expires.isoformat(),
            value,
            unit
        ))

        conn.commit()
    finally:
        conn.close()

    return jsonify({
        "success":True,
        "key":key,
        "duration":f"{value}{unit_label}",
        "days":days,
        "expires":expires.isoformat()
    })

@app.route("/api/admin/list", methods=["POST"])
def admin_list():
    data = request.get_json(silent=True) or {}

    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({
            "success":False,
            "message":"관리자 비밀번호가 틀렸습니다."
        }),403

    conn = get_db()

    try:
        rows = conn.execute("""
            SELECT
                license_key,
                days,
                active,
                hwid,
                expires_at,
                duration_value,
                duration_unit
            FROM licenses
            ORDER BY id DESC
        """).fetchall()
    finally:
        conn.close()

    labels = {
        "minutes":"분",
        "hours":"시간",
        "days":"일",
        "weeks":"주",
        "months":"개월"
    }

    licenses = []

    for row in rows:
        if row["duration_value"] and row["duration_unit"]:
            duration = (
                str(row["duration_value"]) +
                labels.get(row["duration_unit"], row["duration_unit"])
            )
        else:
            # 기존에 만들어진 1/7/30일 라이선스 표시
            duration = str(row["days"]) + "일"

        licenses.append({
            "key":row["license_key"],
            "days":row["days"],
            "duration":duration,
            "active":bool(row["active"]),
            "hwid":row["hwid"],
            "expires":row["expires_at"]
        })

    return jsonify({
        "success":True,
        "licenses":licenses
    })

@app.route("/api/admin/set-active", methods=["POST"])
def admin_set_active():
    data = request.get_json(silent=True) or {}

    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({
            "success":False,
            "message":"관리자 비밀번호가 틀렸습니다."
        }),403

    key = str(data.get("key","")).strip().upper()
    active = data.get("active")

    if not key or active not in [True,False]:
        return jsonify({
            "success":False,
            "message":"잘못된 요청입니다."
        }),400

    conn = get_db()

    try:
        cursor = conn.execute("""
            UPDATE licenses
            SET active = ?
            WHERE license_key = ?
        """,(1 if active else 0,key))

        conn.commit()
        changed = cursor.rowcount
    finally:
        conn.close()

    if changed == 0:
        return jsonify({
            "success":False,
            "message":"존재하지 않는 라이선스입니다."
        }),404

    return jsonify({"success":True})

@app.route("/api/admin/reset-hwid", methods=["POST"])
def admin_reset_hwid():
    data = request.get_json(silent=True) or {}

    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({
            "success":False,
            "message":"관리자 비밀번호가 틀렸습니다."
        }),403

    key = str(data.get("key","")).strip().upper()

    if not key:
        return jsonify({
            "success":False,
            "message":"라이선스 키가 없습니다."
        }),400

    conn = get_db()

    try:
        cursor = conn.execute("""
            UPDATE licenses
            SET hwid = NULL
            WHERE license_key = ?
        """,(key,))

        conn.commit()
        changed = cursor.rowcount
    finally:
        conn.close()

    if changed == 0:
        return jsonify({
            "success":False,
            "message":"존재하지 않는 라이선스입니다."
        }),404

    return jsonify({"success":True})

@app.route("/api/license/verify", methods=["POST"])
def verify_license():
    data = request.get_json(silent=True) or {}

    key = data.get("key")
    hwid = data.get("hwid")

    if not key:
        return jsonify({
            "valid":False,
            "message":"라이선스 키가 없습니다."
        }),400

    if not hwid:
        return jsonify({
            "valid":False,
            "message":"HWID가 없습니다."
        }),400

    key = str(key).strip().upper()
    hwid_hash = hash_hwid(hwid)

    conn = get_db()

    try:
        license_data = conn.execute("""
            SELECT *
            FROM licenses
            WHERE license_key = ?
        """,(key,)).fetchone()

        if not license_data:
            return jsonify({
                "valid":False,
                "message":"존재하지 않는 라이선스입니다."
            })

        if license_data["active"] != 1:
            return jsonify({
                "valid":False,
                "message":"차단된 라이선스입니다."
            })

        try:
            expires = datetime.fromisoformat(license_data["expires_at"])
        except ValueError:
            return jsonify({
                "valid":False,
                "message":"라이선스 데이터가 잘못되었습니다."
            }),500

        if now_utc() >= expires:
            return jsonify({
                "valid":False,
                "message":"라이선스가 만료되었습니다."
            })

        stored_hwid = license_data["hwid"]

        if not stored_hwid:
            conn.execute("""
                UPDATE licenses
                SET hwid = ?
                WHERE license_key = ?
            """,(hwid_hash,key))
            conn.commit()

        elif stored_hwid != hwid_hash:
            return jsonify({
                "valid":False,
                "message":"등록된 PC와 다른 PC입니다."
            })
    finally:
        conn.close()

    return jsonify({
        "valid":True,
        "days":license_data["days"],
        "expires":license_data["expires_at"]
    })

init_db()

if __name__ == "__main__":
    print("================================")
    print("       License Server")
    print("================================")
    print("Admin: http://127.0.0.1:" + str(PORT))

    app.run(
        host="0.0.0.0",
        port=PORT
    )
