"""
Test login HTTP Xerox AltaLink y descarga de informe XSA.
Uso: python test_web_accounting.py
Requiere: pip install requests
"""
import requests, sys, os, json
from urllib.parse import urljoin
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

IP       = "10.55.161.248"
BASE     = f"http://{IP}"
USER     = "admin"
PASSWORD = input("Contraseña admin de la impresora: ").strip()

s = requests.Session()
s.verify = False
s.timeout = 10
s.headers.update({"User-Agent": "Mozilla/5.0"})

def intentar(url, method="GET", data=None, desc=""):
    try:
        if method == "POST":
            r = s.post(url, data=data, allow_redirects=True)
        else:
            r = s.get(url, allow_redirects=True)
        print(f"  [{r.status_code}] {desc or url[:80]}")
        return r
    except Exception as e:
        print(f"  [ERR] {desc}: {e}")
        return None

print(f"\n{'='*60}")
print(f"  Xerox AltaLink C8170 - Test login web")
print(f"  IP: {IP}")
print(f"{'='*60}\n")

# ── 1. Probar endpoints de login conocidos en Xerox AltaLink ─────────────────
print("── Probando login...")

# Método 1: form estándar Xerox CentreWare
login_urls = [
    ("/login",              {"_fun_function": "HTTP_Authenticate_Function",
                             "NextPage":      "/index.html",
                             "curwebpage":    "login.html",
                             "returnURL":     "/index.html",
                             "txtUserName":   USER,
                             "txtUserPassword": PASSWORD}),
    ("/userpost.html",     {"username": USER, "password": PASSWORD}),
    ("/cgi-bin/login",     {"user": USER, "passwd": PASSWORD}),
]

logueado = False
for path, payload in login_urls:
    url = BASE + path
    r = intentar(url, "POST", payload, f"POST {path}")
    if r and r.status_code in (200, 302) and "logout" in r.text.lower():
        print(f"  ✔  Login OK vía {path}")
        logueado = True
        break

if not logueado:
    # Intentar GET de la home a ver qué pide
    r = intentar(BASE + "/index.html", desc="GET /index.html")
    if r:
        # Guardar HTML para inspección
        with open("xerox_home.html", "w", encoding="utf-8", errors="replace") as f:
            f.write(r.text)
        print(f"  HTML de home guardado en xerox_home.html ({len(r.text)} bytes)")
        # Buscar el action del form de login
        import re
        forms = re.findall(r'<form[^>]*action=["\']([^"\']+)["\']', r.text, re.I)
        inputs = re.findall(r'<input[^>]*name=["\']([^"\']+)["\']', r.text, re.I)
        print(f"  Forms encontrados: {forms}")
        print(f"  Inputs: {inputs[:10]}")

# ── 2. Buscar URLs de contabilidad XSA ───────────────────────────────────────
print("\n── Buscando URLs de informe de contabilidad...")

candidates = [
    "/Properties/Accounting/XeroxStandardAccounting",
    "/Properties/Accounting/",
    "/Accounting/",
    "/accountingtracking",
    "/Properties/Accounting/Report",
    "/Properties/Accounting/UsageReport",
    "/Properties/Accounting/XSAReport",
    "/Properties/Accounting/XeroxStandardAccountingReport",
    "/accounting/report",
    "/report/accounting",
    "/cgi-bin/accounting",
    "/Properties/Accounting/XeroxStandardAccountingUsageReport",
    "/Properties/Accounting/JobLog",
    "/status/joblog",
]

encontradas = []
for path in candidates:
    r = intentar(BASE + path, desc=f"GET {path}")
    if r and r.status_code == 200 and len(r.text) > 500:
        encontradas.append((path, len(r.text), r.text[:200]))

if encontradas:
    print("\n  Páginas que responden:")
    for path, size, preview in encontradas:
        print(f"  ✔  {path}  ({size} bytes)")
        print(f"     {preview[:100]!r}")
        fname = path.replace("/","_").strip("_") + ".html"
        with open(fname, "w", encoding="utf-8", errors="replace") as f:
            f.write(preview)

# ── 3. Si hay sesión, buscar links a CSV en las páginas encontradas ──────────
print("\n── Buscando links CSV/descarga...")
import re

for path, size, _ in encontradas:
    r = s.get(BASE + path)
    csv_links = re.findall(r'href=["\']([^"\']*(?:csv|report|download|export)[^"\']*)["\']',
                            r.text, re.I)
    if csv_links:
        print(f"  En {path}:")
        for link in csv_links:
            full = urljoin(BASE + path, link)
            print(f"    → {full}")
            # Intentar descargar
            rd = s.get(full)
            if rd.status_code == 200 and len(rd.content) > 100:
                fname = f"accounting_{link.split('/')[-1] or 'report'}"
                if not fname.endswith(".csv"):
                    fname += ".csv"
                with open(fname, "wb") as f:
                    f.write(rd.content)
                print(f"    ✔  Descargado: {fname} ({len(rd.content)} bytes)")
                print(f"    Preview: {rd.text[:300]!r}")

# ── 4. Intentar descargar directamente conociendo el patrón Xerox ────────────
print("\n── Intento descarga directa de CSV XSA...")
# Algunos firmware exponen el CSV directamente
csv_directs = [
    "/Properties/Accounting/XeroxStandardAccountingReport.csv",
    "/Accounting/XSAReport.csv",
    "/Properties/Accounting/report.csv",
    "/cgi-bin/get_accounting_report",
]
for path in csv_directs:
    r = intentar(BASE + path, desc=f"CSV directo {path}")
    if r and r.status_code == 200 and len(r.content) > 50:
        fname = f"xsa_report_{path.split('/')[-1]}"
        with open(fname, "wb") as f:
            f.write(r.content)
        print(f"  ✔  CSV descargado: {fname}")
        print(f"  Preview: {r.text[:400]}")

print(f"\n{'='*60}\n")
