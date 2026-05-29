import asyncio
from pysnmp.hlapi.v1arch.asyncio import (
    SnmpDispatcher, CommunityData, UdpTransportTarget,
    ObjectType, ObjectIdentity, get_cmd, walk_cmd
)

IP = "192.168.1.114"
COMUNIDAD = "public"

async def test():
    dispatcher = SnmpDispatcher()
    transport = await UdpTransportTarget.create((IP, 161), timeout=3, retries=1)

    # Test sysDescr
    print("=== sysDescr ===")
    errI, errS, errX, vb = await get_cmd(
        dispatcher, CommunityData(COMUNIDAD), transport,
        ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))
    )
    if errI: print("ERROR:", errI)
    else:
        for oid, val in vb:
            print(val.prettyPrint())

    # Walk Printer MIB completa
    print("\n=== Walk Printer MIB (43.11) ===")
    count = 0
    async for errI, errS, errX, vb in walk_cmd(
        dispatcher, CommunityData(COMUNIDAD), transport,
        ObjectType(ObjectIdentity("1.3.6.1.2.1.43.11")),
        lexicographicMode=False
    ):
        if errI or errS: break
        for oid, val in vb:
            print(f"  {oid}: {val.prettyPrint()}")
            count += 1
    print(f"Total OIDs encontrados: {count}")

    # Walk prtMarkerSupplies (alternativa Brother)
    print("\n=== Walk 1.3.6.1.2.1.43 completo ===")
    count2 = 0
    async for errI, errS, errX, vb in walk_cmd(
        dispatcher, CommunityData(COMUNIDAD), transport,
        ObjectType(ObjectIdentity("1.3.6.1.2.1.43")),
        lexicographicMode=False
    ):
        if errI or errS: break
        for oid, val in vb:
            print(f"  {oid}: {val.prettyPrint()[:80]}")
            count2 += 1
        if count2 > 60:
            print("  ... (limitado a 60)")
            break

asyncio.run(test())