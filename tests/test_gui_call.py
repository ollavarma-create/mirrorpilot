"""Guard the actual GUI call shape without importing Qt."""
import ast
from pathlib import Path

from mirrorpilot.diagnostics import run_diagnostics
import inspect


def test_gui_diagnostics_call_matches_signature():
    source = Path(__file__).resolve().parents[1] / "mirrorpilot" / "app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run_job"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "run_diagnostics"
    ]
    assert len(calls) == 1
    args_tuple = calls[0].args[1]
    assert isinstance(args_tuple, ast.Tuple)
    signature = inspect.signature(run_diagnostics)
    # Worker supplies progress by keyword, not as part of positional args.
    positional = [object()] * len(args_tuple.elts)
    signature.bind(*positional, progress=lambda *args: None)


def test_about_dialog_contains_project_identity_and_license():
    source = (Path(__file__).resolve().parents[1] / "mirrorpilot" / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "show_about"]
    assert len(methods) == 1
    assert "GPL-3.0-only" in source
    assert "https://github.com/ollavarma-create/mirrorpilot" in source
    assert "not affiliated with the Fedora Project" in source
    assert "AI-assisted" in source
