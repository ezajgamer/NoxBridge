# -*- mode: python ; coding: utf-8 -*-
# NoxBridge.exe + مجلد _internal فيه كل شي: المكتبات والمرقّع ومكتبة اللعبة وبيانات الشخصيات.
# (مو ملف واحد: الملف الواحد يفك المرقّع بـ%TEMP% ومضادات الفيروسات مثل Kaspersky تشيله)
# يبنيه tools\build-release.ps1 — المرقّع ومكتبة اللعبة لازم يكونون مبنيين قبله.
import os

ROOT = os.path.dirname(SPECPATH)
APP = os.path.join(ROOT, 'app')
PATCHER = os.path.join(ROOT, 'patcher', 'bin', 'Release', 'net472')

datas = [(os.path.join(ROOT, 'game', 'bin', 'Release', 'net46', 'NoxGame.dll'), 'game'),
         (os.path.join(ROOT, 'data', 'nox-callers.json'), 'data')]
for f in os.listdir(PATCHER):
    if f.endswith(('.exe', '.dll', '.config')):
        datas.append((os.path.join(PATCHER, f), 'patcher'))

# مكتبات تنسحب مع غيرها والبرنامج ما يستخدمها
EXCLUDES = ['numpy', 'PIL', 'cryptography', 'yaml', 'setuptools', 'pkg_resources', 'winloop', 'psutil',
            'tkinter', 'unittest', 'pydoc', 'PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick',
            'PySide6.QtOpenGL', 'PySide6.QtPdf', 'PySide6.QtSvg']

# من Qt: النوافذ والستايل وأيقونة ico بس
QT_DROP = ('opengl32sw', 'Qt6Quick', 'Qt6Qml', 'Qt6Pdf', 'Qt6VirtualKeyboard', 'Qt6OpenGL', 'Qt6Network',
           'Qt6Svg', 'QtNetwork.pyd')
QT_PLUGINS_KEEP = ('platforms/qwindows', 'platforms/qoffscreen', 'styles/', 'imageformats/qico')


def keep(dest: str) -> bool:
    d = dest.replace('\\', '/')
    if not d.startswith('PySide6/'):
        return True
    if '/translations/' in d:
        return False
    if '/plugins/' in d:
        return any(k in d for k in QT_PLUGINS_KEEP)
    return not any(k in d for k in QT_DROP)


a = Analysis([os.path.join(APP, 'nox_app.pyw')], pathex=[APP], datas=datas, excludes=EXCLUDES)
a.binaries = [b for b in a.binaries if keep(b[0])]
a.datas = [b for b in a.datas if keep(b[0])]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='NoxBridge', icon=os.path.join(APP, 'nox.ico'),
          console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='NoxBridge', upx=False)
