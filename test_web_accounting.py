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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
})

print(f"\n{'='*55}\n  XSA Download  |  {BASE}\n{'='*55}\n")

# ── 1. Login ──────────────────────────────────────────────────────────────────
r = s.get(BASE + LOGIN, allow_redirects=True)
csrf = (re.search(r'name=["\']CSRFToken["\'][^>]*value=["\']([^"\']+)["\']', r.text) or
        re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']CSRFToken["\']', r.text))
s.post(BASE + "/userpost/xerox.set", allow_redirects=True,
       headers={"Referer": BASE + LOGIN, "Origin": BASE},
       data={"_fun_function": "HTTP_Authenticate_fn",
             "NextPage": "/properties/authentication/luidLogin.php?type=&authStatus=",
             "frmwebUsername": USER, "frmwebPassword": PASSWORD,
             "frmaltDomain": "default",
             "CSRFToken": csrf.group(1) if csrf else ""})
print(f"  Cookies tras login: {dict(s.cookies)}")

# ── 2. Simular navegación completa como el browser ────────────────────────────
# El browser establece cookies de navegación al cargar cada sección
print("\n── Simulando navegación al panel de contabilidad...")

# Cargar página principal (establece cookies de menú)
s.get(BASE + "/properties/dataManagement/autoConfiguration.php",
      headers={"Referer": BASE + "/"})
print(f"  Cookies tras home: {dict(s.cookies)}")

# Establecer manualmente las cookies de navegación que vimos en el browser
s.cookies.set("scnMboxSelected",  "n1",  domain=IP)
s.cookies.set("scnMboxNumNodes",  "8",   domain=IP)
s.cookies.set("propSelected",     "n2",  domain=IP)
s.cookies.set("propHierarchy",    "00000001010000000000000000000000", domain=IP)

# Cargar la página de contabilidad (igual que hace el browser)
r = s.get(BASE + REDIR, allow_redirects=True,
          headers={"Referer": BASE + "/properties/dataManagement/autoConfiguration.php"})
if "login.php" in r.url:
    print("  ✘ No autenticado"); exit()
print(f"  ✔ En página de contabilidad: {r.url}")
print(f"  Cookies completas: {dict(s.cookies)}")

# ── 3. POST a xerox.set para GENERAR el fichero CSV (como hace el browser) ────
import time as _time
_ts = int(_time.time() * 1000)
print(f"\n── Paso 0: POST xerox.set para disparar generación del CSV...")
# Obtener CSRF fresco desde la página de contabilidad
csrf2 = (re.search(r'name=["\']CSRFToken["\'][^>]*value=["\']([^"\']+)["\']', r.text) or
         re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']CSRFToken["\']', r.text))
csrf2_val = csrf2.group(1) if csrf2 else ""
print(f"  CSRF para generate: {csrf2_val!r}")

rp = s.post(f"{BASE}/userpost/xerox.set?ajts{_ts}",
            headers={
                "Referer":           BASE + REDIR,
                "Origin":            BASE,
                "X-Requested-With":  "XMLHttpRequest",
                "Accept":            "application/json, text/javascript, */*; q=0.01",
                "Content-Type":      "application/x-www-form-urlencoded; charset=UTF-8",
            },
            data={
                "_fun_function":  "XSA_Generate_fn",
                "CSRFToken":      csrf2_val,
            })
print(f"  [{rp.status_code}] Content-Type: {rp.headers.get('Content-Type','')}")
print(f"  Body: {rp.text[:300]!r}")

time.sleep(0.5)  # esperar a que el servidor genere el fichero

# ── 4. Paso generate: NO seguir redirect, capturar Location exacta ───────────
print("\n── Paso 1: XSA_generate_date.php (sin seguir redirect)...")
rg = s.get(f"{BASE}/properties/accounting/XSA_generate_date.php",
           allow_redirects=False,
           headers={
               "Referer":        BASE + REDIR,
               "Accept":         "text/html,application/xhtml+xml,*/*;q=0.8",
               "Sec-Fetch-Dest": "document",
               "Sec-Fetch-Mode": "navigate",
               "Sec-Fetch-Site": "same-origin",
               "Sec-Fetch-User": "?1",
           })
