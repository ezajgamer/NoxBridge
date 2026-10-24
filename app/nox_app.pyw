# -*- coding: utf-8 -*-
"""
NoxBridge — البرنامج: الجسر يشتغل بالخلفية داخله، والإعدادات والحسابات والتركيب بنافذة وحدة.

بدون متصفح مدموج ولا حركات (عناصر Qt عادية بستايل Fusion) عشان ما يثقّل على الكرت وأنت تلعب.
التشغيل: pythonw nox_app.pyw  (أو أيقونة NoxBridge على سطح المكتب)

الحسابات: كل مزوّد Provider بقائمة PROVIDERS — بطاقته بصفحة الحسابات وموديلاته بقسم
لحاله بقائمة الموديلات: Grok وChatGPT والمحلي (LM Studio).
"""

import os
import sys
import time
import threading
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import Qt, QObject, QThread, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QStandardItemModel  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import nox_bridge  # noqa: E402
import nox_paths  # noqa: E402
import nox_providers  # noqa: E402
import nox_settings  # noqa: E402
import nox_stats  # noqa: E402
import nox_translate  # noqa: E402

APP_ID = "Noxvyn.NoxBridge"
STEAM_URL = "steam://rungameid/4954910"
ICON_PATH = os.path.join(nox_paths.SAVE if nox_paths.RELEASE else HERE, "nox.ico")
ERROR_LOG = os.path.join(nox_paths.SAVE, "app-error.log")

ACCENT = "#2563eb"
OK, WARN, BAD, MUTED = "#15803d", "#b45309", "#b91c1c", "#6b7280"

STYLE = f"""
QWidget {{ font-family: "Segoe UI"; font-size: 10pt; color: #1d2129; }}
QMainWindow, QWidget#content {{ background: #f4f5f7; }}

QFrame#sidebar {{ background: #ffffff; border-left: 1px solid #e3e6ea; }}
QLabel#brand {{ font-size: 15pt; font-weight: 700; color: {ACCENT}; padding: 6px 4px 14px; }}
QPushButton#nav {{ background: transparent; color: #374151; text-align: right; padding: 10px 14px;
                   border: 0; border-radius: 8px; font-weight: 600; }}
QPushButton#nav:hover {{ background: #f1f4f9; }}
QPushButton#nav:checked {{ background: #e8efff; color: {ACCENT}; }}

QLabel#pageTitle {{ font-size: 16pt; font-weight: 700; }}
QLabel#pageSub {{ color: {MUTED}; }}
QFrame#card {{ background: #ffffff; border: 1px solid #e3e6ea; border-radius: 10px; }}
QLabel#cardTitle {{ font-size: 11.5pt; font-weight: 700; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#tileValue {{ font-size: 11pt; font-weight: 700; }}
QLabel#avatar {{ color: #fff; font-size: 16pt; font-weight: 700; border-radius: 22px; }}

QPushButton {{ background: {ACCENT}; color: #fff; border: 0; border-radius: 7px; padding: 8px 18px; font-weight: 600; }}
QPushButton:hover {{ background: #1d4ed8; }}
QPushButton:disabled {{ background: #a9bdf0; }}
QPushButton#big {{ font-size: 12pt; padding: 12px 28px; }}
QPushButton#secondary {{ background: #e8edf7; color: {ACCENT}; }}
QPushButton#secondary:hover {{ background: #dbe4f5; }}
QPushButton#danger {{ background: #fdecec; color: {BAD}; }}
QPushButton#danger:hover {{ background: #fadcdc; }}
QPushButton#danger:disabled, QPushButton#secondary:disabled {{ background: #f1f2f4; color: #a0a6b0; }}

QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #b9c0ca; border-radius: 4px; background: #fff; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QPlainTextEdit {{ background: #fff; border: 1px solid #e3e6ea; border-radius: 8px; font-family: "Consolas", "Segoe UI"; font-size: 9.5pt; }}

QScrollBar:vertical {{ background: #eef0f3; width: 12px; margin: 0; border-radius: 6px; }}
QScrollBar::handle:vertical {{ background: #b9c0ca; min-height: 36px; border-radius: 6px; }}
QScrollBar::handle:vertical:hover {{ background: #98a1ad; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{ height: 0; }}
"""


# ═══════════════════════════════════════════════════════════════ أدوات

def log_crash(exc_type, exc, tb):
    try:
        os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + "".join(traceback.format_exception(exc_type, exc, tb)) + "\n")
    except OSError:
        pass


def make_icon() -> QIcon:
    """أيقونة بسيطة (حرف N) — تنحفظ nox.ico لاختصار سطح المكتب."""
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
    if not os.path.isfile(ICON_PATH):
        pix.save(ICON_PATH, "ICO")
    return QIcon(pix)


class Worker(QThread):
    """يشغّل دالة بخيط خلفي ويرجّع النتيجة للواجهة."""
    finished_with = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            result = self.fn()
        except Exception as e:  # noqa: BLE001
            log_crash(type(e), e, e.__traceback__)
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        self.finished_with.emit(result)


class LogBus(QObject):
    line = Signal(str, str)
    login = Signal(str, str, str)   # المزوّد، الرابط، الكود


def rtl(text: str) -> str:
    """RLM بالبداية: السطر يمين لليسار حتى لو بدأ بكلمة إنجليزية (ChatGPT، Grok…)."""
    return "‏" + text if text else text


def label(text="", name=None, wrap=True) -> QLabel:
    lbl = QLabel(rtl(text))
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def colored(lbl: QLabel, color: str, text: str):
    lbl.setText(rtl(text))
    lbl.setStyleSheet(f"color: {color};")


def field(w):
    """القوائم وخانات الأرقام بستايل Fusion الأصلي (QSS عليها يخرّب الأسهم) — بس نكبّرها."""
    w.setMinimumHeight(32)
    return w


def card(title: str = None):
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    if title:
        lay.addWidget(label(title, "cardTitle"))
    return frame, lay


def form() -> QFormLayout:
    f = QFormLayout()
    f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    f.setHorizontalSpacing(16)
    f.setVerticalSpacing(10)
    f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    return f


def combo(items=()) -> QComboBox:
    c = field(QComboBox())
    for value, text in items:
        c.addItem(text, value)
    return c


