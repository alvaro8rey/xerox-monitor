"""
SNMP Full Walk - explora todos los OIDs del dispositivo y exporta a txt.
Uso: python test_oids_usuarios.py
"""
import asyncio, datetime, os
from pysnmp.hlapi.v1arch.asyncio import (
    SnmpDispatcher, CommunityData, UdpTransportTarget,
    ObjectType, ObjectIdentity, next_cmd
)

IP        = "10.55.161.248"
COMUNIDAD = "public"
TIMEOUT   = 2.0
OUT_FILE  = f"snmp_walk_{IP.replace('.','_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

# Árboles a explorar en orden
ARBOLES = [
    ("MIB-II estándar",            "1.3.6.1.2.1"),
    ("Xerox Enterprise",           "1.3.6.1.4.1.253"),
    ("Job Monitoring MIB",         "1.3.6.1.4.1.2699"),
    ("Host Resources MIB extra",   "1.3.6.1.2.1.25"),
]

async def snmp_walk(dispatcher, transport, base_oid, lineas, max_oids=5000):
    """Walk GETNEXT desde base_oid. Devuelve nº de OIDs encontrados."""
    current_oid = base_oid
    count = 0

    while count < max_oids:
        try:
            errI, errS, _, vb = await next_cmd(
                dispatcher, CommunityData(COMUNIDAD), transport,
                ObjectType(ObjectIdentity(current_oid))
            )
        except Exception as e:
            lineas.append(f"  [EXCEPCIÓN] {e}")
            break

        if errI or errS:
            break

        if not vb:
            break

        oid_obj, val = vb[0]
        oid_str = str(oid_obj)

        # Parar si salimos del árbol base
        if not oid_str.startswith(base_oid):
            break

        tipo = type(val).__name__
        valor = str(val)

        # Filtrar no-such y end-of
        if "No Such" in valor or "End of" in valor:
            break

        lineas.append(f"  {oid_str}")
        lineas.append(f"    tipo={tipo}  valor={valor!r}")

        current_oid = oid_str
        count += 1

    return count

async def main():
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lineas = []
    lineas.append("=" * 70)
    lineas.append(f"  SNMP Full Walk  |  IP: {IP}  |  Comunidad: {COMUNIDAD}")
    lineas.append(f"  Fecha: {ts}")
    lineas.append("=" * 70)

    print(f"\n{'='*70}")
    print(f"  SNMP Full Walk  |  IP: {IP}")
    print(f"  Salida → {OUT_FILE}")
    print(f"{'='*70}\n")

    dispatcher = SnmpDispatcher()
    try:
        transport = await UdpTransportTarget.create(
            (IP, 161), timeout=TIMEOUT, retries=1)
    except Exception as e:
        print(f"[ERROR] No se pudo conectar: {e}")
        return

    # Verificar conectividad
    from pysnmp.hlapi.v1arch.asyncio import get_cmd
    errI, errS, _, vb = await get_cmd(
        dispatcher, CommunityData(COMUNIDAD), transport,
        ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))
    )
    for _, val in vb:
        v = str(val)
        if "No Such" not in v:
            lineas.append(f"\n  sysDescr: {v}")
            print(f"  Dispositivo: {v[:70]}\n")

    total = 0
    for nombre, base in ARBOLES:
        print(f"  Explorando {nombre} ({base})...", flush=True)
        lineas.append(f"\n{'─'*70}")
        lineas.append(f"  {nombre}  ({base})")
        lineas.append(f"{'─'*70}")

        n = await snmp_walk(dispatcher, transport, base, lineas)
        total += n
        resumen = f"→ {n} OIDs" if n > 0 else "→ sin respuesta"
        print(f"    {resumen}")
        lineas.append(f"  [subtotal: {n} OIDs]\n")

    lineas.append("=" * 70)
    lineas.append(f"  TOTAL OIDs encontrados: {total}")
    lineas.append("=" * 70)

    # Escribir archivo
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))

    print(f"\n  Total: {total} OIDs")
    print(f"  Archivo guardado: {os.path.abspath(OUT_FILE)}\n")

    # Mostrar en consola solo los OIDs interesantes (Xerox + no estándar)
    xerox_lines = [l for l in lineas if "253" in l or "2699" in l]
    if xerox_lines:
        print("─" * 70)
        print("  OIDs Xerox/Job con datos (resumen en pantalla):")
        print("─" * 70)
        for l in xerox_lines[:80]:
            print(l)
        if len(xerox_lines) > 80:
            print(f"  ... ({len(xerox_lines)-80} líneas más en el archivo)")

if __name__ == "__main__":
    asyncio.run(main())
