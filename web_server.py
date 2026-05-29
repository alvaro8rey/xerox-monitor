"""
Fleet Monitor Pro — servidor web de solo lectura.
Arranca con: python web_server.py
Acceso desde la red: http://<ip-servidor>:5050
"""
import json, os, threading
from datetime import datetime
from flask import Flask, jsonify, render_template_string

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
DB_FILE           = os.path.join(BASE_DIR, "impresoras.json")
HISTORIAL_FILE    = os.path.join(BASE_DIR, "historial.json")
CONTABILIDAD_FILE = os.path.join(BASE_DIR, "contabilidad_xsa.json")
ALERTAS_FILE      = os.path.join(BASE_DIR, "alertas.json")
CONFIG_FILE       = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {"umbral_critico": 15, "umbral_alerta": 20}

app = Flask(__name__)

def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

# ── API ────────────────────────────────────────────────────────────────────────

@app.route("/api/impresoras")
def api_impresoras():
    cfg       = {**DEFAULT_CONFIG, **_load(CONFIG_FILE, {})}
    impres    = _load(DB_FILE, [])
    historial = _load(HISTORIAL_FILE, {})
    alertas   = _load(ALERTAS_FILE, {})
    crit      = cfg["umbral_critico"]
    alerta    = cfg["umbral_alerta"]

    out = []
    for imp in impres:
        if isinstance(imp, str):
            imp = {"ip": imp, "nombre": imp, "ubicacion": ""}
        ip        = imp.get("ip", "")
        registros = historial.get(ip, [])
        ultimo    = registros[-1] if registros else None
        cons      = ultimo["consumibles"] if ultimo else None
        ts        = ultimo["ts"]         if ultimo else None

        estado = "sin datos"
        cons_list = []
        if cons:
            niveles = [c.get("porcentaje", 100) for c in cons]
            min_niv = min(niveles) if niveles else 100
            estado  = "critico" if min_niv <= crit else ("alerta" if min_niv <= alerta else "ok")
            for c in cons:
                pct = c.get("porcentaje", -1)
                cons_list.append({
                    "nombre": c.get("componente", c.get("descripcion", c.get("nombre", ""))),
                    "pct":    pct,
                    "estado": "critico" if pct <= crit else ("alerta" if pct <= alerta else "ok"),
                })
            cons_list.sort(key=lambda x: x["pct"])

        nombre = (ultimo.get("nombre") if ultimo else None) or imp.get("nombre", ip)

        # Alertas activas guardadas por la app de escritorio
        alerta_ip = alertas.get(ip, {})
        alerts_list = alerta_ip.get("alerts", [])

        out.append({
            "nombre":    nombre,
            "ip":        ip,
            "ubicacion": imp.get("ubicacion", ""),
            "estado":    estado,
            "ts":        ts,
            "consumibles": cons_list,
            "alerts":    alerts_list,
        })

    out.sort(key=lambda x: (
        0 if x["estado"] == "critico" else
        1 if x["estado"] == "alerta"  else
        2 if x["estado"] == "ok"      else 3
    ))
    resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/contabilidad")
def api_contabilidad():
    datos = _load(CONTABILIDAD_FILE, {})
    DEPARTAMENTOS = {d.lower() for d in (
        "ADMINISTRACIÓN","DIRECCIÓN","VICEDIRECCIÓN","SECRETARÍA",
        "XEFATURA DE ESTUDOS","RECURSOS","ALEMÁN","PORTUGUÉS",
        "FRANCÉS","ITALIANO","GALEGO","PLAMBE_EDLG","INGLÉS","SUSTITUTO",
    )}
    EXCLUIR = {u.lower() for u in (
        "System User","CUENTA GENERAL","Customer Service Engineer Account",
        "Xerox Administrative Group","Admin","Diagnostics","Local System User",
        "Print Exceptions Group","10.55.161.196","Guest",
        "IPP Exception Group","IPP Exception User",
    )}

    result = []
    for ip, bloque in datos.items():
        nombre_imp = bloque.get("nombre_impresora", ip)
        snapshots  = bloque.get("snapshots", {})
        sorted_keys = sorted(snapshots.keys())
        if not sorted_keys:
            continue

        result.append({
            "ip":           ip,
            "nombre":       nombre_imp,
            "meses":        sorted_keys,
            "snapshots":    snapshots,
            "departamentos": list(DEPARTAMENTOS),
            "excluir":       list(EXCLUIR),
        })
    resp = jsonify(result)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── HTML ───────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fleet Monitor Pro</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1d2e;color:#e8eaf0;font-family:'Segoe UI',sans-serif;font-size:14px}
