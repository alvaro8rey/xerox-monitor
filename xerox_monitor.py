import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
import json, os, asyncio, socket, threading, csv, ipaddress
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── SNMP ──────────────────────────────────────────────────────────────────────
SNMP_OK = False
SNMP_ERROR = ""
try:
    from pysnmp.hlapi.v1arch.asyncio import (
        SnmpDispatcher, CommunityData, UdpTransportTarget,
        ObjectType, ObjectIdentity, get_cmd
    )
    SNMP_OK = True
except Exception as e:
    SNMP_ERROR = str(e)

# ── HELPERS CONSUMIBLES ───────────────────────────────────────────────────────
_ABREV_MAP = [
    ("Black Toner",   "Negro"),  ("Cyan Toner",    "Cian"),
    ("Magenta Toner", "Magenta"),("Yellow Toner",  "Amarillo"),
    ("Black Drum",    "Tambor Negro"), ("Cyan Drum","Tambor Cian"),
    ("Magenta Drum",  "Tambor Magenta"),("Yellow Drum","Tambor Amarillo"),
    ("Black",  "Negro"), ("Cyan",  "Cian"),
    ("Magenta","Magenta"),("Yellow","Amarillo"),
    ("Toner",  "Tóner"), ("Drum",  "Tambor"), ("Fuser","Fusor"),
    ("Transfer Roller","Transfer"),("Transfer","Transfer"),
    ("Maintenance","Mant."),("Waste Toner","Residuo"),
    ("Waste",  "Residuo"),("Staple","Grapas"),
    ("Hole Punch","Taladro"),
]

def _abrev_consumible(name):
    n = name
    for orig, rep in _ABREV_MAP:
        if orig.lower() in n.lower():
            n = n.lower().replace(orig.lower(), rep)
            break
    n = n.strip().title()
    return n[:16] if len(n) > 16 else n

def _formato_consumibles(cons, umbral_critico, umbral_alerta):
    if not cons:
        return "—"
    sorted_c = sorted(cons, key=lambda c: c["porcentaje"])
    parts, ok_count = [], 0
    for c in sorted_c:
        pct = c["porcentaje"]
        if pct <= umbral_alerta:
            sym = "⚠" if pct <= umbral_critico else "·"
            parts.append(f"{sym} {_abrev_consumible(c['componente'])}: {pct}%")
        else:
            ok_count += 1
    if ok_count == 1:
        ok_item = next(c for c in cons if c["porcentaje"] > umbral_alerta)
        parts.append(f"✓ {_abrev_consumible(ok_item['componente'])}: {ok_item['porcentaje']}%")
    elif ok_count > 1:
        parts.append(f"✓ {ok_count} en buen nivel")
    return "   ".join(parts) if parts else "✓ Todo OK"

# ── CONSTANTES ────────────────────────────────────────────────────────────────
DB_FILE        = "impresoras.json"
HISTORIAL_FILE = "historial.json"
CONFIG_FILE    = "config.json"
BASE_OID       = "1.3.6.1.2.1.43.11.1.1"
DEFAULT_CONFIG = {
    "umbral_critico": 15,
    "umbral_alerta":  20,
    "comunidad_snmp": "public",
    "timeout_snmp":   2.0,
    "autorefresh_seg": 0,
}

# ── PALETA ────────────────────────────────────────────────────────────────────
BG      = "#1a1d2e"
BG2     = "#232640"
BG3     = "#2c3057"
ACCENT  = "#4f8ef7"
TEXT    = "#e8eaf0"
TEXT2   = "#8b92b8"
OK      = "#2ecc71"
WARN    = "#f39c12"
CRIT    = "#e74c3c"
OFFLINE = "#6c7a99"
ROW_ALT = "#1e2238"
ROW_SEL = "#2a3560"
BORDER  = "#353860"

# ── PERSISTENCIA ──────────────────────────────────────────────────────────────
def cargar_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def guardar_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def cargar_impresoras():
    raw = cargar_json(DB_FILE, [])
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append({"ip": item, "nombre": item, "ubicacion": "", "comunidad": ""})
        else:
            out.append(item)
    return out

def guardar_historial(ip, consumibles):
    h = cargar_json(HISTORIAL_FILE, {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if ip not in h:
        h[ip] = []
    h[ip].append({"ts": ts, "consumibles": consumibles})
    h[ip] = h[ip][-100:]
    guardar_json(HISTORIAL_FILE, h)

# ── SNMP ──────────────────────────────────────────────────────────────────────
def limpiar_nombre(n):
    for sep in [";", ", PN", " (", ","]:
        if sep in n:
            n = n.split(sep)[0]
    return n.strip()

async def _snmp_bulk(ip, comunidad, timeout):
    desc, level, maxcap = {}, {}, {}
    dispatcher = SnmpDispatcher()
    try:
        transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=1)
    except Exception as e:
        return None, f"No se pudo conectar: {e}"

    for supply_idx in range(1, 20):
        idx = f"1.{supply_idx}"
        nombre_val = level_val = maxcap_val = None
        for sub, oid_full in [
            (".6.", BASE_OID + ".6." + idx),
            (".8.", BASE_OID + ".8." + idx),
            (".9.", BASE_OID + ".9." + idx),
        ]:
            try:
                errI, errS, _, vb = await get_cmd(
                    dispatcher, CommunityData(comunidad), transport,
                    ObjectType(ObjectIdentity(oid_full))
                )
                if errI or errS:
                    continue
                for oid, val in vb:
                    v = str(val)
                    if "No Such" in v or "End of" in v:
                        continue
                    if sub == ".6.":
                        nombre_val = v
                    elif sub == ".8.":
                        try: maxcap_val = int(val)
                        except: pass
                    elif sub == ".9.":
                        try: level_val = int(val)
                        except: pass
            except Exception:
                pass
        if nombre_val is None:
            break
        desc[idx] = nombre_val
        if maxcap_val is not None: maxcap[idx] = maxcap_val
        if level_val  is not None: level[idx]  = level_val

    resultados = []
    for idx, name in desc.items():
        lvl = level.get(idx)
        maximum = maxcap.get(idx)
        if lvl is None or maximum is None: continue
        if lvl == -2: continue
        if maximum > 0 and lvl >= 0:
            pct = max(0, min(round((lvl / maximum) * 100), 100))
        elif lvl == -3:
            pct = 100
        else:
            continue
        resultados.append({"componente": limpiar_nombre(name), "porcentaje": pct})

    if not resultados:
        return None, "Sin consumibles detectados"
    return resultados, None

async def _snmp_nombre(ip, comunidad, timeout):
    dispatcher = SnmpDispatcher()
    try:
        transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=1)
        errI, errS, _, vb = await get_cmd(
            dispatcher, CommunityData(comunidad), transport,
            ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))
        )
        if errI or errS: return None
        for _, val in vb:
            n = str(val).strip()
            if n and "No Such" not in n:
                return n.split(";")[0].split(",")[0].strip()[:60]
    except Exception:
        pass
    return None

def obtener_consumibles(ip, comunidad="public", timeout=2.0):
    try:    return asyncio.run(_snmp_bulk(ip, comunidad, timeout))
    except Exception as e: return None, str(e)

def obtener_nombre_snmp(ip, comunidad="public", timeout=2.0):
    try:    return asyncio.run(_snmp_nombre(ip, comunidad, timeout))
    except: return None

