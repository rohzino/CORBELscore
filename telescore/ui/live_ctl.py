"""Runs the project's live-data source (Sportzcast) and reports its health."""

from __future__ import annotations

from typing import Dict

from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal

from ..core.sportzcast import SourceStatus, SportzcastSource
from .session import Session

TOKEN_KEY = "sportzcast/token"


class LiveController(QObject):
    status = pyqtSignal()                 # state, detail, packets, keys changed
    _from_thread = pyqtSignal()

    def __init__(self, session: Session, settings: QSettings, parent=None):
        super().__init__(parent)
        self.session = session
        self.settings = settings
        self.source: SportzcastSource = SportzcastSource(session.project.source, self.token(),
                                                         session.engine.feed, self._on_status)
        self._from_thread.connect(self.status.emit)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)
        session.source.connect(self.restart)

    # The token is a secret: it lives in this computer's settings, never in the project file.
    def token(self) -> str:
        return str(self.settings.value(TOKEN_KEY, "") or "")

    def set_token(self, token: str) -> None:
        self.settings.setValue(TOKEN_KEY, token)

    def _on_status(self, st: SourceStatus) -> None:
        self._from_thread.emit()

    def _poll(self):
        self.source.check_stale()
        self.status.emit()

    def start(self) -> None:
        self.restart()
        self._timer.start()

    def restart(self) -> None:
        self.source.stop()
        self.source = SportzcastSource(self.session.project.source, self.token(), self.session.engine.feed,
                                       self._on_status)
        if not self.session.project.source.kind:
            self.session.engine.clear_sources()
            self.session.engine.publish()
        self.source.start()
        self.status.emit()

    def stop(self) -> None:
        self._timer.stop()
        self.source.stop()

    def keys(self) -> Dict[str, str]:
        return self.source.snapshot_keys()
