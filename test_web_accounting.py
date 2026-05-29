"""
Descarga CSV XSA Xerox AltaLink C8170.
Uso: python test_web_accounting.py
"""
import requests, re
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

print(f"\n{'='*55}\n  XSA Download  |  {BASE}\n{'='*55}\n")

# ── Login ─────────────────────────────────────────────────────────────────────
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

r = s.get(BASE + REDIR, allow_redirects=True)
if "login.php" in r.url:
    print("✘ Login fallido"); exit()
print(f"✔ Sesión activa\n")

# ── Generar + descargar en una sola llamada siguiendo el redirect 302 ──────────
print("── Descargando CSV (generate → redirect → download)...")
r = s.get(f"{BASE}/properties/accounting/XSA_generate_date.php",
          headers={"Referer": BASE + REDIR},
          allow_redirects=True)   # sigue el 302 → download_csv.php → CSV

ct = r.headers.get("Content-Type", "")
cd = r.headers.get("Content-Disposition", "")
print(f"  [{r.status_code}] URL final: {r.url}")
print(f"  Content-Type: {ct}")
print(f"  Content-Disposition: {cd}")
print(f"  Tamaño: {len(r.content):,} bytes")

es_csv = ("csv" in ct or "octet" in ct or cd or
          (len(r.content) > 200 and not r.text.strip().startswith("<")))

if es_csv:
    with open("xsa_report.csv", "wb") as f:
        f.write(r.content)
    print(f"\n✔ CSV guardado: xsa_report.csv")
    print(f"\nPrimeras líneas:\n{r.text[:600]}")
else:
    print(f"\n✘ No es CSV:\n{r.text[:300]!r}")
