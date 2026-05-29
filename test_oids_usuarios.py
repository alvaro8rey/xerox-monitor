"""
Test SNMP Xerox - diagnóstico completo de OIDs con datos.
Uso: python test_oids_usuarios.py
"""
import asyncio
from pysnmp.hlapi.v1arch.asyncio import (
    SnmpDispatcher, CommunityData, UdpTransportTarget,
    ObjectType, ObjectIdentity, get_cmd
)

IP        = "10.55.161.248"
COMUNIDAD = "public"
TIMEOUT   = 2.0

# Ramas a explorar en busca de OIDs con datos reales
RAMAS = [
    # Xerox propietario - contabilidad
    ("Xerox accounting .8.53",    "1.3.6.1.4.1.253.8.53",    30, 5),
    ("Xerox accounting .8.61",    "1.3.6.1.4.1.253.8.61",    30, 5),
    ("Xerox accounting .8.62",    "1.3.6.1.4.1.253.8.62",    30, 5),
    # Job Monitoring MIB (RFC 2707) - estándar, a veces implementado
    ("Job Monitor MIB",           "1.3.6.1.4.1.2699.1.1",    20, 5),
    # Xerox MIB raíz
    ("Xerox root .8.51",          "1.3.6.1.4.1.253.8.51",    20, 5),
    ("Xerox root .8.52",          "1.3.6.1.4.1.253.8.52",    20, 5),
    ("Xerox root .8.56",          "1.3.6.1.4.1.253.8.56",    20, 5),
    ("Xerox root .8.57",          "1.3.6.1.4.1.253.8.57",    20, 5),
    # HR MIB - contadores de trabajos
    ("hrStorage",                 "1.3.6.1.2.1.25.2.3.1",    10, 5),
    ("prtInterpreter",            "1.3.6.1.2.1.43.15.1.1",   10, 5),
    ("prtChannel",                "1.3.6.1.2.1.43.14.1.1",   10, 5),
    ("prtJob (si existe)",        "1.3.6.1.2.1.43.13.1.1",   10, 5),
]

async def walk_rama(dispatcher, transport, base_oid, max_sub, max_idx):
    """
    Walk 2D: prueba base.sub.idx para sub en 1..max_sub, idx en 1..max_idx.
    Devuelve lista de (oid_completo, tipo, valor) con datos reales.
    """
    encontrados = []
    for sub in range(1, max_sub + 1):
        for idx in range(1, max_idx + 1):
            oid = f"{base_oid}.{sub}.{idx}"
            try:
                errI, errS, _, vb = await get_cmd(
                    dispatcher, CommunityData(COMUNIDAD), transport,
                    ObjectType(ObjectIdentity(oid))
                )
                if errI or errS:
                    continue
                for _, val in vb:
                    tipo = type(val).__name__
                    v = str(val)
                    if "No Such" in v or "End of" in v:
                        continue
                    if v.strip():  # solo si tiene valor no vacío
                        encontrados.append((oid, tipo, v))
            except Exception:
                pass
    return encontrados

async def main():
    print(f"\n{'='*65}")
    print(f"  Diagnóstico SNMP Xerox - búsqueda de OIDs con datos")
    print(f"  IP: {IP}  |  Comunidad: {COMUNIDAD}")
    print(f"{'='*65}\n")

    dispatcher = SnmpDispatcher()
    try:
        transport = await UdpTransportTarget.create((IP, 161), timeout=TIMEOUT, retries=0)
    except Exception as e:
        print(f"[ERROR] No se pudo conectar: {e}")
        return

    # Verificar conectividad básica
    errI, errS, _, vb = await get_cmd(
        dispatcher, CommunityData(COMUNIDAD), transport,
        ObjectType(ObjectIdentity("1.3.6.1.2.1.1.5.0"))
    )
    for _, val in vb:
        print(f"  Dispositivo: {val}\n")

    total_encontrados = 0

    for nombre, base, max_sub, max_idx in RAMAS:
        print(f"── {nombre} ({base}) ", end="", flush=True)
        resultados = await walk_rama(dispatcher, transport, base, max_sub, max_idx)
        if resultados:
            print(f"→ {len(resultados)} OIDs con datos:")
            for oid, tipo, val in resultados:
                print(f"    {oid}")
                print(f"      tipo={tipo}  valor={val!r}")
            total_encontrados += len(resultados)
        else:
            print("→ sin datos")

    print(f"\n{'='*65}")
    print(f"  Total OIDs con datos encontrados: {total_encontrados}")

    if total_encontrados == 0:
        print("""
  DIAGNÓSTICO: La impresora no expone contadores por usuario vía SNMP.

  Posibles causas:
    1. Network Accounting desactivado en la impresora.
       → Entrar al panel web (http://10.55.161.248) como admin
         → Propiedades → Contabilidad → Activar "Network Accounting"
         → Crear usuarios con sus cuotas

    2. Los datos requieren SNMPv3 con autenticación (no community public).
       → Habría que configurar un usuario SNMPv3 en la impresora.

    3. Esta impresora no implementa contabilidad por usuario vía SNMP.
       → Alternativa: scraping del panel web con requests+BeautifulSoup.
""")
    print(f"{'='*65}\n")

if __name__ == "__main__":
    asyncio.run(main())