# OIDs adicionales útiles
OIDS_INFO = {
    "sys_desc":     "1.3.6.1.2.1.1.1.0",      # Descripción del sistema
    "sys_nombre":   "1.3.6.1.2.1.1.5.0",      # Nombre del host (sysName)
    "sys_uptime":   "1.3.6.1.2.1.1.3.0",      # Uptime del dispositivo
    "paginas":      "1.3.6.1.2.1.43.10.2.1.4.1.1",  # Contador páginas impresas
    "estado_imp":   "1.3.6.1.2.1.25.3.5.1.1.1",     # hrPrinterStatus (idle/printing/error)
    "estado_det":   "1.3.6.1.2.1.25.3.5.1.2.1",     # hrPrinterDetectedErrorState
    "modelo":       "1.3.6.1.2.1.25.3.2.1.3.1",     # hrDeviceDescr (modelo)
    "serial":       "1.3.6.1.2.1.43.5.1.1.17.1",    # prtGeneralSerialNumber
    "bandeja_cap":  "1.3.6.1.2.1.43.8.2.1.9.1.1",   # Capacidad bandeja entrada
    "bandeja_nivel":"1.3.6.1.2.1.43.8.2.1.10.1.1",  # Nivel actual bandeja entrada
}

ESTADO_IMP_MAP = {
    "1": "Otro", "2": "Desconocido", "3": "Idle",
    "4": "Imprimiendo", "5": "Calentando"
}

async def _snmp_info_extra(ip, comunidad, timeout):
    """Obtiene OIDs adicionales: páginas, uptime, estado, serie, bandeja..."""
    dispatcher = SnmpDispatcher()
    info = {}
    try:
        transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=1)
    except Exception as e:
        return info

    for clave, oid in OIDS_INFO.items():
        try:
            errI, errS, _, vb = await get_cmd(
                dispatcher, CommunityData(comunidad), transport,
                ObjectType(ObjectIdentity(oid))
            )
            if errI or errS: continue
            for _, val in vb:
                v = str(val).strip()
                if "No Such" in v or "End of" in v or not v: continue
                info[clave] = v
        except Exception:
            pass
    return info

def obtener_info_extra(ip, comunidad="public", timeout=2.0):
    try:    return asyncio.run(_snmp_info_extra(ip, comunidad, timeout))
    except: return {}

# ── ESCANEO DE RED ────────────────────────────────────────────────────────────
def _parsear_rango(texto):
    """Devuelve lista de IPs a escanear desde CIDR, rango A-B o IP única."""
    texto = texto.strip()
    ips = []
    try:
        if "/" in texto:
            red = ipaddress.IPv4Network(texto, strict=False)
            ips = [str(h) for h in red.hosts()]
        elif "-" in texto:
            partes = texto.rsplit("-", 1)
            base = partes[0].rsplit(".", 1)
            prefijo = base[0]
            ini = int(base[1])
            fin = int(partes[1])
            ips = [f"{prefijo}.{i}" for i in range(ini, fin + 1)]
        else:
            ipaddress.IPv4Address(texto)
            ips = [texto]
    except Exception:
        pass
    return ips

def _snmp_ping(ip, comunidad, timeout):
    """Intenta obtener sysDescr. Devuelve dict con info o None si no responde."""
    try:
        resultado = asyncio.run(_snmp_info_extra(ip, comunidad, min(timeout, 1.5)))
        if not resultado:
            return None
        desc = resultado.get("sys_desc", "")
        # Filtrar dispositivos que probablemente no son impresoras si no hay datos relevantes
        nombre = resultado.get("sys_nombre") or resultado.get("modelo") or ""
        modelo = resultado.get("modelo", "")
        return {
            "ip": ip,
            "sys_desc": desc[:60],
            "nombre": nombre[:50] or ip,
            "modelo": modelo[:40],
        }
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════════════════
# DIALOGO ESCANEO DE RED
# ══════════════════════════════════════════════════════════════════════════════
class DialogEscaneoRed(ctk.CTkToplevel):
    def __init__(self, parent, cfg, ips_existentes):
        super().__init__(parent)
        self.cfg = cfg
        self.ips_existentes = set(ips_existentes)
        self.resultado = []          # lista de dicts a añadir
        self._cancelar = False
        self._checks = {}            # ip → BooleanVar

        self.title("Escaneo de red")
        self.geometry("620x580")
        self.minsize(540, 480)
        self.configure(fg_color=BG2)
        self.grab_set()
        self.lift()
        self.focus_force()

        # ── Barra inferior fija ──
        btns = ctk.CTkFrame(self, fg_color=BG2, height=56)
        btns.pack(side="bottom", fill="x", padx=20, pady=12)
        btns.pack_propagate(False)
        self.btn_cancel = ctk.CTkButton(
            btns, text="Cancelar", width=130, height=36,
            fg_color=BG3, hover_color=BORDER, text_color=TEXT,
            font=("Segoe UI", 12), command=self._on_cancel)
        self.btn_cancel.pack(side="left", padx=4)
        self.btn_add = ctk.CTkButton(
            btns, text="＋  Añadir seleccionados", width=190, height=36,
            fg_color=ACCENT, hover_color="#3a7de8", text_color=TEXT,
            font=("Segoe UI", 12, "bold"), command=self._añadir_sel,
            state="disabled")
        self.btn_add.pack(side="right", padx=4)

        sep = ctk.CTkFrame(self, fg_color=BORDER, height=1)
        sep.pack(side="bottom", fill="x")

        # ── Cuerpo ──
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # Fila de entrada
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row1, text="Rango de red:", text_color=TEXT2,
                     font=("Segoe UI", 11)).pack(side="left")
        self.entry_rango = ctk.CTkEntry(
            row1, placeholder_text="192.168.1.0/24  ó  192.168.1.1-254",
            width=300, height=32, fg_color=BG3, border_color=BORDER, text_color=TEXT,
            font=("Segoe UI", 11))
        self.entry_rango.pack(side="left", padx=8)
        self.btn_scan = ctk.CTkButton(
            row1, text="▶  Escanear", width=110, height=32,
            fg_color=ACCENT, hover_color="#3a7de8", text_color=TEXT,
            font=("Segoe UI", 11, "bold"), command=self._iniciar_scan)
        self.btn_scan.pack(side="left", padx=4)

        # Progreso
        self.lbl_prog = ctk.CTkLabel(body, text="", text_color=TEXT2,
                                      font=("Segoe UI", 10))
        self.lbl_prog.pack(anchor="w")
        self.progress = ctk.CTkProgressBar(body, width=580, height=8,
                                            fg_color=BG3, progress_color=ACCENT)
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(2, 8))

        # Cabecera de resultados
        hdr = ctk.CTkFrame(body, fg_color=BG3, corner_radius=4, height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="✔", width=30, font=("Segoe UI", 10, "bold"),
                     text_color=TEXT2).pack(side="left", padx=4)
        for txt, w in [("IP", 130), ("Nombre / Hostname", 180), ("Modelo", 200)]:
            ctk.CTkLabel(hdr, text=txt, width=w, font=("Segoe UI", 9, "bold"),
                         text_color=TEXT2, anchor="w").pack(side="left", padx=4)

        # Lista de resultados (scroll)
        self.scroll = ctk.CTkScrollableFrame(body, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, pady=(2, 0))

        self.lbl_vacio = ctk.CTkLabel(
            self.scroll, text="Introduce un rango y pulsa Escanear",
            text_color=TEXT2, font=("Segoe UI", 11))
        self.lbl_vacio.pack(pady=40)

    def _iniciar_scan(self):
        rango = self.entry_rango.get().strip()
        ips = _parsear_rango(rango)
        if not ips:
            self.lbl_prog.configure(text="⚠  Rango no válido. Ej: 192.168.1.0/24", text_color=CRIT)
            return
        if len(ips) > 1024:
            self.lbl_prog.configure(text="⚠  Rango demasiado grande (máx 1024 IPs)", text_color=CRIT)
            return

        # Limpiar resultados anteriores
        for w in self.scroll.winfo_children():
            w.destroy()
        self._checks.clear()
        self.btn_add.configure(state="disabled")
        self.btn_scan.configure(state="disabled")
        self._cancelar = False
        self.progress.set(0)
        self.lbl_prog.configure(text=f"Escaneando {len(ips)} IPs...", text_color=TEXT2)

        threading.Thread(target=self._scan_worker, args=(ips,), daemon=True).start()

    def _scan_worker(self, ips):
        total = len(ips)
        encontrados = 0
        com = self.cfg["comunidad_snmp"]
        timeout = min(self.cfg["timeout_snmp"], 1.5)

        # Usamos hasta 80 hilos en paralelo — el timeout corto evita bloqueos
        with ThreadPoolExecutor(max_workers=min(80, total)) as ex:
            futures = {ex.submit(_snmp_ping, ip, com, timeout): ip for ip in ips}
            done = 0
            for fut in as_completed(futures):
                if self._cancelar:
                    ex.shutdown(wait=False, cancel_futures=True)
                    break
                done += 1
                resultado = fut.result()
                progreso = done / total
                self.after(0, lambda p=progreso, d=done, t=total:
                           self._actualizar_prog(p, d, t))
                if resultado:
                    encontrados += 1
                    self.after(0, lambda r=resultado: self._agregar_fila(r))

        if not self._cancelar:
            self.after(0, lambda e=encontrados: self._scan_done(e))

    def _actualizar_prog(self, p, done, total):
        self.progress.set(p)
        self.lbl_prog.configure(
            text=f"Escaneando... {done}/{total} IPs  ({int(p*100)}%)",
            text_color=TEXT2)

    def _scan_done(self, encontrados):
        self.btn_scan.configure(state="normal")
        self.progress.set(1)
        if encontrados == 0:
            self.lbl_prog.configure(
                text="Sin dispositivos SNMP encontrados en ese rango.", text_color=WARN)
            self.lbl_vacio = ctk.CTkLabel(
                self.scroll, text="Sin resultados", text_color=TEXT2,
                font=("Segoe UI", 11))
            self.lbl_vacio.pack(pady=40)
        else:
            ya = sum(1 for ip in self._checks if ip in self.ips_existentes)
            nuevos = encontrados - ya
            self.lbl_prog.configure(
                text=f"✔  {encontrados} dispositivos encontrados  ({nuevos} nuevos)",
                text_color=OK)
            if nuevos > 0:
                self.btn_add.configure(state="normal")

    def _agregar_fila(self, r):
        ip = r["ip"]
        ya_existe = ip in self.ips_existentes
        var = tk.BooleanVar(value=not ya_existe)
        self._checks[ip] = (var, r)

        fila = ctk.CTkFrame(self.scroll, fg_color=BG3 if ya_existe else BG2,
                             corner_radius=3, height=30)
        fila.pack(fill="x", pady=1)
        fila.pack_propagate(False)

        cb = ctk.CTkCheckBox(fila, text="", variable=var, width=30,
                              fg_color=ACCENT, hover_color="#3a7de8",
                              state="disabled" if ya_existe else "normal",
                              command=self._check_changed)
        cb.pack(side="left", padx=4)

        color = TEXT2 if ya_existe else TEXT
        ctk.CTkLabel(fila, text=ip, width=130, font=("Consolas", 10),
                     text_color=color, anchor="w").pack(side="left", padx=4)
        nombre = (r["nombre"] or ip)
        sufijo = "  (ya añadida)" if ya_existe else ""
        ctk.CTkLabel(fila, text=nombre + sufijo, width=180,
                     font=("Segoe UI", 10), text_color=color,
                     anchor="w").pack(side="left", padx=4)
        ctk.CTkLabel(fila, text=r.get("modelo","—") or "—", width=200,
                     font=("Segoe UI", 10), text_color=TEXT2,
                     anchor="w").pack(side="left", padx=4)

    def _check_changed(self):
        hay_sel = any(
            var.get() and ip not in self.ips_existentes
            for ip, (var, _) in self._checks.items()
        )
        self.btn_add.configure(state="normal" if hay_sel else "disabled")

    def _añadir_sel(self):
        self.resultado = [
            {"ip": ip, "nombre": r["nombre"] or ip,
             "ubicacion": "", "comunidad": ""}
            for ip, (var, r) in self._checks.items()
            if var.get() and ip not in self.ips_existentes
        ]
        self.destroy()

    def _on_cancel(self):
        self._cancelar = True
        self.destroy()

