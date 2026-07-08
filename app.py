"""
Cloudflare CDN Toolkit — unified desktop GUI.

Tabs:
  1. Scan       — pull a vless config list, filter to Cloudflare IPs, ping,
                  save alive IPs.
  2. Speed Test — v2rayN-style xray-core real speed test against candidate IPs.
  3. DNS Update — replace A records for a hostname with the top N IPs via the
                  Cloudflare API.
  4. Profiles   — save/load VLESS + Cloudflare presets to disk.

Requires: PySide6, requests, pysocks, xray-core binary on PATH or next to
the script for the Speed Test tab.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, QObject, QThread, Signal, QSize, QTimer, Slot
from PySide6.QtGui import QFont, QIcon, QTextCursor, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSpinBox,
    QDoubleSpinBox, QPlainTextEdit, QSplitter, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

# ---- pull in existing modules ---------------------------------------------
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cloudflare_api import (  # noqa: E402
    CloudflareAPI, CloudflareAuthError, CloudflareError,
    CloudflareNotFoundError, CloudflareRateLimitError,
)
import scanner  # noqa: E402
import xray_test  # noqa: E402
from utils import load_ips_from_file  # noqa: E402


PROFILES_FILE = HERE / "profiles.json"


# ===========================================================================
# Neon-mint hacker theme (QSS)
# ===========================================================================
QSS = """
* { font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace; }

QWidget {
    background: #0d1b2a;
    color: #d6f5e6;
    selection-background-color: #2dd4a8;
    selection-color: #0d1b2a;
}

