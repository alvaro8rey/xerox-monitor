"""
Test de OIDs Xerox propietarios para conteo por usuario.
Uso: python test_oids_usuarios.py
"""
import asyncio
from pysnmp.hlapi.v1arch.asyncio import (
    SnmpDispatcher, CommunityData, UdpTransportTarget,
    ObjectType, ObjectIdentity, get_cmd, bulk_cmd
)

IP        = "10.55.161.248"
COMUNIDAD = "public"
TIMEOUT   = 3.0

# OIDs a explorar
OIDS_TEST = {
    "user_names_base":   "1.3.6.1.4.1.253.8.53.15",
    "user_counter_base": "1.3.6.1.4.1.253.8.53.14",
    # Variantes comunes con subíndices
    "user_names_1":      "1.3.6.1.4.1.253.8.53.15.1",
    "user_names_2":      "1.3.6.1.4.1.253.8.53.15.2",
    "user_counter_1":    "1.3.6.1.4.1.253.8.53.14.1",
    "user_counter_2":    "1.3.6.1.4.1.253.8.53.14.2",
}

async def get_one(dispatcher, transport, oid):
    errI, errS, _, vb = await get_cmd(
        dispatcher, CommunityData(COMUNIDAD), transport,
        ObjectType(ObjectIdentity(oid))
    )
    if errI or errS:
        return f"ERROR: {errI or errS}"
    for _, val in vb:
        v = str(val)
        if "No Such" in v or "End of" in v:
            return f"No responde ({v[:40]})"
        return v
    return "Sin datos"

async def walk_oid(dispatcher, transport, base_oid, max_rows=30):
    """Hace un SNMP walk manual probando índices del 1 al max_rows."""
    resultados = {}
    for i in range(1, max_rows + 1):
        oid = f"{base_oid}.{i}"
        errI, errS, _, vb = await get_cmd(
            dispatcher, CommunityData(COMUNIDAD), transport,
            ObjectType(ObjectIdentity(oid))
        )
        if errI or errS:
            break
        for _, val in vb:
            v = str(val)
            if "No Such" in v or "End of" in v:
                return resultados
            resultados[i] = v
    return resultados

async def main():
    print(f"\n{'='*60}")
    print(f"  Test OIDs Xerox por usuario")
    print(f"  IP: {IP}  |  Comunidad: {COMUNIDAD}")
    print(f"{'='*60}\n")

    dispatcher = SnmpDispatcher()
    try:
        transport = await UdpTransportTarget.create((IP, 161), timeout=TIMEOUT, retries=1)
    except Exception as e:
        print(f"[ERROR] No se pudo conectar: {e}")
        return

    # 1. GET simple de cada OID
    print("── GET directo de OIDs base ──────────────────────────────")
    for nombre, oid in OIDS_TEST.items():
        resultado = await get_one(dispatcher, transport, oid)
        print(f"  {nombre:<22} ({oid})")
        print(f"    → {resultado}\n")

    # 2. Walk de la rama de nombres de usuario (índices 1..30)
    print("\n── WALK .1.3.6.1.4.1.253.8.53.15 (nombres de usuario) ───")
    nombres = await walk_oid(dispatcher, transport, "1.3.6.1.4.1.253.8.53.15", 30)
    if nombres:
        for idx, val in nombres.items():
            print(f"  [{idx:>2}] {val}")
    else:
        print("  Sin respuesta en ningún índice.")

    # 3. Walk de la rama de contadores (índices 1..30)
    print("\n── WALK .1.3.6.1.4.1.253.8.53.14 (contadores) ──────────")
    contadores = await walk_oid(dispatcher, transport, "1.3.6.1.4.1.253.8.53.14", 30)
    if contadores:
        for idx, val in contadores.items():
            print(f"  [{idx:>2}] {val}")
    else:
        print("  Sin respuesta en ningún índice.")

    # 4. Si encontramos ambos, intentar cruzarlos
    if nombres and contadores:
        print("\n── CRUCE nombre ↔ contador ──────────────────────────────")
        for idx in sorted(nombres):
            nombre_u = nombres.get(idx, "?")
            contador = contadores.get(idx, "—")
            print(f"  [{idx:>2}] {nombre_u:<30} páginas: {contador}")

    # 5. Explorar subárboles adicionales de la MIB Xerox
    print("\n── Exploración ramas adicionales Xerox (.8.53.x) ────────")
    for rama in range(10, 20):
        oid_test = f"1.3.6.1.4.1.253.8.53.{rama}.1"
        r = await get_one(dispatcher, transport, oid_test)
        if "No responde" not in r and "ERROR" not in r:
            print(f"  .8.53.{rama}.1 → {r}")

    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    asyncio.run(main())
