"""Qt 6 GUI for read-only DNF5 diagnostics."""
from __future__ import annotations

import sys
from PySide6.QtCore import QObject, QThread, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)
from mirrorpilot.check import check_baseurl
from mirrorpilot.repos import get_repositories, _version
from mirrorpilot.speed import benchmark


class Worker(QObject):
    finished = Signal(object, object)
    progress = Signal(int, int)

    def __init__(self, action, *args):
        super().__init__()
        self.action, self.args = action, args

    @Slot()
    def run(self):
        try:
            result = self.action(*self.args, progress=self.progress.emit) if self.action is benchmark else self.action(*self.args)
            self.finished.emit(result, None)
        except Exception as error:
            self.finished.emit(None, str(error))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MirrorPilot — DNF5 diagnostics (read-only)")
        self.resize(1000, 600)
        self.repos = []
        self.threads = []
        self.workers = []  # Retain Python references until background work finishes.
        self.benchmark_label = 'Benchmark approved mirrors (up to 8; read-only)'
        self.spinner_frames = ('◐', '◓', '◑', '◒')
        self.spinner_step = 0
        self.benchmark_progress = 'Finding mirrors…'
        self.benchmark_timer = QTimer(self)
        self.benchmark_timer.setInterval(140)
        self.benchmark_timer.timeout.connect(self.animate_benchmark)

        main = QWidget()
        layout = QVBoxLayout(main)
        layout.addWidget(QLabel("DNF5 software repositories — read-only preview"))
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Release version:"))
        self.version = QLineEdit()
        self.version.setPlaceholderText("Current release or e.g. 45")
        toolbar.addWidget(self.version)
        self.refresh_button = QPushButton("Load repositories")
        self.refresh_button.clicked.connect(self.load_repos)
        toolbar.addWidget(self.refresh_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Repository", "Status", "Effective source", "Config file"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        layout.addWidget(self.table)

        self.check_button = QPushButton("Check selected HTTPS base URL")
        self.check_button.setEnabled(False)
        self.check_button.clicked.connect(self.check_selected)
        layout.addWidget(self.check_button)
        self.speed_button = QPushButton(self.benchmark_label)
        self.speed_button.clicked.connect(self.test_speeds)
        layout.addWidget(self.speed_button)
        self.speed_table = QTableWidget(0, 6)
        self.speed_table.setHorizontalHeaderLabels(['Country', 'Mirror URL', 'Median Mbit/s', 'Range Mbit/s', 'Median TTFB ms', 'Status'])
        self.speed_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.speed_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.speed_table.setMinimumHeight(150)
        layout.addWidget(self.speed_table)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(125)
        layout.addWidget(self.details)
        layout.addWidget(QLabel("No repositories, installed packages or DNF settings are changed."))
        self.setCentralWidget(main)
        self.statusBar().showMessage("Ready")
        self.load_repos()

    def run_job(self, action, args, callback, progress_callback=None):
        thread = QThread(self)
        worker = Worker(action, *args)
        self.workers.append(worker)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(callback)
        if progress_callback is not None:
            worker.progress.connect(progress_callback)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda w=worker: self.workers.remove(w) if w in self.workers else None)
        self.threads.append(thread)
        thread.finished.connect(lambda: self.threads.remove(thread) if thread in self.threads else None)
        thread.start()

    def load_repos(self):
        self.refresh_button.setEnabled(False)
        self.check_button.setEnabled(False)
        self.statusBar().showMessage("Reading effective DNF5 configuration...")
        self.run_job(get_repositories, (self.version.text().strip() or None,), self.loaded)

    def loaded(self, repos, error):
        self.refresh_button.setEnabled(True)
        if error:
            self.statusBar().showMessage("Unable to read DNF5 repositories")
            QMessageBox.warning(self, "DNF5 error", error)
            return
        self.repos = repos
        self.table.setRowCount(len(repos))
        for i, repo in enumerate(repos):
            for col, value in enumerate((repo.name, repo.status, repo.source, repo.filename)):
                self.table.setItem(i, col, QTableWidgetItem(value))
        self.statusBar().showMessage(f"Found {len(repos)} repositories")

    def selection_changed(self):
        index = self.table.currentRow()
        if not 0 <= index < len(self.repos):
            self.check_button.setEnabled(False)
            return
        repo = self.repos[index]
        self.details.setPlainText(
            f"ID: {repo.repo_id}\nBase URL: {repo.baseurl}\n"
            f"Metalink: {repo.metalink}\nMirrorlist: {repo.mirrorlist}"
        )
        url = repo.baseurl.strip()
        self.check_button.setEnabled(
            url.startswith("https://") and "$" not in url and " " not in url
        )

    def check_selected(self):
        index = self.table.currentRow()
        if not 0 <= index < len(self.repos):
            return
        self.check_button.setEnabled(False)
        self.statusBar().showMessage("Testing repository metadata...")
        self.run_job(check_baseurl, (self.repos[index].baseurl,), self.checked)

    def animate_benchmark(self):
        frame = self.spinner_frames[self.spinner_step % len(self.spinner_frames)]
        self.spinner_step += 1
        self.speed_button.setText(f'{frame} {self.benchmark_progress}')

    def benchmark_progress_changed(self, done, total):
        self.benchmark_progress = f'Testing mirror {done + 1}/{total}…' if done < total else f'Finishing {total}/{total}…'
        if total == 0:
            self.benchmark_progress = 'No eligible mirrors found…'
        self.animate_benchmark()

    def test_speeds(self):
        self.speed_button.setEnabled(False)
        self.benchmark_progress = 'Finding mirrors…'
        self.animate_benchmark()
        self.benchmark_timer.start()
        self.statusBar().showMessage('Mirror benchmark running...')
        self.run_job(benchmark, (self.version.text().strip() or _version(),),
                     self.speeds_finished, self.benchmark_progress_changed)

    def speeds_finished(self, results, error):
        self.benchmark_timer.stop()
        self.speed_button.setText(self.benchmark_label)
        self.speed_button.setEnabled(True)
        if error:
            self.details.setPlainText('Mirror speed test failed: ' + error)
            self.statusBar().showMessage('Speed test failed')
            return
        if not results:
            self.details.setPlainText('No approved mirror hosts found. No speed-test connections made.')
            return
        self.speed_table.setRowCount(len(results))
        for i, result in enumerate(results):
            values = (result.country, result.url, str(result.mbps) if result.mbps is not None else '-',
                      '{}–{}'.format(result.min_mbps, result.max_mbps) if result.min_mbps is not None else '-',
                      str(result.ttfb_ms) if result.ttfb_ms is not None else '-', result.status)
            for col, value in enumerate(values):
                self.speed_table.setItem(i, col, QTableWidgetItem(value))
        self.details.setPlainText('Three bounded samples per mirror; median shown. Country is MirrorManager registration, not verified location. Integrity/freshness not checked.')
        self.statusBar().showMessage('Tested {} mirrors (indicative speeds)'.format(len(results)))
    def checked(self, diagnostic, error):
        self.selection_changed()
        if error:
            self.details.setPlainText("Diagnostic failed: " + error)
            self.statusBar().showMessage("Diagnostic failed")
        else:
            self.details.setPlainText(
                f"{diagnostic.status.upper()}: {diagnostic.message}\n{diagnostic.source}"
            )
            self.statusBar().showMessage(f"Diagnostic status: {diagnostic.status}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
