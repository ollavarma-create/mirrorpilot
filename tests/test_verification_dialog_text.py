"""DNF5 verification dialogs should show real line breaks, not literal escapes."""
from types import SimpleNamespace

from mirrorpilot.manual_edit import verify_effective_values


def test_verification_mismatch_message_has_real_newlines(monkeypatch):
    monkeypatch.setattr(
        "mirrorpilot.manual_edit.persistent_mirror_url",
        lambda repo_id, url, release: "https://example.org/updates/$releasever/$basearch/",
    )
    monkeypatch.setattr(
        "mirrorpilot.manual_edit._expand",
        lambda template, release: "https://example.org/updates/45/x86_64/",
    )
    plan = SimpleNamespace(
        repo_id="updates", proposed_url="https://example.org/updates/45/x86_64/",
        target_release="45",
    )
    ok, message = verify_effective_values(
        plan, {"baseurl": "https://other.example.org/", "metalink": "", "mirrorlist": ""},
        raw_baseurl="https://other.example.org/",
    )
    assert not ok
    assert "\\n" not in message
    assert "recommendation.\nCurrent mirror:" in message
    assert "\n\nNo changes have been made by MirrorPilot." in message
