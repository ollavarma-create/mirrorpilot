"""Startup preflight is independent of Qt and never modifies system state."""
import subprocess
from mirrorpilot import environment as env


FEDORA = 'ID=fedora\nPRETTY_NAME="Fedora Linux 45"\n'
UBUNTU = 'ID=ubuntu\nPRETTY_NAME="Ubuntu Linux"\n'


def test_non_fedora_rejected_without_invoking_dnf(monkeypatch):
    monkeypatch.setattr(env.shutil, "which", lambda name: (_ for _ in ()).throw(AssertionError("dnf called")))
    result = env.check_environment(UBUNTU)
    assert not result.supported
    assert "Ubuntu" in result.message


def test_missing_dnf5(monkeypatch):
    monkeypatch.setattr(env.shutil, "which", lambda name: None)
    result = env.check_environment(FEDORA)
    assert not result.supported
    assert "DNF5 was not found" in result.message


def test_working_dnf5(monkeypatch):
    monkeypatch.setattr(env.shutil, "which", lambda name: "/usr/bin/dnf5")
    seen = []
    def run(argv, **kwargs):
        seen.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="dnf5 version 5.4.0", stderr="")
    monkeypatch.setattr(env.subprocess, "run", run)
    assert env.check_environment(FEDORA).supported
    assert seen[0][0] == ["/usr/bin/dnf5", "--version"]
    assert seen[0][1]["timeout"] == 5


def test_dnf5_nonzero_exit(monkeypatch):
    monkeypatch.setattr(env.shutil, "which", lambda name: "/usr/bin/dnf5")
    monkeypatch.setattr(env.subprocess, "run", lambda argv, **kwargs:
                        subprocess.CompletedProcess(argv, 2, stdout="", stderr="error"))
    assert not env.check_environment(FEDORA).supported


def test_dnf5_timeout(monkeypatch):
    monkeypatch.setattr(env.shutil, "which", lambda name: "/usr/bin/dnf5")
    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
    monkeypatch.setattr(env.subprocess, "run", timeout)
    assert "timed out" in env.check_environment(FEDORA).message


def test_dnf5_unexpected_response(monkeypatch):
    monkeypatch.setattr(env.shutil, "which", lambda name: "/usr/bin/dnf5")
    monkeypatch.setattr(env.subprocess, "run", lambda argv, **kwargs:
                        subprocess.CompletedProcess(argv, 0, stdout="other command", stderr=""))
    assert not env.check_environment(FEDORA).supported


def test_dnf5_os_error(monkeypatch):
    monkeypatch.setattr(env.shutil, "which", lambda name: "/usr/bin/dnf5")
    def fail(argv, **kwargs):
        raise OSError("execution denied")
    monkeypatch.setattr(env.subprocess, "run", fail)
    assert "execution denied" in env.check_environment(FEDORA).message
