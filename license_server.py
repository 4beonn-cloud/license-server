from pathlib import Path

src = Path("/mnt/data/붙여넣은 텍스트 (1)(6).txt")
text = src.read_text(encoding="utf-8")

# Schema
text = text.replace(
'''            expires_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)''',
'''            expires_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            hwid TEXT
        )
    """)''', 1)

# Migration
needle = '''    conn.commit()
    conn.close()


# ==================================================
# 라이선스 키 생성'''
replacement = '''    # 기존 DB에 hwid 컬럼이 없으면 추가
    columns = conn.execute("PRAGMA table_info(licenses)").fetchall()
    column_names = {row["name"] for row in columns}
    if "hwid" not in column_names:
        conn.execute("ALTER TABLE licenses ADD COLUMN hwid TEXT")

    conn.commit()
    conn.close()


# ==================================================
# 라이선스 키 생성'''
if needle not in text:
    raise RuntimeError("migration point not found")
text = text.replace(needle, replacement, 1)

# Admin HTML
hs = text.index('ADMIN_HTML = """')
he = text.index('\n\n\n# ==================================================\n# 관리자 페이지', hs)
html = '''ADMIN_HTML = """
<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>License Admin</title>
<style>
body{background:#111;color:white;font-family:Arial;text-align:center;padding:40px 15px}
.box{width:1100px;max-width:100%;margin:auto;background:#1c1c1c;padding:30px;border-radius:12px}
input{padding:12px;width:280px;margin:8px;border-radius:6px;border:0}
button{padding:12px 18px;margin:5px;border:0;border-radius:8px;cursor:pointer}
#result{margin:20px 0;word-break:break-all}.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:850px}th,td{border-bottom:1px solid #333;padding:12px}
th{background:#252525}.active{color:#7CFF7C;font-weight:bold}.inactive{color:#FF7777;font-weight:bold}.mono{font-family:monospace;font-size:12px}
</style></head><body>
<div class="box">
<h1>License Admin</h1>
<input type="password" id="password" placeholder="관리자 비밀번호"><br>
<button onclick="createLicense(1)">1일권 생성</button>
<button onclick="createLicense(7)">7일권 생성</button>
<button onclick="createLicense(30)">30일권 생성</button>
<div id="result"></div>
<button onclick="loadLicenses()">라이선스 목록 새로고침</button>
<div class="table-wrap"><table>
<thead><tr><th>KEY</th><th>기간</th><th>상태</th><th>HWID</th><th>만료</th><th>관리</th></tr></thead>
<tbody id="licenseTable"><tr><td colspan="6">관리자 비밀번호를 입력하고 새로고침하세요.</td></tr></tbody>
</table></div>
</div>
<script>
async function post(url,body){
 const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
 return await r.json();
}
function esc(v){return String(v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");}
async function createLicense(days){
 const password=document.getElementById("password").value;
 const result=document.getElementById("result");
 if(!password){result.innerHTML="관리자 비밀번호를 입력하세요.";return;}
 result.innerHTML="생성 중...";
 try{
  const d=await post("/api/admin/create",{password:password,days:days});
  result.innerHTML=d.success?"생성된 키:<br><br><b>"+esc(d.key)+"</b><br><br>기간: "+d.days+"일<br>만료: "+esc(d.expires):"오류: "+esc(d.message);
  if(d.success) loadLicenses();
 }catch(e){result.innerHTML="서버 오류가 발생했습니다.";}
}
async function loadLicenses(){
 const password=document.getElementById("password").value;
 const table=document.getElementById("licenseTable");
 if(!password){table.innerHTML='<tr><td colspan="6">관리자 비밀번호를 입력하세요.</td></tr>';return;}
 table.innerHTML='<tr><td colspan="6">불러오는 중...</td></tr>';
 try{
  const d=await post("/api/admin/list",{password:password});
  if(!d.success){table.innerHTML='<tr><td colspan="6">오류: '+esc(d.message)+'</td></tr>';return;}
  table.innerHTML=d.licenses.length?d.licenses.map(x=>{
   const s=x.active?'<span class="active">활성</span>':'<span class="inactive">중지</span>';
   const h=x.hwid?'<span class="mono">'+esc(x.hwid)+'</span>':'미등록';
   const b=x.active
    ?'<button onclick="setActive(\''+x.key+'\',false)">중지</button>'
    :'<button onclick="setActive(\''+x.key+'\',true)">재활성화</button>';
   return '<tr><td class="mono">'+esc(x.key)+'</td><td>'+x.days+'일</td><td>'+s+'</td><td>'+h+'</td><td>'+esc(x.expires)+'</td><td>'+b+'<button onclick="resetHwid(\''+x.key+'\')">HWID 초기화</button></td></tr>';
  }).join(""):'<tr><td colspan="6">발급된 라이선스가 없습니다.</td></tr>';
 }catch(e){table.innerHTML='<tr><td colspan="6">서버 오류가 발생했습니다.</td></tr>';}
}
async function setActive(key,active){
 const password=document.getElementById("password").value;
 if(!confirm(active?"이 키를 재활성화할까요?":"이 키를 중지할까요?"))return;
 const d=await post("/api/admin/set-active",{password:password,key:key,active:active});
 if(!d.success)alert(d.message); loadLicenses();
}
async function resetHwid(key){
 const password=document.getElementById("password").value;
 if(!confirm("이 키의 HWID를 초기화할까요?"))return;
 const d=await post("/api/admin/reset-hwid",{password:password,key:key});
 if(!d.success)alert(d.message); loadLicenses();
}
</script></body></html>
"""
'''
text = text[:hs] + html + text[he:]

