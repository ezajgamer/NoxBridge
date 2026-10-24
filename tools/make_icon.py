# -*- coding: utf-8 -*-
"""يرسم app\\nox.ico (نفس أيقونة البرنامج — make_icon بـnox_app.pyw) للبناء بدون فتح البرنامج."""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap

ACCENT = "#2563eb"   # نفس nox_app.ACCENT

app = QGuiApplication(sys.argv)
pix = QPixmap(256, 256)
pix.fill(Qt.transparent)
p = QPainter(pix)
p.setRenderHint(QPainter.Antialiasing)
p.setBrush(QColor(ACCENT))
p.setPen(Qt.NoPen)
p.drawRoundedRect(8, 8, 240, 240, 48, 48)
p.setPen(QColor("#ffffff"))
p.setFont(QFont("Segoe UI", 150, QFont.Bold))
p.drawText(pix.rect(), Qt.AlignCenter, "N")
p.end()
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "nox.ico")
if not pix.save(path, "ICO"):
    sys.exit("ما قدرت أحفظ " + path)
print(path)
