"""
The Operate tab: everything the scorekeeper touches during a game.

Left: one card per field, grouped by the first word of its key (Away, Home,
Clock, ...), generated from Setup → Fields, so a new field is operable the
moment it exists. Right: the project's buttons (with their shortcuts) and a
live preview of any board.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QSizePolicy, QSplitter, QTabWidget, QVBoxLayout,
                             QWidget)

from ..core.fields import (ChoiceField, ClockField, CounterField, Field, ImageField, PenaltyField,
                           TextField, ToggleField)
from ..core.project import Button
from ..core.timefmt import format_ms
from . import theme
from .session import Session
from .widgets import (BoardView, FlowRow, Kbd, StateChip, button, caps, clear_layout, label, panel)


class Card(QWidget):
    """Base for a field card: a panel with a caption row."""

    def __init__(self, session: Session, f: Field, parent=None):
        super().__init__(parent)
        self.session, self.f = session, f
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.frame, self.body = panel(self, pad=12, spacing=8)
        outer.addWidget(self.frame)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.caption = caps(f.label)
        self.caption.setToolTip(f"Field key: {f.key}")
        head.addWidget(self.caption)
        head.addStretch(1)
        # LIVE (bound to a bot) and OVERRIDE states, as a colour and a word.
        self.flag = StateChip("", "muted")
        self.flag.hide()
        self.flag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.flag.mousePressEvent = lambda _ev: self._clear_override()
        head.addWidget(self.flag)
        self._flag_state = None
        self.head = head
        self.body.addLayout(head)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

    def act(self, **action) -> None:
        action.setdefault("field", self.f.key)
        self.session.act(action)

    def keys(self) -> set:
        return {self.f.key}

    def update_values(self, values) -> None:
        pass

    def update_meta(self, snap) -> None:
        f = self.f
        if f.override_on:
            state = ("OVERRIDE", "user", "Showing the override text. Click to turn the override off.")
        elif f.source and f.key in snap.live:
            state = ("LIVE", "hi", f"Following live data {f.source}. Buttons change the field's own value, "
                                   "which shows again if the bot stops sending it.")
        elif f.source:
            state = ("WAITING", "muted", f"Bound to live data {f.source}, which has not arrived. "
                                         "Showing the field's own value.")
        else:
            state = None
        if state == self._flag_state:
            return
        self._flag_state = state
        self.flag.setVisible(state is not None)
        if state:
            self.flag.set(state[0], state[1])
            self.flag.setToolTip(state[2])

    def _clear_override(self) -> None:
        if self.f.override_on:
            self.f.override_on = False
            self.session.fields_changed()


def _entry(placeholder: str, on_enter: Callable[[str], None], width: int = 0) -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setFont(theme.tfont("entry"))
    if width:
        e.setFixedWidth(width)

    def go():
        text = e.text().strip()
        if text:
            on_enter(text)
            e.clear()
    e.returnPressed.connect(go)
    e._go = go  # type: ignore[attr-defined]
    return e


class ClockCard(Card):
    def __init__(self, session, f: ClockField, parent=None):
        super().__init__(session, f, parent)
        self.chip = StateChip("STOPPED", "muted")
        self.head.addWidget(self.chip)
        self.value = QLabel("0:00")
        self.value.setFont(theme.tfont("count"))
        self.body.addWidget(self.value)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.go = button("Start", "accent", lambda: self.act(do="toggle"), big=True)
        self.go.setMinimumWidth(110)
        row.addWidget(self.go)
        row.addWidget(button("Reset", "", lambda: self.act(do="reset"), tip="Stop and restore the period length"))
        row.addStretch(1)
        self.body.addLayout(row)
        adj = QHBoxLayout()
        adj.setSpacing(4)
        steps = [("−1:00", -60_000), ("−0:01", -1000), ("+0:01", 1000), ("+1:00", 60_000)]
        if f.clock.tenths_under_ms:
            steps = steps[:2] + [("−0.1", -100), ("+0.1", 100)] + steps[2:]
        for text, ms in steps:
            b = button(text, "", lambda ms=ms: self.act(do="adjust", ms=ms), tip="Change the time without stopping")
            b.setProperty("seg", True)
            adj.addWidget(b)
        adj.addStretch(1)
        self.body.addLayout(adj)
        setrow = QHBoxLayout()
        self.entry = _entry(f.clock.fmt.replace("t", "0").replace("z", "0") if f.clock.fmt else "m:ss",
                            lambda t: self.act(do="set", value=t), 110)
        self.entry.setToolTip("Type a time and press Enter: 12:00, 45, 1:30.5")
        setrow.addWidget(self.entry)
        setrow.addWidget(button("Set", "", lambda: self.entry._go()))
        setrow.addStretch(1)
        mode = "Counts down" if f.clock.countdown else "Counts up"
        setrow.addWidget(label(f"{mode} · {format_ms(f.clock.initial_ms, f.clock.fmt)}", "small", muted=True))
        self.body.addLayout(setrow)

    def keys(self):
        return {self.f.key, self.f.key + ".running"}

    def update_values(self, values):
        c = self.f.clock
        self.value.setText(values.get(self.f.key, "") or format_ms(c.value(), c.fmt, c.countdown))
        running = c.running
        at_zero = c.countdown and c.value() <= 0
        if running:
            self.chip.set("RUNNING", "accent")
        elif at_zero:
            self.chip.set("ZERO", "alert")
        else:
            self.chip.set("STOPPED", "muted")
        want = ("Stop", "alert") if running else ("Start", "accent")
        if self.go.text() != want[0]:
            self.go.setText(want[0])
            self.go.setProperty("role", want[1])
            theme.repolish(self.go)
        self.go.setEnabled(running or not at_zero)


class CounterCard(Card):
    def __init__(self, session, f: CounterField, parent=None):
        super().__init__(session, f, parent)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.value = QLabel("0")
        self.value.setFont(theme.tfont("figure"))
        self.value.setMinimumWidth(70)
        row.addWidget(self.value)
        row.addStretch(1)
        minus = button("−1", "alert", lambda: self.act(do="add", amount=-1))
        minus.setProperty("seg", True)
        row.addWidget(minus)
        for s in f.steps:
            b = button(f"+{s}" if s > 0 else str(s), "", lambda s=s: self.act(do="add", amount=s))
            b.setProperty("seg", True)
            b.setMinimumWidth(48)
            row.addWidget(b)
        self.body.addLayout(row)
        setrow = QHBoxLayout()
        self.entry = _entry("Set to…", lambda t: self.act(do="set", value=t), 90)
        setrow.addWidget(self.entry)
        setrow.addWidget(button("Reset", "", lambda: self.act(do="reset"), tip=f"Back to {f.default}"))
        setrow.addStretch(1)
        self.body.addLayout(setrow)

    def update_values(self, values):
        self.value.setText(values.get(self.f.key, "") or ("0" if self.f.blank_zero else ""))


class TextCard(Card):
    def __init__(self, session, f: TextField, parent=None):
        super().__init__(session, f, parent)
        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setFont(theme.tfont("entry"))
        self.edit.returnPressed.connect(self._send)
        row.addWidget(self.edit, 1)
        row.addWidget(button("Set", "", self._send))
        row.addWidget(button("Clear", "", lambda: self.act(do="set", value="")))
        self.body.addLayout(row)
        self.state = label("", "small", muted=True)
        self.body.addWidget(self.state)

    def _send(self):
        self.act(do="set", value=self.edit.text())

    def update_values(self, values):
        v = self.f.value
        if not self.edit.hasFocus():
            self.edit.setText(v)
        pending = self.edit.hasFocus() and self.edit.text() != v
        self.state.setText("Press Enter to send" if pending else ("On air: “%s”" % values.get(self.f.key, "")
                                                                 if v else "Empty"))


class ToggleCard(Card):
    def __init__(self, session, f: ToggleField, parent=None):
        super().__init__(session, f, parent)
        self.chip = StateChip("OFF", "muted")
        self.head.addWidget(self.chip)
        row = QHBoxLayout()
        self.on = button("On", "", lambda: self.act(do="set", value=True), checkable=True)
        self.off = button("Off", "", lambda: self.act(do="set", value=False), checkable=True)
        for b in (self.on, self.off):
            b.setProperty("seg", True)
            b.setMinimumWidth(64)
            row.addWidget(b)
        row.addWidget(button("Flip", "", lambda: self.act(do="toggle")))
        row.addStretch(1)
        self.body.addLayout(row)

    def update_values(self, values):
        v = self.f.value
        self.on.setChecked(v)
        self.off.setChecked(not v)
        word = (self.f.on_text or "ON") if v else "OFF"
        self.chip.set(word.upper() if len(word) <= 12 else "ON", "accent" if v else "muted")


class ChoiceCard(Card):
    def __init__(self, session, f: ChoiceField, parent=None):
        super().__init__(session, f, parent)
        self.row = FlowRow()
        self.buttons: List[QPushButton] = []
        for i, opt in enumerate(f.options):
            b = button(opt or "(blank)", "", lambda i=i: self.act(do="set", value=i), checkable=True)
            b.setProperty("seg", True)
            b.setMinimumWidth(44)
            self.row.add(b)
            self.buttons.append(b)
        self.body.addWidget(self.row)
        nav = QHBoxLayout()
        nav.addWidget(button("Previous", "", lambda: self.act(do="prev")))
        nav.addWidget(button("Next", "", lambda: self.act(do="next")))
        nav.addStretch(1)
        self.body.addLayout(nav)

    def update_values(self, values):
        for i, b in enumerate(self.buttons):
            b.setChecked(i == self.f.index)


class PenaltyCard(Card):
    def __init__(self, session, f: PenaltyField, parent=None):
        super().__init__(session, f, parent)
        self.master = label("", "small", muted=True)
        self.head.addWidget(self.master)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)
        self.body.addLayout(self.rows)
        add = QHBoxLayout()
        self.player = QLineEdit()
        self.player.setPlaceholderText("Player, e.g. #12")
        self.time = QLineEdit("2:00")
        self.time.setFixedWidth(70)
        self.player.returnPressed.connect(self._add)
        self.time.returnPressed.connect(self._add)
        add.addWidget(self.player, 1)
        add.addWidget(self.time)
        for t in ("2:00", "5:00"):
            b = button(t, "", lambda t=t: self.time.setText(t))
            b.setProperty("seg", True)
            add.addWidget(b)
        add.addWidget(button("Add", "accent", self._add))
        self.body.addLayout(add)
        self._last = None

    def _add(self):
        self.act(do="penalty.add", player=self.player.text().strip(), time=self.time.text().strip() or "2:00")
        self.player.clear()

    def keys(self):
        return {self.f.key} | {f"{self.f.key}.{n}.time" for n in range(1, self.f.slots + 1)} | \
               {f"{self.f.key}.{n}.player" for n in range(1, self.f.slots + 1)}

    def update_values(self, values):
        entries = [(e["player"], e["ms"]) for e in self.f.entries]
        mf = self.session.engine.fields.get(self.f.master)
        self.master.setText(f"Runs with {mf.label}" if mf else "No master clock: set one in Data")
        if entries == self._last:
            return
        self._last = entries
        clear_layout(self.rows)
        if not entries:
            self.rows.addWidget(label("No penalties.", "small", muted=True))
        for i, (player, ms) in enumerate(entries):
            r = QHBoxLayout()
            on_board = i < self.f.slots
            num = label(str(i + 1), "cell", muted=not on_board)
            num.setFixedWidth(20)
            r.addWidget(num)
            r.addWidget(label(player or "—", "cell", muted=not on_board), 1)
            r.addWidget(label(format_ms(ms, self.f.fmt) + ("" if on_board else "  waiting"), "cell",
                              muted=not on_board))
            r.addWidget(button("Remove", "alert", lambda i=i: self.act(do="penalty.remove", index=i + 1)))
            self.rows.addLayout(r)


class ImageCard(Card):
    def __init__(self, session, f: ImageField, parent=None):
        super().__init__(session, f, parent)
        row = QHBoxLayout()
        self.path = label("", "small", muted=True)
        self.path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.addWidget(self.path, 1)
        row.addWidget(button("Choose…", "", self._choose))
        row.addWidget(button("Clear", "", lambda: self.act(do="set", value="")))
        self.body.addLayout(row)

    def _choose(self):
        start = os.path.dirname(self.f.value) if self.f.value else ""
        path, _ = QFileDialog.getOpenFileName(self, f"Choose a picture for {self.f.label}", start,
                                              "Pictures (*.png *.jpg *.jpeg *.gif *.webp *.svg *.bmp)")
        if path:
            self.act(do="set", value=path)

    def update_values(self, values):
        v = self.f.value
        self.path.setText(os.path.basename(v) if v else "No picture")
        self.path.setToolTip(v)


CARDS = {ClockField: ClockCard, CounterField: CounterCard, TextField: TextCard, ToggleField: ToggleCard,
         ChoiceField: ChoiceCard, PenaltyField: PenaltyCard, ImageField: ImageCard}


class PanelButton(QPushButton):
    """An operator button: its label and its shortcut, set as a key cap."""

    def __init__(self, b: Button, run: Callable[[], None], parent=None):
        super().__init__(parent)
        self.setProperty("role", b.role if b.role != "neutral" else "")
        self.setProperty("big", True)
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # The name gets the full width (two lines fit); the shortcut sits in the
        # bottom-right corner instead of squeezing the name into three lines.
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 5)
        lay.setSpacing(0)
        name = QLabel(b.label)
        name.setFont(theme.font(14.5, 800))
        name.setWordWrap(True)
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        c = theme.CURRENT
        ink = {"accent": c["accent-ink"]}.get(b.role, c["ink"])
        if b.role == "alert":
            ink = c["alert-text"]
        name.setStyleSheet(f"color:{ink}; background:transparent;")
        name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        name.setMinimumWidth(0)
        lay.addWidget(name, 1)
        if b.hotkey:
            k = Kbd(b.hotkey)
            k.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(k, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.setToolTip(f"{b.label}" + (f"  ·  shortcut {b.hotkey}" if b.hotkey else ""))
        self.clicked.connect(lambda _=False: run())
        self.setText("")

    HEIGHT = 66
    MIN_WIDTH = 112

    def sizeHint(self):
        return QSize(150, self.HEIGHT)

    def minimumSizeHint(self):
        return QSize(self.MIN_WIDTH, self.HEIGHT)


class ButtonGrid(QWidget):
    """A panel's buttons in its set number of columns, or fewer when the
    space is too narrow, so buttons never spill sideways or get cut off."""

    GAP = 8

    def __init__(self, buttons: List[QWidget], columns: int, parent=None):
        super().__init__(parent)
        self.buttons = buttons
        self.columns = max(1, columns)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 10, 0, 0)
        self.grid.setSpacing(self.GAP)
        self._cols = 0
        self._place(self.columns)

    def fit_columns(self, width: int) -> int:
        per = PanelButton.MIN_WIDTH + self.GAP
        return max(1, min(self.columns, (width + self.GAP) // per))

    def _place(self, cols: int) -> None:
        if cols == self._cols:
            return
        self._cols = cols
        for b in self.buttons:
            self.grid.removeWidget(b)
        for c in range(self.grid.columnCount()):
            self.grid.setColumnStretch(c, 0)
        for i, b in enumerate(self.buttons):
            r, c = divmod(i, cols)
            self.grid.addWidget(b, r, c)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        self.grid.setRowStretch(self.grid.rowCount(), 1)

    def minimumSizeHint(self):
        return QSize(PanelButton.MIN_WIDTH, super().minimumSizeHint().height())

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._place(self.fit_columns(ev.size().width()))


class OperateTab(QWidget):
    open_projector = pyqtSignal(str)          # board id
    copy_url = pyqtSignal(str)                # board id

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.cards: List[Card] = []
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split)

        # Left: field cards
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        self.cards_layout = QVBoxLayout(holder)
        self.cards_layout.setContentsMargins(0, 0, 10, 0)
        self.cards_layout.setSpacing(14)
        self.cards_scroll.setWidget(holder)
        split.addWidget(self.cards_scroll)

        # Right: buttons and preview
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 0, 0, 0)
        rl.setSpacing(14)
        self.panel_tabs = QTabWidget()
        self.panel_tabs.setDocumentMode(True)
        self.panel_tabs.tabBar().setDrawBase(False)
        rl.addWidget(self.panel_tabs, 3)
        pv, pvl = panel(pad=10, spacing=8)
        top = QHBoxLayout()
        top.addWidget(caps("Preview"))
        self.board_pick = QComboBox()
        self.board_pick.currentIndexChanged.connect(self._pick_board)
        top.addWidget(self.board_pick, 1)
        top.addWidget(button("Projector", "", lambda: self._emit_board(self.open_projector),
                             tip="Open this board full screen on a projector, TV or LED wall"))
        top.addWidget(button("Copy URL", "", lambda: self._emit_board(self.copy_url),
                             tip="Copy the browser-source address for OBS or vMix"))
        pvl.addLayout(top)
        self.preview = BoardView(checker=True)
        self.preview.setMinimumHeight(180)
        pvl.addWidget(self.preview, 1)
        rl.addWidget(pv, 2)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([700, 520])

        session.snapshot.connect(self._on_snapshot)
        session.structure.connect(self.rebuild_cards)
        session.panels.connect(self.rebuild_buttons)
        session.boards.connect(self.rebuild_boards)
        session.board_edited.connect(self._board_edited)
        session.animations.connect(self._anims_changed)
        self.rebuild_cards()
        self.rebuild_buttons()
        self.rebuild_boards()

    # ----- cards -----------------------------------------------------------
    def rebuild_cards(self) -> None:
        clear_layout(self.cards_layout)
        self.cards = []
        groups: Dict[str, List[Field]] = {}
        for f in self.session.engine.fields.values():
            g = f.key.split(".")[0] if "." in f.key else "game"
            groups.setdefault(g, []).append(f)
        if not groups:
            self.cards_layout.addWidget(label("This project has no fields yet. Add them in Setup → Fields, or start "
                                              "from a template with File → New.", "body", muted=True, wrap=True))
        for g, fields in groups.items():
            title = caps(g.replace("_", " "))
            title.setFont(theme.tfont("section"))
            title.setProperty("accenttext", True)
            title.setProperty("muted", False)
            self.cards_layout.addWidget(title)
            grid = QGridLayout()
            grid.setSpacing(10)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            r = c = 0
            for f in fields:
                cls = CARDS.get(type(f))
                if cls is None:
                    continue
                card = cls(self.session, f)
                self.cards.append(card)
                if isinstance(f, (ClockField, PenaltyField)):   # wide cards take a full row
                    if c:
                        r, c = r + 1, 0
                    grid.addWidget(card, r, 0, 1, 2)
                    r += 1
                else:
                    grid.addWidget(card, r, c)
                    r, c = (r, 1) if c == 0 else (r + 1, 0)
            self.cards_layout.addLayout(grid)
        self.cards_layout.addStretch(1)
        values = self.session.values()
        snap = self.session.engine.snapshot()
        for c in self.cards:
            c.update_values(values)
            c.update_meta(snap)

    def _on_snapshot(self, snap, changed) -> None:
        meta = "#live" in changed
        for c in self.cards:
            if c.keys() & changed:
                c.update_values(snap.values)
            if meta:
                c.update_meta(snap)
        self.preview.setValues(snap.values, changed, snap.fx)

    # ----- buttons ---------------------------------------------------------
    def rebuild_buttons(self) -> None:
        self.panel_tabs.clear()
        for p in self.session.project.panels:
            if p.buttons:
                page: QWidget = ButtonGrid([PanelButton(b, lambda b=b: self.session.act(b.action))
                                            for b in p.buttons], p.columns)
            else:
                page = QWidget()
                pl = QVBoxLayout(page)
                pl.setContentsMargins(0, 10, 0, 0)
                pl.addWidget(label("No buttons on this panel. Add them in Setup → Buttons.", "small", muted=True))
                pl.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(page)
            self.panel_tabs.addTab(scroll, p.name)

    # ----- preview ---------------------------------------------------------
    def rebuild_boards(self) -> None:
        current = self.board_pick.currentData()
        self.board_pick.blockSignals(True)
        self.board_pick.clear()
        for b in self.session.project.boards:
            self.board_pick.addItem(b.name, b.id)
        idx = max(0, self.board_pick.findData(current))
        self.board_pick.setCurrentIndex(idx)
        self.board_pick.blockSignals(False)
        self._pick_board()

    def _pick_board(self, *_):
        bid = self.board_pick.currentData()
        self.preview.setBoard(self.session.board(bid) if bid else None, self.session.project.animations)
        self.preview.setValues(self.session.values(), None, self.session.fx())

    def _anims_changed(self):
        self.preview.setAnimations(self.session.project.animations)

    def _board_edited(self, bid: str):
        if self.preview.board is not None and self.preview.board.id == bid:
            self.preview.refresh_keys()

    def _emit_board(self, signal) -> None:
        bid = self.board_pick.currentData()
        if bid:
            signal.emit(bid)
