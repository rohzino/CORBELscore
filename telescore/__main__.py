"""python -m telescore"""
import sys


def run() -> int:
    try:
        import PyQt6  # noqa: F401
    except ImportError:
        sys.stderr.write("TeleScore needs PyQt6. Install it with:\n    python -m pip install -r requirements.txt\n")
        return 1
    from telescore.ui.app import main
    return main()


if __name__ == "__main__":
    sys.exit(run())