# ══════════════════════════════════════════════════════════════════════════════
# DIALOGO AÑADIR/EDITAR
# ══════════════════════════════════════════════════════════════════════════════
class DialogImpresora(ctk.CTkToplevel):
    def __init__(self, parent, cfg, imp=None):
        super().__init__(parent)
        self.cfg = cfg
        self.resultado = None
        self.title("Añadir dispositivo" if not imp else "Editar dispositivo")
        self.geometry("420x480")
        self.minsize(380, 440)
        self.resizable(True, True)
        self.configure(fg_color=BG2)
        self.grab_set()
        self.lift()
        self.focus_force()

        # Botones ABAJO fijos
        btns = ctk.CTkFrame(self, fg_color=BG2, height=56)
        btns.pack(side="bottom", fill="x", padx=20, pady=12)
        btns.pack_propagate(False)
        ctk.CTkButton(btns, text="Cancelar", width=130, height=36,
                      fg_color=BG3, hover_color=BORDER, text_color=TEXT,
                      font=("Segoe UI", 12), command=self.destroy).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="✔  Guardar", width=130, height=36,
                      fg_color=ACCENT, hover_color="#3a7de8", text_color=TEXT,
                      font=("Segoe UI", 12, "bold"), command=self._guardar).pack(side="right", padx=4)

        self.status_lbl = ctk.CTkLabel(self, text="", text_color=WARN, font=("Segoe UI", 10))
        self.status_lbl.pack(side="bottom", pady=(0,4))

        sep = ctk.CTkFrame(self, fg_color=BORDER, height=1)
        sep.pack(side="bottom", fill="x")

        # Scroll para el contenido
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        pad = {"padx": 20, "pady": 6}

        ctk.CTkLabel(scroll, text="Dirección IP *", text_color=TEXT2, font=("Segoe UI", 11)).pack(anchor="w", **pad)
        self.ip = ctk.CTkEntry(scroll, placeholder_text="192.168.1.100", width=360, fg_color=BG3, border_color=BORDER, text_color=TEXT)
        self.ip.pack(**pad)
        if imp: self.ip.insert(0, imp.get("ip", ""))

        ctk.CTkLabel(scroll, text="Nombre (vacío = autodetectar por SNMP)", text_color=TEXT2, font=("Segoe UI", 11)).pack(anchor="w", **pad)
        self.nombre = ctk.CTkEntry(scroll, placeholder_text="Xerox Planta 2", width=360, fg_color=BG3, border_color=BORDER, text_color=TEXT)
        self.nombre.pack(**pad)
        if imp: self.nombre.insert(0, imp.get("nombre", ""))

        ctk.CTkLabel(scroll, text="Ubicación", text_color=TEXT2, font=("Segoe UI", 11)).pack(anchor="w", **pad)
        self.ubic = ctk.CTkEntry(scroll, placeholder_text="Sala de reuniones A", width=360, fg_color=BG3, border_color=BORDER, text_color=TEXT)
        self.ubic.pack(**pad)
        if imp: self.ubic.insert(0, imp.get("ubicacion", ""))

        ctk.CTkLabel(scroll, text="Comunidad SNMP", text_color=TEXT2, font=("Segoe UI", 11)).pack(anchor="w", **pad)
        self.com = ctk.CTkEntry(scroll, placeholder_text="public", width=360, fg_color=BG3, border_color=BORDER, text_color=TEXT)
        self.com.pack(**pad)
        if imp: self.com.insert(0, imp.get("comunidad", ""))

    def _guardar(self):
        ip = self.ip.get().strip()
        if not ip:
            self.status_lbl.configure(text="⚠  La IP es obligatoria.")
            return
        nombre = self.nombre.get().strip()
        comunidad = self.com.get().strip() or self.cfg["comunidad_snmp"]
        if not nombre:
            self.status_lbl.configure(text="⏳  Autodetectando nombre...")
            self.update()
            nombre = obtener_nombre_snmp(ip, comunidad, self.cfg["timeout_snmp"]) or ip
        self.resultado = {
            "ip": ip, "nombre": nombre,
            "ubicacion": self.ubic.get().strip(),
            "comunidad": self.com.get().strip()
        }
        self.destroy()