def seconds_box(lo, hi, decimals=False):
    w = field(QDoubleSpinBox() if decimals else QSpinBox())
    w.setRange(lo, hi)
    if decimals:
        w.setDecimals(0)
    w.setSuffix(" ثانية")
    w.setMaximumWidth(150)
    return w


def add_header(box: QComboBox, text: str):
    """عنوان قسم داخل القائمة (ما ينختار)."""
    box.addItem(text, None)
    item = box.model().item(box.count() - 1) if isinstance(box.model(), QStandardItemModel) else None
    if item is not None:
        item.setEnabled(False)
        f = item.font()
        f.setBold(True)
        item.setFont(f)


# ═══════════════════════════════════════════════════════════════ الحسابات

class Provider:
    """حساب/مزوّد. الحالة والربط والموديلات — كل واحد يطبّقها بطريقته."""
    key = ""
    name = ""
    letter = ""
    color = ACCENT
    provides = ""
    prefix = ""                 # بادئة الموديل اللي يوجّه فيها الجسر (nox_providers)
    can_disconnect = True
    connect_text = ("ربط", "ربط حساب ثاني")

    def status(self):           # (مربوط؟, وصف) — سريع، بدون شبكة
        return False, None

    def probe(self):            # فحص بالشبكة — ينادى بخيط خلفي
        pass

    def connect(self, parent) -> bool:   # True = بدأ تسجيل دخول
        return False

    def disconnect(self):
        pass

    def models(self) -> list:   # [{"id": ..}] — ينادى بخيط خلفي
        return []


class GrokProvider(Provider):
    key = "grok"
    name = "Grok (xAI)"
    letter = "G"
    color = "#111827"
    provides = "المحادثة · صوت الشخصيات · تفريغ المايك"

    def status(self):
        store = nox_bridge.BRIDGE.store
        if not store.logged_in:
            return False, None
        return True, "الحساب: " + (store.identity.get("email") or store.identity.get("name") or "؟")

    def connect(self, parent):
        nox_bridge.BRIDGE.start_login()
        return True

    def disconnect(self):
        nox_bridge.BRIDGE.logout()

    def models(self):
        b = nox_bridge.BRIDGE
        return b.run(b.models(), 30) if b.store.logged_in else []


class ChatGPTProvider(Provider):
    key = "chatgpt"
    name = "ChatGPT (OpenAI)"
    letter = "C"
    color = "#10a37f"
    provides = "المحادثة بس — الصوت والتفريغ يظلون على Grok"
    prefix = "chatgpt:"

    def status(self):
        store = nox_bridge.BRIDGE.gpt.store
        if not store.logged_in:
            return False, None
        return True, "الحساب: " + (store.identity.get("email") or store.identity.get("name") or "؟")

    def connect(self, parent):
        nox_bridge.BRIDGE.start_gpt_login()
        return True

    def disconnect(self):
        nox_bridge.BRIDGE.gpt_logout()

    def models(self):
        return nox_bridge.BRIDGE.gpt.models()


class LocalProvider(Provider):
    key = "local"
    name = "المحلي (LM Studio)"
    letter = "L"
    color = "#7c3aed"
    provides = "المحادثة من كرتك بدون اشتراك — LM Studio لازم مفتوح والسيرفر شغّال"
    prefix = "local:"
    connect_text = ("ربط", "فحص الاتصال")

    @staticmethod
    def enabled() -> bool:
        return bool(nox_settings.bridge_settings().get("local_enabled"))

    def status(self):
        # ما ينحسب مربوط لمجرد إن LM Studio شغّال — لازم المستخدم يربطه
        local = nox_bridge.BRIDGE.local
        if not self.enabled() or not local.reachable:
            return False, ("LM Studio مو شغّال — افتحه وشغّل Local Server" if self.enabled() else None)
        loaded = "محمّل: " + "، ".join(local.loaded_keys) if local.loaded_keys else "ما فيه موديل محمّل على الكرت"
        return True, f"{len(local.model_ids)} موديل متاح · {loaded}"

    def probe(self):
        if not self.enabled():
            return
        b = nox_bridge.BRIDGE
        b.run(b.local.probe(b.client), 5)

    def connect(self, parent):
        b = nox_bridge.BRIDGE
        b.run(b.local.probe(b.client), 5)
        if not b.local.reachable:
            QMessageBox.information(parent, "NoxBridge",
                                    "السيرفر المحلي ما يرد.\nافتح LM Studio، وشغّل Local Server من تبويب Developer، وبعدها اضغط «ربط».")
            return False
        nox_settings.set_bridge_option("local_enabled", True)
        nox_bridge.log(f"✅ المحلي: انربط ({len(b.local.model_ids)} موديل)")
        return False

    def disconnect(self):
        nox_settings.set_bridge_option("local_enabled", False)
        nox_bridge.log("المحلي: انفصل")

    def models(self):
        return nox_bridge.BRIDGE.local.models() if self.enabled() else []


PROVIDERS = [GrokProvider(), ChatGPTProvider(), LocalProvider()]


def provider_for(model_id: str) -> Provider:
    for prov in PROVIDERS:
        if prov.prefix and model_id.startswith(prov.prefix):
            return prov
    return PROVIDERS[0]


def model_label(model_id: str) -> str:
    """«chatgpt:gpt-5.5» ← «gpt-5.5 · ChatGPT»."""
    if not model_id:
        return "—"
    prov = provider_for(model_id)
    return f"{model_id[len(prov.prefix):]} · {prov.name.split(' (')[0]}"


# ═══════════════════════════════════════════════════════════════ الصفحات

class Page(QScrollArea):
    """صفحة بعنوان ووصف، تتمرر لو طالت."""

    def __init__(self, title: str, subtitle: str):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("content")
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(26, 22, 26, 22)
        self.body.setSpacing(14)
        self.body.addWidget(label(title, "pageTitle"))
        self.body.addWidget(label(subtitle, "pageSub"))
        self.setWidget(inner)

    def finish(self):
        self.body.addStretch(1)


