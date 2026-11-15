"""Qt interface for read-only DNF5 mirror diagnostics."""
from __future__ import annotations

import sys
from dataclasses import replace
from PySide6.QtCore import QObject, QThread, Signal, Slot, QTimer, Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget, QAbstractItemView, QComboBox,
)
from mirrorpilot.check import check_baseurl
from mirrorpilot.repos import get_repositories, _version
from mirrorpilot.releases import available_targets
from mirrorpilot.audit import audit_referenced
from mirrorpilot.diagnostics import run_diagnostics, fastest_verified, explain_source

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
        self.refresh_button = QPushButton("Load repositories")
        self.refresh_button.clicked.connect(self.load_repos)
        toolbar.addWidget(self.refresh_button)
        layout.addLayout(toolbar)

        repo_options = QHBoxLayout()
        repo_options.addWidget(QLabel("Repository to diagnose:"))
        self.repo_choice = QComboBox()
        self.repo_choice.addItem("Fedora release (Everything)", "fedora")
        self.repo_choice.addItem("Fedora updates", "updates")
        repo_options.addWidget(self.repo_choice)
        repo_options.addStretch()
        layout.addLayout(repo_options)
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
        self.check_button = QPushButton("Check selected repository URL (advanced)")
        self.check_button.setEnabled(False)
        self.check_button.clicked.connect(self.check_selected)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        layout.addWidget(self.check_button)

        self.scan_label = "Run diagnostics (up to 8 mirrors; metadata on fastest matching mirror)"
        self.scan_button = QPushButton(self.scan_label)
        self.scan_button.clicked.connect(self.start_scan)
        layout.addWidget(self.scan_button)
        self.summary = QLabel("Not checked. Speed alone does not establish repository health.")
        layout.addWidget(self.summary)

        self.mirrors = QTableWidget(0, 6)
        self.mirrors.setHorizontalHeaderLabels(["Country", "Mirror", "Mbit/s", "Range", "Health", "Index / Metadata"])
        self.mirrors.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.mirrors.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.mirrors.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mirrors.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mirrors.itemSelectionChanged.connect(self.selected_mirror)
        layout.addWidget(self.mirrors, 1)

        self.verify_button = QPushButton("Verify selected mirror metadata (optional; up to 512 MiB/file)")
        self.verify_button.setEnabled(False)
        self.verify_button.clicked.connect(self.verify_selected)
        layout.addWidget(self.verify_button)
        layout.addWidget(QLabel("Details (select a mirror to inspect errors and checks)"))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(105)
        layout.addWidget(self.details)
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
        self.scan_button.setText(("◐", "◓", "◑", "◒")[self.spinner % 4] + " " + self.progress_text)

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

    def start_scan(self):
        # Explicit opt-in: only one full metadata verification by default.
        # Eight full verifications could download up to 12 GiB.
        if self.running:
            return
        self.running = True
        self.scan_button.setEnabled(False)
        self.repo_choice.setEnabled(False)
        self.version.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.check_button.setEnabled(False)
        self.progress_text = "Finding mirrors…"
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
        self.run_job(run_diagnostics, (self.scan_release, 1, self.scan_repo, self.configured_url),
                     self.scan_finished, self.scan_progress)

    def scan_finished(self, results, error):
        self.running = False
        self.timer.stop()
        self.scan_button.setText(self.scan_label)
        self.scan_button.setEnabled(True)
        self.repo_choice.setEnabled(True)
        self.version.setEnabled(True)
        self.selection_changed()
        if error:
            self.summary.setText("Diagnostics failed")
            self.details.setPlainText(error)
            return
        self.results = results
        self.render_results()

    def render_results(self):
        self.mirrors.setRowCount(len(self.results))
        winner = fastest_verified(self.results)
        failures = sum(r.health in ("problem", "error") for r in self.results)
        uncertain = sum(r.health == "uncertain" for r in self.results)
        verified = sum(r.health == "verified" for r in self.results)
        self.summary.setText(
            f"Fedora {self.scan_release} {self.scan_repo} · {len(self.results)} sources · {verified} verified · {failures} problems · "
            f"{uncertain} inconclusive · {len(self.results)-verified-failures-uncertain} not fully checked"
            + (f" · Recommended: {winner.speed.country} {winner.speed.mbps:.1f} Mbit/s" if winner else
               " · No verified recommendation yet")
        )
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
        current = next((r for r in self.results if r.speed.country == "Configured"), None)
        self.summary.setWordWrap(True)
        self.summary.setText(explain_source(current) + "  " + self.summary.text())
        self.statusBar().showMessage("Diagnostics complete")
        if current is not None and current.health in ("problem", "error", "uncertain"):
            self.mirrors.selectRow(self.results.index(current))
        else:
            self.selected_mirror()

    def selected_mirror(self):
        row = self.mirrors.currentRow()
        valid = 0 <= row < len(self.results)
        self.verify_button.setEnabled(valid and not self.running)
        if not valid:
            return
        entry = self.results[row]
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
        self.verify_button.setText("Verifying selected metadata…")
        entry = self.results[row]
        self.pending_row = row
        self.run_job(audit_referenced,
                     (entry.speed.url, entry.speed.country, self.scan_release),
                     self.verify_finished)

    def verify_finished(self, result, error):
        self.running = False
        self.scan_button.setEnabled(True)
        self.verify_button.setText("Verify selected mirror metadata (optional; up to 512 MiB/file)")
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
