"""
Test Xerox Standard Accounting (XSA) - contadores por usuario vía SNMP.
Ejecutar con contabilidad estándar Xerox activada en la impresora.
Uso: python test_xsa_usuarios.py
"""
import asyncio, datetime
from pysnmp.hlapi.v1arch.asyncio import (
    SnmpDispatcher, CommunityData, UdpTransportTarget,
    ObjectType, ObjectIdentity, get_cmd, next_cmd
)

IP        = "10.55.161.248"
COMUNIDAD = "public"
TIMEOUT   = 2.0
OUT_FILE  = f"xsa_walk_{IP.replace('.','_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

# Ramas XSA conocidas de la MIB Xerox propietaria
# Con XSA activo estos OIDs deberían devolver datos
RAMAS_XSA = [
    # Contabilidad estándar Xerox - usuarios y contadores
    "1.3.6.1.4.1.253.8.53.14",    # Per-user counters
    "1.3.6.1.4.1.253.8.53.15",    # User names
    "1.3.6.1.4.1.253.8.53.16",    # XSA additional
    "1.3.6.1.4.1.253.8.53.17",    # XSA additional
    "1.3.6.1.4.1.253.8.53.18",    # XSA additional
    "1.3.6.1.4.1.253.8.53.19",    # XSA additional
    "1.3.6.1.4.1.253.8.53.20",
    # Rama de contabilidad general
    "1.3.6.1.4.1.253.8.53.13",
    # Otras ramas XSA reportadas en foros
    "1.3.6.1.4.1.253.8.62.1.35",  # Accounting config
    "1.3.6.1.4.1.253.8.62.1.36",
    "1.3.6.1.4.1.253.8.62.1.37",
    "1.3.6.1.4.1.253.8.62.1.38",
    # Job log (ya confirmado activo)
    "1.3.6.1.4.1.253.8.51.5",
]

async def walk(dispatcher, transport, base_oid, max_oids=2000):
    """Walk GETNEXT. Devuelve lista de (oid, tipo, valor)."""
    resultados = []
    current = base_oid
    seen = set()

    for _ in range(max_oids):
        try:
            errI, errS, _, vb = await next_cmd(
                dispatcher, CommunityData(COMUNIDAD), transport,
                ObjectType(ObjectIdentity(current))
            )
        except Exception as e:
            break

        if errI or errS or not vb:
            break

        oid_obj, val = vb[0]
        oid_str = str(oid_obj)

        if not oid_str.startswith(base_oid) or oid_str in seen:
            break
        seen.add(oid_str)

        tipo  = type(val).__name__
        valor = str(val)
        if "No Such" in valor or "End of" in valor:
            break

        resultados.append((oid_str, tipo, valor))
        current = oid_str

    return resultados

async def main():
    lineas = []
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lineas.append("=" * 70)
    lineas.append(f"  XSA Walk  |  IP: {IP}  |  {ts}")
    lineas.append("=" * 70)

    print(f"\n{'='*70}")
    print(f"  Xerox Standard Accounting - Walk SNMP")
    print(f"  IP: {IP}  |  Salida → {OUT_FILE}")
    print(f"{'='*70}\n")

    dispatcher = SnmpDispatcher()
    try:
        transport = await UdpTransportTarget.create(
            (IP, 161), timeout=TIMEOUT, retries=1)
    except Exception as e:
        print(f"[ERROR] No se pudo conectar: {e}")
        return

    total = 0
    todos_resultados = {}  # base_oid → lista de (oid, tipo, valor)

    for base in RAMAS_XSA:
        print(f"  Walking {base} ...", end=" ", flush=True)
        res = await walk(dispatcher, transport, base)
        print(f"{len(res)} OIDs")

        lineas.append(f"\n{'─'*70}")
        lineas.append(f"  {base}  →  {len(res)} OIDs")
        lineas.append(f"{'─'*70}")

        for oid, tipo, valor in res:
            lineas.append(f"  {oid}")
            lineas.append(f"    [{tipo}] {valor!r}")

        todos_resultados[base] = res
        total += len(res)

    # ── Intentar interpretar estructura de usuarios ──────────────────────────
    # Buscar en todas las ramas OIDs que contengan strings no vacíos
    # que parezcan nombres de usuario
    lineas.append(f"\n{'='*70}")
    lineas.append("  ANÁLISIS: OIDs con texto (posibles usuarios/nombres)")
    lineas.append(f"{'='*70}")

    print(f"\n  Analizando OIDs con texto...")
    usuarios_candidatos = []
    for base, res in todos_resultados.items():
        for oid, tipo, valor in res:
            if tipo == "OctetString" and valor.strip() and len(valor) > 1:
                usuarios_candidatos.append((oid, valor))
                lineas.append(f"  {oid}")
                lineas.append(f"    → {valor!r}")

    # ── Intentar cruzar contadores (Integer) con nombres cercanos ────────────
    lineas.append(f"\n{'='*70}")
    lineas.append("  ANÁLISIS: OIDs con números (posibles contadores)")
    lineas.append(f"{'='*70}")

    for base, res in todos_resultados.items():
        for oid, tipo, valor in res:
            if tipo in ("Integer", "Counter32", "Counter64", "Gauge32"):
                try:
                    n = int(valor)
                    if n > 0:  # solo contadores con valor
                        lineas.append(f"  {oid}  =  {n}")
                except Exception:
                    pass

    lineas.append(f"\n{'='*70}")
    lineas.append(f"  TOTAL: {total} OIDs encontrados")
    lineas.append(f"{'='*70}")

    # Guardar archivo
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))

    print(f"\n  Total: {total} OIDs")
    print(f"  Archivo: {OUT_FILE}\n")

    # Resumen en pantalla
    if usuarios_candidatos:
        print("─" * 70)
        print("  Textos encontrados (posibles usuarios):")
        print("─" * 70)
        for oid, val in usuarios_candidatos[:30]:
            print(f"  {oid}")
            print(f"    → {val!r}")
    else:
        print("  ⚠  No se encontraron OIDs con texto en las ramas XSA.")
        print("  Posibles causas:")
        print("    - No hay usuarios creados en la contabilidad estándar todavía")
        print("    - Los OIDs de XSA están bajo una rama diferente en este modelo")
        print("    - La comunidad SNMP 'public' no tiene acceso a datos de contabilidad")
        print()
        print("  → Prueba también con comunidad 'xerox' o la configurada en la impresora")

if __name__ == "__main__":
    asyncio.run(main())