class MainWindow(QMainWindow):
    def __init__(self, bus: LogBus):
        super().__init__()
        self.setWindowTitle("NoxBridge")
        self.resize(980, 680)
        self.setMinimumSize(820, 560)
        self.workers = set()
        self.busy = False
        self.game_running = False
        self.mod_installed = False
        self._mod_stamp = None
        self._local_up = None
        self.saved_llm = ""
        self.any_linked = None
        self.gated = []          # بطاقات تختفي لما ما فيه حساب مربوط
        self.link_banners = []   # «اربط حساب أول»
        self.provider_widgets = {}

        root = QWidget()
        root_lay = QHBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        root_lay.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        root_lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        pages = [
            ("🏠   الرئيسية", self._home_page()),
            ("👤   الحسابات", self._accounts_page()),
            ("🤖   الذكاء الاصطناعي", self._ai_page()),
            ("🔊   الصوت والشخصيات", self._voice_page()),
            ("📜   السجل", self._log_page()),
        ]
        group = QButtonGroup(self)
        group.setExclusive(True)
        for i, (text, page) in enumerate(pages):
            self.stack.addWidget(page)
            btn = QPushButton(text)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, i=i: self.stack.setCurrentIndex(i))
            group.addButton(btn)
            self.nav_lay.insertWidget(self.nav_lay.count() - 2, btn)
            if i == 0:
                btn.setChecked(True)

        self.update_translate_count()
        bus.line.connect(self.on_log)
        bus.login.connect(self.show_login_code)
        self._load_log_tail()
        nox_stats.backfill_from_log(nox_bridge.LOG_PATH)   # أول مرة بس
        self.refresh_stats()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(4000)
        self.refresh_status()
        self.load_settings()

    # ---------------------------------------------------------------- خلفية
    def bg(self, fn, done):
        w = Worker(fn, self)
        self.workers.add(w)

        def _finish(result):
            self.workers.discard(w)
            done(result)
        w.finished_with.connect(_finish)
        w.start()

    # ---------------------------------------------------------------- القائمة
    def _sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        self.nav_lay = QVBoxLayout(side)
        self.nav_lay.setContentsMargins(12, 16, 12, 16)
        self.nav_lay.setSpacing(4)
        self.nav_lay.addWidget(label("NoxBridge", "brand"))
        self.nav_lay.addStretch(1)
        self.side_status = label("● الجسر شغّال", "muted")
        self.side_status.setStyleSheet(f"color: {OK};")
        self.nav_lay.addWidget(self.side_status)
        return side

    # ---------------------------------------------------------------- الرئيسية
    def _tile(self, grid, col, title):
        frame, lay = card()
        lay.setSpacing(4)
        lay.addWidget(label(title, "muted"))
        value = label("…", "tileValue")
        lay.addWidget(value)
        grid.addWidget(frame, 0, col)
        return value

    def _home_page(self) -> Page:
        page = Page("الرئيسية", "شغّل اللعبة من هني وخلّ البرنامج مفتوح — هو اللي يرد على الشخصيات.")

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.t_accounts = self._tile(grid, 0, "الحسابات")
        self.t_mod = self._tile(grid, 1, "المود")
        self.t_game = self._tile(grid, 2, "اللعبة")
        self.t_model = self._tile(grid, 3, "الموديل")
        page.body.addLayout(grid)

        box, b = card("اللعب")
        row = QHBoxLayout()
        self.btn_play = QPushButton("▶   شغّل اللعبة")
        self.btn_play.setObjectName("big")
        self.btn_play.clicked.connect(self.play)
        row.addWidget(self.btn_play)
        row.addStretch(1)
        b.addLayout(row)
        self.last_reply = label("آخر رد: —", "muted")
        b.addWidget(self.last_reply)
        page.body.addWidget(box)

        box, b = card("التركيب")
        b.addWidget(label("بعد أي تحديث من ستيم اضغط «إعادة التركيب». التغيير يحتاج اللعبة مسكّرة.", "muted"))
        f = form()
        row = QHBoxLayout()
        self.game_path = label("", "muted")
        self.game_path.setWordWrap(True)
        btn_dir = QPushButton("اختر مجلد اللعبة…")
        btn_dir.setObjectName("secondary")
        btn_dir.clicked.connect(self.choose_game_dir)
        row.addWidget(self.game_path, 1)
        row.addWidget(btn_dir)
        f.addRow("مجلد اللعبة", row)
        b.addLayout(f)
        row = QHBoxLayout()
        self.btn_install = QPushButton("إعادة التركيب")
        self.btn_install.clicked.connect(self.install)
        self.btn_restore = QPushButton("رجّع اللعبة أصلية")
        self.btn_restore.setObjectName("danger")
        self.btn_restore.clicked.connect(self.restore)
        row.addWidget(self.btn_install)
        row.addWidget(self.btn_restore)
        row.addStretch(1)
        b.addLayout(row)
        self.install_msg = label("", "muted")
        b.addWidget(self.install_msg)
        page.body.addWidget(box)

        box, b = card("مهلة رد الشخصية")
        b.addWidget(label("كم ثانية تنطر اللعبة رد الشخصية قبل ما تقطع. الأصل حق اللعبة ١٥. "
                          "التغيير يحتاج اللعبة مسكّرة.", "muted"))
        row = QHBoxLayout()
        self.timeout = seconds_box(10, 90)
        self.timeout.setValue(int(round(float(nox_settings.bridge_settings().get("timeout") or 15))))
        self.btn_timeout = QPushButton("طبّق")
        self.btn_timeout.clicked.connect(self.apply_timeout)
        row.addWidget(self.timeout)
        row.addWidget(self.btn_timeout)
        row.addStretch(1)
        b.addLayout(row)
        self.timeout_msg = label("", "muted")
        b.addWidget(self.timeout_msg)
        page.body.addWidget(box)

        page.finish()
        return page

    # ---------------------------------------------------------------- الحسابات
    def _accounts_page(self) -> Page:
        page = Page("الحسابات", "الاشتراكات المربوطة. موديلات كل حساب مربوط تطلع بقائمة الموديلات.")
        for prov in PROVIDERS:
            box, b = card()
            top = QHBoxLayout()
            avatar = QLabel(prov.letter)
            avatar.setObjectName("avatar")
            avatar.setFixedSize(44, 44)
            avatar.setAlignment(Qt.AlignCenter)
            avatar.setStyleSheet(f"background: {prov.color};")
            top.addWidget(avatar)
            info = QVBoxLayout()
            info.setSpacing(2)
            info.addWidget(label(prov.name, "cardTitle"))
            info.addWidget(label(prov.provides, "muted"))
            who = label("", "muted")
            info.addWidget(who)
            top.addLayout(info, 1)
            state = label("…", wrap=False)
            state.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            top.addWidget(state, 0, Qt.AlignTop)
            b.addLayout(top)
            row = QHBoxLayout()
            btn_connect = QPushButton(prov.connect_text[0])
            btn_connect.clicked.connect(lambda _=False, p=prov: self.connect_provider(p))
            btn_disconnect = QPushButton("فصل")
            btn_disconnect.setObjectName("danger")
            btn_disconnect.clicked.connect(lambda _=False, p=prov: self.disconnect_provider(p))
            btn_disconnect.setVisible(prov.can_disconnect)
            row.addWidget(btn_connect)
            row.addWidget(btn_disconnect)
            row.addStretch(1)
            b.addLayout(row)
            if prov.key == "local":
                self._local_controls(b)
            page.body.addWidget(box)
            self.provider_widgets[prov.key] = (state, who, btn_connect, btn_disconnect)
        page.body.addWidget(label("الصوت وتفريغ المايك على Grok دايم — ChatGPT والمحلي للمحادثة بس.", "muted"))
        page.finish()
        return page

    # ---------------------------------------------------------------- المحلي: الكرت
    def _local_controls(self, lay: QVBoxLayout):
        row = QHBoxLayout()
        self.btn_local_load = QPushButton("حمّل موديل الرد على الكرت")
        self.btn_local_load.setObjectName("secondary")
        self.btn_local_load.clicked.connect(lambda: self.local_load())
        self.btn_local_unload = QPushButton("فرّغ الكرت")
        self.btn_local_unload.setObjectName("secondary")
        self.btn_local_unload.clicked.connect(self.local_unload)
        row.addWidget(self.btn_local_load)
        row.addWidget(self.btn_local_unload)
        row.addStretch(1)
        lay.addLayout(row)
        self.chk_auto_unload = QCheckBox("فرّغ الكرت لحاله لما أسكّر اللعبة")
        self.chk_auto_unload.setChecked(bool(nox_settings.bridge_settings().get("auto_unload")))
        self.chk_auto_unload.toggled.connect(lambda on: nox_settings.set_bridge_option("auto_unload", bool(on)))
        lay.addWidget(self.chk_auto_unload)
        lay.addWidget(label("حمّل الموديل قبل اللعب عشان أول رد ما يتعدّى مهلة اللعبة. "
                            "التفريغ يشمل أي موديل محمّل بـLM Studio (حتى لو برنامج ثاني يستخدمه).", "muted"))

    def local_load(self, then=None):
        model = self.saved_llm or ""
        if not model.startswith(nox_providers.LOCAL_PREFIX):
            QMessageBox.information(self, "NoxBridge", "موديل الرد مو محلي — اختار موديل من قسم «المحلي» بصفحة الذكاء الاصطناعي واحفظ.")
            return
        key = model[len(nox_providers.LOCAL_PREFIX):]
        self.btn_local_load.setEnabled(False)
        nox_bridge.log(f"⏳ المحلي: أحمّل {key} على الكرت…")
        b = nox_bridge.BRIDGE

        def done(r):
            self.btn_local_load.setEnabled(True)
            if r.get("ok"):
                secs = r.get("seconds")
                nox_bridge.log(f"✅ المحلي: {key} محمّل" + (f" ({secs:.0f}s)" if isinstance(secs, (int, float)) else ""))
                if then:
                    then()
            else:
                nox_bridge.log(f"❌ المحلي: {r.get('error')}")
                QMessageBox.warning(self, "NoxBridge", str(r.get("error")))
            self.refresh_status()
        self.bg(lambda: b.run(b.local.load(b.client, key), 320), done)

    def local_unload(self, ask=True):
        if ask and QMessageBox.question(self, "NoxBridge", "أفرّغ كل الموديلات المحمّلة بـLM Studio من الكرت؟",
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        b = nox_bridge.BRIDGE

        def done(r):
            if r.get("unloaded"):
                nox_bridge.log("🧹 المحلي: فرّغت " + "، ".join(r["unloaded"]))
            elif r.get("ok"):
                nox_bridge.log("🧹 المحلي: ما فيه شي محمّل")
            if r.get("error"):
                nox_bridge.log("❌ المحلي: " + r["error"])
            self.refresh_status()
        self.bg(lambda: b.run(b.local.unload_all(b.client), 120), done)

    def connect_provider(self, prov: Provider):
        connected, _ = prov.status()
        if connected and prov.can_disconnect:
            ask = QMessageBox.question(self, "NoxBridge", f"{prov.name} مربوط. تبي تربطه بحساب ثاني؟ (يفصل الحالي)",
                                       QMessageBox.Yes | QMessageBox.No)
            if ask != QMessageBox.Yes:
                return
            prov.disconnect()
        if prov.connect(self):
            nox_bridge.log(f"🔑 {prov.name}: أجهّز تسجيل الدخول…")
        self.refresh_status()
        self.load_settings()

    def show_login_code(self, provider: str, url: str, code: str):
        QApplication.clipboard().setText(code)
        box = QMessageBox(self)
        box.setWindowTitle(f"تسجيل دخول {provider}")
        box.setIcon(QMessageBox.Information)
        box.setText(rtl(f"فتحت لك المتصفح. إذا طلب كود، الصقه (نسخته لك):\n\n{code}\n\n"
                        "بعد ما توافق بالمتصفح ارجع هني — الربط يكمل لحاله."))
        box.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_open = box.addButton("افتح الرابط مرة ثانية", QMessageBox.ActionRole)
        box.addButton("تمام", QMessageBox.AcceptRole)
        btn_open.clicked.connect(lambda: os.startfile(url))
        box.setModal(False)
        box.show()

    def disconnect_provider(self, prov: Provider):
        ask = QMessageBox.question(self, "NoxBridge", f"تفصل {prov.name}؟ الشخصيات ما ترد عليه لين تربطه من جديد.",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ask == QMessageBox.Yes:
            prov.disconnect()
            self.refresh_status()

    # ---------------------------------------------------------------- الذكاء
    def _ai_page(self) -> Page:
        page = Page("الذكاء الاصطناعي", "الموديل اللي يرد على الشخصيات، والاحتياط لو تأخر.")
        self._link_banner(page)

        box, b = card("الموديل")
        self.gated.append(box)
        f = form()
        self.llm_model = combo()
        self.reasoning = combo([("", "بدون (أسرع)"), ("low", "خفيف"), ("medium", "متوسط"), ("high", "عالي (أبطأ)")])
        f.addRow("موديل الرد", self.llm_model)
        f.addRow("مستوى التفكير", self.reasoning)
        b.addLayout(f)
        b.addWidget(label("التفكير يأثر على الموديلات اللي تفكّر بس. الأعلى أدق بس أبطأ.", "muted"))
        page.body.addWidget(box)

        box, b = card("الاحتياط")
        self.gated.append(box)
        f = form()
        self.fallback = combo()
        self.hedge = seconds_box(3, 60, decimals=True)
        f.addRow("موديل الاحتياط", self.fallback)
        f.addRow("يتحوّل له بعد", self.hedge)
        b.addLayout(f)
        self.hedge_hint = label("", "muted")
        b.addWidget(self.hedge_hint)
        page.body.addWidget(box)

        page.body.addLayout(self._save_row())

        box, b = card("أداء الموديلات")
        self.gated.append(box)
        b.addWidget(label("من كل الردود اللي مرت بالجسر. «راح للاحتياط» = تأخر أو فشل وجاوب الاحتياط بداله. "
                          "«ألغته اللعبة» = عدّى مهلة رد الشخصية.", "muted"))
        self.stats_table = QTableWidget(0, 7)
        self.stats_table.setHorizontalHeaderLabels(["الموديل", "الردود", "المتوسط", "أبطأ رد", "راح للاحتياط", "فشل", "ألغته اللعبة"])
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.stats_table.setSelectionMode(QTableWidget.NoSelection)
        self.stats_table.setFocusPolicy(Qt.NoFocus)
        hdr = self.stats_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 7):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        b.addWidget(self.stats_table)
        row = QHBoxLayout()
        btn_reset = QPushButton("صفّر الإحصائيات")
        btn_reset.setObjectName("secondary")
        btn_reset.clicked.connect(self.reset_stats)
        row.addWidget(btn_reset)
        row.addStretch(1)
        b.addLayout(row)
        page.body.addWidget(box)
        page.finish()

        self.hedge.valueChanged.connect(self.check_hedge)
        self.timeout.valueChanged.connect(self.check_hedge)
        self.fallback.currentIndexChanged.connect(self.check_hedge)
        return page

    # ---------------------------------------------------------------- الصوت
    def _voice_page(self) -> Page:
        page = Page("الصوت والشخصيات", "صوت الشخصيات وتفريغ المايك ولهجتهم وصعوبتهم.")
        self._link_banner(page)

        box, b = card("الصوت")
        self.gated.append(box)
        f = form()
        self.tts = combo([(code, f"Grok — {name}") for code, name in nox_settings.TTS_LANGS.items()]
                         + [("game", "صوت اللعبة الأصلي")])
        self.stt = combo([("grok", "Grok"), ("game", "تفريغ اللعبة الأصلي")])
        f.addRow("صوت الشخصيات", self.tts)
        f.addRow("تفريغ المايك", self.stt)
        b.addLayout(f)
        self.tts_note = label("النطق على حسب الشخصية: الكويتي والإماراتي بنطق إماراتي، والسعودي واليمني سعودي، "
                              "والمصري والسوداني مصري، والهندي والباكستاني بلكنة هندية، والبنغالي بنغالية. "
                              "اللي تختاره هني لباقي شخصيات اللعبة. الصوت يتغيّر من تشغيل اللعبة الجاي، "
                              "والتفريغ بعد «إعادة التركيب».", "muted")
        self.tts_note.setWordWrap(True)
        b.addWidget(self.tts_note)
        page.body.addWidget(box)

        self.translate_box, b = card("ترجمة الشاشات")
        self.gated.append(self.translate_box)
        self.translate = QCheckBox("ترجم النصوص الإنجليزية داخل اللعبة لحالها (Grok)")
        b.addWidget(self.translate)
        b.addWidget(label("أول مرة يطلع نص إنجليزي ينرسل للترجمة، ومن المرة الجاية يطلع عربي. "
                          "القوائم مترجمة من اللعبة نفسها — هذي لشاشات الكمبيوتر داخل اللعبة وغيرها. يتغيّر من تشغيل اللعبة الجاي.", "muted"))
        row = QHBoxLayout()
        self.translate_count = label("", "muted")
        btn_clear = QPushButton("امسح الترجمات")
        btn_clear.setObjectName("secondary")
        btn_clear.clicked.connect(self.clear_translations)
        row.addWidget(self.translate_count, 1)
        row.addWidget(btn_clear)
        b.addLayout(row)
        page.body.addWidget(self.translate_box)

        box, b = card("الشخصيات")
        self.gated.append(box)
        f = form()
        self.difficulty = combo([("easy", "سهلة"), ("normal", "متوسطة"), ("realistic", "واقعية")])
        f.addRow("الصعوبة", self.difficulty)
        b.addLayout(f)
        self.dialect_note = label("اللهجة على حسب الشخصية: كل واحد يتكلم لهجته (كويتي، سعودي، إماراتي، مصري، "
                                  "سوداني، يمني، وعربي العمالة للهندي والباكستاني والبنغالي والفلبينية)، "
                                  "وشخصيات اللعبة الأصلية عربي عام. «إعادة التركيب» تخلّي طابور المكالمات "
                                  "شخصياتنا بس، و«رجّع اللعبة أصلية» يرجّع طابور اللعبة.", "muted")
        self.dialect_note.setWordWrap(True)
        b.addWidget(self.dialect_note)
        page.body.addWidget(box)

        page.body.addLayout(self._save_row())
        page.finish()
        return page

    def refresh_stats(self):
        rows = nox_stats.summary()
        limit = self.timeout.value()
        t = self.stats_table
        t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            avg, slow = r["avg"], r["slowest"]
            cells = [model_label(r["model"]), str(r["replies"]),
                     f"{avg:.1f} ث" if avg else "—", f"{slow:.1f} ث" if slow else "—",
                     str(r["hedged"]), str(r["failed"]), str(r["cancelled"])]
            for j, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter if j else Qt.AlignRight | Qt.AlignVCenter)
                if j == 2 and avg and avg > limit - 8:
                    item.setForeground(QColor(WARN))   # المتوسط قريب من المهلة
                if j in (4, 5, 6) and int(text) > 0:
                    item.setForeground(QColor(BAD if j > 4 else WARN))
                t.setItem(i, j, item)
        t.setFixedHeight(t.horizontalHeader().height() + sum(t.rowHeight(i) for i in range(len(rows))) + 4)

    def reset_stats(self):
        if QMessageBox.question(self, "NoxBridge", "تصفّر إحصائيات كل الموديلات؟", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            nox_stats.reset()
            self.refresh_stats()

    def _link_banner(self, page: "Page"):
        banner = label("اربط حساب من «الحسابات» أول — بعدها تطلع الموديلات والإعدادات.", "cardTitle")
        banner.setStyleSheet(f"color: {WARN};")
        banner.hide()
        page.body.addWidget(banner)
        self.link_banners.append(banner)

    def _save_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        btn = QPushButton("حفظ")
        btn.setEnabled(False)
        btn.clicked.connect(self.save_settings)
        msg = label("تطبق خلال ثانية حتى واللعبة شغّالة.", "muted")
        row.addWidget(btn)
        row.addWidget(msg, 1)
        self.__dict__.setdefault("save_rows", []).append((btn, msg))
        return row

    # ---------------------------------------------------------------- السجل
    def _log_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("content")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(10)
        lay.addWidget(label("السجل", "pageTitle"))
        bar = QHBoxLayout()
        self.follow = QCheckBox("تابع آخر سطر")
        self.follow.setChecked(True)
        btn_bottom = QPushButton("⬇  آخر سطر")
        btn_bottom.setObjectName("secondary")
        btn_bottom.clicked.connect(self.scroll_bottom)
        btn_file = QPushButton("افتح ملف السجل")
        btn_file.setObjectName("secondary")
        btn_file.clicked.connect(lambda: os.startfile(nox_bridge.LOG_PATH))
        bar.addWidget(self.follow)
        bar.addStretch(1)
        bar.addWidget(btn_bottom)
        bar.addWidget(btn_file)
        lay.addLayout(bar)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.log_view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        lay.addWidget(self.log_view, 1)
        return page

    @staticmethod
    def _fmt(stamp: str, line: str) -> str:
        # RLM بالبداية = السطر يمين لليسار حتى لو بدأ بإنجليزي؛ الوقت آخره بدل التاريخ الطويل
        return f"‏{line}   ·   {stamp[11:]}"

    def scroll_bottom(self):
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _load_log_tail(self):
        try:
            with open(nox_bridge.LOG_PATH, encoding="utf-8") as f:
                lines = f.readlines()[-400:]
        except OSError:
            return
        out = []
        for raw in lines:
            raw = raw.rstrip("\n")
            if raw.startswith("[") and raw[20:22] == "] ":
                out.append(self._fmt(raw[1:20], raw[22:]))
                if raw[22:].startswith("✓ ") and "توكن" in raw:
                    self.last_reply.setText(f"آخر رد: {raw[22:][2:]}   ·   {raw[12:20]}")
            else:
                out.append("‏" + raw)
        self.log_view.setPlainText("\n".join(out))
        self.scroll_bottom()

    def on_log(self, stamp: str, line: str):
        self.log_view.appendPlainText(self._fmt(stamp, line))
        if self.follow.isChecked():
            self.scroll_bottom()
        # سطر الرد الناجح: «✓ grok-4.5 6.2s · ...»
        if line.startswith("✓ ") and "توكن" in line:
            self.last_reply.setText(f"آخر رد: {line[2:]}   ·   {stamp[11:]}")
        if line[:2] in ("✓ ", "✗ ", "↩ ") and not line.startswith(("✓ صوت", "✓ تفريغ", "✗ صوت", "✗ تفريغ")):
            self.refresh_stats()
        if "تم تسجيل الدخول" in line or "تسجيل الخروج" in line:
            self.refresh_status()
            self.load_settings()

    # ---------------------------------------------------------------- الحالة
    def refresh_status(self):
        connected = 0
        for prov in PROVIDERS:
            ok, desc = prov.status()
            state, who, btn_connect, btn_disconnect = self.provider_widgets[prov.key]
            if ok:
                connected += 1
                colored(state, OK, "● مربوط")
                who.setText(rtl(desc or ""))
                btn_connect.setText(prov.connect_text[1])
                btn_connect.setObjectName("secondary")
            else:
                # مربوط بس الخدمة طافية (المحلي) ⇒ وصف؛ وإلا مو مربوط
                colored(state, WARN if desc else BAD, "● طافي" if desc else "● مو مربوط")
                who.setText(rtl(desc or ""))
                btn_connect.setText(prov.connect_text[0])
                btn_connect.setObjectName("")
            btn_connect.style().unpolish(btn_connect)
            btn_connect.style().polish(btn_connect)
            btn_disconnect.setEnabled(ok or bool(desc))
        colored(self.t_accounts, OK if connected else BAD, f"{connected} من {len(PROVIDERS)} مربوط")
        if self.any_linked != (connected > 0):
            self.any_linked = connected > 0
            self.apply_linked_ui()
            self.load_settings()

        def check():
            for p in PROVIDERS:
                p.probe()
            gd = nox_settings.game_dir()
            dll = os.path.join(gd, "Scam With Your Friends_Data", "Managed", "Assembly-CSharp.dll")
            try:
                stamp = os.path.getmtime(dll)
            except OSError:
                stamp = None
            installed = (self.mod_installed if stamp == self._mod_stamp else nox_settings.mod_installed(gd)) if gd else False
            return {"running": nox_settings.game_running(), "installed": installed, "stamp": stamp, "dir": gd}

        def done(r):
            if "running" not in r:
                return
            local_was = self._local_up
            self._local_up = LocalProvider.enabled() and nox_bridge.BRIDGE.local.reachable
            if local_was != self._local_up and (local_was is not None or self._local_up):
                self.refresh_status()   # بطاقة المحلي تتحدث
                self.load_settings()    # موديلاته تنضاف/تنشال من القوائم
            was_running = self.game_running
            self.game_running, self.mod_installed, self._mod_stamp = r["running"], r["installed"], r["stamp"]
            if was_running and not self.game_running:
                self.on_game_closed()
            if r["dir"]:
                self.game_path.setStyleSheet("")
                self.game_path.setText(rtl(r["dir"]))
                colored(self.t_mod, OK if self.mod_installed else WARN,
                        "مركّب" if self.mod_installed else "مو مركّب — أعد التركيب")
                colored(self.t_game, OK if self.game_running else MUTED, "شغّالة" if self.game_running else "مسكّرة")
            else:
                colored(self.game_path, BAD, "ما لقيت اللعبة بمكتبات ستيم — اختر مجلدها")
                colored(self.t_mod, MUTED, "—")
                colored(self.t_game, BAD, "ما لقيتها")
            self.update_buttons()
        self.bg(check, done)

    def apply_linked_ui(self):
        """بلا أي حساب مربوط: لا موديل ولا إعدادات — بس «اربط حساب أول»."""
        linked = bool(self.any_linked)
        for w in self.gated:
            w.setVisible(linked)
        for btn, msg in self.save_rows:
            btn.setVisible(linked)
            msg.setVisible(linked)
        for banner in self.link_banners:
            banner.setVisible(not linked)
        self.translate_box.setVisible(linked)
        if not linked:
            self.t_model.setText("—")
            for box in (self.llm_model, self.fallback):
                box.clear()

    def update_translate_count(self):
        self.translate_count.setText(f"المحفوظ: {nox_translate.count(nox_settings.game_dir())} نص")

    def clear_translations(self):
        if QMessageBox.question(self, "NoxBridge", "تمسح كل الترجمات المحفوظة؟ بتنترجم من جديد وأنت تلعب.",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            nox_translate.clear(nox_settings.game_dir())
            self.update_translate_count()

    def on_game_closed(self):
        nox_bridge.log("⏹ اللعبة تسكّرت")
        if nox_settings.bridge_settings().get("auto_unload") and nox_bridge.BRIDGE.local.loaded_keys:
            self.local_unload(ask=False)

    def update_buttons(self):
        idle = not self.busy and not self.game_running
        self.btn_install.setEnabled(idle)
        self.btn_restore.setEnabled(idle)
        self.btn_timeout.setEnabled(idle)
        self.btn_play.setEnabled(not self.game_running and not self.busy)
        if not self.busy:
            self.install_msg.setText("اللعبة شغّالة — التركيب يحتاجها مسكّرة." if self.game_running else "")

    # ---------------------------------------------------------------- أفعال
    def play(self):
        if not self.mod_installed:
            ask = QMessageBox.question(self, "NoxBridge", "المود مو مركّب (يمكن ستيم حدّث اللعبة).\nأركّبه أول؟",
                                       QMessageBox.Yes | QMessageBox.No)
            if ask == QMessageBox.Yes:
                self.install(then_play=True)
                return
        model = self.saved_llm or ""
        local = nox_bridge.BRIDGE.local
        if model.startswith(nox_providers.LOCAL_PREFIX) and local.reachable \
                and model[len(nox_providers.LOCAL_PREFIX):] not in local.loaded_keys:
            ask = QMessageBox.question(self, "NoxBridge",
                                       "موديل الرد محلي ومو محمّل على الكرت — أول رد بيتأخر وممكن يتعدّى مهلة اللعبة.\n"
                                       "أحمّله قبل ما أشغّل اللعبة؟", QMessageBox.Yes | QMessageBox.No)
            if ask == QMessageBox.Yes:
                self.local_load(then=self._start_game)
                return
        self._start_game()

    def _start_game(self):
        os.startfile(STEAM_URL)
        nox_bridge.log("▶ شغّلت اللعبة من ستيم")

    def _run_patcher(self, title: str, fn, then=None):
        self.busy = True
        self.update_buttons()
        self.install_msg.setText(f"{title}… (دقيقة تقريباً)")
        nox_bridge.log(f"⚙ {title}…")

        def done(r):
            self.busy = False
            for line in (r.get("output") or "").splitlines():
                nox_bridge.log("   " + line)
            if r.get("ok"):
                nox_bridge.log(f"✅ {title}: تم")
                colored(self.install_msg, OK, f"✓ {title}: تم")
                if then:
                    then()
            else:
                nox_bridge.log(f"❌ {title}: {r.get('error')}")
                colored(self.install_msg, BAD, "✗ " + str(r.get("error")))
                QMessageBox.warning(self, "NoxBridge", f"{title} فشل:\n{r.get('error')}")
            self._mod_stamp = object()  # إجبار فحص المود من جديد
            self.refresh_status()
        self.bg(fn, done)

    def install(self, then_play=False):
        self._run_patcher("إعادة التركيب", lambda: nox_settings.install(),
                          then=(lambda: os.startfile(STEAM_URL)) if then_play else None)

    def apply_timeout(self):
        seconds = self.timeout.value()
        self._run_patcher("تغيير المهلة", lambda: nox_settings.install(seconds))

    def _show_timeout(self, applied):
        self.timeout.setValue(int(round(float(nox_settings.bridge_settings().get("timeout") or 15))))
        if applied:
            self.timeout_msg.setText(f"المطبّق باللعبة الحين: {float(applied):g} ثانية.")
        else:
            self.timeout_msg.setText("المود مو مركّب — اللعبة على مهلتها الأصلية (١٥ ثانية).")

    def choose_game_dir(self):
        start = nox_settings.game_dir() or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "مجلد اللعبة (اللي فيه Scam With Your Friends.exe)", start)
        if not d:
            return
        if not nox_settings.set_game_dir(d):
            QMessageBox.warning(self, "NoxBridge", f"هذا المجلد ما فيه {nox_settings.GAME_EXE}.\n"
                                                   "اختر مجلد اللعبة نفسه (ستيم ← كليك يمين على اللعبة ← Manage ← Browse local files).")
            return
        nox_bridge.log(f"⚙ مجلد اللعبة: {d}")
        self._mod_stamp = object()   # إجبار فحص المود من جديد
        self.refresh_status()
        self.load_settings()

    def restore(self):
        ask = QMessageBox.question(
            self, "NoxBridge",
            "يرجّع ملفات اللعبة أصلية ويشيل المود، ويرجّع إعداد الذكاء حق اللعبة للأصلي.\n"
            "بعدها الشخصيات تشتغل على خدمة اللعبة نفسها مو على اشتراكك.\n\nمتأكد؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ask == QMessageBox.Yes:
            self._run_patcher("إرجاع اللعبة أصلية", nox_settings.restore)

    # ---------------------------------------------------------------- الإعدادات
    def _save_state(self, enabled: bool, text: str, color: str = None):
        for btn, msg in self.save_rows:
            btn.setEnabled(enabled)
            if color:
                colored(msg, color, text)
            else:
                msg.setStyleSheet("")
                msg.setText(text)

    def load_settings(self):
        self._save_state(False, "أجيب الموديلات…")

        def fetch():
            groups = []
            for prov in PROVIDERS:
                prov.probe()
                if prov.status()[0]:
                    ids = [m["id"] for m in prov.models()]
                    if ids:
                        groups.append((prov, ids))
            return {"groups": groups, "settings": nox_settings.current()}

        def done(r):
            if "settings" not in r:
                self._save_state(False, "✗ ما قدرت أقرا الإعدادات: " + str(r.get("error")), BAD)
                return
            s, groups = r["settings"], r["groups"]
            linked = bool(groups) and bool(self.any_linked)
            if linked:
                self.fill_models(self.llm_model, groups, s["llm_model"], with_none=False)
                self.fill_models(self.fallback, groups, s["fallback_model"], with_none=True)
            else:
                self.llm_model.clear()
                self.fallback.clear()
            for box, value in ((self.reasoning, s["reasoning_effort"]), (self.tts, s["tts"]), (self.stt, s["stt"]),
                               (self.difficulty, s["difficulty"])):
                box.setCurrentIndex(max(0, box.findData(value)))
            self.hedge.setValue(float(s["hedge_after"]))
            self.translate.setChecked(bool(s.get("translate", True)))
            self._show_timeout(s.get("timeout"))
            self.t_model.setText(model_label(s["llm_model"]) if linked else "—")
            self.saved_llm = (s["llm_model"] or "") if linked else ""
            if linked:
                self._save_state(True, "تطبق خلال ثانية حتى واللعبة شغّالة.")
            else:
                self._save_state(False, "اربط حساب أول من صفحة «الحسابات».")
            self.apply_linked_ui()
            self.check_hedge()
        self.bg(fetch, done)

    @staticmethod
    def fill_models(box: QComboBox, groups, current: str, with_none: bool):
        box.clear()
        if with_none:
            box.addItem("بدون احتياط", "")
        known = {m for _, ids in groups for m in ids}
        if current and current not in known:
            add_header(box, "— المحفوظ —")
            box.addItem("   " + model_label(current), current)
        for prov, ids in groups:
            add_header(box, f"— {prov.name} —")
            for i in ids:
                box.addItem("   " + i[len(prov.prefix):], i)
        idx = box.findData(current)
        if idx < 0:
            idx = next((i for i in range(box.count()) if box.itemData(i) is not None), 0)
        box.setCurrentIndex(idx)

    def check_hedge(self):
        bad = bool(self.fallback.currentData()) and self.hedge.value() > self.timeout.value() - 4
        if bad:
            colored(self.hedge_hint, WARN, f"⚠ قريب من مهلة اللعبة ({self.timeout.value()} ثانية) — الاحتياط ما يلحق يرد. "
                                           f"خلّه {max(3, self.timeout.value() - 8)} أو أقل.")
        else:
            self.hedge_hint.setStyleSheet("")
            self.hedge_hint.setText("لو الموديل ما رد خلال هالوقت، نفس الطلب يروح للاحتياط وأول رد يفوز.")

    def save_settings(self):
        data = {
            "llm_model": self.llm_model.currentData() or "",
            "reasoning_effort": self.reasoning.currentData(),
            "fallback_model": self.fallback.currentData() or "",
            "hedge_after": self.hedge.value(),
            "tts": self.tts.currentData(),
            "stt": self.stt.currentData(),
            "difficulty": self.difficulty.currentData(),
            "translate": self.translate.isChecked(),
        }
        r = nox_settings.save(data)
        if r["ok"]:
            self._save_state(True, "✓ انحفظت", OK)
            self.t_model.setText(model_label(data["llm_model"]))
            self.saved_llm = data["llm_model"]
            b = nox_settings.bridge_settings()
            nox_bridge.log(f"⚙ الإعدادات انحفظت: {data['llm_model']} · تفكير {b['reasoning_effort'] or 'بدون'}"
                           f" · احتياط {b['fallback_model'] or 'بدون'} بعد {b['hedge_after']:g}s")
        else:
            self._save_state(True, "✗ " + r["error"], BAD)

    # ---------------------------------------------------------------- الإغلاق
    def closeEvent(self, event):
        # البرنامج ما يشتغل بالخلفية: الإغلاق = يقفل (والجسر معه)
        if self.game_running:
            ask = QMessageBox.question(
                self, "NoxBridge",
                "اللعبة شغّالة — لو قفلت البرنامج يوقف الجسر والشخصيات ما ترد.\nتقفل؟",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ask != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()


# ═══════════════════════════════════════════════════════════════ التشغيل

def setup_style(app: QApplication):
    # Fusion: شريط التمرير ظاهر دايم (ستايل ويندوز 11 يخفيه). بس Fusion يتبع الوضع الداكن
    # حق ويندوز ⇒ القوائم وخانات الأرقام تطلع سودا — نثبّت الفاتح.
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:
        pass
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyleSheet(STYLE)
    app.setWindowIcon(make_icon())


def main() -> int:
    sys.excepthook = log_crash
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)  # أيقونتنا بشريط المهام
    except Exception:
        pass

    app = QApplication(sys.argv)
    setup_style(app)

    bus = LogBus()
    nox_bridge.LOG_LISTENERS.append(lambda stamp, line: bus.line.emit(stamp, line))
    nox_bridge.LOGIN_LISTENERS.append(lambda provider, url, code: bus.login.emit(provider, url, code))
    nox_bridge.init_bridge(prompt_login=False)   # الدخول بس لما يضغط «ربط» — ما ينفتح المتصفح لحاله
    try:
        server = nox_bridge.start_server(login_on_start=False)
    except OSError:
        QMessageBox.information(None, "NoxBridge",
                                "NoxBridge شغّال أصلاً — شوف أيقونته جنب الساعة (يمكن تحت سهم الأيقونات المخفية).\n"
                                f"لو مو هو، فيه برنامج ثاني ماسك المنفذ {nox_bridge.PORT}.")
        return 1
    threading.Thread(target=server.serve_forever, daemon=True).start()

    win = MainWindow(bus)
    win.show()
    code = app.exec()
    server.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