# Admin APIs
marker = '''# ==================================================
# C++ 라이선스 인증
# ==================================================
'''
routes = '''# ==================================================
# 관리자 라이선스 목록
# ==================================================

@app.route("/api/admin/list", methods=["POST"])
def admin_list():
    data = request.get_json(silent=True) or {}
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "관리자 비밀번호가 틀렸습니다."}), 403

    conn = get_db()
    try:
        rows = conn.execute("SELECT license_key,days,active,hwid,expires_at FROM licenses ORDER BY id DESC").fetchall()
    finally:
        conn.close()

    return jsonify({"success": True, "licenses": [
        {"key":r["license_key"],"days":r["days"],"active":bool(r["active"]),"hwid":r["hwid"],"expires":r["expires_at"]}
        for r in rows
    ]})


# ==================================================
# 관리자 라이선스 활성 / 중지
# ==================================================

@app.route("/api/admin/set-active", methods=["POST"])
def admin_set_active():
    data = request.get_json(silent=True) or {}
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "관리자 비밀번호가 틀렸습니다."}), 403
    key = str(data.get("key","")).strip().upper()
    active = data.get("active")
    if not key or active not in [True,False]:
        return jsonify({"success": False, "message": "잘못된 요청입니다."}), 400
    conn=get_db()
    try:
        cur=conn.execute("UPDATE licenses SET active=? WHERE license_key=?",(1 if active else 0,key))
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount==0:
        return jsonify({"success":False,"message":"존재하지 않는 라이선스입니다."}),404
    return jsonify({"success":True})


# ==================================================
# 관리자 HWID 초기화
# ==================================================

@app.route("/api/admin/reset-hwid", methods=["POST"])
def admin_reset_hwid():
    data=request.get_json(silent=True) or {}
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"success":False,"message":"관리자 비밀번호가 틀렸습니다."}),403
    key=str(data.get("key","")).strip().upper()
    conn=get_db()
    try:
        cur=conn.execute("UPDATE licenses SET hwid=NULL WHERE license_key=?",(key,))
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount==0:
        return jsonify({"success":False,"message":"존재하지 않는 라이선스입니다."}),404
    return jsonify({"success":True})


'''
if marker not in text:
    raise RuntimeError("API marker not found")
text = text.replace(marker, routes + marker, 1)

# HWID-aware verification
vs=text.index('@app.route(\n    "/api/license/verify"')
ve=text.index('\n\n\n# ==================================================\n# DB 초기화',vs)
verify='''@app.route(
    "/api/license/verify",
    methods=["POST"]
)
def verify_license():
    data=request.get_json(silent=True) or {}
    key=data.get("key")
    hwid=data.get("hwid")

    if not key:
        return jsonify({"valid":False,"message":"라이선스 키가 없습니다."}),400
    if not hwid:
        return jsonify({"valid":False,"message":"HWID가 없습니다."}),400

    key=str(key).strip().upper()
    hwid=str(hwid).strip()

    conn=get_db()
    try:
        license_data=conn.execute("SELECT * FROM licenses WHERE license_key=?",(key,)).fetchone()

        if not license_data:
            return jsonify({"valid":False,"message":"존재하지 않는 라이선스입니다."})
        if license_data["active"] != 1:
            return jsonify({"valid":False,"message":"차단된 라이선스입니다."})

        try:
            expires=datetime.fromisoformat(license_data["expires_at"])
        except ValueError:
            return jsonify({"valid":False,"message":"라이선스 데이터가 잘못되었습니다."}),500

        if now_utc() >= expires:
            return jsonify({"valid":False,"message":"라이선스가 만료되었습니다."})

        stored_hwid=license_data["hwid"]
        if not stored_hwid:
            conn.execute("UPDATE licenses SET hwid=? WHERE license_key=?",(hwid,key))
            conn.commit()
        elif stored_hwid != hwid:
            return jsonify({"valid":False,"message":"등록된 PC와 다른 PC입니다."})
    finally:
        conn.close()

    return jsonify({"valid":True,"days":license_data["days"],"expires":license_data["expires_at"]})
'''
text=text[:vs]+verify+text[ve:]

out=Path("/mnt/data/license_server_hwid.py")
out.write_text(text,encoding="utf-8")
compile(text,str(out),"exec")
print("완료:",out)
print("키 목록 / 중지 / 재활성화 / HWID 등록 / HWID 초기화 / 다른 PC 차단 추가 완료")
