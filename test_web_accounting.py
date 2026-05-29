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
ACCT     = f"{BASE}/properties/accounting"

s = requests.Session()
s.verify  = False
s.timeout = 15
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8",
})

def show(r, desc):
    ct = r.headers.get("Content-Type","")[:40]
    cd = r.headers.get("Content-Disposition","")
    print(f"  [{r.status_code}] {desc}  ({len(r.content):,}b)  {ct}")
    if cd: print(f"           Disposition: {cd}")
    return r

print(f"\n{'='*60}\n  XSA Download  |  {BASE}\n{'='*60}\n")

# ── 1. Login ──────────────────────────────────────────────────────────────────
print("── Login...")
r = s.get(BASE + LOGIN, allow_redirects=True)
csrf = (re.search(r'name=["\']CSRFToken["\'][^>]*value=["\']([^"\']+)["\']', r.text) or
        re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']CSRFToken["\']', r.text))
csrf_token = csrf.group(1) if csrf else ""

s.post(BASE + "/userpost/xerox.set", allow_redirects=True,
       headers={"Referer": BASE + LOGIN, "Origin": BASE},
       data={"_fun_function": "HTTP_Authenticate_fn",
             "NextPage": "/properties/authentication/luidLogin.php?type=&authStatus=",
             "frmwebUsername": USER, "frmwebPassword": PASSWORD,
             "frmaltDomain": "default", "CSRFToken": csrf_token})

# Verificar sesión
r = s.get(BASE + REDIR, allow_redirects=True)
if "login.php" in r.url:
    print("  ✘ Login fallido"); exit()
print(f"  ✔ Sesión activa → {r.url}")

# ── 2. Trigger generate sin seguir redirect JS ────────────────────────────────
print("\n── Generando informe (sin seguir redirect)...")
r = s.get(f"{ACCT}/XSA_generate_date.php",
          headers={"Referer": BASE + REDIR},
          allow_redirects=False)   # ← clave: no seguir el redirect JS
show(r, "XSA_generate_date.php")
print(f"  Location: {r.headers.get('Location','(ninguno)')}")
print(f"  Body: {r.text[:150]!r}")

# ── 3. AJAX check (como hace el browser) ─────────────────────────────────────
print("\n── AJAX lastGeneratedDate...")
ts = int(time.time() * 1000)
r = s.post(f"{ACCT}/aapAjaxHandler.php",
           params={"command": "lastGeneratedDate", "ajts": ts},
           headers={"Referer": BASE + REDIR,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "text/html, */*; q=0.01"},
           allow_redirects=False)
show(r, "aapAjaxHandler.php")
print(f"  Respuesta: {r.text[:200]!r}")

# ── 4. Intentar download con allow_redirects=False ────────────────────────────
print("\n── Descargando CSV (sin seguir redirect)...")
r = s.get(f"{ACCT}/download_csv.php",
          headers={"Referer": BASE + REDIR},
          allow_redirects=False)
show(r, "download_csv.php (no redirect)")
print(f"  Location: {r.headers.get('Location','(ninguno)')}")

# Si hay redirect 302, seguirlo manualmente
if r.status_code == 302:
    loc = r.headers.get("Location","")
    print(f"\n── Siguiendo redirect manual → {loc}...")
    if not loc.startswith("http"):
        loc = BASE + loc
    r = s.get(loc, headers={"Referer": BASE + REDIR}, allow_redirects=False)
    show(r, "redirect destino")

# ── 5. Evaluar resultado y guardar ────────────────────────────────────────────
ct = r.headers.get("Content-Type","")
cd = r.headers.get("Content-Disposition","")
es_csv = ("csv" in ct or "octet" in ct or cd or
          (len(r.content) > 200 and not r.text.strip().startswith("<")))

if es_csv:
    with open("xsa_report.csv","wb") as f: f.write(r.content)
    print(f"\n  ✔ CSV guardado ({len(r.content):,} bytes)")
    print(f"\n  Primeras líneas:\n{r.text[:500]}")
else:
    print(f"\n  ✘ No es CSV. Body: {r.text[:300]!r}")
    # Último intento: download con allow_redirects=True
    print("\n── Último intento: download con redirect...")
    r = s.get(f"{ACCT}/download_csv.php",
              headers={"Referer": BASE + REDIR},
              allow_redirects=True)
    show(r, "download_csv.php (con redirect)")
    if not r.text.strip().startswith("<") and len(r.content) > 200:
        with open("xsa_report.csv","wb") as f: f.write(r.content)
        print(f"  ✔ CSV guardado ({len(r.content):,} bytes)\n{r.text[:400]}")
    else:
        print(f"  Body: {r.text[:200]!r}")
