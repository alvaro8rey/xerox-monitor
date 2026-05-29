"""
Descarga CSV XSA Xerox AltaLink C8170.
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
LOGIN    = f"/properties/authentication/login.php?redir={REDIR}"

s = requests.Session()
s.verify  = False
s.timeout = 15
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8",
})

print(f"\n{'='*60}\n  XSA Download  |  {BASE}\n{'='*60}\n")

# ── 1. GET login para obtener CSRFToken ───────────────────────────────────────
print("── Paso 1: GET login...")
r = s.get(BASE + LOGIN, allow_redirects=True)
print(f"  [{r.status_code}] → {r.url}")

csrf = (re.search(r'name=["\']CSRFToken["\'][^>]*value=["\']([^"\']+)["\']', r.text) or
        re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']CSRFToken["\']', r.text))
csrf_token = csrf.group(1) if csrf else ""
print(f"  CSRFToken: {csrf_token[:20]}...")

# ── 2. POST login con campos exactos capturados del navegador ─────────────────
print("\n── Paso 2: POST login...")
payload = {
    "_fun_function":  "HTTP_Authenticate_fn",   # valor exacto del browser
    "NextPage":       "/properties/authentication/luidLogin.php?type=&authStatus=",
    "frmwebUsername": USER,
    "frmwebPassword": PASSWORD,
    "frmaltDomain":   "default",                # valor exacto del browser
    "CSRFToken":      csrf_token,
}
r = s.post(BASE + "/userpost/xerox.set", data=payload,
           headers={"Referer": BASE + LOGIN, "Origin": BASE},
           allow_redirects=True)
print(f"  [{r.status_code}] → {r.url}")
print(f"  Cookies: {dict(s.cookies)}")

autenticado = "authStatus=0" not in r.url and "login.php" not in r.url
print(f"  Login: {'✔ OK' if autenticado else '✘ FALLÓ — ' + r.url}")

# ── 3. Navegar a usageReport para verificar sesión ───────────────────────────
print("\n── Paso 3: verificando sesión...")
r = s.get(BASE + REDIR, headers={"Referer": BASE + "/"}, allow_redirects=True)
print(f"  [{r.status_code}] → {r.url}")
sesion_ok = "login.php" not in r.url
print(f"  Sesión: {'✔ activa' if sesion_ok else '✘ no autenticado'}")

if not sesion_ok:
    print("\n  Login fallido. Revisa usuario/contraseña.")
    exit()

# ── 4. Generar informe ────────────────────────────────────────────────────────
print("\n── Paso 4: generando informe XSA...")
r = s.get(BASE + "/properties/accounting/XSA_generate_date.php",
          headers={"Referer": BASE + REDIR}, allow_redirects=True)
print(f"  [{r.status_code}] XSA_generate_date.php  ({len(r.content):,} bytes)")

# ── 5. Descargar CSV ──────────────────────────────────────────────────────────
print("\n── Paso 5: descargando CSV...")
r = s.get(BASE + "/properties/accounting/download_csv.php",
          headers={"Referer": BASE + REDIR}, allow_redirects=True)
ct = r.headers.get("Content-Type", "")
cd = r.headers.get("Content-Disposition", "")
print(f"  [{r.status_code}] {len(r.content):,} bytes")
print(f"  Content-Type: {ct}")
print(f"  Content-Disposition: {cd}")

es_csv = not r.text.strip().startswith("<") or "csv" in ct or cd
if es_csv and len(r.content) > 50:
    with open("xsa_report.csv", "wb") as f:
        f.write(r.content)
    print(f"\n  ✔ CSV guardado: xsa_report.csv")
    print(f"\n  Primeras líneas:\n{r.text[:600]}")
else:
    print(f"\n  ✘ Devuelve HTML, no CSV.")
    print(f"  Primeras líneas: {r.text[:200]!r}")
