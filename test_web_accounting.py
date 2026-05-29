"""
Descubrimiento de la interfaz web Xerox AltaLink C8170.
Uso: python test_web_accounting.py
Requiere: pip install requests
"""
import requests, re, os, json
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

IP       = "10.55.161.248"
USER     = "admin"
PASSWORD = input("Contraseña admin: ").strip()

BASES = [
    f"http://{IP}",
    f"https://{IP}",
    f"http://{IP}:53303",
    f"https://{IP}:443",
]

s = requests.Session()
s.verify = False
s.timeout = 8
s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/json,*/*"})

def get(url, **kw):
    try:
        r = s.get(url, allow_redirects=True, **kw)
        return r
    except Exception as e:
        return None

def post(url, **kw):
    try:
        r = s.post(url, allow_redirects=True, **kw)
        return r
    except Exception as e:
        return None

print(f"\n{'='*65}")
print(f"  Descubrimiento interfaz web  |  IP: {IP}")
print(f"{'='*65}\n")

# ── 1. Encontrar base URL activa ─────────────────────────────────────────────
print("── Buscando puertos activos...")
base_activa = None
for base in BASES:
    r = get(base + "/", timeout=4)
    if r is not None:
        print(f"  [{r.status_code}] {base}/  →  final: {r.url}")
        if r.status_code < 404:
            base_activa = base
            html_root = r.text
            with open("xerox_root.html", "w", encoding="utf-8", errors="replace") as f:
                f.write(r.text)
            print(f"    Guardado xerox_root.html ({len(r.text)} bytes)")
            # Mostrar links y scripts
            links  = re.findall(r'href=["\']([^"\']+)["\']', r.text)[:15]
            scripts= re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', r.text)[:5]
            apis   = re.findall(r'["\']/(api|webapi|rest|cgi-bin|servlet)[^"\']*["\']', r.text)[:10]
            if links:   print(f"    Links: {links}")
            if scripts: print(f"    Scripts: {scripts}")
            if apis:    print(f"    APIs detectadas: {apis}")
            break
    else:
        print(f"  [---] {base}/ sin respuesta")

if not base_activa:
    print("\n  No se encontró interfaz web activa. Verifica que HTTP esté habilitado.")
    exit()

base = base_activa
print()

# ── 2. Descubrir rutas Xerox AltaLink ───────────────────────────────────────
print("── Probando rutas conocidas de AltaLink C8170...")

RUTAS = [
    # Raíz y dashboard
    "/", "/ui", "/ui/", "/app", "/web",
    # API REST moderna Xerox
    "/webapi/","/webapi/session","/webapi/v1/",
    "/api/", "/api/v1/", "/api/session",
    "/rest/", "/rest/v1/",
    # CentreWare Web clásico
    "/cwis/", "/CWIS/",
    # Accounting específico
    "/accounting", "/xsa", "/xsa/report",
    "/webapi/accounting", "/webapi/xsa",
    "/api/accounting", "/api/report",
    # Servicios web internos
    "/webservices/", "/services/",
    # Páginas de login conocidas en AltaLink
    "/login.php", "/cgi-bin/weblogin",
    "/ui/#/login", "/ui/login",
    # Configuración y propiedades
    "/properties", "/configuration",
    "/webapi/properties/accounting",
    # Jobs
    "/webapi/jobs", "/api/jobs",
    "/jobs", "/joblog",
]

activas = []
for ruta in RUTAS:
    r = get(base + ruta, timeout=4)
    if r is not None and r.status_code not in (404, 400):
        content_type = r.headers.get("Content-Type","")
        size = len(r.content)
        print(f"  [{r.status_code}] {ruta:<45} ({size:>7} bytes)  {content_type[:40]}")
        if size > 200:
            activas.append((ruta, r))
    # Si es JSON interesante, mostrarlo
        if "json" in content_type and size < 2000:
            try: print(f"           JSON: {r.json()}")
            except: pass

# ── 3. Intentar login con credenciales ──────────────────────────────────────
print("\n── Intentando login...")

# Estrategia 1: Basic Auth
r = get(base + "/", auth=(USER, PASSWORD))
if r and r.status_code == 200:
    print(f"  ✔ Basic Auth funciona")

# Estrategia 2: JSON API login
for login_path in ["/webapi/session", "/api/session", "/api/login",
                   "/webapi/login", "/rest/session"]:
    r = post(base + login_path,
             json={"username": USER, "password": PASSWORD},
             headers={"Content-Type": "application/json"})
    if r and r.status_code in (200, 201):
        print(f"  ✔ Login JSON en {login_path}: {r.text[:200]}")
        break
    elif r and r.status_code not in (404, 405):
        print(f"  [{r.status_code}] {login_path}: {r.text[:100]}")

# Estrategia 3: Form login
for login_path in ["/login", "/cgi-bin/login", "/ui/login"]:
    for payload in [
        {"username": USER, "password": PASSWORD},
        {"txtUserName": USER, "txtUserPassword": PASSWORD,
         "_fun_function": "HTTP_Authenticate_Function"},
        {"user": USER, "pass": PASSWORD},
    ]:
        r = post(base + login_path, data=payload)
        if r and r.status_code in (200, 302) and r.status_code != 404:
            print(f"  [{r.status_code}] Form login {login_path}")
            if "logout" in r.text.lower() or "welcome" in r.text.lower():
                print(f"  ✔ Login exitoso!")
            break

# ── 4. Si hay rutas activas, buscar en ellas links a CSV/informes ────────────
if activas:
    print(f"\n── Analizando {len(activas)} rutas activas en busca de informes...")
    for ruta, r in activas:
        csv_links = re.findall(
            r'["\']([^"\']*(?:csv|report|download|export|accounting|xsa|usage)[^"\']*)["\']',
            r.text, re.I)
        if csv_links:
            print(f"\n  En {ruta}:")
            for link in set(csv_links[:10]):
                print(f"    → {link}")

# ── 5. Guardar resumen ───────────────────────────────────────────────────────
print(f"\n{'='*65}")
print("  Pega la salida completa de este script para analizar.")
print(f"{'='*65}\n")
