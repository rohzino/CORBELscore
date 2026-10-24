"""The main window: start page, the five tabs, menus, files, recovery."""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Dict, List, Optional

from PyQt6.QtCore import QSettings, QStandardPaths, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon, QKeySequence
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                             QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..core.fields import ClockField
from ..core.presets import make_project
from ..core.project import Project, ProjectError
from . import theme
from .builder import BuildTab
from .buttons_tab import ButtonsTab
from .data_tab import DataTab
from .hotkeys import GlobalHotkeys, HotkeyRouter
from .live_ctl import LiveController
from .live_tab import LiveTab
from .logic_tab import LogicTab
from .operate import OperateTab
from .outputs_ctl import OutputController
from .outputs_tab import OutputsTab
from .projector import ProjectorWindow
from .session import Session
from .startpage import StartPage
from .widgets import Notice, StatusDot, label

FILTER = "TeleScore projects (*.tsproj);;TeleScore 1.x projects (*.json);;All files (*)"


def app_data_dir() -> str:
    d = os.environ.get("TELESCORE_DATA_DIR") or \
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not d:
        d = os.path.join(os.path.expanduser("~"), ".telescore")
    os.makedirs(d, exist_ok=True)
    return d


class Buzzer:
    """Plays a clock's buzzer file when it reaches zero."""

    def __init__(self):
        self._players: Dict[str, object] = {}

    def play(self, path: str) -> Optional[str]:
        if not path:
            return None
        if not os.path.isfile(path):
            return f"The buzzer file is missing: {path}"
        try:
            from PyQt6.QtCore import QUrl as _Url
            if path.lower().endswith(".wav"):
                from PyQt6.QtMultimedia import QSoundEffect
                fx = self._players.get(path)
                if fx is None:
                    fx = QSoundEffect()
                    fx.setSource(_Url.fromLocalFile(path))
                    fx.setVolume(1.0)
                    self._players[path] = fx
                fx.play()
            else:
                from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
                pair = self._players.get(path)
                if pair is None:
                    player, out = QMediaPlayer(), QAudioOutput()
                    out.setVolume(1.0)
                    player.setAudioOutput(out)
                    player.setSource(_Url.fromLocalFile(path))
                    pair = (player, out)
                    self._players[path] = pair
                pair[0].setPosition(0)
                pair[0].play()
        except Exception as e:  # no audio device, missing multimedia plugin
            return f"Could not play the buzzer: {e}"
        return None


