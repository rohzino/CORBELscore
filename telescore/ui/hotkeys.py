"""
Keyboard shortcuts for operator buttons.

In-app shortcuts work on every platform (1.x hotkeys were Windows-only and
started one global keyboard hook per button). Rules:
  * a held key fires once (auto-repeat is ignored), so holding Space cannot
    start and stop the clock ten times;
  * while you type in a text box, plain keys type; only shortcuts with Ctrl,
    Alt or a function key still fire;
  * shortcuts are live on the Operate tab and in projector windows.

Background shortcuts (when TeleScore is not the active window) are optional
and use one pynput listener. They are limited to combinations with Ctrl or
Alt and to function keys, because a plain letter would fire while you type in
any other program.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6.QtCore import QEvent, QKeyCombination, QObject, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QKeySequenceEdit, QLineEdit,
                             QPlainTextEdit, QTextEdit)

MODIFIER_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr,
                 Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock}
TEXT_INPUTS = (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox, QKeySequenceEdit)


def normalise(seq: str) -> str:
    """'ctrl+space' -> 'Ctrl+Space' (Qt portable text); '' if invalid."""
    if not seq:
        return ""
    ks = QKeySequence.fromString(seq, QKeySequence.SequenceFormat.PortableText)
    if ks.isEmpty():
        return ""
    return QKeySequence(ks[0]).toString(QKeySequence.SequenceFormat.PortableText)


def is_global_safe(seq: str) -> bool:
    s = normalise(seq)
    if not s:
        return False
    parts = s.split("+")
    key = parts[-1]
    mods = set(parts[:-1])
    return bool(mods & {"Ctrl", "Alt", "Meta"}) or (key.startswith("F") and key[1:].isdigit())


class HotkeyRouter(QObject):
    """An application-wide key filter that runs bound callbacks."""

    def __init__(self, is_active: Callable[[], bool], parent=None):
        super().__init__(parent)
        self._bindings: Dict[str, Callable[[], None]] = {}
        self._is_active = is_active
        self.skip: set = set()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def set_bindings(self, bindings: Dict[str, Callable[[], None]]) -> None:
        self._bindings = {normalise(k): fn for k, fn in bindings.items() if normalise(k)}

    def bindings(self) -> Dict[str, Callable[[], None]]:
        return dict(self._bindings)

    def eventFilter(self, obj, ev) -> bool:
        if ev.type() != QEvent.Type.KeyPress or not self._bindings:
            return False
        if ev.isAutoRepeat() or ev.key() in MODIFIER_KEYS:
            return False
        if not self._is_active():
            return False
        mods = ev.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        combo = QKeySequence(QKeyCombination(mods, ev.keyCombination().key())).toString(
            QKeySequence.SequenceFormat.PortableText)
        fn = self._bindings.get(combo)
        if fn is None or combo in self.skip:
            return False
        focus = QApplication.focusWidget()
        typing = isinstance(focus, TEXT_INPUTS) or (isinstance(focus, QComboBox) and focus.isEditable())
        is_fkey = Qt.Key.Key_F1.value <= ev.key() <= Qt.Key.Key_F35.value
        has_cmd = bool(mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier |
                               Qt.KeyboardModifier.MetaModifier))
        if typing and not (has_cmd or is_fkey):
            return False
        fn()
        return True


class GlobalHotkeys:
    """Background shortcuts through pynput (optional dependency)."""

    def __init__(self):
        self._listener = None
        self.error = ""

    @staticmethod
    def available() -> bool:
        try:
            import pynput  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def to_pynput(seq: str) -> Optional[str]:
        s = normalise(seq)
        if not s or not is_global_safe(s):
            return None
        out = []
        names = {"Ctrl": "<ctrl>", "Alt": "<alt>", "Shift": "<shift>", "Meta": "<cmd>", "Space": "<space>",
                 "Left": "<left>", "Right": "<right>", "Up": "<up>", "Down": "<down>", "Return": "<enter>",
                 "Enter": "<enter>", "Tab": "<tab>", "Esc": "<esc>", "Home": "<home>", "End": "<end>",
                 "PgUp": "<page_up>", "PgDown": "<page_down>", "Ins": "<insert>", "Del": "<delete>",
                 "Backspace": "<backspace>"}
        for part in s.split("+"):
            if part in names:
                out.append(names[part])
            elif part.startswith("F") and part[1:].isdigit():
                out.append(f"<{part.lower()}>")
            elif len(part) == 1:
                out.append(part.lower())
            else:
                return None
        return "+".join(out)

    def start(self, bindings: Dict[str, Callable[[], None]]) -> set:
        """Start listening. Returns the Qt key strings now handled globally."""
        self.stop()
        mapping, handled = {}, set()
        for qt_key, fn in bindings.items():
            pk = self.to_pynput(qt_key)
            if pk:
                mapping[pk] = fn
                handled.add(normalise(qt_key))
        if not mapping:
            return set()
        try:
            from pynput import keyboard
            self._listener = keyboard.GlobalHotKeys(mapping)
            self._listener.daemon = True
            self._listener.start()
            self.error = ""
            return handled
        except Exception as e:  # missing permissions (macOS), no X server, ...
            self._listener = None
            self.error = f"Background shortcuts are unavailable here: {e}"
            return set()

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
