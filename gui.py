"""PySide6 GUI for the Cloudflare DNS Manager."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cloudflare_api import (
    CloudflareAPI,
    CloudflareAuthError,
    CloudflareError,
    CloudflareNotFoundError,
    CloudflareRateLimitError,
)
from utils import load_ips_from_file


@dataclass
class JobConfig:
    api_token: str
    zone_id: str
    record_name: str
    file_path: str


class Worker(QObject):
    """Runs the DNS update job on a background thread."""

    log = Signal(str)
    progress = Signal(int, int)  # current, total
    finished = Signal(bool, str)  # success, message

    def __init__(self, config: JobConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        try:
            self._run()
        except Exception as e:  # noqa: BLE001
            self.log.emit(f"Unexpected error: {e}")
            self.finished.emit(False, str(e))

    def _run(self) -> None:
        cfg = self.config

        self.log.emit("Loading IP list...")
        try:
            ips: List[str] = load_ips_from_file(cfg.file_path)
        except FileNotFoundError as e:
            self.log.emit(str(e))
            self.finished.emit(False, str(e))
            return
        except ValueError as e:
            self.log.emit(str(e))
            self.finished.emit(False, str(e))
            return

        if not ips:
            msg = "No IP addresses found in file."
            self.log.emit(msg)
            self.finished.emit(False, msg)
            return

        self.log.emit(f"{len(ips)} IP addresses loaded.\n")

        try:
            api = CloudflareAPI(
                api_token=cfg.api_token,
                zone_id=cfg.zone_id,
                logger=lambda m: self.log.emit(m),
            )
        except ValueError as e:
            self.log.emit(str(e))
            self.finished.emit(False, str(e))
            return

        # Verify token
        self.log.emit("Verifying API token...")
        try:
            api.verify_token()
        except CloudflareAuthError as e:
            self.log.emit(f"Invalid API token: {e}")
            self.finished.emit(False, "Invalid API token")
            return
        except CloudflareError as e:
            self.log.emit(f"Token verification failed: {e}")
            self.finished.emit(False, str(e))
            return
        self.log.emit("Token OK.\n")

        # Find existing records
        self.log.emit("Searching for existing records...")
        try:
            existing = api.list_a_records(cfg.record_name)
        except CloudflareNotFoundError as e:
            self.log.emit(f"Invalid Zone ID or zone not found: {e}")
            self.finished.emit(False, "Invalid Zone ID")
            return
        except CloudflareAuthError as e:
            self.log.emit(f"Invalid API token: {e}")
            self.finished.emit(False, "Invalid API token")
            return
        except CloudflareRateLimitError as e:
            self.log.emit(str(e))
            self.finished.emit(False, str(e))
            return
        except CloudflareError as e:
            self.log.emit(f"API error: {e}")
            self.finished.emit(False, str(e))
            return

        self.log.emit(f"Found {len(existing)} records.")

        total_steps = len(existing) + len(ips)
        step = 0
        self.progress.emit(step, max(total_steps, 1))

        if existing:
            self.log.emit("Deleting...")
            for rec in existing:
                try:
                    api.delete_record(rec.id)
                    self.log.emit(f"Record deleted. ({rec.content})")
                except CloudflareError as e:
                    self.log.emit(f"Failed to delete {rec.content}: {e}")
                step += 1
                self.progress.emit(step, max(total_steps, 1))
        self.log.emit("")

        errors = 0
        for ip in ips:
            self.log.emit("Creating:")
            self.log.emit(f"{cfg.record_name} -> {ip}")
            try:
                api.create_a_record(
                    name=cfg.record_name,
                    ip=ip,
                    proxied=False,
                    ttl=1,  # Auto
                )
                self.log.emit("Success\n")
            except CloudflareError as e:
                errors += 1
                self.log.emit(f"Failed: {e}\n")
            step += 1
            self.progress.emit(step, max(total_steps, 1))

        if errors:
            msg = f"Finished with {errors} error(s)."
            self.log.emit(msg)
            self.finished.emit(False, msg)
        else:
            self.log.emit("Finished successfully.")
            self.finished.emit(True, "Finished successfully.")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cloudflare DNS Manager")
        self.resize(760, 640)

        self.thread: QThread | None = None
        self.worker: Worker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        title = QLabel("Cloudflare DNS Manager")
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        form = QFormLayout()
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("Cloudflare API Token")

        self.zone_input = QLineEdit()
        self.zone_input.setPlaceholderText("Zone ID")

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. mci.gamespeednet.top")

        form.addRow("API Token:", self.token_input)
        form.addRow("Zone ID:", self.zone_input)
        form.addRow("DNS Record Name:", self.name_input)
        root.addLayout(form)

        file_row = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Select a .txt file with one IP per line")
        self.file_input.setReadOnly(True)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.pick_file)
        file_row.addWidget(self.file_input, 1)
        file_row.addWidget(browse)
        root.addLayout(file_row)

        actions = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_job)
        self.clear_btn = QPushButton("Clear Log")
        self.clear_btn.clicked.connect(lambda: self.log_view.clear())
        actions.addWidget(self.start_btn)
        actions.addWidget(self.clear_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Menlo, Consolas, monospace", 10))
        root.addWidget(self.log_view, 1)

        self.status = QLabel("Idle")
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight)
        root.addWidget(self.status)

    # -------------------------------------------------------- UI event handlers
    def pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select IP list", "", "Text files (*.txt);;All files (*)"
        )
        if path:
            self.file_input.setText(path)

    def append_log(self, text: str) -> None:
        self.log_view.append(text)
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def set_status(self, text: str, ok: bool | None = None) -> None:
        color = ""
        if ok is True:
            color = "color: #16a34a;"  # green
        elif ok is False:
            color = "color: #dc2626;"  # red
        else:
            color = "color: #6b7280;"  # gray
        self.status.setStyleSheet(f"font-weight: bold; {color}")
        self.status.setText(text)

    def start_job(self) -> None:
        token = self.token_input.text().strip()
        zone = self.zone_input.text().strip()
        name = self.name_input.text().strip()
        file_path = self.file_input.text().strip()

        if not token or not zone or not name or not file_path:
            QMessageBox.warning(
                self,
                "Missing fields",
                "Please fill in the API Token, Zone ID, DNS Record Name and select a TXT file.",
            )
            return

        cfg = JobConfig(
            api_token=token, zone_id=zone, record_name=name, file_path=file_path
        )

        self.start_btn.setEnabled(False)
        self.set_status("Running...", None)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

        self.thread = QThread()
        self.worker = Worker(cfg)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def _on_progress(self, current: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(current)

    def _on_finished(self, ok: bool, message: str) -> None:
        self.start_btn.setEnabled(True)
        self.set_status("Success" if ok else f"Error: {message}", ok)


def run() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
