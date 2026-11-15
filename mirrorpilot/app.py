"""Qt interface for read-only DNF5 mirror diagnostics."""
from __future__ import annotations

import sys
from dataclasses import replace
from PySide6.QtCore import QObject, QThread, Signal, Slot, QTimer, Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget, QAbstractItemView, QComboBox, QToolButton,
)
from mirrorpilot.check import check_baseurl
from mirrorpilot.repos import get_repositories, _version
from mirrorpilot.releases import available_targets
from mirrorpilot.audit import audit_referenced
from mirrorpilot.diagnostics import run_diagnostics, check_current_repository, fastest_verified, explain_source
from mirrorpilot.summary import summary_lines

class Worker(QObject):
    finished = Signal(object, object)
    progress = Signal(str, int, int, str)

    def __init__(self, action, args, report=False):
        super().__init__()
        self.action, self.args, self.report = action, args, report

    @Slot()
    def run(self):
        try:
            result = self.action(*self.args, progress=self.progress.emit) if self.report else self.action(*self.args)
            self.finished.emit(result, None)
        except Exception as exc:
            self.finished.emit(None, str(exc))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MirrorPilot — DNF5 diagnostics (read-only)")
        self.resize(1120, 680)
        self.repos = []
        self.results = []
        self.current_result = None
        self.current_result_key = None
        self.threads = []
        self.workers = []
        self.running = False
        self.spinner = 0
        self.progress_text = "Finding mirrors…"
        self.timer = QTimer(self)
        self.timer.setInterval(160)
        self.timer.timeout.connect(self.animate)

        main = QWidget()
        layout = QVBoxLayout(main)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel(f"Installed: Fedora {_version()} · Diagnose release:"))
        self.version = QComboBox()
        self.version.addItem(f"Fedora {_version()} — installed", _version())
        self.version.currentIndexChanged.connect(self.load_repos)
        toolbar.addWidget(self.version)
        toolbar.addWidget(QLabel("Repository:"))
        self.repo_choice = QComboBox()
        self.repo_choice.addItem("Fedora release (Everything)", "fedora")
        self.repo_choice.addItem("Fedora updates", "updates")
        toolbar.addWidget(self.repo_choice)
        toolbar.addStretch()
        self.refresh_button = QToolButton()
        self.refresh_button.setText("↻")
        self.refresh_button.setToolTip("Reload configured repositories from disk (read-only)")
        self.refresh_button.clicked.connect(self.load_repos)
        toolbar.addWidget(self.refresh_button)
        layout.addLayout(toolbar)

        actions = QHBoxLayout()
        self.current_label = "Check current"
        self.current_button = QPushButton(self.current_label)
        self.current_button.setToolTip("Check availability, Fedora reference index and metadata of the configured source. No speed benchmark; may download large metadata files.")
        self.current_button.clicked.connect(self.start_current_check)
        actions.addWidget(self.current_button)
        self.scan_label = "Find better mirrors"
        self.scan_button = QPushButton(self.scan_label)
        self.scan_button.setToolTip("Discover and benchmark up to 8 country-approved mirrors; check indexes and verify metadata on the fastest matching mirror. Read-only.")
        self.scan_button.clicked.connect(self.start_scan)
        actions.addWidget(self.scan_button)
        self.check_button = QPushButton("Check selected (advanced)")
        self.check_button.setToolTip("Check the HTTPS base URL of the selected row in Configured repositories. Requires a concrete URL.")
        self.check_button.setEnabled(False)
        self.check_button.clicked.connect(self.check_selected)
        actions.addWidget(self.check_button)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Configured repositories"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Repository", "Status", "Effective source", "Config file"])
        # Keep every column user-resizable. Stretch would lock Effective source
        # and could push Config file off-screen without a usable horizontal scroll.
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, self.table.fontMetrics().horizontalAdvance(" disabled ") + 20)
        self.table.setColumnWidth(2, 440)
        self.table.setColumnWidth(3, 240)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMaximumHeight(155)
        layout.addWidget(self.table)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.summary = QLabel("Not checked. Speed alone does not establish repository health.")
        layout.addWidget(self.summary)

        self.mirrors = QTableWidget(0, 6)
        self.mirrors.setHorizontalHeaderLabels(["Country", "Mirror", "Mbit/s", "Range", "Health", "Index / Metadata"])
        # Do not stretch the Mirror column: it prevents users from dragging
        # its right edge and can hide the Index / Metadata column.
        mirror_header = self.mirrors.horizontalHeader()
        mirror_header.setStretchLastSection(False)
        mirror_header.setSectionsMovable(True)
        for col in range(6):
            mirror_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate((105, 420, 85, 110, 125, 190)):
            self.mirrors.setColumnWidth(col, width)
        self.mirrors.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.mirrors.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.mirrors.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mirrors.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mirrors.itemSelectionChanged.connect(self.selected_mirror)
        layout.addWidget(self.mirrors, 1)

        self.verify_button = QPushButton("Verify selected mirror metadata (optional; up to 512 MiB/file)")
        self.verify_button.setEnabled(False)
        self.verify_button.clicked.connect(self.verify_selected)
        layout.addWidget(QLabel("Details (select a mirror to inspect errors and checks)"))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(105)
        layout.addWidget(self.details)
        self.verify_button.setText("Verify selected metadata")
        self.verify_button.setToolTip("Verify up to 3 referenced metadata files for the selected mirror (up to 512 MiB each). Read-only.")
        layout.addWidget(self.verify_button)
        layout.addWidget(QLabel("Read-only: no DNF settings, packages or caches are modified."))
        self.setCentralWidget(main)
        self.statusBar().showMessage("Ready")
        self.load_repos()
        self.run_job(available_targets, (), self.releases_loaded)

    def releases_loaded(self, targets, error):
        if error or not targets:
            return
        selected = self.version.currentData()
        self.version.blockSignals(True)
        self.version.clear()
        for value, label in targets:
            self.version.addItem(label, value)
        index = self.version.findData(selected)
        self.version.setCurrentIndex(max(index, 0))
        self.version.blockSignals(False)

    def run_job(self, action, args, callback, progress=None):
        thread = QThread(self)
        worker = Worker(action, args, report=progress is not None)
        self.workers.append(worker)
        self.threads.append(thread)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(callback)
        if progress is not None:
            worker.progress.connect(progress)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda w=worker: self.workers.remove(w) if w in self.workers else None)
        thread.finished.connect(lambda t=thread: self.threads.remove(t) if t in self.threads else None)
        thread.start()

    def load_repos(self):
        self.refresh_button.setEnabled(False)
        self.run_job(get_repositories, (self.version.currentData() or None,), self.loaded)

    def loaded(self, repos, error):
        self.refresh_button.setEnabled(True)
        if error:
            QMessageBox.warning(self, "Repository error", error)
            return
        self.repos = repos
        self.table.setRowCount(len(repos))
        for i, repo in enumerate(repos):
            for col, value in enumerate((repo.name, repo.status, repo.source, repo.filename)):
                self.table.setItem(i, col, QTableWidgetItem(value))
        self.statusBar().showMessage(f"Found {len(repos)} repositories")

    def selection_changed(self):
        row = self.table.currentRow()
        enabled = 0 <= row < len(self.repos) and not self.running
        if enabled:
            url = self.repos[row].baseurl.strip()
            enabled = url.startswith("https://") and "$" not in url and " " not in url
        self.check_button.setEnabled(enabled)

    def check_selected(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.repos):
            return
        self.check_button.setEnabled(False)
        self.run_job(check_baseurl, (self.repos[row].baseurl,), self.checked)

    def checked(self, result, error):
        self.selection_changed()
        self.details.setPlainText("Repository check failed: " + error if error else
                                  f"{result.status.upper()}: {result.message}\n{result.source}")

    def animate(self):
        self.spinner += 1
        active = self.current_button if getattr(self, "current_only", False) else self.scan_button
        active.setText(("◐", "◓", "◑", "◒")[self.spinner % 4] + " " + self.progress_text)

    def scan_progress(self, phase, done, total, detail):
        if phase == "benchmark":
            self.progress_text = f"Benchmarking mirror {min(done + 1, total)}/{total}…" if done < total else "Checking indexes…"
        elif phase == "current":
            self.progress_text = "Checking configured repository…"
        elif phase == "index":
            self.progress_text = f"Checking index {done}/{total}…"
        elif phase == "metadata":
            self.progress_text = f"Verifying metadata {done}/{total}…"
        elif phase == "bytes":
            self.progress_text = "Verifying " + detail
        self.animate()

    def start_current_check(self):
        self.start_scan(current_only=True)

    def start_scan(self, current_only=False):
        # Explicit opt-in: only one full metadata verification by default.
        # Eight full verifications could download up to 12 GiB.
        if self.running:
            return
        self.running = True
        self.scan_button.setEnabled(False)
        self.current_button.setEnabled(False)
        self.repo_choice.setEnabled(False)
        self.version.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.check_button.setEnabled(False)
        self.current_only = current_only
        self.progress_text = "Checking current repository…" if current_only else "Finding mirrors…"
        self.timer.start()
        self.animate()
        self.summary.setText("Running read-only diagnostics…")
        self.details.clear()
        self.results = []
        self.mirrors.setRowCount(0)
        self.scan_repo = self.repo_choice.currentData()
        self.scan_release = self.version.currentData() or _version()
        configured = next((r for r in self.repos
                           if r.repo_id == self.scan_repo and r.status == "enabled"), None)
        self.configured_url = configured.baseurl.strip() if configured and configured.baseurl.strip().startswith("https://") else None
        self.scan_key = (self.scan_release, self.scan_repo, self.configured_url)
        if current_only:
            self.run_job(check_current_repository,
                         (self.scan_release, self.scan_repo, self.configured_url),
                         self.scan_finished, self.scan_progress)
        else:
            self.run_job(run_diagnostics,
                         (self.scan_release, 1, self.scan_repo, self.configured_url),
                         self.scan_finished, self.scan_progress)

    def scan_finished(self, results, error):
        self.running = False
        self.timer.stop()
        self.scan_button.setText(self.scan_label)
        self.current_button.setText(self.current_label)
        self.current_button.setEnabled(True)
        self.scan_button.setEnabled(True)
        self.repo_choice.setEnabled(True)
        self.version.setEnabled(True)
        self.selection_changed()
        if error:
            self.summary.setText("Diagnostics failed")
            self.details.setPlainText(error)
            return
        self.results = results
        if self.current_only:
            self.current_result = results[0] if results else None
            self.current_result_key = self.scan_key
        self.render_results()

    def render_results(self):
        self.mirrors.setRowCount(len(self.results))
        winner = fastest_verified(self.results)
        failures = sum(r.health in ("problem", "error") for r in self.results)
        uncertain = sum(r.health == "uncertain" for r in self.results)
        verified = sum(r.health == "verified" for r in self.results)
        self.summary.setWordWrap(True)
        current = (self.current_result if self.current_result_key == self.scan_key else None)
        self.summary.setText("\n".join(summary_lines(
            self.results, self.scan_release, self.scan_repo, current=current)))
        for i, row in enumerate(self.results):
            speed = row.speed
            label = {"verified": "Verified", "problem": "Problem", "error": "Error",
                     "uncertain": "Inconclusive", "unchecked": "Not checked"}[row.health]
            if row is winner:
                label = "★ Recommended"
            if speed.country == "Configured":
                label = "Current · " + ("Unavailable" if speed.status == "error" and
                          ("404" in speed.detail or "Not Found" in speed.detail) else label)
            checks = f"{row.index.status if row.index else '—'} / {row.metadata.status if row.metadata else 'not checked'}"
            values = [speed.country, speed.url,
                      f"{speed.mbps:.2f}" if speed.mbps is not None else "—",
                      f"{speed.min_mbps:.1f}–{speed.max_mbps:.1f}" if speed.min_mbps is not None else "—",
                      label, checks]
            color = {"verified": "#d7f0dd", "problem": "#ffd9d9", "error": "#ffd9d9",
                     "uncertain": "#fff0c2", "unchecked": None}[row.health]
            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, i)
                if color:
                    item.setBackground(QBrush(QColor(color)))
                if row is winner:
                    item.setForeground(QBrush(QColor("#166534")))
                self.mirrors.setItem(i, j, item)
        self.statusBar().showMessage("Diagnostics complete")
        if self.current_only and len(self.results) == 1:
            # One current-source result is informational, not a comparison.
            # Keep the health background visible instead of Qt selection blue.
            self.mirrors.clearSelection()
            self.mirrors.setCurrentItem(None)
            self.verify_button.setEnabled(False)
            self.show_details(self.results[0])
        else:
            self.selected_mirror()

    def selected_mirror(self):
        row = self.mirrors.currentRow()
        valid = 0 <= row < len(self.results) and bool(self.mirrors.selectedItems())
        self.verify_button.setEnabled(valid and not self.running)
        if not valid:
            return
        self.show_details(self.results[row])

    def show_details(self, entry):
        lines = [entry.speed.url, f"Speed: {entry.speed.status} — {entry.speed.detail}",
                 f"Index: {entry.index.status}: {entry.index.message}" if entry.index else "Index: not checked",
                 f"Metadata: {entry.metadata.status}: {entry.metadata.message}" if entry.metadata else
                 "Metadata: not checked (speed is not proof of integrity)"]
        self.details.setPlainText("\n".join(lines))

    def verify_selected(self):
        row = self.mirrors.currentRow()
        if self.running or not 0 <= row < len(self.results):
            return
        self.running = True
        self.verify_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self.current_button.setEnabled(False)
        self.verify_button.setText("Verifying selected metadata…")
        entry = self.results[row]
        self.pending_row = row
        self.run_job(audit_referenced,
                     (entry.speed.url, entry.speed.country, self.scan_release),
                     self.verify_finished)

    def verify_finished(self, result, error):
        self.running = False
        self.scan_button.setEnabled(True)
        self.current_button.setEnabled(True)
        self.verify_button.setText("Verify selected metadata")
        if error:
            self.details.setPlainText("Verification failed: " + error)
        else:
            row = self.pending_row
            self.results[row] = replace(self.results[row], metadata=result)
            self.render_results()
        self.selected_mirror()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