# ══════════════════════════════════════════════════════════════════════════════
# DIALOGO CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════
class DialogConfig(ctk.CTkToplevel):
    def __init__(self, parent, cfg, on_save):
        super().__init__(parent)
        self.cfg = cfg
        self.on_save = on_save
        self.title("Configuración")
        self.geometry("420x560")
        self.minsize(380, 520)
        self.resizable(True, True)
        self.configure(fg_color=BG2)
        self.grab_set()
        self.lift()
        self.focus_force()

        # Botones ABAJO fijos (antes del scroll)
        btns = ctk.CTkFrame(self, fg_color=BG2, height=56)
        btns.pack(side="bottom", fill="x", padx=20, pady=12)
        btns.pack_propagate(False)
        ctk.CTkButton(btns, text="Cancelar", width=130, height=36,
                      fg_color=BG3, hover_color=BORDER, text_color=TEXT,
                      font=("Segoe UI", 12), command=self.destroy).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="✔  Guardar", width=130, height=36,
                      fg_color=ACCENT, hover_color="#3a7de8", text_color=TEXT,
                      font=("Segoe UI", 12, "bold"), command=self._guardar).pack(side="right", padx=4)

        sep = ctk.CTkFrame(self, fg_color=BORDER, height=1)
        sep.pack(side="bottom", fill="x")

        # Scroll para el contenido
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        pad = {"padx": 20, "pady": 5}

        def lbl(text):
            ctk.CTkLabel(scroll, text=text, text_color=TEXT2, font=("Segoe UI", 11)).pack(anchor="w", **pad)

        lbl("Umbral crítico (%)")
        self.crit_var = tk.IntVar(value=cfg["umbral_critico"])
        self.crit_lbl = ctk.CTkLabel(scroll, text=str(self.crit_var.get()), text_color=CRIT, font=("Segoe UI", 13, "bold"))
        self.crit_lbl.pack(anchor="w", padx=24)
        ctk.CTkSlider(scroll, from_=1, to=50, variable=self.crit_var, width=340,
                      command=lambda v: self.crit_lbl.configure(text=str(int(v)))).pack(**pad)

        lbl("Umbral alerta (%)")
        self.alert_var = tk.IntVar(value=cfg["umbral_alerta"])
        self.alert_lbl = ctk.CTkLabel(scroll, text=str(self.alert_var.get()), text_color=WARN, font=("Segoe UI", 13, "bold"))
        self.alert_lbl.pack(anchor="w", padx=24)
        ctk.CTkSlider(scroll, from_=1, to=70, variable=self.alert_var, width=340,
                      command=lambda v: self.alert_lbl.configure(text=str(int(v)))).pack(**pad)

        lbl("Comunidad SNMP")
        self.com = ctk.CTkEntry(scroll, width=340, fg_color=BG3, border_color=BORDER, text_color=TEXT)
        self.com.insert(0, cfg["comunidad_snmp"])
        self.com.pack(**pad)

        lbl("Timeout SNMP (segundos)")
        self.timeout = ctk.CTkEntry(scroll, width=340, fg_color=BG3, border_color=BORDER, text_color=TEXT)
        self.timeout.insert(0, str(cfg["timeout_snmp"]))
        self.timeout.pack(**pad)

        lbl("Auto-refresco")
        self.autoref = ctk.CTkOptionMenu(scroll, values=["Desactivado","30s","60s","2 min","5 min"],
                                          width=340, fg_color=BG3, button_color=ACCENT, text_color=TEXT)
        mapa = {0:"Desactivado", 30:"30s", 60:"60s", 120:"2 min", 300:"5 min"}
        self.autoref.set(mapa.get(cfg["autorefresh_seg"], "Desactivado"))
        self.autoref.pack(**pad)

    def _guardar(self):
        try:
            mapa_inv = {"Desactivado":0,"30s":30,"60s":60,"2 min":120,"5 min":300}
            self.cfg.update({
                "umbral_critico":  int(self.crit_var.get()),
                "umbral_alerta":   int(self.alert_var.get()),
                "comunidad_snmp":  self.com.get().strip() or "public",
                "timeout_snmp":    float(self.timeout.get()),
                "autorefresh_seg": mapa_inv.get(self.autoref.get(), 0),
            })
            guardar_json(CONFIG_FILE, self.cfg)
            self.on_save()
            self.destroy()
        except ValueError:
            pass

