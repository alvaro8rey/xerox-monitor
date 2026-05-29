"""
Debug del formulario de login Xerox AltaLink C8170.
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
    "Accept-Language": "es-ES,es;q=0.9",
})

print(f"\n{'='*60}\n  Debug login  |  {BASE}\n{'='*60}\n")

# ── 1. GET login page ─────────────────────────────────────────────────────────
r = s.get(BASE + LOGIN, allow_redirects=True)
print(f"[{r.status_code}] GET login.php  → {r.url}")

# Extraer TODOS los inputs del form
all_inputs = re.findall(
    r'<input([^>]*)>', r.text, re.I | re.S)
print("\n── Todos los <input> del formulario:")
form_data = {}
for inp in all_inputs:
    name  = re.search(r'name=["\']([^"\']*)["\']',  inp, re.I)
    value = re.search(r'value=["\']([^"\']*)["\']', inp, re.I)
    type_ = re.search(r'type=["\']([^"\']*)["\']',  inp, re.I)
    if name:
        n = name.group(1)
        v = value.group(1) if value else ""
        t = type_.group(1) if type_ else "text"
        print(f"  name={n!r:<30} type={t:<10} value={v[:60]!r}")
        form_data[n] = v

# Extraer action del form
form_action = re.search(r'<form[^>]*action=["\']([^"\']*)["\']', r.text, re.I)
print(f"\n── Form action: {form_action.group(1) if form_action else 'NO ENCONTRADO'}")

# ── 2. Construir payload completo con todos los campos ────────────────────────
# Sobreescribir los campos de credenciales
form_data["frmwebUsername"] = USER
form_data["frmwebPassword"] = PASSWORD
# Forzar NextPage correcto
form_data["NextPage"]       = REDIR

print(f"\n── Payload completo a enviar:")
for k, v in form_data.items():
    val_display = v[:80] if k != "frmwebPassword" else "***"
    print(f"  {k:<30} = {val_display!r}")

# ── 3. POST ───────────────────────────────────────────────────────────────────
action = form_action.group(1) if form_action else "/userpost/xerox.set"
if not action.startswith("http"):
    action = BASE + action

print(f"\n── POST → {action}")
r2 = s.post(action, data=form_data,
            headers={"Referer": BASE + LOGIN,
                     "Origin":  BASE},
            allow_redirects=True)
print(f"[{r2.status_code}] URL final: {r2.url}")
print(f"Cookies: {dict(s.cookies)}")
print(f"Respuesta completa ({len(r2.text)} bytes):\n{r2.text[:500]!r}")

# ── 4. Verificar sesión ───────────────────────────────────────────────────────
print(f"\n── Verificando sesión...")
r3 = s.get(BASE + REDIR, headers={"Referer": BASE + "/"})
print(f"[{r3.status_code}] → {r3.url}")
if "login.php" not in r3.url:
    print("✔  AUTENTICADO — intentando descargar CSV...")
    s.get(BASE + "/properties/accounting/XSA_generate_date.php",
          headers={"Referer": BASE + REDIR})
    r4 = s.get(BASE + "/properties/accounting/download_csv.php",
               headers={"Referer": BASE + REDIR})
    print(f"[{r4.status_code}] download_csv — {r4.headers.get('Content-Type','')} — {len(r4.content)} bytes")
    if not r4.text.strip().startswith("<"):
        with open("xsa_report.csv","wb") as f: f.write(r4.content)
        print(f"✔  CSV guardado: {r4.text[:400]}")
    else:
        print(f"Sigue siendo HTML: {r4.text[:200]!r}")
else:
    print("✘  Sigue sin autenticar.")
    print("\n>>> ACCIÓN NECESARIA: abre F12 → Red en el navegador, inicia")
    print(">>> sesión manualmente y busca POST /userpost/xerox.set.")
    print(">>> Copia todos los campos del payload y compártelos.")