body.locked header,body.locked nav,body.locked section{visibility:hidden}
a{color:inherit;text-decoration:none}

/* HEADER */
header{background:#232640;padding:12px 20px;display:flex;align-items:center;gap:16px;border-bottom:1px solid #353860;position:sticky;top:0;z-index:100}
header h1{font-size:17px;font-weight:700}
header .ts{color:#8b92b8;font-size:12px;margin-left:auto}
.badge{background:#2c3057;border-radius:6px;padding:4px 12px;font-size:12px;display:flex;flex-direction:column;align-items:center;min-width:70px}
.badge .num{font-size:20px;font-weight:700;line-height:1.2}
.badge .lbl{color:#8b92b8;font-size:10px}
.col-ok{color:#2ecc71} .col-warn{color:#f39c12} .col-crit{color:#e74c3c} .col-off{color:#6c7a99}

/* TABS */
nav{background:#232640;display:flex;gap:2px;padding:0 16px;border-bottom:1px solid #353860}
nav button{background:none;border:none;color:#8b92b8;padding:10px 18px;cursor:pointer;font-size:13px;font-family:inherit;border-bottom:2px solid transparent}
nav button.active{color:#e8eaf0;border-bottom-color:#4f8ef7}
nav button:hover{color:#e8eaf0}

/* SECTIONS */
section{display:none;padding:16px 20px}
section.active{display:block}

/* KPI row */
.kpi-row{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap}

/* TABLES */
table{width:100%;border-collapse:collapse}
th{background:#2c3057;color:#8b92b8;font-size:11px;font-weight:600;text-transform:uppercase;padding:8px 10px;text-align:left;position:sticky;top:52px}
td{padding:7px 10px;border-bottom:1px solid #1e2238;vertical-align:middle}
tr:hover td{background:#1e2238}
tr.crit td{color:#e74c3c}
tr.warn td{color:#f39c12}
tr.off td{color:#6c7a99}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.dot-ok{background:#2ecc71} .dot-warn{background:#f39c12} .dot-crit{background:#e74c3c} .dot-off{background:#6c7a99}

/* CONSUMIBLES */
.cons-bars{display:flex;flex-direction:column;gap:3px;min-width:200px}
.cons-item{display:flex;align-items:center;gap:6px;font-size:12px}
.bar-bg{flex:1;background:#1a1d2e;border-radius:3px;height:6px;min-width:80px}
.bar-fill{height:6px;border-radius:3px;transition:width .3s}
.bar-ok{background:#2ecc71} .bar-warn{background:#f39c12} .bar-crit{background:#e74c3c}
.cons-lbl{width:150px;min-width:150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#c8cae0}
.cons-pct{width:34px;text-align:right;font-size:11px}

/* ALERTAS */
.alerts-cell{display:flex;flex-direction:column;gap:2px}
.alert-badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;padding:2px 7px;border-radius:4px;white-space:nowrap}
.alert-crit{background:#3d0f0f;color:#e74c3c}
.alert-warn{background:#2e1e00;color:#f39c12}
.alert-info{background:#0f1e3d;color:#7ab4f5}

/* CONTABILIDAD */
.cont-controls{display:flex;gap:10px;margin-bottom:12px;align-items:center;flex-wrap:wrap}
.cont-controls label{color:#8b92b8;font-size:12px}
select{background:#2c3057;border:1px solid #353860;color:#e8eaf0;padding:5px 10px;border-radius:6px;font-size:13px;font-family:inherit}
.sec-header td{background:#1c2a3a;color:#7ab4f5;font-weight:700;font-size:12px;cursor:pointer}
.total-row td{background:#2c3057;font-weight:700;color:#4f8ef7}

/* PIN MODAL */
.pin-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:500;align-items:center;justify-content:center}
.pin-overlay.show{display:flex}
.pin-box{background:#232640;border:1px solid #353860;border-radius:12px;padding:32px 36px;text-align:center;min-width:280px}
.pin-box h2{font-size:15px;margin-bottom:6px}
.pin-box p{color:#8b92b8;font-size:12px;margin-bottom:20px}
.pin-dots{display:flex;justify-content:center;gap:12px;margin-bottom:20px}
.pin-dot{width:14px;height:14px;border-radius:50%;background:#2c3057;border:2px solid #353860;transition:background .15s}
.pin-dot.filled{background:#4f8ef7;border-color:#4f8ef7}
.pin-keypad{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;max-width:200px;margin:0 auto}
.pin-key{background:#2c3057;border:none;color:#e8eaf0;font-size:18px;font-family:inherit;padding:14px;border-radius:8px;cursor:pointer;transition:background .15s}
.pin-key:hover{background:#353860}
.pin-key:active{background:#4f8ef7}
.pin-err{color:#e74c3c;font-size:12px;min-height:18px;margin-top:8px}

/* LOADER */
.loader{text-align:center;padding:40px;color:#8b92b8}
.spinner{display:inline-block;width:28px;height:28px;border:3px solid #353860;border-top-color:#4f8ef7;border-radius:50%;animation:spin .8s linear infinite;vertical-align:middle;margin-right:8px}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body class="locked">

<!-- PIN MODAL — bloquea toda la página hasta autenticarse -->
<div class="pin-overlay show" id="pin-overlay">
  <div class="pin-box">
    <h2>🔒 Fleet Monitor Pro</h2>
    <p>Introduce el PIN para acceder</p>
    <div class="pin-dots" id="pin-dots">
      <div class="pin-dot" id="pd0"></div>
      <div class="pin-dot" id="pd1"></div>
      <div class="pin-dot" id="pd2"></div>
      <div class="pin-dot" id="pd3"></div>
    </div>
    <div class="pin-keypad">
      <button class="pin-key" onclick="pinKey('1')">1</button>
      <button class="pin-key" onclick="pinKey('2')">2</button>
      <button class="pin-key" onclick="pinKey('3')">3</button>
      <button class="pin-key" onclick="pinKey('4')">4</button>
      <button class="pin-key" onclick="pinKey('5')">5</button>
      <button class="pin-key" onclick="pinKey('6')">6</button>
      <button class="pin-key" onclick="pinKey('7')">7</button>
      <button class="pin-key" onclick="pinKey('8')">8</button>
      <button class="pin-key" onclick="pinKey('9')">9</button>
      <button class="pin-key" onclick="pinKey('back')" style="font-size:14px">⌫</button>
      <button class="pin-key" onclick="pinKey('0')">0</button>
      <button class="pin-key" onclick="pinKey('clear')" style="font-size:12px">C</button>
    </div>
    <div class="pin-err" id="pin-err"></div>
  </div>
</div>

<header>
  <span style="font-size:20px">🖨</span>
  <h1>Fleet Monitor Pro</h1>
  <div style="display:flex;gap:8px" id="kpi-badges"></div>
  <span class="ts" id="last-update"></span>
</header>

<nav>
  <button class="active" onclick="showTab('impresoras',this)">Impresoras</button>
  <button onclick="showTab('contabilidad',this)">Contabilidad</button>
</nav>

<section id="tab-impresoras" class="active">
  <div id="imp-table-wrap"><div class="loader"><span class="spinner"></span>Cargando datos...</div></div>
</section>

<section id="tab-contabilidad">
  <div class="cont-controls">
    <label>Impresora:</label>
    <select id="sel-imp" onchange="updateMesOptions();renderContabilidad()"></select>
    <label>Mes:</label>
    <select id="sel-mes" onchange="renderContabilidad()"></select>
    <label>Vista:</label>
    <select id="sel-vista" onchange="renderContabilidad()">
      <option value="Acumulado">Acumulado</option>
      <option value="Mensual">Mensual</option>
    </select>
  </div>
  <div id="cont-table-wrap"><div class="loader"><span class="spinner"></span>Cargando...</div></div>
</section>

<script>
let _impData  = [];
let _contData = [];
let _pinUnlocked = false;
let _pinBuffer   = '';
const PIN_CORRECT = '2026';

// ── PIN ───────────────────────────────────────────────────────────────────────
function pinKey(k) {
  if (k === 'back')      _pinBuffer = _pinBuffer.slice(0, -1);
  else if (k === 'clear') _pinBuffer = '';
  else if (_pinBuffer.length < 4) _pinBuffer += k;
  updatePinDots();
  document.getElementById('pin-err').textContent = '';
  if (_pinBuffer.length === 4) {
    if (_pinBuffer === PIN_CORRECT) {
      _pinUnlocked = true;
      document.getElementById('pin-overlay').classList.remove('show');
      document.body.classList.remove('locked');
      loadImpresoras();
      loadContabilidad();
    } else {
      document.getElementById('pin-err').textContent = 'PIN incorrecto';
      setTimeout(() => { _pinBuffer = ''; updatePinDots(); }, 700);
    }
  }
}

function updatePinDots() {
  for (let i = 0; i < 4; i++)
    document.getElementById('pd' + i).classList.toggle('filled', i < _pinBuffer.length);
}

document.addEventListener('keydown', e => {
  if (!document.getElementById('pin-overlay').classList.contains('show')) return;
  if (e.key >= '0' && e.key <= '9') pinKey(e.key);
  else if (e.key === 'Backspace') pinKey('back');
  else if (e.key === 'Escape') {}  // no se puede cerrar sin PIN
});

// ── TABS ──────────────────────────────────────────────────────────────────────
function showTab(name, btn) {
  document.querySelectorAll('section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
}

// ── IMPRESORAS ────────────────────────────────────────────────────────────────
async function loadImpresoras() {
  try {
    const r = await fetch('/api/impresoras');
    _impData = await r.json();
    renderImpresoras();
  } catch(e) {
    document.getElementById('imp-table-wrap').innerHTML =
      '<div class="loader">Error cargando datos: ' + e + '</div>';
  }
}

function renderImpresoras() {
  const data = _impData;
  let ok=0, warn=0, crit=0, off=0;
  data.forEach(d => {
    if(d.estado==='ok') ok++;
    else if(d.estado==='alerta') warn++;
    else if(d.estado==='critico') crit++;
    else off++;
  });
  document.getElementById('kpi-badges').innerHTML = `
    <div class="badge"><span class="num col-ok">${ok}</span><span class="lbl">En línea</span></div>
    <div class="badge"><span class="num col-off">${off}</span><span class="lbl">Sin datos</span></div>
    <div class="badge"><span class="num col-crit">${crit}</span><span class="lbl">Crítico</span></div>
    <div class="badge"><span class="num col-warn">${warn}</span><span class="lbl">Alerta</span></div>
  `;
  document.getElementById('last-update').textContent =
    'Actualizado: ' + new Date().toLocaleTimeString('es-ES');

  let rows = data.map(d => {
    const cls    = d.estado==='critico'?'crit':d.estado==='alerta'?'warn':d.estado==='sin datos'?'off':'';
    const dotCls = d.estado==='critico'?'dot-crit':d.estado==='alerta'?'dot-warn':d.estado==='sin datos'?'dot-off':'dot-ok';
    const ts     = d.ts ? d.ts.slice(0,16) : '—';

    const consBars = d.consumibles.length ? `
      <div class="cons-bars">
        ${d.consumibles.slice(0,6).map(c => `
          <div class="cons-item">
            <span class="cons-lbl">${esc(c.nombre)}</span>
            <div class="bar-bg"><div class="bar-fill bar-${c.estado}" style="width:${Math.max(0,c.pct)}%"></div></div>
            <span class="cons-pct ${c.estado==='critico'?'col-crit':c.estado==='alerta'?'col-warn':''}">${c.pct>=0?c.pct+'%':'?'}</span>
          </div>`).join('')}
      </div>` : '<span style="color:#6c7a99">Sin datos</span>';

    const alertBadges = (d.alerts||[]).map(a => {
      const cls2 = a.nivel==='critical'?'alert-crit':a.nivel==='warning'?'alert-warn':'alert-info';
      const ico  = a.nivel==='critical'?'🔴':a.nivel==='warning'?'🟡':'🔵';
      return `<span class="alert-badge ${cls2}">${ico} ${esc(a.texto)}</span>`;
    }).join('');
    const alertsCell = alertBadges
      ? `<div class="alerts-cell">${alertBadges}</div>`
      : '<span style="color:#6c7a99;font-size:12px">—</span>';

    return `<tr class="${cls}">
      <td><span class="dot ${dotCls}"></span>${esc(d.nombre)}</td>
      <td style="color:#8b92b8">${esc(d.ip)}</td>
      <td style="color:#8b92b8">${esc(d.ubicacion||'')}</td>
      <td>${consBars}</td>
      <td>${alertsCell}</td>
      <td style="color:#6c7a99;font-size:12px">${ts}</td>
    </tr>`;
  }).join('');

  document.getElementById('imp-table-wrap').innerHTML = `
    <table>
      <thead><tr>
        <th>Nombre</th><th>IP</th><th>Ubicación</th>
        <th>Consumibles</th><th>Alertas</th><th>Última lectura</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── CONTABILIDAD ──────────────────────────────────────────────────────────────
async function loadContabilidad() {
  try {
    const r = await fetch('/api/contabilidad');
    _contData = await r.json();
    populateContSelectors();
    renderContabilidad();
  } catch(e) {
    document.getElementById('cont-table-wrap').innerHTML =
      '<div class="loader">Error: ' + e + '</div>';
  }
}

function populateContSelectors() {
  const selImp = document.getElementById('sel-imp');
  selImp.innerHTML = _contData.map((d,i) =>
    `<option value="${i}">${esc(d.nombre)}</option>`).join('');
  updateMesOptions();
}

function updateMesOptions() {
  const idx = parseInt(document.getElementById('sel-imp').value||'0');
  const imp = _contData[idx];
  if (!imp) return;
  const selMes = document.getElementById('sel-mes');
  const meses = [...imp.meses].reverse();
  selMes.innerHTML = '<option value="Acumulado">Acumulado</option>' +
    meses.map(m => `<option value="${m}">${mesLabel(m)}</option>`).join('');
}

function mesLabel(key) {
  const meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                 'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const [y, m] = key.split('-');
  return `${meses[parseInt(m)-1]} ${y}`;
}

function renderContabilidad() {
  const idx   = parseInt(document.getElementById('sel-imp').value||'0');
  const mesV  = document.getElementById('sel-mes').value;
  const vista = document.getElementById('sel-vista').value;
  const imp   = _contData[idx];
  if (!imp) return;

  const sorted = [...imp.meses].sort();
  const DEPTOS = new Set(imp.departamentos.map(d=>d.toLowerCase()));
  const EXCL   = new Set(imp.excluir.map(d=>d.toLowerCase()));

  let curKey, prevKey = null;
  if (mesV === 'Acumulado' || vista === 'Acumulado') {
    curKey = sorted[sorted.length-1];
  } else {
    curKey = sorted.includes(mesV) ? mesV : sorted[sorted.length-1];
    const idx2 = sorted.indexOf(curKey);
    if (idx2 > 0) prevKey = sorted[idx2-1];
  }
  if (!curKey) {
    document.getElementById('cont-table-wrap').innerHTML = '<div class="loader">Sin snapshots</div>';
    return;
  }

  const curSnap  = imp.snapshots[curKey]  || {usuarios:[]};
  const prevSnap = prevKey ? imp.snapshots[prevKey] : null;
  const prevMap  = prevSnap ? Object.fromEntries(prevSnap.usuarios.map(u=>[u.usuario,u])) : {};

  let deptos=[], users=[];
  for (const u of curSnap.usuarios) {
    if (EXCL.has(u.usuario.toLowerCase())) continue;
    const uid = u.id||'';
    let ib=u.imp_bw, ic=u.imp_color, cb=u.cop_bw, cc=u.cop_color;
    if (prevKey && prevMap[u.usuario]) {
      const p = prevMap[u.usuario];
      ib=Math.max(0,ib-p.imp_bw); ic=Math.max(0,ic-p.imp_color);
      cb=Math.max(0,cb-p.cop_bw); cc=Math.max(0,cc-p.cop_color);
    }
    const total = ib+ic+cb+cc;
    const label = uid ? `${u.usuario} (${uid})` : u.usuario;
    const row = {label, ib, ic, cb, cc, total};
    if (DEPTOS.has(u.usuario.toLowerCase())) deptos.push(row);
    else users.push(row);
  }
  deptos.sort((a,b)=>b.total-a.total);
  users.sort((a,b)=>b.total-a.total);

  const hasColor = [...deptos,...users].some(r=>r.ic>0||r.cc>0);
  const colColor = hasColor ? `<th>Imp. Color</th><th>Cop. Color</th>` : '';

  function fRow(r) {
    const color = hasColor ? `<td>${r.ic||'—'}</td><td>${r.cc||'—'}</td>` : '';
    return `<tr><td>${esc(r.label)}</td><td>${r.ib||'—'}</td>${color}<td>${r.cb||'—'}</td><td>${r.total||'—'}</td></tr>`;
  }

  if (!renderContabilidad._collapsed) renderContabilidad._collapsed = {};
  const _col = renderContabilidad._collapsed;

  function secHeader(key, titulo) {
    const cols = 4 + (hasColor?2:0);
    const icono = _col[key] ? '▶' : '▼';
    return `<tr class="sec-header" onclick="toggleSection('${key}')">
      <td colspan="${cols}">${icono}&nbsp;&nbsp;${titulo}</td></tr>`;
  }
  function secRows(key, filas) {
    return _col[key] ? '' : filas.map(r => fRow(r)).join('');
  }

  const all = [...deptos,...users];
  const totColor = hasColor ?
    `<td>${all.reduce((s,r)=>s+r.ic,0)||'—'}</td><td>${all.reduce((s,r)=>s+r.cc,0)||'—'}</td>` : '';
  const totalRow = `<tr class="total-row">
    <td>TOTAL</td><td>${all.reduce((s,r)=>s+r.ib,0)||'—'}</td>${totColor}
    <td>${all.reduce((s,r)=>s+r.cb,0)||'—'}</td><td>${all.reduce((s,r)=>s+r.total,0)||'—'}</td>
  </tr>`;

  const titulo = mesV==='Acumulado' ? 'Acumulado' : mesLabel(curKey);
  document.getElementById('cont-table-wrap').innerHTML = `
    <p style="color:#8b92b8;font-size:12px;margin-bottom:8px">
      ${esc(imp.nombre)} — ${titulo} — ${vista}
      &nbsp;·&nbsp; snapshot: ${curSnap.ts||'?'}
      ${prevKey?'&nbsp;·&nbsp; mes anterior: '+mesLabel(prevKey):''}
    </p>
    <table>
      <thead><tr><th>Usuario</th><th>Imp. B/N</th>${colColor}<th>Cop. B/N</th><th>Total</th></tr></thead>
      <tbody>
        ${deptos.length ? secHeader('deptos','DEPARTAMENTOS ('+deptos.length+')') + secRows('deptos',deptos) : ''}
        ${users.length  ? secHeader('users', 'USUARIOS ('    +users.length +')')  + secRows('users', users)  : ''}
        ${totalRow}
      </tbody>
    </table>`;
}

function toggleSection(key) {
  if (!renderContabilidad._collapsed) renderContabilidad._collapsed = {};
  renderContabilidad._collapsed[key] = !renderContabilidad._collapsed[key];
  renderContabilidad();
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── AUTO REFRESH ──────────────────────────────────────────────────────────────
// Carga inicial tras PIN — si se carga antes del PIN, se lanza desde pinKey()
// setInterval de refresco solo cuando ya estamos autenticados
setInterval(() => { if (_pinUnlocked) loadImpresoras(); }, 30000);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)


if __name__ == "__main__":
    import socket
    try:
        ip_local = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip_local = "localhost"
    print(f"\n  Fleet Monitor Pro — Servidor web")
    print(f"  Local:  http://localhost:5050")
    print(f"  Red:    http://{ip_local}:5050")
    print(f"\n  Ctrl+C para detener\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