# ══════════════════════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Fleet Monitor Pro")
        self.geometry("1280x720")
        self.minsize(960, 560)
        self.configure(fg_color=BG)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.cfg        = {**DEFAULT_CONFIG, **cargar_json(CONFIG_FILE, {})}
        self.impresoras = cargar_impresoras()
        self.cache      = {}
        self.sel_ip     = None
        self._scan_thread = None
        self._autoref_job = None

        self._build_ui()
        self._poblar_tabla()
        self._schedule_autoref()

        if not SNMP_OK:
            messagebox.showerror("Error SNMP", f"No se pudo cargar pysnmp:\n{SNMP_ERROR}\n\nEjecuta: pip install pysnmp")

    # ── BUILD UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Toolbar ──
        tb = ctk.CTkFrame(self, fg_color=BG2, height=50, corner_radius=0)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        ctk.CTkLabel(tb, text="🖨  Fleet Monitor Pro",
                     font=("Segoe UI", 14, "bold"), text_color=TEXT).pack(side="left", padx=16)
        self.lbl_ts = ctk.CTkLabel(tb, text="", font=("Segoe UI", 10), text_color=TEXT2)
        self.lbl_ts.pack(side="left", padx=6)

        btn_defs = [
            ("⚙  Config",    self._abrir_config,   BG3),
            ("＋  Añadir",   self._añadir,          BG3),
            ("⊕  Escanear red", self._escanear_red, BG3),
            ("✎  Editar",   self._editar,          BG3),
            ("✕  Eliminar", self._eliminar,        BG3),
            ("↓  Exportar", self._exportar_todo,   BG3),
            ("↺  Refrescar",self._refrescar_todo,  ACCENT),
        ]
        for txt, cmd, color in reversed(btn_defs):
            ctk.CTkButton(tb, text=txt, width=105, height=30,
                          fg_color=color, hover_color=BORDER if color!=ACCENT else "#3a7de8",
                          text_color=TEXT, font=("Segoe UI", 11),
                          command=cmd).pack(side="right", padx=3, pady=9)

        # ── KPI bar ──
        kpi_bar = ctk.CTkFrame(self, fg_color=BG2, height=56, corner_radius=0)
        kpi_bar.pack(fill="x")
        kpi_bar.pack_propagate(False)
        sep = ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0)
        sep.pack(fill="x")

        self.kpi_vars = {}
        for key, lbl, color in [
            ("online",   "En línea",      OK),
            ("offline",  "Sin conexión",  OFFLINE),
            ("criticos", "Nivel crítico", CRIT),
            ("alertas",  "En alerta",     WARN),
        ]:
            f = ctk.CTkFrame(kpi_bar, fg_color="transparent")
            f.pack(side="left", padx=28, pady=6)
            var = tk.StringVar(value="0")
            self.kpi_vars[key] = var
            ctk.CTkLabel(f, textvariable=var, font=("Segoe UI", 20, "bold"), text_color=color).pack()
            ctk.CTkLabel(f, text=lbl, font=("Segoe UI", 9), text_color=TEXT2).pack()

        # ── Search bar ──
        sb = ctk.CTkFrame(self, fg_color=BG, height=38, corner_radius=0)
        sb.pack(fill="x", padx=8, pady=(6,2))
        sb.pack_propagate(False)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filtrar())
        ctk.CTkEntry(sb, textvariable=self.search_var,
                     placeholder_text="🔍  Buscar por nombre o IP...",
                     width=300, height=30, fg_color=BG2, border_color=BORDER, text_color=TEXT,
                     font=("Segoe UI", 11)).pack(side="left", padx=4)

        self.solo_alertas_var = tk.BooleanVar()
        ctk.CTkCheckBox(sb, text="Solo con alertas", variable=self.solo_alertas_var,
                        text_color=TEXT2, font=("Segoe UI", 11),
                        command=self._filtrar).pack(side="left", padx=14)

        self.lbl_scan = ctk.CTkLabel(sb, text="", font=("Segoe UI", 10), text_color=TEXT2)
        self.lbl_scan.pack(side="left", padx=10)

        # ── Cuerpo: tabla + panel ──
        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.pack(fill="both", expand=True, padx=8, pady=(0,8))

        # Tabla
        tbl_frame = ctk.CTkFrame(body, fg_color=BG2, corner_radius=6)
        tbl_frame.pack(side="left", fill="both", expand=True, padx=(0,4))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("F.Treeview",
            background=BG2, fieldbackground=BG2, foreground=TEXT,
            rowheight=30, borderwidth=0, font=("Segoe UI", 10))
        style.configure("F.Treeview.Heading",
            background=BG3, foreground=TEXT2,
            font=("Segoe UI", 9, "bold"), relief="flat", borderwidth=0)
        style.map("F.Treeview",
            background=[("selected", ROW_SEL)],
            foreground=[("selected", TEXT)])
        style.layout("F.Treeview", [("F.Treeview.treearea", {"sticky": "nswe"})])

        cols = ("estado","nombre","ip","ubicacion","paginas","consumibles","ts")
        self.tree = ttk.Treeview(tbl_frame, columns=cols, show="headings",
                                  style="F.Treeview", selectmode="browse")
        for col, hdr, w, stretch in [
            ("estado",     "Estado",       80,  False),
            ("nombre",     "Nombre",       190, True),
            ("ip",         "IP",           115, False),
            ("ubicacion",  "Ubicación",    120, False),
            ("paginas",    "Páginas",      75,  False),
            ("consumibles","Consumibles",  280, True),
            ("ts",         "Última lect.", 75,  False),
        ]:
            self.tree.heading(col, text=hdr,
                command=lambda c=col: self._sort(c))
            self.tree.column(col, width=w, anchor="w", stretch=stretch)

        self.tree.tag_configure("ok",      background=BG2,      foreground=TEXT)
        self.tree.tag_configure("alerta",  background="#29200a", foreground=WARN)
        self.tree.tag_configure("critico", background="#280a0a", foreground=CRIT)
        self.tree.tag_configure("offline", background=BG2,      foreground=OFFLINE)
        self.tree.tag_configure("alt_ok",  background=ROW_ALT,  foreground=TEXT)

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self._refrescar_sel())

        # Panel detalle
        self.panel = ctk.CTkFrame(body, fg_color=BG2, corner_radius=6, width=290)
        self.panel.pack(side="right", fill="y", padx=(4,0))
        self.panel.pack_propagate(False)
        self._panel_vacio()

        self._sort_col = None
        self._sort_rev = False

    # ── PANEL DETALLE ─────────────────────────────────────────────────────────
    def _panel_vacio(self):
        for w in self.panel.winfo_children(): w.destroy()
        ctk.CTkLabel(self.panel, text="🖨️", font=("Segoe UI", 36), text_color=TEXT2).pack(pady=(70,8))
        ctk.CTkLabel(self.panel, text="Selecciona un dispositivo\npara ver el detalle",
                     font=("Segoe UI", 12), text_color=TEXT2, justify="center").pack()

    def _panel_detalle(self, ip):
        for w in self.panel.winfo_children(): w.destroy()
        imp   = next((i for i in self.impresoras if i["ip"]==ip), None)
        if not imp: return
        cache = self.cache.get(ip, {})
        cons  = cache.get("consumibles")
        error = cache.get("error")
        ts    = cache.get("ts")
        estado= cache.get("estado","offline")

        col_e = {OFFLINE: "offline", OK: "ok", WARN: "alerta", CRIT: "critico"}
        color_map  = {"ok":OK,"alerta":WARN,"critico":CRIT,"offline":OFFLINE}
        label_map  = {"ok":"OK","alerta":"Alerta","critico":"Crítico","offline":"Offline"}
        color = color_map.get(estado, OFFLINE)
        label = label_map.get(estado, "—")

        # Header
        hdr = ctk.CTkFrame(self.panel, fg_color=BG3, corner_radius=6)
        hdr.pack(fill="x", padx=10, pady=(10,4))
        top = ctk.CTkFrame(hdr, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8,2))
        ctk.CTkLabel(top, text=imp["nombre"], font=("Segoe UI", 12, "bold"),
                     text_color=TEXT, wraplength=220, justify="left").pack(side="left", anchor="w")
        ctk.CTkLabel(top, text=f"● {label}", font=("Segoe UI", 10, "bold"),
                     text_color=color).pack(side="right")
        ctk.CTkLabel(hdr, text=ip, font=("Consolas", 10), text_color=TEXT2).pack(anchor="w", padx=10, pady=(0,8))

        # Info rows
        def fila(lbl, val):
            f = ctk.CTkFrame(self.panel, fg_color="transparent")
            f.pack(fill="x", padx=14, pady=1)
            ctk.CTkLabel(f, text=lbl, font=("Segoe UI", 10), text_color=TEXT2, width=75, anchor="w").pack(side="left")
            ctk.CTkLabel(f, text=val, font=("Segoe UI", 10, "bold"), text_color=TEXT, anchor="w", wraplength=180).pack(side="left")

        ctk.CTkLabel(self.panel, text="INFORMACIÓN", font=("Segoe UI", 8, "bold"),
                     text_color=TEXT2).pack(anchor="w", padx=14, pady=(10,2))
        fila("Ubicación:", imp.get("ubicacion","") or "—")
        fila("Comunidad:", imp.get("comunidad","") or self.cfg["comunidad_snmp"])
        fila("Lectura:",   ts.strftime("%H:%M:%S") if ts else "—")

        # Info extra SNMP
        info = cache.get("info", {})
        if info:
            ctk.CTkLabel(self.panel, text="DISPOSITIVO", font=("Segoe UI", 8, "bold"),
                         text_color=TEXT2).pack(anchor="w", padx=14, pady=(10,2))
            if info.get("modelo"):
                fila("Modelo:", info["modelo"][:35])
            if info.get("sys_nombre"):
                fila("Hostname:", info["sys_nombre"][:35])
            if info.get("serial"):
                fila("Serie:", info["serial"][:25])
            if info.get("paginas"):
                try:   pag_fmt = f"{int(info['paginas']):,}".replace(",",".")
                except: pag_fmt = info["paginas"]
                fila("Páginas:", pag_fmt)
            if info.get("estado_imp"):
                fila("Estado imp.:", ESTADO_IMP_MAP.get(info["estado_imp"], info["estado_imp"]))
            if info.get("bandeja_nivel") and info.get("bandeja_cap"):
                try:
                    bn = int(info["bandeja_nivel"])
                    bc = int(info["bandeja_cap"])
                    if bc > 0:
                        fila("Bandeja:", f"{bn}/{bc} hojas ({round(bn/bc*100)}%)")
                except: pass
            if info.get("sys_uptime"):
                fila("Uptime:", info["sys_uptime"][:30])

        # Consumibles
        ctk.CTkLabel(self.panel, text="CONSUMIBLES", font=("Segoe UI", 8, "bold"),
                     text_color=TEXT2).pack(anchor="w", padx=14, pady=(12,2))

        scroll = ctk.CTkScrollableFrame(self.panel, fg_color="transparent", height=340)
        scroll.pack(fill="both", expand=True, padx=8, pady=(0,4))

        if error:
            ctk.CTkLabel(scroll, text=f"⚠  {error}", font=("Segoe UI", 10),
                         text_color=WARN, wraplength=240, justify="left").pack(anchor="w", pady=6)
        elif cons:
            for c in cons:
                pct = c["porcentaje"]
                bc  = CRIT if pct<=self.cfg["umbral_critico"] else WARN if pct<=self.cfg["umbral_alerta"] else OK
                ctk.CTkLabel(scroll, text=c["componente"], font=("Segoe UI", 10),
                             text_color=TEXT, anchor="w").pack(fill="x", pady=(6,0))
                bar_bg = ctk.CTkFrame(scroll, fg_color=BG3, height=10, corner_radius=5)
                bar_bg.pack(fill="x", pady=(2,0))
                bar_bg.pack_propagate(False)
                if pct > 0:
                    ctk.CTkFrame(bar_bg, fg_color=bc, height=10, corner_radius=5,
                                 width=int(pct/100*240)).place(x=0, y=0, relheight=1)
                row_pct = ctk.CTkFrame(scroll, fg_color="transparent")
                row_pct.pack(fill="x")
                ctk.CTkLabel(row_pct, text=f"{pct}%", font=("Segoe UI", 9, "bold"),
                             text_color=bc).pack(side="right")
        else:
            ctk.CTkLabel(scroll, text="Sin datos disponibles", text_color=TEXT2,
                         font=("Segoe UI", 10)).pack(anchor="w", pady=6)

        # Botones panel
        bp = ctk.CTkFrame(self.panel, fg_color="transparent")
        bp.pack(fill="x", padx=10, pady=6)
        ctk.CTkButton(bp, text="↺  Refrescar", height=28, fg_color=ACCENT,
                      font=("Segoe UI", 11), command=self._refrescar_sel).pack(fill="x", pady=2)
        ctk.CTkButton(bp, text="↓  Exportar CSV", height=28, fg_color=BG3,
                      text_color=TEXT, font=("Segoe UI", 11),
                      command=lambda: self._exportar_csv(ip)).pack(fill="x", pady=2)

    # ── TABLA ─────────────────────────────────────────────────────────────────
    def _poblar_tabla(self):
        filtro = self.search_var.get().lower()
        solo   = self.solo_alertas_var.get()
        for row in self.tree.get_children():
            self.tree.delete(row)

        kpi = {"online":0,"offline":0,"criticos":0,"alertas":0}
        alt = False

        for imp in self.impresoras:
            ip = imp["ip"]
            if filtro and filtro not in ip.lower() and filtro not in imp["nombre"].lower():
                continue

            cache  = self.cache.get(ip, {})
            cons   = cache.get("consumibles")
            error  = cache.get("error")
            ts     = cache.get("ts")
            estado = cache.get("estado","pendiente")
            ts_str = ts.strftime("%H:%M") if ts else "—"

            if estado == "offline":   kpi["offline"]  += 1
            elif estado == "ok":      kpi["online"]   += 1
            elif estado == "alerta":  kpi["online"]   += 1;  kpi["alertas"]  += 1
            elif estado == "critico": kpi["online"]   += 1;  kpi["criticos"] += 1

            if solo and estado in ("ok","pendiente"):
                continue

            if error:
                cons_str = f"⚠  {error[:55]}"
            elif cons:
                cons_str = _formato_consumibles(cons, self.cfg["umbral_critico"], self.cfg["umbral_alerta"])
            elif estado == "pendiente":
                cons_str = "Pendiente de escaneo..."
            else:
                cons_str = "—"

            dot  = {"ok":"●","alerta":"●","critico":"●","offline":"○","pendiente":"…"}.get(estado,"?")
            elbl = {"ok":"OK","alerta":"Alerta","critico":"Crítico","offline":"Offline","pendiente":"—"}.get(estado,"")
            estado_str = f"{dot}  {elbl}"

            tag = estado if estado in ("ok","alerta","critico","offline") else "ok"
            if alt and tag == "ok":
                tag = "alt_ok"
            alt = not alt

            paginas_str = "—"
            if cache.get("info"):
                pag = cache["info"].get("paginas","")
                if pag:
                    try: paginas_str = f"{int(pag):,}".replace(",",".")
                    except: paginas_str = pag

            # Usar hostname SNMP si está disponible, sino el nombre configurado
            info_cache = cache.get("info", {})
            nombre_mostrar = info_cache.get("sys_nombre") or imp["nombre"]

            self.tree.insert("", "end", iid=ip, values=(
                estado_str, nombre_mostrar, ip,
                imp.get("ubicacion",""), paginas_str, cons_str, ts_str
            ), tags=(tag,))

        for k, v in kpi.items():
            self.kpi_vars[k].set(str(v))
        self.lbl_ts.configure(text=f"  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    def _filtrar(self):
        self._poblar_tabla()

    def _sort(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False
        idx = {"estado":0,"nombre":1,"ip":2,"ubicacion":3,"paginas":4,"consumibles":5,"ts":6}[col]
        rows = [(self.tree.set(k, col), k) for k in self.tree.get_children()]
        rows.sort(reverse=self._sort_rev)
        for i, (_, k) in enumerate(rows):
            self.tree.move(k, "", i)

    def _on_select(self, event):
        sel = self.tree.selection()
        if sel:
            self.sel_ip = sel[0]
            self._panel_detalle(self.sel_ip)

    # ── ESCANEO ───────────────────────────────────────────────────────────────
    def _refrescar_todo(self):
        self.cache.clear()
        self._poblar_tabla()
        if self._scan_thread and self._scan_thread.is_alive():
            return
        self._scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
        self._scan_thread.start()

    def _refrescar_sel(self):
        if not self.sel_ip: return
        self.cache.pop(self.sel_ip, None)
        ip = self.sel_ip
        def worker():
            imp = next((i for i in self.impresoras if i["ip"]==ip), {})
            com = imp.get("comunidad") or self.cfg["comunidad_snmp"]
            cons, err = obtener_consumibles(ip, com, self.cfg["timeout_snmp"])
            info = obtener_info_extra(ip, com, self.cfg["timeout_snmp"]) if not err else {}
            if err:
                est = "offline"
            else:
                tc = any(c["porcentaje"]<=self.cfg["umbral_critico"] for c in (cons or []))
                ta = any(c["porcentaje"]<=self.cfg["umbral_alerta"]  for c in (cons or []))
                est = "critico" if tc else "alerta" if ta else "ok"
                if cons: guardar_historial(ip, cons)
            self.cache[ip] = {"consumibles":cons,"error":err,"ts":datetime.now(),"estado":est,"info":info}
            self.after(0, self._poblar_tabla)
            if self.sel_ip == ip:
                self.after(0, lambda: self._panel_detalle(ip))
        threading.Thread(target=worker, daemon=True).start()

    def _scan_worker(self):
        total = len(self.impresoras)
        for i, imp in enumerate(self.impresoras):
            ip  = imp["ip"]
            com = imp.get("comunidad") or self.cfg["comunidad_snmp"]
            self.after(0, lambda t=f"Escaneando {i+1}/{total}: {ip}":
                       self.lbl_scan.configure(text=t))
            cons, err = obtener_consumibles(ip, com, self.cfg["timeout_snmp"])
            info = obtener_info_extra(ip, com, self.cfg["timeout_snmp"]) if not err else {}
            if err:
                est = "offline"
            else:
                tc = any(c["porcentaje"]<=self.cfg["umbral_critico"] for c in (cons or []))
                ta = any(c["porcentaje"]<=self.cfg["umbral_alerta"]  for c in (cons or []))
                est = "critico" if tc else "alerta" if ta else "ok"
                if cons: guardar_historial(ip, cons)
            self.cache[ip] = {"consumibles":cons,"error":err,"ts":datetime.now(),"estado":est,"info":info}
            self.after(0, self._poblar_tabla)
            if self.sel_ip == ip:
                self.after(0, lambda _ip=ip: self._panel_detalle(_ip))
        self.after(0, lambda: self.lbl_scan.configure(text="✔  Escaneo completado"))

    # ── AUTO-REFRESCO ─────────────────────────────────────────────────────────
    def _schedule_autoref(self):
        if self._autoref_job:
            self.after_cancel(self._autoref_job)
            self._autoref_job = None
        seg = self.cfg.get("autorefresh_seg", 0)
        if seg > 0:
            self._autoref_job = self.after(seg * 1000, self._tick_autoref)

    def _tick_autoref(self):
        self._refrescar_todo()
        self._schedule_autoref()

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def _añadir(self):
        d = DialogImpresora(self, self.cfg)
        self.wait_window(d)
        if d.resultado:
            ips = [i["ip"] for i in self.impresoras]
            if d.resultado["ip"] in ips:
                messagebox.showwarning("Duplicado", f"{d.resultado['ip']} ya existe.")
                return
            self.impresoras.append(d.resultado)
            guardar_json(DB_FILE, self.impresoras)
            self._poblar_tabla()
            ip = d.resultado["ip"]
            threading.Thread(target=lambda: self._escanear_one(ip), daemon=True).start()

    def _editar(self):
        if not self.sel_ip:
            messagebox.showinfo("", "Selecciona un dispositivo primero.")
            return
        imp = next((i for i in self.impresoras if i["ip"]==self.sel_ip), None)
        if not imp: return
        d = DialogImpresora(self, self.cfg, imp=imp)
        self.wait_window(d)
        if d.resultado:
            imp.update(d.resultado)
            guardar_json(DB_FILE, self.impresoras)
            self._poblar_tabla()
            self._panel_detalle(self.sel_ip)

    def _eliminar(self):
        if not self.sel_ip:
            messagebox.showinfo("", "Selecciona un dispositivo primero.")
            return
        imp = next((i for i in self.impresoras if i["ip"]==self.sel_ip), None)
        if not messagebox.askyesno("Eliminar", f"¿Eliminar '{imp['nombre']}' ({self.sel_ip})?"):
            return
        self.impresoras = [i for i in self.impresoras if i["ip"]!=self.sel_ip]
        self.cache.pop(self.sel_ip, None)
        guardar_json(DB_FILE, self.impresoras)
        self.sel_ip = None
        self._panel_vacio()
        self._poblar_tabla()

    def _escanear_one(self, ip):
        imp = next((i for i in self.impresoras if i["ip"]==ip), {})
        com = imp.get("comunidad") or self.cfg["comunidad_snmp"]
        cons, err = obtener_consumibles(ip, com, self.cfg["timeout_snmp"])
        info = obtener_info_extra(ip, com, self.cfg["timeout_snmp"]) if not err else {}
        if err:
            est = "offline"
        else:
            tc = any(c["porcentaje"]<=self.cfg["umbral_critico"] for c in (cons or []))
            ta = any(c["porcentaje"]<=self.cfg["umbral_alerta"]  for c in (cons or []))
            est = "critico" if tc else "alerta" if ta else "ok"
            if cons: guardar_historial(ip, cons)
        self.cache[ip] = {"consumibles":cons,"error":err,"ts":datetime.now(),"estado":est,"info":info}
        self.after(0, self._poblar_tabla)

    # ── ESCANEO RED ───────────────────────────────────────────────────────────
    def _escanear_red(self):
        ips_existentes = [i["ip"] for i in self.impresoras]
        d = DialogEscaneoRed(self, self.cfg, ips_existentes)
        self.wait_window(d)
        if not d.resultado:
            return
        añadidas = 0
        ips_ya = {i["ip"] for i in self.impresoras}
        for imp in d.resultado:
            if imp["ip"] in ips_ya:
                continue
            self.impresoras.append(imp)
            añadidas += 1
        if añadidas:
            guardar_json(DB_FILE, self.impresoras)
            self._poblar_tabla()
            # Escanear consumibles de las recién añadidas en background
            for imp in d.resultado:
                ip = imp["ip"]
                threading.Thread(target=lambda _ip=ip: self._escanear_one(_ip),
                                 daemon=True).start()
            messagebox.showinfo("Añadidas", f"Se añadieron {añadidas} impresoras.")

    # ── CONFIG ────────────────────────────────────────────────────────────────
    def _abrir_config(self):
        def on_save():
            self._schedule_autoref()
            self._poblar_tabla()
        DialogConfig(self, self.cfg, on_save)

    # ── EXPORTAR ──────────────────────────────────────────────────────────────
    def _recopilar_filas(self, ip=None):
        filas = []
        ips = [ip] if ip else [i["ip"] for i in self.impresoras]
        for _ip in ips:
            imp   = next((i for i in self.impresoras if i["ip"]==_ip), {})
            cache = self.cache.get(_ip, {})
            info  = cache.get("info", {})
            estado= cache.get("estado","")
            ts_s  = cache["ts"].strftime("%Y-%m-%d %H:%M:%S") if cache.get("ts") else ""
            pag   = info.get("paginas","—")
            modelo= info.get("modelo","—")
            serial= info.get("serial","—")
            uptime= info.get("sys_uptime","—")
            cons  = cache.get("consumibles") or []
            if cons:
                for c in cons:
                    filas.append({
                        "IP": _ip, "Nombre": imp.get("nombre",""),
                        "Ubicacion": imp.get("ubicacion",""),
                        "Modelo": modelo, "Serie": serial,
                        "Paginas": pag, "Uptime": uptime,
                        "Consumible": c["componente"], "Porcentaje": c["porcentaje"],
                        "Estado": estado.upper(), "Timestamp": ts_s
                    })
            else:
                filas.append({
                    "IP": _ip, "Nombre": imp.get("nombre",""),
                    "Ubicacion": imp.get("ubicacion",""),
                    "Modelo": modelo, "Serie": serial,
                    "Paginas": pag, "Uptime": uptime,
                    "Consumible": "—", "Porcentaje": "—",
                    "Estado": estado.upper() or "SIN DATOS", "Timestamp": ts_s
                })
        return filas

    def _exportar_csv(self, ip=None):
        from tkinter.filedialog import asksaveasfilename
        path = asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV","*.csv")],
            initialfile=f"reporte_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
        if not path: return
        filas = self._recopilar_filas(ip)
        if not filas:
            messagebox.showinfo("", "Sin datos para exportar.")
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=filas[0].keys())
            w.writeheader(); w.writerows(filas)
        messagebox.showinfo("Exportado", f"CSV guardado en:\n{path}")

    def _exportar_excel(self, ip=None):
        from tkinter.filedialog import asksaveasfilename
        try:
            import openpyxl
            from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
        except ImportError:
            messagebox.showerror("Error", "Instala openpyxl:\npip install openpyxl")
            return

        path = asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel","*.xlsx")],
            initialfile=f"reporte_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
        if not path: return

        filas = self._recopilar_filas(ip)
        if not filas:
            messagebox.showinfo("", "Sin datos para exportar.")
            return

        wb = openpyxl.Workbook()

        # ── Hoja 1: Resumen por dispositivo ──────────────────────────────────
        ws1 = wb.active
        ws1.title = "Resumen"
        ws1.sheet_view.showGridLines = False
        ws1.freeze_panes = "A2"

        # Colores
        fill_header  = PatternFill("solid", fgColor="1A1D2E")
        fill_ok      = PatternFill("solid", fgColor="1A3A2A")
        fill_alerta  = PatternFill("solid", fgColor="3A2A00")
        fill_critico = PatternFill("solid", fgColor="3A0A0A")
        fill_offline = PatternFill("solid", fgColor="2A2A2A")
        fill_alt     = PatternFill("solid", fgColor="1E2238")

        font_header = Font(name="Segoe UI", bold=True, color="E8EAF0", size=10)
        font_text   = Font(name="Segoe UI", color="E8EAF0", size=10)
        font_ok     = Font(name="Segoe UI", color="2ECC71", bold=True, size=10)
        font_warn   = Font(name="Segoe UI", color="F39C12", bold=True, size=10)
        font_crit   = Font(name="Segoe UI", color="E74C3C", bold=True, size=10)
        font_off    = Font(name="Segoe UI", color="6C7A99", size=10)
        align_c     = Alignment(horizontal="center", vertical="center")
        align_l     = Alignment(horizontal="left",   vertical="center")

        thin = Side(style="thin", color="353860")
        border = Border(bottom=thin)

        # Cabecera resumen
        hdrs1 = ["IP","Nombre","Ubicación","Modelo","Serie","Páginas","Estado","Última lect."]
        ws1.row_dimensions[1].height = 22
        for ci, h in enumerate(hdrs1, 1):
            c = ws1.cell(row=1, column=ci, value=h)
            c.fill = fill_header; c.font = font_header; c.alignment = align_c

        # Datos resumen (una fila por impresora)
        vistos = set()
        fila_num = 2
        for f in filas:
            ip_f = f["IP"]
            if ip_f in vistos: continue
            vistos.add(ip_f)
            estado_f = f["Estado"]
            fill_f = {"OK":fill_ok,"ALERTA":fill_alerta,"CRITICO":fill_critico}.get(estado_f, fill_offline)
            font_e = {"OK":font_ok,"ALERTA":font_warn,"CRITICO":font_crit}.get(estado_f, font_off)
            vals = [ip_f, f["Nombre"], f["Ubicacion"], f["Modelo"], f["Serie"],
                    f["Paginas"], estado_f, f["Timestamp"]]
            ws1.row_dimensions[fila_num].height = 20
            for ci, v in enumerate(vals, 1):
                c = ws1.cell(row=fila_num, column=ci, value=v)
                c.fill = fill_f
                c.font = font_e if ci==7 else font_text
                c.alignment = align_c if ci in (1,6,7,8) else align_l
                c.border = border
            fila_num += 1

        anchos1 = [16,28,20,30,18,12,12,18]
        for ci, w in enumerate(anchos1, 1):
            ws1.column_dimensions[get_column_letter(ci)].width = w

        # ── Hoja 2: Consumibles detalle ───────────────────────────────────────
        ws2 = wb.create_sheet("Consumibles")
        ws2.sheet_view.showGridLines = False
        ws2.freeze_panes = "A2"

        hdrs2 = ["IP","Nombre","Ubicación","Consumible","Porcentaje","Estado","Timestamp"]
        ws2.row_dimensions[1].height = 22
        for ci, h in enumerate(hdrs2, 1):
            c = ws2.cell(row=1, column=ci, value=h)
            c.fill = fill_header; c.font = font_header; c.alignment = align_c

        alt = False
        for fi, f in enumerate(filas, 2):
            pct = f["Porcentaje"]
            try: pct_int = int(pct)
            except: pct_int = -1

            if pct_int >= 0:
                if pct_int <= self.cfg["umbral_critico"]:
                    fill_f, font_p = fill_critico, font_crit
                elif pct_int <= self.cfg["umbral_alerta"]:
                    fill_f, font_p = fill_alerta, font_warn
                else:
                    fill_f, font_p = (fill_alt if alt else fill_ok), font_ok
            else:
                fill_f, font_p = fill_offline, font_off

            alt = not alt
            vals2 = [f["IP"],f["Nombre"],f["Ubicacion"],f["Consumible"],
                     f"{pct}%" if pct_int>=0 else pct, f["Estado"], f["Timestamp"]]
            ws2.row_dimensions[fi].height = 20
            for ci, v in enumerate(vals2, 1):
                c = ws2.cell(row=fi, column=ci, value=v)
                c.fill = fill_f
                c.font = font_p if ci==5 else font_text
                c.alignment = align_c if ci in (1,5,6,7) else align_l
                c.border = border

        anchos2 = [16,28,20,28,13,12,18]
        for ci, w in enumerate(anchos2, 1):
            ws2.column_dimensions[get_column_letter(ci)].width = w

        # ── Hoja 3: Solo alertas ──────────────────────────────────────────────
        ws3 = wb.create_sheet("Alertas")
        ws3.sheet_view.showGridLines = False
        ws3.freeze_panes = "A2"
        for ci, h in enumerate(hdrs2, 1):
            c = ws3.cell(row=1, column=ci, value=h)
            c.fill = fill_header; c.font = font_header; c.alignment = align_c

        fila_alerta = 2
        for f in filas:
            pct = f["Porcentaje"]
            try: pct_int = int(pct)
            except: pct_int = 101
            if pct_int > self.cfg["umbral_alerta"] and f["Estado"] not in ("OFFLINE","SIN DATOS"):
                continue
            fill_f = fill_critico if pct_int <= self.cfg["umbral_critico"] else fill_alerta
            font_p = font_crit    if pct_int <= self.cfg["umbral_critico"] else font_warn
            vals3 = [f["IP"],f["Nombre"],f["Ubicacion"],f["Consumible"],
                     f"{pct}%" if pct_int<=100 else pct, f["Estado"], f["Timestamp"]]
            ws3.row_dimensions[fila_alerta].height = 20
            for ci, v in enumerate(vals3, 1):
                c = ws3.cell(row=fila_alerta, column=ci, value=v)
                c.fill = fill_f
                c.font = font_p if ci==5 else font_text
                c.alignment = align_c if ci in (1,5,6,7) else align_l
                c.border = border
            fila_alerta += 1

        for ci, w in enumerate(anchos2, 1):
            ws3.column_dimensions[get_column_letter(ci)].width = w

        wb.save(path)
        messagebox.showinfo("Exportado", f"Excel guardado en:\n{path}\n\nHojas: Resumen · Consumibles · Alertas")

    def _exportar_todo(self):
        # Preguntar formato
        from tkinter.simpledialog import askstring
        fmt = askstring("Formato", "Exportar como:\n  1 → Excel (.xlsx)\n  2 → CSV (.csv)", parent=self)
        if fmt == "1":
            self._exportar_excel()
        elif fmt == "2":
            self._exportar_csv()

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()