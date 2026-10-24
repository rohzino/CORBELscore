"""Start the desktop application."""

from __future__ import annotations

import datetime as _dt
import os
import sys
import traceback


def _crash_log_dir() -> str:
    from PyQt6.QtCore import QStandardPaths
    d = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation) or \
        os.path.join(os.path.expanduser("~"), ".telescore")
    os.makedirs(d, exist_ok=True)
    return d


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication, QMessageBox

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName("TeleScore")
    app.setOrganizationName("TeleScore")
    app.setApplicationDisplayName("TeleScore")

    from . import theme
    from .mainwindow import MainWindow
    from PyQt6.QtCore import QSettings

    theme.FAMILY = theme.load_fonts()
    theme.apply(app, QSettings("TeleScore", "TeleScore").value("scheme", theme.DEFAULT_SCHEME))

    def excepthook(etype, value, tb):
        # Log it, tell the operator, and keep running: a scoreboard must not
        # vanish in the middle of a game (1.x showed a dialog and then quit).
        text = "".join(traceback.format_exception(etype, value, tb))
        path = os.path.join(_crash_log_dir(), "errors.log")
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"\n--- {_dt.datetime.now().isoformat(timespec='seconds')}\n{text}")
        except OSError:
            path = "(could not write the log)"
        sys.__stderr__ and sys.__stderr__.write(text)
        try:
            QMessageBox.warning(None, "Something went wrong",
                                f"{etype.__name__}: {value}\n\nTeleScore is still running and the clocks keep "
                                f"time. Details were saved to:\n{path}")
        except Exception:
            pass

    sys.excepthook = excepthook
    win = MainWindow()
    win.show()
    for a in argv[1:]:
        if os.path.isfile(a):
            win.open_project(a)
            break
    return app.exec()
