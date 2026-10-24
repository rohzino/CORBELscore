"""
The open project and the signals every tab listens to.

Tabs never call each other. They change the project through the session and
react to its signals, so the Operate panel, the builder, the projector and
the outputs stay in step.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..core.board import Board
from ..core.refactor import field_references, rename_field_everywhere
from ..core.engine import ActionError, Snapshot
from ..core.project import Project


class Session(QObject):
    snapshot = pyqtSignal(object, object)     # Snapshot, set of changed keys
    structure = pyqtSignal()                  # fields added, removed, renamed, reconfigured
    boards = pyqtSignal()                     # a board added, removed, renamed or reordered
    board_edited = pyqtSignal(str)            # board id whose content changed
    panels = pyqtSignal()
    outputs = pyqtSignal()
    dirty_changed = pyqtSignal(bool)
    message = pyqtSignal(str, bool)           # text, is_alert
    expired = pyqtSignal(str)                 # clock key that hit zero
    logic = pyqtSignal()                      # conditions changed
    animations = pyqtSignal()                 # the project's animation recipes changed
    source = pyqtSignal()                     # live-data settings changed

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self._dirty = False
        self._suspend = 0
        project.engine.on_change(self._on_change)
        project.engine.on_expired(self._on_expired)
        self.timer = QTimer(self)
        self.timer.setInterval(33)            # ~30 refreshes a second; time itself is exact
        try:
            from PyQt6.QtCore import Qt
            self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        except Exception:
            pass
        self.timer.timeout.connect(self._tick)

    # ----- engine ----------------------------------------------------------
    @property
    def engine(self):
        return self.project.engine

    def start(self) -> None:
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def _tick(self) -> None:
        for action, err in self.engine.tick():
            if err:
                self.message.emit(f"Remote action failed: {err}", True)

    def _on_change(self, snap: Snapshot, changed: set) -> None:
        self.snapshot.emit(snap, changed)

    def _on_expired(self, key: str) -> None:
        self.expired.emit(key)

    def values(self):
        snap = self.engine.snapshot()
        return snap.values if snap else {}

    def fx(self):
        snap = self.engine.snapshot()
        return snap.fx if snap else {}

    def conditions_changed(self) -> None:
        self.engine.set_conditions(self.engine.logic.conditions)
        self.logic.emit()
        self.set_dirty()

    def animations_changed(self) -> None:
        self.animations.emit()
        self.set_dirty()

    def source_changed(self) -> None:
        self.source.emit()
        self.set_dirty()

    def act(self, action: dict) -> bool:
        """Run an operator action. Errors become a notice, never a crash."""
        try:
            self.engine.perform(action)
            return True
        except ActionError as e:
            self.message.emit(str(e), True)
        except Exception as e:  # defensive: an action must never take the app down
            self.message.emit(f"That did not work: {e}", True)
        return False

    # ----- editing ---------------------------------------------------------
    @property
    def dirty(self) -> bool:
        return self._dirty

    def set_dirty(self, dirty: bool = True) -> None:
        if dirty != self._dirty:
            self._dirty = dirty
            self.dirty_changed.emit(dirty)

    def fields_changed(self) -> None:
        self.engine.publish(force=True)
        self.structure.emit()
        self.set_dirty()

    def board_changed(self, board: Board) -> None:
        self.board_edited.emit(board.id)
        self.set_dirty()

    def boards_changed(self) -> None:
        self.boards.emit()
        self.set_dirty()

    def panels_changed(self) -> None:
        self.panels.emit()
        self.set_dirty()

    def outputs_changed(self) -> None:
        self.outputs.emit()
        self.set_dirty()

    def board(self, bid: str) -> Optional[Board]:
        return self.project.board(bid)

    # ----- refactoring -----------------------------------------------------
    def rename_key_everywhere(self, old: str, new: str) -> int:
        """Rename a field and every reference to it. Returns how many moved."""
        n = rename_field_everywhere(self.project, old, new)
        self.fields_changed()
        self.boards.emit()
        for b in self.project.boards:
            self.board_edited.emit(b.id)
        self.panels.emit()
        return n

    def references(self, key: str):
        return field_references(self.project, key)
