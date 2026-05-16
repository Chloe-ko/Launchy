# PyInstaller spec for the launchy compat tool runner.
#
# The bundle includes Python + the launchy package + gi typelibs for GTK4/Adw.
# GTK4/libadwaita shared libraries are NOT bundled — they load from the host system.
# If GTK4 is unavailable at runtime, launchy falls back to launching without UI.

block_cipher = None

a = Analysis(
    ['launchy/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('launchy/logo.svg', 'launchy'),
    ],
    hiddenimports=[
        'gi',
        'gi.repository.Gtk',
        'gi.repository.Adw',
        'gi.repository.Gdk',
        'gi.repository.GLib',
        'gi.repository.Gio',
        'gi.repository.GObject',
        'gi.repository.GdkPixbuf',
        'gi.repository.Pango',
        'gi.repository.PangoCairo',
    ],
    hookspath=[],
    hooksconfig={
        'gi': {
            'module-versions': {
                'Gtk': '4.0',
                'Adw': '1',
            },
        },
    },
    runtime_hooks=[],
    excludes=['_tkinter', 'tkinter'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='launchy-runner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=True,
)
