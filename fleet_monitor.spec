# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para Fleet Monitor Pro
# Genera: dist\FleetMonitorPro\FleetMonitorPro.exe (carpeta portable)

import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# customtkinter necesita sus temas y assets
ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')

# pysnmp tiene imports dinámicos masivos
pysnmp_datas, pysnmp_binaries, pysnmp_hiddenimports = collect_all('pysnmp')
pyasn1_datas,  pyasn1_binaries,  pyasn1_hiddenimports  = collect_all('pyasn1')

a = Analysis(
    ['xerox_monitor.py'],
    pathex=[],
    binaries=[] + ctk_binaries + pysnmp_binaries + pyasn1_binaries,
    datas=[
        # web_server.py importado directamente en modo frozen
        ('web_server.py', '.'),
    ] + ctk_datas + pysnmp_datas + pyasn1_datas,
    hiddenimports=[
        'web_server',
        'flask',
        'jinja2',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.routing',
        'werkzeug.exceptions',
        'click',
        'requests',
        'urllib3',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageDraw',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'asyncio',
    ] + ctk_hiddenimports + pysnmp_hiddenimports + pyasn1_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'PyQt5', 'PyQt6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FleetMonitorPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # sin ventana de consola (equivalente a pythonw)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',      # descomenta y pon tu .ico si tienes uno
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FleetMonitorPro',
)