print(f"  [{rg.status_code}] Location: {rg.headers.get('Location','(ninguna)')}")
print(f"  Content-Type: {rg.headers.get('Content-Type','')}")
print(f"  Cookies tras generate: {dict(s.cookies)}")
print(f"  Body ({len(rg.content)}b): {rg.text[:300]!r}")

# Si ya devuelve el CSV aquí mismo (200 + CSV)
if rg.status_code == 200 and len(rg.content) > 200 and not rg.text.strip().startswith("<"):
    with open("xsa_report.csv", "wb") as f: f.write(rg.content)
    print(f"\n  ✔ CSV en generate! Guardado: xsa_report.csv")
    print(rg.text[:600])
    exit()

# ── 4. Paso download: seguir la Location manualmente ─────────────────────────
loc = rg.headers.get("Location", "")
if not loc:
    print("\n  ✘ Sin Location — probando download_csv.php directamente...")
    loc = "/properties/accounting/download_csv.php"

# La Location puede ser relativa o absoluta
download_url = loc if loc.startswith("http") else BASE + loc
print(f"\n── Paso 2: GET {download_url}")

time.sleep(0.3)

r = s.get(download_url,
          allow_redirects=False,
          headers={
              "Referer":        BASE + REDIR,
              "Accept":         "text/csv,application/octet-stream,*/*;q=0.8",
              "Sec-Fetch-Dest": "document",
              "Sec-Fetch-Mode": "navigate",
              "Sec-Fetch-Site": "same-origin",
          })
print(f"  [{r.status_code}] URL: {r.url}")
print(f"  Content-Type: {r.headers.get('Content-Type','')}")
print(f"  Content-Disposition: {r.headers.get('Content-Disposition','')}")
print(f"  Location: {r.headers.get('Location','')}")
print(f"  Tamaño: {len(r.content):,} bytes")
print(f"  Body[:200]: {r.text[:200]!r}")

# Si hay otro redirect
if r.status_code in (301, 302, 303):
    loc2 = r.headers.get("Location", "")
    download_url2 = loc2 if loc2.startswith("http") else BASE + loc2
    print(f"\n── Paso 3: Otro redirect → {download_url2}")
    r = s.get(download_url2, allow_redirects=False,
              headers={"Referer": BASE + REDIR,
                       "Accept": "text/csv,application/octet-stream,*/*;q=0.8"})
    print(f"  [{r.status_code}] Content-Type: {r.headers.get('Content-Type','')}")
    print(f"  Tamaño: {len(r.content):,} bytes")
    print(f"  Body[:200]: {r.text[:200]!r}")

ct = r.headers.get("Content-Type", "")
cd = r.headers.get("Content-Disposition", "")
es_csv = ("csv" in ct or "octet" in ct or cd or
          (len(r.content) > 200 and not r.text.strip().startswith("<")))

if es_csv:
    with open("xsa_report.csv", "wb") as f:
        f.write(r.content)
    print(f"\n  ✔ CSV guardado: xsa_report.csv")
    print(f"\n  Primeras líneas:\n{r.text[:600]}")
else:
    print(f"\n  ✘ No es CSV.")

    # ── Último recurso: POST a download_csv.php ────────────────────────────────
    print("\n── Probando POST a download_csv.php...")
    r3 = s.post(f"{BASE}/properties/accounting/download_csv.php",
                allow_redirects=False,
                headers={"Referer": BASE + REDIR},
                data={})
    print(f"  [{r3.status_code}] {r3.headers.get('Content-Type','')} {len(r3.content)}b")
    print(f"  Body: {r3.text[:300]!r}")