class HeaderBar(QFrame):
    """The flat head-colour band: brand, project, save state, output lights."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("headbar", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(14)
        brand = QLabel("TeleScore")
        brand.setFont(theme.tfont("brand"))
        lay.addWidget(brand)
        self.project = QLabel("")
        self.project.setFont(theme.tfont("title"))
        lay.addWidget(self.project)
        self.saved = label("", "small")
        lay.addWidget(self.saved)
        lay.addStretch(1)
        self.lights: Dict[str, StatusDot] = {}
        for key, text in (("live", "Live"), ("files", "Files"), ("web", "Web")):
            d = StatusDot()
            t = label(text, "label")
            lay.addWidget(d)
            lay.addWidget(t)
            self.lights[key] = d
        ver = label(f"v{__version__}", "small")
        ver.setProperty("muted", True)
        lay.addWidget(ver)


class MainWindow(QMainWindow):
    def __init__(self, settings: Optional[QSettings] = None):
        super().__init__()
        self.settings = settings or QSettings("TeleScore", "TeleScore")
        self.session: Optional[Session] = None
        self.ctl: Optional[OutputController] = None
        self.live: Optional[LiveController] = None
        self.projectors: List[ProjectorWindow] = []
        self.buzzer = Buzzer()
        self.global_keys = GlobalHotkeys()
        self.setWindowIcon(QIcon(os.path.join(theme.ASSETS, "icon.ico")))
        self.resize(1360, 860)
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.header = HeaderBar()
        cl.addWidget(self.header)
        self.notice = Notice()
        nl = QHBoxLayout()
        nl.setContentsMargins(16, 8, 16, 0)
        nl.addWidget(self.notice)
        cl.addLayout(nl)
        self.stack = QStackedWidget()
        cl.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.tabs: Optional[QTabWidget] = None
        self.router = HotkeyRouter(self._hotkeys_active, self)

        self.recovery_path = os.path.join(app_data_dir(), "recovery.tsproj")
        self._recovery_timer = QTimer(self)
        self._recovery_timer.setSingleShot(True)
        self._recovery_timer.setInterval(3000)
        self._recovery_timer.timeout.connect(self._write_recovery)

        self._build_menus()
        self._set_on_top(self.settings.value("on_top", False, type=bool), save=False)
        self.show_start()
        QTimer.singleShot(200, self._offer_recovery)

    # ----- menus -----------------------------------------------------------------
    @staticmethod
    def _act(menu, text, slot, shortcut=None) -> QAction:
        a = menu.addAction(text)
        a.triggered.connect(lambda _=False: slot())
        if shortcut is not None:
            a.setShortcut(QKeySequence(shortcut))
        return a

    def _build_menus(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        self._act(f, "New…", self.show_start, QKeySequence.StandardKey.New)
        self._act(f, "Open…", lambda: self.open_project(""), QKeySequence.StandardKey.Open)
        self.recent_menu = f.addMenu("Open recent")
        f.addSeparator()
        self.a_save = self._act(f, "Save", self.save, QKeySequence.StandardKey.Save)
        self.a_save_as = self._act(f, "Save as…", self.save_as, "Ctrl+Shift+S")
        f.addSeparator()
        self._act(f, "Quit", self.close, QKeySequence.StandardKey.Quit)

        v = mb.addMenu("&View")
        self.proj_menu = v.addMenu("Projector window")
        self.proj_menu.aboutToShow.connect(self._fill_projector_menu)
        self.a_top = QAction("Keep this window on top", self)
        self.a_top.setCheckable(True)
        self.a_top.toggled.connect(self._set_on_top)
        v.addAction(self.a_top)
        colours = v.addMenu("Colours")
        group = QActionGroup(self)
        current = self.settings.value("scheme", theme.DEFAULT_SCHEME)
        for name in theme.SCHEMES:
            a = QAction(name, self)
            a.setCheckable(True)
            a.setChecked(name == current)
            a.triggered.connect(lambda _=False, n=name: self.set_scheme(n))
            group.addAction(a)
            colours.addAction(a)

        s = mb.addMenu("&Settings")
        self.a_global = QAction("Shortcuts work while TeleScore is in the background", self)
        self.a_global.setCheckable(True)
        self.a_global.setChecked(self.settings.value("global_keys", False, type=bool))
        self.a_global.setEnabled(GlobalHotkeys.available())
        if not GlobalHotkeys.available():
            self.a_global.setText(self.a_global.text() + " (install pynput)")
        self.a_global.toggled.connect(self._set_global)
        s.addAction(self.a_global)

        h = mb.addMenu("&Help")
        self._act(h, "Browser sources and feeds", lambda: self.ctl and QDesktopServices.openUrl(QUrl(self.ctl.url("/"))))
        self._act(h, "Project page", lambda: QDesktopServices.openUrl(QUrl("https://github.com/JumpShot-Interactive/TeleScore")))
        h.addSeparator()
        self._act(h, "About TeleScore", self.about)
        self._fill_recent()
        self._update_actions()

    def _update_actions(self):
        has = self.session is not None
        self.a_save.setEnabled(has)
        self.a_save_as.setEnabled(has)
        self.proj_menu.setEnabled(has)

    def _fill_recent(self):
        self.recent_menu.clear()
        for path in self.recent():
            self._act(self.recent_menu, path, lambda p=path: self.open_project(p))
        self.recent_menu.setEnabled(bool(self.recent()))

    def _fill_projector_menu(self):
        self.proj_menu.clear()
        if self.session:
            for b in self.session.project.boards:
                self._act(self.proj_menu, b.name, lambda bid=b.id: self.open_projector(bid))

    # ----- recent ---------------------------------------------------------------
    def recent(self) -> List[str]:
        val = self.settings.value("recent", [])
        if isinstance(val, str):
            val = [val]
        return [p for p in (val or []) if isinstance(p, str)]

    def add_recent(self, path: str):
        path = os.path.abspath(path)
        lst = [p for p in self.recent() if os.path.normcase(p) != os.path.normcase(path)]
        lst.insert(0, path)                       # newest first; the oldest falls off
        self.settings.setValue("recent", lst[:12])
        self._fill_recent()

    # ----- project lifecycle ------------------------------------------------------
    def show_start(self):
        if not self._confirm_discard():
            return
        self._close_project()
        page = StartPage(self.recent())
        page.new_project.connect(self.new_project)
        page.open_file.connect(self.open_project)
        self._swap(page)
        self._update_title()

    def _swap(self, w: QWidget):
        old = self.stack.currentWidget()
        self.stack.addWidget(w)
        self.stack.setCurrentWidget(w)
        if old is not None:
            self.stack.removeWidget(old)
            old.deleteLater()

    def new_project(self, preset: str):
        self.load_project(make_project(preset))

    def open_project(self, path: str = ""):
        if not path:
            start = os.path.dirname(self.recent()[0]) if self.recent() else ""
            path, _ = QFileDialog.getOpenFileName(self, "Open project", start, FILTER)
            if not path:
                return
        if not self._confirm_discard():
            return
        try:
            p = Project.load(path)
        except (ProjectError, OSError, ValueError, KeyError, TypeError) as e:
            QMessageBox.warning(self, "Cannot open project",
                                f"{os.path.basename(path)} could not be opened.\n\n{e}")
            return
        self.load_project(p)
        if p.imported_from:
            notes = "\n• ".join(p.import_notes)
            self.notice.show_message(f"Converted from TeleScore 1.x. Save it as a new .tsproj file; the original "
                                     f"is untouched. {len(p.import_notes)} note(s): " +
                                     (p.import_notes[0] if p.import_notes else ""), alert=False)
            if notes:
                QMessageBox.information(self, "Imported from TeleScore 1.x", "• " + notes)
        else:
            self.add_recent(path)

    def load_project(self, project: Project):
        self._close_project()
        self.session = Session(project, self)
        s = self.session
        s.message.connect(lambda t, a: self.notice.show_message(t, a, 0 if a else 5000))
        s.dirty_changed.connect(lambda _d: (self._update_title(), self._schedule_recovery()))
        s.expired.connect(self._expired)
        s.panels.connect(self._bind_hotkeys)
        self.ctl = OutputController(s, self)
        self.ctl.status.connect(self._lights)
        self.live = LiveController(s, self.settings, self)
        self.live.status.connect(self._lights)
        self._build_workspace()
        self.ctl.start()
        self.live.start()
        s.start()
        self._bind_hotkeys()
        self._update_title()
        self._update_actions()

    def _build_workspace(self, keep_tab: int = 0):
        s = self.session
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        self.operate = OperateTab(s)
        self.operate.open_projector.connect(self.open_projector)
        self.operate.copy_url.connect(self._copy_board_url)
        tabs.addTab(self.operate, "Operate")
        tabs.addTab(BuildTab(s), "Build")
        tabs.addTab(DataTab(s), "Data")
        tabs.addTab(LogicTab(s), "Logic")
        tabs.addTab(LiveTab(s, self.live), "Live data")
        tabs.addTab(ButtonsTab(s), "Buttons")
        tabs.addTab(OutputsTab(s, self.ctl), "Outputs")
        tabs.setCurrentIndex(keep_tab)
        self.tabs = tabs
        self._swap(tabs)

    def _close_project(self):
        for w in list(self.projectors):
            w.close()
        self.projectors = []
        if self.session is not None:
            self.session.stop()
        if self.ctl is not None:
            self.ctl.stop()
            self.ctl.deleteLater()
        if self.live is not None:
            self.live.stop()
            self.live.deleteLater()
            self.live = None
        self.global_keys.stop()
        self.router.set_bindings({})
        self.session, self.ctl, self.tabs = None, None, None
        self.notice.hide()
        self._update_actions()

    def _confirm_discard(self) -> bool:
        if self.session is None or not self.session.dirty:
            return True
        r = QMessageBox.question(self, "Save changes?",
                                 f"Save the changes to {self.session.project.name}?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                 QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def save(self) -> bool:
        if self.session is None:
            return False
        p = self.session.project
        if not p.path:
            return self.save_as()
        try:
            p.save()
        except (OSError, ProjectError) as e:
            QMessageBox.warning(self, "Not saved", f"The project could not be saved.\n\n{e}")
            return False
        self.session.set_dirty(False)
        self.add_recent(p.path)
        self._clear_recovery()
        self.notice.show_message(f"Saved {os.path.basename(p.path)}.", False, 2500)
        return True

    def save_as(self) -> bool:
        if self.session is None:
            return False
        p = self.session.project
        start = p.path or os.path.join(os.path.dirname(self.recent()[0]) if self.recent() else
                                       os.path.expanduser("~"), f"{p.name}.tsproj")
        if p.imported_from and not p.path:
            start = os.path.splitext(p.imported_from)[0] + ".tsproj"
        path, _ = QFileDialog.getSaveFileName(self, "Save project", start, "TeleScore projects (*.tsproj)")
        if not path:
            return False
        if not path.lower().endswith(".tsproj"):
            path += ".tsproj"
        if p.imported_from and os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(p.imported_from)):
            QMessageBox.warning(self, "Choose another name", "That is the TeleScore 1.x file. Save under a new name.")
            return False
        p.path = path
        if p.name in ("Untitled",):
            p.name = os.path.splitext(os.path.basename(path))[0]
        return self.save()

    # ----- recovery ------------------------------------------------------------------
    def _schedule_recovery(self):
        if self.session is not None and self.session.dirty:
            self._recovery_timer.start()

    def _write_recovery(self):
        if self.session is None or not self.session.dirty:
            return
        try:
            d = self.session.project.to_dict()
            d["_recovery"] = {"path": self.session.project.path, "at": _dt.datetime.now().isoformat(timespec="seconds")}
            from ..core.project import atomic_write_text
            atomic_write_text(self.recovery_path, json.dumps(d))
        except OSError:
            pass

    def _clear_recovery(self):
        try:
            os.remove(self.recovery_path)
        except OSError:
            pass

    def _offer_recovery(self):
        if not os.path.isfile(self.recovery_path):
            return
        try:
            with open(self.recovery_path, encoding="utf-8") as fh:
                d = json.load(fh)
            meta = d.pop("_recovery", {})
        except (OSError, ValueError):
            self._clear_recovery()
            return
        r = QMessageBox.question(self, "Restore unsaved work?",
                                 f"TeleScore closed without saving “{d.get('name', 'a project')}” "
                                 f"({meta.get('at', 'recently')}). Restore it?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            try:
                p = Project.from_dict(d)
                p.path = meta.get("path", "")
                self.load_project(p)
                self.session.set_dirty(True)
            except (ProjectError, ValueError, TypeError) as e:
                QMessageBox.warning(self, "Cannot restore", str(e))
        self._clear_recovery()

    # ----- tabs, hotkeys, projectors ----------------------------------------------
    def _hotkeys_active(self) -> bool:
        if self.session is None or self.tabs is None:
            return False
        w = QApplication.activeWindow()
        if isinstance(w, ProjectorWindow):
            return True
        return w is self and self.stack.currentWidget() is self.tabs and self.tabs.currentIndex() == 0

    def _bind_hotkeys(self):
        if self.session is None:
            return
        bindings = {}
        for p in self.session.project.panels:
            for b in p.buttons:
                if b.hotkey and b.hotkey not in bindings:
                    bindings[b.hotkey] = (lambda a=b.action: self.session and self.session.act(a))
        self.router.set_bindings(bindings)
        self.router.skip = set()
        if self.a_global.isChecked():
            submit = {k: (lambda a=b.action: self.session and self.session.engine.submit(a))
                      for p in self.session.project.panels for b in p.buttons if b.hotkey
                      for k in [b.hotkey]}
            self.router.skip = self.global_keys.start(submit)
            if self.global_keys.error:
                self.notice.show_message(self.global_keys.error, True)
        else:
            self.global_keys.stop()

    def _set_global(self, on: bool):
        self.settings.setValue("global_keys", on)
        self._bind_hotkeys()

    def open_projector(self, bid: str):
        if self.session is None:
            return
        w = ProjectorWindow(self.session, bid)
        w.destroyed.connect(lambda _=None, w=w: self.projectors.remove(w) if w in self.projectors else None)
        self.projectors.append(w)
        w.show()

    def _copy_board_url(self, bid: str):
        if self.ctl is not None:
            url = self.ctl.url(f"/board/{bid}")
            QApplication.clipboard().setText(url)
            self.notice.show_message(f"Copied {url}. In OBS add a Browser source with this address.", False, 5000)

    def _expired(self, key: str):
        f = self.session.engine.fields.get(key) if self.session else None
        if isinstance(f, ClockField) and f.buzzer:
            err = self.buzzer.play(f.buzzer)
            if err:
                self.notice.show_message(err, True)

    def _lights(self):
        if self.ctl is None:
            return
        st = self.ctl.file_status()
        states = [s.state for s in st.values() if s.state != "off"]
        files = "error" if "error" in states else ("live" if states else "off")
        self.header.lights["files"].setState(files)
        o = self.session.project.outputs
        web = "live" if self.ctl.server.running else ("error" if o.http_enabled else "off")
        self.header.lights["web"].setState(web)
        if self.live is not None:
            st = self.live.source.status.state
            self.header.lights["live"].setState({"live": "live", "connecting": "busy", "stale": "busy",
                                                 "error": "error"}.get(st, "off"))

    # ----- window ------------------------------------------------------------------
    def _update_title(self):
        if self.session is None:
            self.setWindowTitle("TeleScore")
            self.header.project.setText("")
            self.header.saved.setText("")
            return
        p = self.session.project
        name = p.name + ("" if p.path else " (not saved yet)")
        self.setWindowTitle(f"{'• ' if self.session.dirty else ''}{p.name} · TeleScore")
        self.header.project.setText(name)
        self.header.saved.setText("Unsaved changes" if self.session.dirty else "Saved")

    def _set_on_top(self, on: bool, save: bool = True):
        if save:
            self.settings.setValue("on_top", on)
        self.a_top.blockSignals(True)
        self.a_top.setChecked(on)
        self.a_top.blockSignals(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        self.show()

    def set_scheme(self, name: str):
        self.settings.setValue("scheme", name)
        theme.apply(QApplication.instance(), name)
        # Widgets with computed colours are rebuilt so every part follows the scheme.
        old_header = self.header
        self.header = HeaderBar()
        self.centralWidget().layout().replaceWidget(old_header, self.header)
        old_header.deleteLater()
        if self.session is not None:
            self._build_workspace(self.tabs.currentIndex() if self.tabs else 0)
            self._update_title()
            self._lights()
        else:
            self.show_start()

    def about(self):
        QMessageBox.about(self, "About TeleScore",
                          f"<b>TeleScore {__version__}</b><br>Open-source scoreboard and live scoring for "
                          "streams and broadcast.<br><br>Community continuation of TeleScore by the JumpShot "
                          "team (riscyseven, TheLittleDoctor, Fisk31, controldelta, SPCcleveland9035, Glenn)."
                          "<br><br>Licensed under the GNU Affero General Public License v3. Archivo font "
                          "© The Archivo Project Authors, SIL Open Font License 1.1.")

    def closeEvent(self, ev):
        if not self._confirm_discard():
            ev.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self._close_project()
        self._clear_recovery()
        ev.accept()
