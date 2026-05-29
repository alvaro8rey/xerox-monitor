"""
Descarga CSV XSA Xerox AltaLink C8170 — login con CSRFToken correcto.
Uso: python test_web_accounting.py
"""
import requests, re, time
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

IP       = "10.55.161.248"
USER     = "admin"
PASSWORD = input("Contraseña admin: ").strip()
BASE     = f"https://{IP}"
REDIR    = "/properties/accounting/usageReport.php?from=Acct_Home"

s = requests.Session()
s.verify  = False
s.timeout = 15
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
})

def show(r, desc):
    ct = r.headers.get("Content-Type","")[:35]
    print(f"  [{r.status_code}] {desc}  ({len(r.content):,} bytes)  {ct}")
    return r

print(f"\n{'='*60}\n  XSA Download  |  {BASE}\n{'='*60}\n")

# ── 1. GET página de login para obtener CSRFToken ─────────────────────────────
print("── Paso 1: obtener CSRFToken de la página de login...")
LOGIN_PAGE = f"/properties/authentication/login.php?redir={REDIR}"
r = s.get(BASE + LOGIN_PAGE, allow_redirects=True)
show(r, "GET login.php")
print(f"    URL final: {r.url}")
print(f"    Cookies: {dict(s.cookies)}")

# Extraer CSRFToken del HTML
csrf = re.search(r'name=["\']CSRFToken["\'][^>]*value=["\']([^"\']+)["\']', r.text)
if not csrf:
    csrf = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']CSRFToken["\']', r.text)
csrf_token = csrf.group(1) if csrf else ""
print(f"    CSRFToken: {csrf_token!r}")

# Extraer otros campos hidden
nextpage = re.search(r'name=["\']NextPage["\'][^>]*value=["\']([^"\']*)["\']', r.text)
nextpage_val = nextpage.group(1) if nextpage else REDIR

# ── 2. POST login con campos correctos ────────────────────────────────────────
print("\n── Paso 2: POST login a /userpost/xerox.set...")
payload = {
    "fred":           "",           # honeypot Xerox, debe ir vacío
    "_fun_function":  "HTTP_Authenticate_Function",
    "NextPage":       nextpage_val or REDIR,
    "frmwebUsername": USER,
    "frmwebPassword": PASSWORD,
    "frmaltDomain":   "",
    "CSRFToken":      csrf_token,
}
print(f"    Payload: { {k: v for k,v in payload.items() if k != 'frmwebPassword'} }")

r = s.post(BASE + "/userpost/xerox.set", data=payload,
           headers={"Referer": BASE + LOGIN_PAGE},
           allow_redirects=True)
show(r, "POST /userpost/xerox.set")
print(f"    URL final: {r.url}")
print(f"    Cookies tras login: {dict(s.cookies)}")
print(f"    Respuesta (primeros 300 chars): {r.text[:300]!r}")

# ── 3. Verificar sesión accediendo a usageReport ──────────────────────────────
print("\n── Paso 3: verificar sesión en usageReport.php...")
r = s.get(BASE + REDIR, headers={"Referer": BASE + "/"}, allow_redirects=True)
show(r, "GET usageReport.php")
print(f"    URL final: {r.url}")
autenticado = "login.php" not in r.url and r.status_code == 200
print(f"    ¿Autenticado? {'✔ SÍ' if autenticado else '✘ NO (redirige a login)'}")
if not autenticado:
    print(f"    Primeros 200 chars: {r.text[:200]!r}")

# ── 4. Generar fecha del informe ───────────────────────────────────────────────
print("\n── Paso 4: XSA_generate_date.php...")
r = s.get(BASE + "/properties/accounting/XSA_generate_date.php",
          headers={"Referer": BASE + REDIR}, allow_redirects=True)
show(r, "XSA_generate_date.php")
is_csv_response = not r.text.strip().startswith("<")
print(f"    Respuesta: {r.text[:150]!r}")

# ── 5. Descargar CSV ───────────────────────────────────────────────────────────
print("\n── Paso 5: download_csv.php...")
r = s.get(BASE + "/properties/accounting/download_csv.php",
          headers={"Referer": BASE + REDIR}, allow_redirects=True)
show(r, "download_csv.php")
ct = r.headers.get("Content-Type","")
cd = r.headers.get("Content-Disposition","")
print(f"    Content-Type: {ct}")
print(f"    Content-Disposition: {cd}")

es_csv = ("csv" in ct.lower() or "octet" in ct.lower() or
          cd or not r.text.strip().startswith("<"))

if es_csv and len(r.content) > 100:
    with open("xsa_report.csv", "wb") as f:
        f.write(r.content)
    print(f"\n  ✔ CSV guardado: xsa_report.csv ({len(r.content):,} bytes)")
    print(f"\n  Primeras líneas:\n{r.text[:600]}")
else:
    with open("debug_step5.html", "w", encoding="utf-8", errors="replace") as f:
        f.write(r.text)
    print(f"\n  ✘ Sigue siendo HTML. Guardado debug_step5.html")

    # ── Intentar variantes de la URL de descarga ──────────────────────────────
    print("\n── Probando variantes de URL de descarga...")
    for url in [
        "/properties/accounting/download_csv.php?type=xsa",
        "/properties/accounting/download_csv.php?report=xsa",
        "/properties/accounting/XSAreport.csv",
        "/properties/accounting/getReport.php",
        "/properties/accounting/exportReport.php",
    ]:
        r2 = s.get(BASE + url, headers={"Referer": BASE + REDIR})
        show(r2, url)
        if r2.status_code == 200 and not r2.text.strip().startswith("<"):
            with open("xsa_report.csv", "wb") as f:
                f.write(r2.content)
            print(f"  ✔ CSV en {url}!")
            print(r2.text[:400])
            break

print(f"\n{'='*60}\n")
