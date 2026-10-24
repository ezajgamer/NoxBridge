# -*- coding: utf-8 -*-
"""
مسارات NoxBridge — نفس الكود يشتغل من المشروع (تطوير) ومن النسخة المجمّعة (PyInstaller).

التطوير:  app\\*.py ، بيانات المستخدم بـapp\\Save ، المرقّع والمكتبة من patcher\\ وgame\\ بعد البناء
المجمّعة:  NoxBridge.exe + _internal\\ (المكتبات والمرقّع والبيانات) ، بيانات المستخدم بـSave\\ جنبه
"""

import os
import sys

RELEASE = bool(getattr(sys, "frozen", False))

# الملفات اللي تجي مع الكود
CODE = getattr(sys, "_MEIPASS", None) if RELEASE else os.path.dirname(os.path.abspath(__file__))
# جذر البرنامج: مجلد NoxBridge.exe، أو جذر المشروع بالتطوير
ROOT = os.path.dirname(sys.executable) if RELEASE else os.path.dirname(CODE)
# بيانات المستخدم: الدخول، السجل، الإعدادات، الإحصائيات
SAVE = os.path.join(ROOT, "Save") if RELEASE else os.path.join(CODE, "Save")


def patcher_command() -> list:
    """أمر تشغيل المرقّع."""
    if RELEASE:
        return [os.path.join(CODE, "patcher", "NoxPatcher2.exe")]
    return [os.path.join(ROOT, "patcher", "bin", "Release", "net472", "NoxPatcher2.exe")]


def game_dll() -> str:
    if RELEASE:
        return os.path.join(CODE, "game", "NoxGame.dll")
    return os.path.join(ROOT, "game", "bin", "Release", "net46", "NoxGame.dll")


def data_dir() -> str:
    return os.path.join(CODE if RELEASE else ROOT, "data")