QMainWindow, QDialog { background: #0a1420; }

QTabWidget::pane {
    border: 1px solid #143a2c;
    border-radius: 8px;
    background: #0f2233;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #6fbf9b;
    padding: 10px 22px;
    border: 1px solid transparent;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    letter-spacing: 1px;
}
QTabBar::tab:hover { color: #73ffb8; }
QTabBar::tab:selected {
    color: #0d1b2a;
    background: #2dd4a8;
    border: 1px solid #2dd4a8;
}

QLabel { background: transparent; color: #b8e6d0; }
QLabel[role="title"] {
    color: #73ffb8;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 2px;
}
QLabel[role="hint"] { color: #5a8a72; font-size: 11px; }
QLabel[role="status-ok"]  { color: #73ffb8; font-weight: 700; }
QLabel[role="status-err"] { color: #ff5b6b; font-weight: 700; }
QLabel[role="status-idle"]{ color: #6b8a80; font-weight: 700; }

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #0a1420;
    color: #d6f5e6;
    border: 1px solid #1b4332;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #2dd4a8;
    selection-color: #0d1b2a;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus {
    border: 1px solid #2dd4a8;
}
QTextEdit, QPlainTextEdit { font-size: 12px; }

QPushButton {
    background: transparent;
    color: #73ffb8;
    border: 1px solid #2dd4a8;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 700;
    letter-spacing: 1px;
}
QPushButton:hover { background: rgba(45,212,168, 0.12); }
QPushButton:pressed { background: rgba(45,212,168, 0.24); }
QPushButton:disabled { color: #3d5a4c; border-color: #21382c; }
QPushButton[role="primary"] {
    background: #2dd4a8;
    color: #0d1b2a;
    border: 1px solid #2dd4a8;
}
QPushButton[role="primary"]:hover { background: #73ffb8; border-color: #73ffb8; }
QPushButton[role="danger"] {
    color: #ff8189;
    border-color: #ff5b6b;
}
QPushButton[role="danger"]:hover { background: rgba(255,91,107,0.12); }

QProgressBar {
    background: #0a1420;
    border: 1px solid #1b4332;
    border-radius: 6px;
    text-align: center;
    color: #d6f5e6;
    height: 18px;
}
QProgressBar::chunk {
    background: #2dd4a8;
    border-radius: 5px;
}

QTableWidget {
    background: #0a1420;
    alternate-background-color: #0f2233;
    gridline-color: #143a2c;
    border: 1px solid #143a2c;
    border-radius: 6px;
}
QHeaderView::section {
    background: #0f2233;
    color: #73ffb8;
    border: none;
    border-bottom: 1px solid #2dd4a8;
    padding: 6px 8px;
    font-weight: 700;
    letter-spacing: 1px;
}
QTableWidget::item:selected {
    background: rgba(45,212,168, 0.22);
    color: #d6f5e6;
}

QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #2dd4a8;
    border-radius: 3px;
    background: #0a1420;
}
QCheckBox::indicator:checked { background: #2dd4a8; }

QScrollBar:vertical, QScrollBar:horizontal {
    background: #0a1420;
    border: none;
}
QScrollBar:vertical { width: 10px; }
QScrollBar:horizontal { height: 10px; }
QScrollBar::handle {
    background: #1b4332;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:hover { background: #2dd4a8; }
QScrollBar::add-line, QScrollBar::sub-line { background: none; border: none; }

QFrame[role="card"] {
    background: #0f2233;
    border: 1px solid #143a2c;
    border-radius: 10px;
}
QFrame[role="divider"] {
    background: #143a2c;
    max-height: 1px;
    min-height: 1px;
}
"""


# ===========================================================================
# Profiles
# ===========================================================================
@dataclass
class Profile:
    name: str
    uuid: str = xray_test.DEFAULT_UUID
    sni: str = xray_test.DEFAULT_SNI
    host: str = xray_test.DEFAULT_HOST
    path: str = xray_test.DEFAULT_PATH
    port: int = xray_test.DEFAULT_PORT
    api_token: str = ""
    zone_id: str = ""
    record_name: str = ""
    scanner_url: str = scanner.DEFAULT_URL


def load_profiles() -> List[Profile]:
    if not PROFILES_FILE.exists():
        return []
    try:
        raw = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        return [Profile(**p) for p in raw]
    except Exception:
        return []


def save_profiles(profiles: List[Profile]) -> None:
    PROFILES_FILE.write_text(
        json.dumps([asdict(p) for p in profiles], indent=2),
        encoding="utf-8",
    )


# ===========================================================================
# Workers
# ===========================================================================
class BaseWorker(QObject):
    log = Signal(str)
    progress = Signal(int, int)
    finished = Signal(bool, str)

    def _emit(self, msg: str) -> None:
        self.log.emit(msg)


class ScanWorker(BaseWorker):
    def __init__(self, url: str, output: str, workers: int, timeout: int,
                 cf_only: bool, tcp_fallback: bool) -> None:
        super().__init__()
        self.url, self.output = url, output
        self.workers, self.timeout = workers, timeout
        self.cf_only, self.tcp_fallback = cf_only, tcp_fallback

    def run(self) -> None:
        try:
            self._emit(f">>> Downloading {self.url}")
            lines = scanner.download_configs(self.url)
            self._emit(f"    {len(lines)} vless entries")

            networks = None
            if self.cf_only:
                self._emit(">>> Fetching Cloudflare IP ranges")
                networks = scanner.fetch_cloudflare_networks()
                self._emit(f"    {len(networks)} CIDR blocks loaded")

            self._emit(">>> Filtering & resolving port 443 hosts")
            endpoints = scanner.collect_port_443_endpoints(lines, networks=networks)
            self._emit(f"    {len(endpoints)} unique endpoints")

            if not endpoints:
                self.finished.emit(False, "No endpoints to test.")
                return

            self._emit(f">>> Pinging with {self.workers} workers")
            alive: list[str] = []
            import concurrent.futures as cf

            def check(ep):
                if scanner.ping(ep.ip, timeout=self.timeout):
                    return ep.ip
                if self.tcp_fallback and scanner.tcp_ping(ep.ip, ep.port,
                                                          timeout=self.timeout):
                    return ep.ip
                return None

            total = len(endpoints)
            with cf.ThreadPoolExecutor(max_workers=self.workers) as pool:
                futs = {pool.submit(check, ep): ep for ep in endpoints}
                for i, fut in enumerate(cf.as_completed(futs), 1):
                    ep = futs[fut]
                    res = fut.result()
                    tag = "OK" if res else "--"
                    self._emit(f"[{i}/{total}] {tag}  {ep.ip:<16} ({ep.host})")
                    if res:
                        alive.append(res)
                    self.progress.emit(i, total)

            alive.sort()
            scanner.save_ips(alive, self.output)
            self._emit(f"\n{len(alive)} alive IPs saved to {self.output}")
            self.finished.emit(True, f"{len(alive)} alive IPs")
        except Exception as e:
            self._emit(f"ERROR: {e}")
            self.finished.emit(False, str(e))


class XrayWorker(BaseWorker):
    result_row = Signal(object)  # xray_test.Result

    def __init__(self, ips: List[str], xray_bin: str, profile: Profile,
                 speed_url: str, min_mbps: float, duration: float,
                 timeout: float, output: str, strict: bool) -> None:
        super().__init__()
        self.ips = ips
        self.xray_bin = xray_bin
        self.profile = profile
        self.speed_url = speed_url
        self.min_mbps = min_mbps
        self.duration = duration
        self.timeout = timeout
        self.output = output
        self.strict = strict

    def run(self) -> None:
        try:
            self._emit(f">>> xray: {self.xray_bin}")
            self._emit(f">>> {len(self.ips)} IPs  SNI={self.profile.sni}  "
                       f"host={self.profile.host}  path={self.profile.path}")
            results: List[xray_test.Result] = []
            total = len(self.ips)
            for i, ip in enumerate(self.ips, 1):
                r = xray_test.probe_ip(
                    ip, self.xray_bin, self.profile.port, self.profile.uuid,
                    self.profile.sni, self.profile.host, self.profile.path,
                    self.speed_url, self.duration, self.timeout,
                )
                results.append(r)
                if r.ok:
                    tag = "OK  " if r.mbps >= self.min_mbps else "SLOW"
                    lat = f"{r.latency_ms:>7.1f}" if r.latency_ms else "   ---"
                    self._emit(f"[{i}/{total}] {tag} {r.ip:<16} {lat} ms  "
                               f"{r.mbps:>6.2f} MB/s")
                else:
                    self._emit(f"[{i}/{total}] FAIL {r.ip:<16}   "
                               f"{r.status}  {r.detail}")
                self.result_row.emit(r)
                self.progress.emit(i, total)

            xray_test.save_outputs(results, self.output, self.min_mbps,
                                   self.strict)
            good = sum(1 for r in results if r.ok and r.mbps >= self.min_mbps)
            self._emit(f"\n{good}/{len(results)} IPs met "
                       f"{self.min_mbps} MB/s target.")
            self._emit(f"Sorted list saved to {self.output}")
            self.finished.emit(True, f"{good} fast IPs")
        except Exception as e:
            self._emit(f"ERROR: {e}")
            self.finished.emit(False, str(e))


class DnsWorker(BaseWorker):
    def __init__(self, api_token: str, zone_id: str, record_name: str,
                 ips: List[str]) -> None:
        super().__init__()
        self.api_token = api_token
        self.zone_id = zone_id
        self.record_name = record_name
        self.ips = ips

    def run(self) -> None:
        try:
            api = CloudflareAPI(self.api_token, self.zone_id,
                                logger=self._emit)
            self._emit(">>> Verifying API token")
            api.verify_token()
            self._emit("    Token OK")

            self._emit(f">>> Listing existing A records for {self.record_name}")
            existing = api.list_a_records(self.record_name)
            self._emit(f"    {len(existing)} records found")

            total = len(existing) + len(self.ips)
            step = 0
            for rec in existing:
                try:
                    api.delete_record(rec.id)
                    self._emit(f"    - deleted {rec.content}")
                except CloudflareError as e:
                    self._emit(f"    ! delete failed {rec.content}: {e}")
                step += 1
                self.progress.emit(step, max(total, 1))

            errors = 0
            for ip in self.ips:
                try:
                    api.create_a_record(name=self.record_name, ip=ip,
                                        proxied=False, ttl=1)
                    self._emit(f"    + created {self.record_name} -> {ip}")
                except CloudflareError as e:
                    errors += 1
                    self._emit(f"    ! create failed {ip}: {e}")
                step += 1
                self.progress.emit(step, max(total, 1))

            if errors:
                self.finished.emit(False, f"{errors} errors")
            else:
                self.finished.emit(True, "DNS updated")
        except (CloudflareAuthError,) as e:
            self.finished.emit(False, f"Auth error: {e}")
        except (CloudflareNotFoundError,) as e:
            self.finished.emit(False, f"Not found: {e}")
        except (CloudflareRateLimitError,) as e:
            self.finished.emit(False, f"Rate limited: {e}")
        except Exception as e:
            self._emit(f"ERROR: {e}")
            self.finished.emit(False, str(e))


# ===========================================================================
# Reusable UI helpers
# ===========================================================================
def card(child: QWidget) -> QFrame:
    f = QFrame()
    f.setProperty("role", "card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(10)
    lay.addWidget(child)
    return f


def title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "title")
    return lbl


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "hint")
    lbl.setWordWrap(True)
    return lbl


def divider() -> QFrame:
    f = QFrame()
    f.setProperty("role", "divider")
    return f


class LogPane(QPlainTextEdit):
    """Paint-safe, buffered log widget.

    Windows Qt can hit recursive repaint errors when many worker signals append
    directly to a QTextEdit.  Buffering into QPlainTextEdit turns dozens of
    append/repaint cycles into one small flush per timer tick.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setMinimumHeight(220)
        # Bound the log so rapid appends never trigger runaway repaints.
        self.document().setMaximumBlockCount(2000)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._pending: list[str] = []
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(80)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush)

    @Slot(str)
    def write(self, text: str) -> None:
        self._pending.append(text)
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def clear(self) -> None:
        self._pending.clear()
        self._flush_timer.stop()
        super().clear()

    def _flush(self) -> None:
        if not self._pending:
            return
        chunk = "\n".join(self._pending)
        self._pending.clear()
        self.appendPlainText(chunk)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class ProgressProxy(QObject):
    """Coalesces worker progress signals before touching QProgressBar."""

    def __init__(self, bar: QProgressBar) -> None:
        super().__init__(bar)
        self.bar = bar
        self._latest = (0, 1)
        self._last_total = 1
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush)

    @Slot(int, int)
    def set_progress(self, current: int, total: int) -> None:
        self._latest = (current, max(total, 1))
        if not self._timer.isActive():
            self._timer.start()

    def reset(self) -> None:
        self._latest = (0, 1)
        self._last_total = 1
        self._timer.stop()
        self.bar.setRange(0, 1)
        self.bar.setValue(0)

    def finish(self) -> None:
        self._timer.stop()
        self._flush()

    def _flush(self) -> None:
        current, total = self._latest
        if total != self._last_total:
            self.bar.setRange(0, total)
            self._last_total = total
        self.bar.setValue(current)


# ===========================================================================
# Tabs
# ===========================================================================
class ScanTab(QWidget):
    def __init__(self, main: "MainWindow") -> None:
        super().__init__()
        self.main = main
        self.thread: Optional[QThread] = None
        self.worker: Optional[ScanWorker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)
        root.addWidget(title("◉ SCAN  ·  find alive Cloudflare IPs"))
        root.addWidget(hint(
            "Pulls a VLESS config list, filters port-443 Cloudflare hosts, "
            "resolves them, and pings for reachability. Output → alive_ips.txt."
        ))

        form = QFormLayout()
        form.setSpacing(8)
        self.url = QLineEdit(scanner.DEFAULT_URL)
        self.output = QLineEdit(scanner.DEFAULT_OUTPUT)
        self.workers = QSpinBox()
        self.workers.setRange(1, 500); self.workers.setValue(50)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 30); self.timeout.setValue(2)
        self.cf_only = QCheckBox("Cloudflare IPs only"); self.cf_only.setChecked(True)
        self.tcp_fb = QCheckBox("TCP:443 fallback"); self.tcp_fb.setChecked(True)

        form.addRow("Config URL:", self.url)
        form.addRow("Output file:", self.output)
        form.addRow("Workers:", self.workers)
        form.addRow("Ping timeout (s):", self.timeout)
        form.addRow("", self.cf_only)
        form.addRow("", self.tcp_fb)

        form_w = QWidget(); form_w.setLayout(form)
        root.addWidget(card(form_w))

        actions = QHBoxLayout()
        self.start = QPushButton("▶  Start scan")
        self.start.setProperty("role", "primary")
        self.start.clicked.connect(self.run)
        self.stop_hint = QLabel("Scanning runs on a background thread.")
        self.stop_hint.setProperty("role", "hint")
        actions.addWidget(self.start)
        actions.addStretch(1)
        actions.addWidget(self.stop_hint)
        root.addLayout(actions)

        self.progress = QProgressBar(); self.progress.setRange(0, 1)
        root.addWidget(self.progress)
        self.progress_proxy = ProgressProxy(self.progress)

        self.log = LogPane()
        root.addWidget(self.log, 1)

    def run(self) -> None:
        if self.thread and self.thread.isRunning():
            return
        self.start.setEnabled(False)
        self.log.clear()
        self.progress_proxy.reset()
        w = ScanWorker(
            self.url.text().strip(), self.output.text().strip(),
            self.workers.value(), self.timeout.value(),
            self.cf_only.isChecked(), self.tcp_fb.isChecked(),
        )
        self.worker = w
        self.thread = QThread()
        w.moveToThread(self.thread)
        self.thread.started.connect(w.run)
        w.log.connect(self.log.write)
        w.progress.connect(self.progress_proxy.set_progress)
        w.finished.connect(self._done)
        w.finished.connect(self.thread.quit)
        w.finished.connect(w.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _done(self, ok: bool, msg: str) -> None:
        self.progress_proxy.finish()
        self.start.setEnabled(True)
        self.main.set_status("SCAN", ok, msg)
        if ok:
            # push output path into speed test / dns tabs
            self.main.speed.ip_file.setText(self.output.text().strip())


class SpeedTab(QWidget):
    def __init__(self, main: "MainWindow") -> None:
        super().__init__()
        self.main = main
        self.thread: Optional[QThread] = None
        self.worker: Optional[XrayWorker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20); root.setSpacing(14)
        root.addWidget(title("◉ SPEED  ·  v2rayN-style xray-core test"))
        root.addWidget(hint(
            "Boots a local xray SOCKS proxy against your VLESS config, one "
            "candidate IP at a time, and measures real MB/s through the tunnel."
        ))

        # Config grid
        grid = QGridLayout(); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(8)
        self.uuid = QLineEdit(xray_test.DEFAULT_UUID)
        self.sni = QLineEdit(xray_test.DEFAULT_SNI)
        self.host = QLineEdit(xray_test.DEFAULT_HOST)
        self.path = QLineEdit(xray_test.DEFAULT_PATH)
        self.port = QSpinBox(); self.port.setRange(1, 65535); self.port.setValue(xray_test.DEFAULT_PORT)
        self.speed_url = QLineEdit(xray_test.DEFAULT_SPEED_URL)
        self.min_mbps = QDoubleSpinBox(); self.min_mbps.setRange(0.0, 100.0)
        self.min_mbps.setValue(xray_test.DEFAULT_MIN_MBPS); self.min_mbps.setSingleStep(0.1)
        self.duration = QDoubleSpinBox(); self.duration.setRange(1.0, 60.0)
        self.duration.setValue(xray_test.DEFAULT_DURATION)
        self.strict = QCheckBox("Strict (only save IPs ≥ target)")

        self.xray_bin = QLineEdit()
        try:
            self.xray_bin.setText(xray_test._find_xray(None))
        except SystemExit:
            self.xray_bin.setPlaceholderText("Path to xray/xray.exe")
        xray_browse = QPushButton("…")
        xray_browse.setFixedWidth(36)
        xray_browse.clicked.connect(self._pick_xray)
        xray_row = QHBoxLayout(); xray_row.addWidget(self.xray_bin, 1); xray_row.addWidget(xray_browse)
        xray_w = QWidget(); xray_w.setLayout(xray_row)

        self.ip_file = QLineEdit(xray_test.DEFAULT_INPUT)
        ip_browse = QPushButton("…"); ip_browse.setFixedWidth(36)
        ip_browse.clicked.connect(self._pick_ips)
        ip_row = QHBoxLayout(); ip_row.addWidget(self.ip_file, 1); ip_row.addWidget(ip_browse)
        ip_w = QWidget(); ip_w.setLayout(ip_row)

        self.output = QLineEdit(xray_test.DEFAULT_OUTPUT)

        def add_row(r, lbl, w1, lbl2=None, w2=None):
            grid.addWidget(QLabel(lbl), r, 0)
            grid.addWidget(w1, r, 1)
            if lbl2:
                grid.addWidget(QLabel(lbl2), r, 2)
                grid.addWidget(w2, r, 3)

        add_row(0, "UUID:", self.uuid, "Port:", self.port)
        add_row(1, "SNI:", self.sni, "Host:", self.host)
        add_row(2, "Path:", self.path, "Min MB/s:", self.min_mbps)
        add_row(3, "Duration (s):", self.duration, "Strict:", self.strict)
        add_row(4, "Speed URL:", self.speed_url)
        add_row(5, "xray binary:", xray_w)
        add_row(6, "IP list:", ip_w, "Output:", self.output)

        grid_w = QWidget(); grid_w.setLayout(grid)
        root.addWidget(card(grid_w))

        actions = QHBoxLayout()
        self.start = QPushButton("▶  Start speed test")
        self.start.setProperty("role", "primary")
        self.start.clicked.connect(self.run)
        self.push_dns = QPushButton("Send top IPs → DNS tab")
        self.push_dns.clicked.connect(self._push_top)
        actions.addWidget(self.start)
        actions.addWidget(self.push_dns)
        actions.addStretch(1)
        root.addLayout(actions)

        self.progress = QProgressBar(); self.progress.setRange(0, 1)
        root.addWidget(self.progress)
        self.progress_proxy = ProgressProxy(self.progress)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["IP", "Latency ms", "MB/s", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.log = LogPane()
        split.addWidget(self.table)
        split.addWidget(self.log)
        split.setSizes([500, 500])
        root.addWidget(split, 1)

    def _pick_xray(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Locate xray binary", "",
                                              "Executables (*.exe);;All files (*)")
        if path: self.xray_bin.setText(path)

    def _pick_ips(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "IP list", "", "Text (*.txt)")
        if path: self.ip_file.setText(path)

    def _push_top(self) -> None:
        # pull top N from the current table
        n, ok = QInputDialog.getInt(self, "Send to DNS",
                                    "How many top IPs?", 5, 1, 200)
        if not ok: return
        rows = [self.table.item(i, 0).text() for i in range(min(n, self.table.rowCount()))]
        if not rows:
            QMessageBox.warning(self, "No IPs", "Run a speed test first.")
            return
        self.main.dns.set_ips(rows)
        self.main.tabs.setCurrentWidget(self.main.dns)

    def run(self) -> None:
        if self.thread and self.thread.isRunning(): return
        xray_bin = self.xray_bin.text().strip()
        if not xray_bin or not Path(xray_bin).exists():
            QMessageBox.warning(self, "xray missing",
                                "Locate the xray binary first.")
            return
        try:
            ips = load_ips_from_file(self.ip_file.text().strip())
        except Exception as e:
            QMessageBox.warning(self, "IP list", str(e)); return
        if not ips:
            QMessageBox.warning(self, "IP list", "Empty IP list."); return

        prof = self.main.current_profile()
        prof.uuid = self.uuid.text().strip()
        prof.sni = self.sni.text().strip()
        prof.host = self.host.text().strip()
        prof.path = self.path.text().strip()
        prof.port = self.port.value()

        self.start.setEnabled(False)
        self.log.clear(); self.table.setRowCount(0)
        self.progress_proxy.reset()

        w = XrayWorker(ips, xray_bin, prof, self.speed_url.text().strip(),
                       self.min_mbps.value(), self.duration.value(),
                       xray_test.DEFAULT_TIMEOUT, self.output.text().strip(),
                       self.strict.isChecked())
        self.worker = w; self.thread = QThread()
        w.moveToThread(self.thread)
        self.thread.started.connect(w.run)
        w.log.connect(self.log.write)
        w.progress.connect(self.progress_proxy.set_progress)
        w.result_row.connect(self._add_row)
        w.finished.connect(self._done)
        w.finished.connect(self.thread.quit)
        w.finished.connect(w.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _add_row(self, r) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        lat = f"{r.latency_ms:.1f}" if r.latency_ms is not None else "—"
        vals = [r.ip, lat, f"{r.mbps:.2f}", r.status]
        for i, v in enumerate(vals):
            item = QTableWidgetItem(v)
            if r.ok and r.mbps >= self.min_mbps.value():
                item.setForeground(QColor("#73ffb8"))
            elif r.ok:
                item.setForeground(QColor("#e8c07a"))
            else:
                item.setForeground(QColor("#ff8189"))
            self.table.setItem(row, i, item)
        # keep sorted by mbps desc
        # sort only when the run finishes (see _done) — sorting every row
        # while signals flood the event loop caused QBackingStore paint errors.

    def _done(self, ok: bool, msg: str) -> None:
        self.progress_proxy.finish()
        self.start.setEnabled(True)
        self.table.setSortingEnabled(True)
        self.table.sortItems(2, Qt.SortOrder.DescendingOrder)
        self.main.set_status("SPEED", ok, msg)


class DnsTab(QWidget):
    def __init__(self, main: "MainWindow") -> None:
        super().__init__()
        self.main = main
        self.thread: Optional[QThread] = None
        self.worker: Optional[DnsWorker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20); root.setSpacing(14)
        root.addWidget(title("◉ DNS  ·  push top IPs to Cloudflare"))
        root.addWidget(hint(
            "Deletes existing A records for the hostname and re-creates them "
            "pointing at the IPs you provide. TTL Auto, unproxied."
        ))

        form = QFormLayout()
        self.token = QLineEdit(); self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("Cloudflare API token")
        self.zone = QLineEdit(); self.zone.setPlaceholderText("Zone ID")
        self.record = QLineEdit(); self.record.setPlaceholderText("record.example.com")
        form.addRow("API token:", self.token)
        form.addRow("Zone ID:", self.zone)
        form.addRow("Record name:", self.record)
        form_w = QWidget(); form_w.setLayout(form)
        root.addWidget(card(form_w))

        # IP list editor
        ip_head = QHBoxLayout()
        ip_head.addWidget(QLabel("IPs (one per line):"))
        ip_head.addStretch(1)
        load = QPushButton("Load file"); load.clicked.connect(self._load_ips)
        ip_head.addWidget(load)
        head_w = QWidget(); head_w.setLayout(ip_head)
        root.addWidget(head_w)

        self.ip_edit = QTextEdit()
        self.ip_edit.setPlaceholderText("104.16.1.2\n104.16.3.4\n...")
        self.ip_edit.setMinimumHeight(140)
        root.addWidget(self.ip_edit)

        actions = QHBoxLayout()
        self.start = QPushButton("▶  Replace records")
        self.start.setProperty("role", "primary")
        self.start.clicked.connect(self.run)
        clear = QPushButton("Clear IPs")
        clear.clicked.connect(lambda: self.ip_edit.clear())
        actions.addWidget(self.start); actions.addWidget(clear)
        actions.addStretch(1)
        root.addLayout(actions)

        self.progress = QProgressBar(); self.progress.setRange(0, 1)
        root.addWidget(self.progress)
        self.progress_proxy = ProgressProxy(self.progress)
        self.log = LogPane(); root.addWidget(self.log, 1)

    def set_ips(self, ips: List[str]) -> None:
        self.ip_edit.setPlainText("\n".join(ips))

    def _load_ips(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "IP list", "", "Text (*.txt)")
        if not path: return
        try:
            ips = load_ips_from_file(path)
            self.set_ips(ips)
        except Exception as e:
            QMessageBox.warning(self, "IP list", str(e))

    def run(self) -> None:
        if self.thread and self.thread.isRunning(): return
        token = self.token.text().strip()
        zone = self.zone.text().strip()
        rec = self.record.text().strip()
        ips = [ln.strip() for ln in self.ip_edit.toPlainText().splitlines()
               if ln.strip()]
        if not (token and zone and rec and ips):
            QMessageBox.warning(self, "Missing fields",
                                "Token, Zone ID, record and at least one IP required.")
            return
        self.start.setEnabled(False)
        self.log.clear()
        self.progress_proxy.reset()
        w = DnsWorker(token, zone, rec, ips)
        self.worker = w; self.thread = QThread()
        w.moveToThread(self.thread)
        self.thread.started.connect(w.run)
        w.log.connect(self.log.write)
        w.progress.connect(self.progress_proxy.set_progress)
        w.finished.connect(self._done)
        w.finished.connect(self.thread.quit)
        w.finished.connect(w.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _done(self, ok: bool, msg: str) -> None:
        self.progress_proxy.finish()
        self.start.setEnabled(True)
        self.main.set_status("DNS", ok, msg)


class ProfilesTab(QWidget):
    def __init__(self, main: "MainWindow") -> None:
        super().__init__()
        self.main = main
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20); root.setSpacing(14)
        root.addWidget(title("◉ PROFILES  ·  saved VLESS + DNS presets"))
        root.addWidget(hint(
            f"Stored in {PROFILES_FILE}. Load a profile to fill the Speed "
            "Test and DNS tabs; save current values as a new profile."
        ))

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Profile:"))
        self.combo = QComboBox(); self.combo.setMinimumWidth(240)
        bar.addWidget(self.combo)
        load = QPushButton("Load"); load.clicked.connect(self.load_selected)
        save = QPushButton("Save current as…")
        save.setProperty("role", "primary")
        save.clicked.connect(self.save_current)
        delete = QPushButton("Delete")
        delete.setProperty("role", "danger")
        delete.clicked.connect(self.delete_selected)
        bar.addWidget(load); bar.addWidget(save); bar.addWidget(delete)
        bar.addStretch(1)
        bar_w = QWidget(); bar_w.setLayout(bar)
        root.addWidget(card(bar_w))

        self.preview = QTextEdit(); self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(280)
        root.addWidget(self.preview, 1)

        self.refresh()

    def refresh(self) -> None:
        self.combo.clear()
        for p in self.main.profiles:
            self.combo.addItem(p.name)
        self._show_selected()
        self.combo.currentIndexChanged.connect(lambda _: self._show_selected())

    def _show_selected(self) -> None:
        i = self.combo.currentIndex()
        if 0 <= i < len(self.main.profiles):
            self.preview.setPlainText(
                json.dumps(asdict(self.main.profiles[i]), indent=2))
        else:
            self.preview.setPlainText("(no profiles yet)")

    def load_selected(self) -> None:
        i = self.combo.currentIndex()
        if not (0 <= i < len(self.main.profiles)): return
        p = self.main.profiles[i]
        s = self.main.speed
        s.uuid.setText(p.uuid); s.sni.setText(p.sni); s.host.setText(p.host)
        s.path.setText(p.path); s.port.setValue(p.port)
        d = self.main.dns
        d.token.setText(p.api_token); d.zone.setText(p.zone_id)
        d.record.setText(p.record_name)
        self.main.scan.url.setText(p.scanner_url)
        self.main.set_status("PROFILE", True, f"loaded {p.name}")

    def save_current(self) -> None:
        name, ok = QInputDialog.getText(self, "Save profile", "Name:")
        if not ok or not name.strip(): return
        s = self.main.speed; d = self.main.dns
        p = Profile(
            name=name.strip(),
            uuid=s.uuid.text().strip(), sni=s.sni.text().strip(),
            host=s.host.text().strip(), path=s.path.text().strip(),
            port=s.port.value(),
            api_token=d.token.text().strip(), zone_id=d.zone.text().strip(),
            record_name=d.record.text().strip(),
            scanner_url=self.main.scan.url.text().strip(),
        )
        # replace by name if exists
        self.main.profiles = [x for x in self.main.profiles if x.name != p.name]
        self.main.profiles.append(p)
        save_profiles(self.main.profiles)
        self.refresh()
        self.combo.setCurrentText(p.name)
        self.main.set_status("PROFILE", True, f"saved {p.name}")

    def delete_selected(self) -> None:
        i = self.combo.currentIndex()
        if not (0 <= i < len(self.main.profiles)): return
        name = self.main.profiles[i].name
        if QMessageBox.question(self, "Delete", f"Delete profile '{name}'?") \
                != QMessageBox.StandardButton.Yes:
            return
        del self.main.profiles[i]
        save_profiles(self.main.profiles)
        self.refresh()


# ===========================================================================
# Main window
# ===========================================================================
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cloudflare CDN Toolkit")
        self.resize(1180, 820)
        self.profiles: List[Profile] = load_profiles()

        central = QWidget(); self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 18, 18, 12); outer.setSpacing(10)

        # Header
        head = QHBoxLayout()
        brand = QLabel("◉  CF·CDN·TOOLKIT")
        brand.setProperty("role", "title")
        head.addWidget(brand)
        head.addStretch(1)
        self.status = QLabel("IDLE")
        self.status.setProperty("role", "status-idle")
        head.addWidget(self.status)
        outer.addLayout(head)
        outer.addWidget(divider())

        self.tabs = QTabWidget()
        self.scan = ScanTab(self)
        self.speed = SpeedTab(self)
        self.dns = DnsTab(self)
        self.profiles_tab = ProfilesTab(self)
        self.tabs.addTab(self.scan, "  SCAN  ")
        self.tabs.addTab(self.speed, "  SPEED  ")
        self.tabs.addTab(self.dns, "  DNS  ")
        self.tabs.addTab(self.profiles_tab, "  PROFILES  ")
        outer.addWidget(self.tabs, 1)

    def set_status(self, tag: str, ok: Optional[bool], msg: str = "") -> None:
        if ok is True:
            self.status.setProperty("role", "status-ok")
            text = f"● {tag}: {msg or 'OK'}"
        elif ok is False:
            self.status.setProperty("role", "status-err")
            text = f"● {tag}: {msg or 'ERROR'}"
        else:
            self.status.setProperty("role", "status-idle")
            text = f"● {tag}"
        self.status.setText(text)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def current_profile(self) -> Profile:
        s = self.speed
        return Profile(
            name="__current__",
            uuid=s.uuid.text().strip(), sni=s.sni.text().strip(),
            host=s.host.text().strip(), path=s.path.text().strip(),
            port=s.port.value(),
        )


def run() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    # Palette fallback for widgets that ignore QSS
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#0d1b2a"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#d6f5e6"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#0a1420"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#d6f5e6"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#0f2233"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#73ffb8"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#2dd4a8"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#0d1b2a"))
    app.setPalette(pal)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
