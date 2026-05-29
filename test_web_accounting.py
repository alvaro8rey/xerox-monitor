"""
Descarga automática del CSV XSA de Xerox AltaLink C8170.
Uso: python test_web_accounting.py
Requiere: pip install requests
"""
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

IP       = "10.55.161.248"
USER     = "admin"
PASSWORD = input("Contraseña admin: ").strip()
BASE     = f"https://{IP}"

s = requests.Session()
s.verify   = False
s.auth     = (USER, PASSWORD)
s.timeout  = 10
s.headers.update({"User-Agent": "Mozilla/5.0"})

print(f"\n── Generando informe...")
r1 = s.get(f"{BASE}/properties/accounting/XSA_generate_date.php", allow_redirects=True)
print(f"  [{r1.status_code}] XSA_generate_date.php")

print(f"── Descargando CSV...")
r2 = s.get(f"{BASE}/properties/accounting/download_csv.php", allow_redirects=True)
print(f"  [{r2.status_code}] download_csv.php  ({len(r2.content)} bytes)")

if r2.status_code == 200 and len(r2.content) > 100:
    with open("xsa_test.csv", "wb") as f:
        f.write(r2.content)
    print(f"\n✔  CSV guardado en xsa_test.csv")
    print(f"\nPrimeras líneas:")
    print(r2.text[:600])
else:
    print(f"\n✘  Error: {r2.text[:200]}")
