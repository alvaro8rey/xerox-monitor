"""
Descarga CSV XSA Xerox AltaLink C8170 con login de sesión PHP.
Uso: python test_web_accounting.py
"""
import requests, re, time
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

IP       = "10.55.161.248"
USER     = "admin"
PASSWORD = input("Contraseña admin: ").strip()
BASE     = f"https://{IP}"

s = requests.Session()
s.verify  = False
s.timeout = 12
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
})

def ok(r, desc=""):
    ct = r.headers.get("Content-Type","")
    print(f"  [{r.status_code}] {desc}  ({len(r.content)} bytes)  {ct[:40]}")
    return r

print(f"\n{'='*60}")
print(f"  XSA Download  |  {BASE}")
print(f"{'='*60}\n")

# ── 1. GET página de login para obtener cookies iniciales + token CSRF ────────
print("── Paso 1: obtener página de login...")
login_pages = [
    "/properties/accounting/usageReport.php?from=Acct_Home",
    "/properties/login.php",
    "/login.php",
    "/",
]
login_html = ""
login_url  = ""
for path in login_pages:
    r = s.get(BASE + path, allow_redirects=True)
    ok(r, path)
    if r.status_code == 200 and len(r.text) > 500:
        login_html = r.text
        login_url  = r.url
        with open("login_page.html", "w", encoding="utf-8", errors="replace") as f:
            f.write(r.text)
        print(f"    → guardado login_page.html, URL final: {login_url}")
        break

# Buscar campos del form de login
forms   = re.findall(r'<form[^>]*action=["\']([^"\']*)["\']', login_html, re.I)
inputs  = re.findall(r'<input[^>]+name=["\']([^"\']+)["\'][^>]*(?:value=["\']([^"\']*)["\'])?', login_html, re.I)
print(f"    Forms: {forms}")
print(f"    Inputs: {inputs[:12]}")

# ── 2. Intentar login con distintos formatos ──────────────────────────────────
print("\n── Paso 2: login...")
REFERER = f"{BASE}/properties/accounting/usageReport.php?from=Acct_Home"

payloads = [
    # Formato típico Xerox CentreWare PHP
    {"_fun_function": "HTTP_Authenticate_Function",
     "NextPage": "/properties/accounting/usageReport.php?from=Acct_Home",
     "curwebpage": "login.php", "returnURL": REFERER,
     "txtUserName": USER, "txtUserPassword": PASSWORD,
     "frmaltlogin": ""},
    {"username": USER, "password": PASSWORD,
     "NextPage": "/properties/accounting/usageReport.php?from=Acct_Home"},
    {"txtUserName": USER, "txtUserPassword": PASSWORD},
    {"user": USER, "pass": PASSWORD},
    {"login": USER, "password": PASSWORD},
]

# Recoger campos hidden del form de login
hidden = {k: v for k, v in inputs if v and k not in ("txtUserName","txtUserPassword","username","password")}
print(f"    Campos hidden detectados: {hidden}")

logueado = False
for i, payload in enumerate(payloads):
    payload.update(hidden)  # añadir tokens hidden
    # Probar la action del form primero, luego rutas comunes
    targets = (forms if forms else []) + [
        "/userpost.html", "/login.php", "/properties/login.php",
        "/properties/userpost.html", "/cgi-bin/login",
    ]
    for target in targets:
        if not target.startswith("http"):
            target = BASE + target
        r = s.post(target, data=payload,
                   headers={"Referer": REFERER},
                   allow_redirects=True)
        ok(r, f"POST payload[{i}] → {target.replace(BASE,'')}")
        # Comprobar si ya estamos dentro (tiene logout link o acceso a accounting)
        if r.status_code == 200 and (
            "logout" in r.text.lower() or
            "sign out" in r.text.lower() or
            "usagereport" in r.url.lower() or
            "download" in r.text.lower()
        ):
            print(f"    ✔ Login exitoso!")
            logueado = True
            break
        if logueado:
            break
    if logueado:
        break

print(f"\n    Cookies activas: {dict(s.cookies)}")

# ── 3. Acceder a la página de informe para establecer contexto ─────────────────
print("\n── Paso 3: navegar a usageReport...")
r = s.get(REFERER, headers={"Referer": BASE + "/"})
ok(r, "usageReport.php")
with open("usage_page.html", "w", encoding="utf-8", errors="replace") as f:
    f.write(r.text)

# ── 4. Generar informe ────────────────────────────────────────────────────────
print("\n── Paso 4: XSA_generate_date.php...")
r = s.get(BASE + "/properties/accounting/XSA_generate_date.php",
          headers={"Referer": REFERER}, allow_redirects=True)
ok(r, "XSA_generate_date.php")
print(f"    Respuesta: {r.text[:200]!r}")

# ── 5. AJAX lastGeneratedDate (como hace el browser) ─────────────────────────
print("\n── Paso 5: aapAjaxHandler lastGeneratedDate...")
ts_ms = int(time.time() * 1000)
r = s.post(BASE + f"/properties/accounting/aapAjaxHandler.php",
           params={"command": "lastGeneratedDate", "ajts": ts_ms},
           headers={"Referer": REFERER, "X-Requested-With": "XMLHttpRequest"},
           allow_redirects=True)
ok(r, "aapAjaxHandler")
print(f"    Respuesta: {r.text[:200]!r}")

# ── 6. Descargar CSV ──────────────────────────────────────────────────────────
print("\n── Paso 6: download_csv.php...")
r = s.get(BASE + "/properties/accounting/download_csv.php",
          headers={"Referer": REFERER}, allow_redirects=True)
ok(r, "download_csv.php")
ct = r.headers.get("Content-Type","")
print(f"    Content-Type: {ct}")
print(f"    Content-Disposition: {r.headers.get('Content-Disposition','')}")

if "csv" in ct.lower() or "octet" in ct.lower() or "download" in ct.lower() or (
        len(r.content) > 100 and not r.text.strip().startswith("<")):
    with open("xsa_report.csv", "wb") as f:
        f.write(r.content)
    print(f"\n  ✔ CSV guardado: xsa_report.csv ({len(r.content)} bytes)")
    print(f"\n  Primeras líneas:\n{r.text[:500]}")
else:
    print(f"\n  ✘ Sigue devolviendo HTML. Guardando como debug.html...")
    with open("debug_download.html", "w", encoding="utf-8", errors="replace") as f:
        f.write(r.text)
    print(f"  Primeras líneas del HTML:\n{r.text[:300]}")
    print(f"\n  Cookies: {dict(s.cookies)}")
