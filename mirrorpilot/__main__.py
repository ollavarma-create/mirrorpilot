"""Standalone entry point for the bundled GUI application."""
import sys


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--diagnose-tls":
        from mirrorpilot.tls_diagnostics import main as diagnose_tls
        return diagnose_tls()
    if len(sys.argv) > 1 and sys.argv[1] == "--diagnose-tls":
        print("Usage: mirrorpilot --diagnose-tls", file=sys.stderr)
        return 2
    from mirrorpilot.app import main as gui_main
    gui_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
