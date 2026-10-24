"""
Drive the real PyQt6 application without a screen.

Runs every tab of every template, presses Operate buttons, edits a board in
the builder, adds a field and a button, saves and reopens, checks the files
and the web server, and saves a screenshot of every tab. Skipped when PyQt6 is
not installed. Screenshots go to $TELESCORE_SHOTS (default: a temp folder,
printed at the end).

    python -m unittest tests.test_ui_smoke -v
"""

import json
import os
import socket
import sys
import tempfile
import time
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QSettings, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QPushButton
except ImportError:  # pragma: no cover
    QApplication = None

SHOTS = os.environ.get("TELESCORE_SHOTS") or os.path.join(tempfile.gettempdir(), "telescore-shots")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@unittest.skipIf(QApplication is None, "PyQt6 is not installed")
class UISmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="telescore-ui-")
        os.environ["TELESCORE_DATA_DIR"] = os.path.join(cls.tmp, "data")
        cls.app = QApplication.instance() or QApplication([])
        from telescore.ui import theme
        theme.FAMILY = theme.load_fonts()
        theme.apply(cls.app, theme.DEFAULT_SCHEME)
        os.makedirs(SHOTS, exist_ok=True)

    def wait(self, ms=50):
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.005)

    def make_window(self):
        from telescore.ui.mainwindow import MainWindow
        settings = QSettings(os.path.join(self.tmp, f"settings-{time.time_ns()}.ini"), QSettings.Format.IniFormat)
        win = MainWindow(settings)
        win.resize(1440, 900)
        win.show()
        self.wait(50)
        self.addCleanup(self._close, win)
        return win

    def _close(self, win):
        if win.session is not None:
            win.session.set_dirty(False)
        win.close()
        self.wait(20)

    def shot(self, widget, name):
        path = os.path.join(SHOTS, name.replace(" ", "_") + ".png")
        widget.grab().save(path)
        return path

    def load(self, win, preset, port=None):
        from telescore.core.presets import make_project
        p = make_project(preset)
        p.outputs.folder = os.path.join(self.tmp, "out-" + preset.replace(" ", "_"))
        p.outputs.http_port = port or free_port()
        win.load_project(p)
        self.wait(150)
        return p

    # ---------------------------------------------------------------------------
    def test_start_page_and_schemes(self):
        win = self.make_window()
        self.shot(win, "00 start page")
        for name in ("Keystone Light", "Rally", "Keystone Dark"):
            win.set_scheme(name)
            self.wait(30)
            self.shot(win, f"00 start page {name}")

    def test_every_template_every_tab(self):
        from telescore.core.presets import PRESETS
        win = self.make_window()
        for preset in PRESETS:
            with self.subTest(preset=preset):
                self.load(win, preset)
                self.assertIsNotNone(win.tabs)
                for i in range(win.tabs.count()):
                    win.tabs.setCurrentIndex(i)
                    self.wait(40)
                    if preset in ("Basketball", "Hockey", "Blank project"):
                        self.shot(win, f"{preset} {i} {win.tabs.tabText(i)}")
                win.session.set_dirty(False)

    def test_operate_buttons_and_clock(self):
        win = self.make_window()
        p = self.load(win, "Basketball")
        win.tabs.setCurrentIndex(0)
        self.wait(50)
        op = win.operate
        from telescore.ui.operate import ClockCard, CounterCard
        clock_card = next(c for c in op.cards if isinstance(c, ClockCard) and c.f.key == "clock.game")
        QTest.mouseClick(clock_card.go, Qt.MouseButton.LeftButton)
        self.wait(1300)
        self.assertTrue(p.engine.field("clock.game").clock.running)
        self.assertEqual(clock_card.go.text(), "Stop")
        self.assertEqual(clock_card.chip.text(), "RUNNING")
        self.assertNotEqual(clock_card.value.text(), "10:00")
        QTest.mouseClick(clock_card.go, Qt.MouseButton.LeftButton)
        self.wait(50)
        self.assertFalse(p.engine.field("clock.game").clock.running)
        score = next(c for c in op.cards if isinstance(c, CounterCard) and c.f.key == "home.score")
        plus3 = next(b for b in score.findChildren(QPushButton) if b.text() == "+3")
        QTest.mouseClick(plus3, Qt.MouseButton.LeftButton)
        self.wait(50)
        self.assertEqual(score.value.text(), "3")
        # typed set
        QTest.keyClicks(clock_card.entry, "4:00")
        QTest.keyClick(clock_card.entry, Qt.Key.Key_Return)
        self.wait(50)
        self.assertEqual(p.engine.snapshot().values["clock.game"], "4:00")
        # a bad time is a notice, not a crash
        QTest.keyClicks(clock_card.entry, "soon")
        QTest.keyClick(clock_card.entry, Qt.Key.Key_Return)
        self.wait(50)
        self.assertTrue(win.notice.isVisible())
        self.assertIn("not a time", win.notice.text.text())
        self.shot(win, "operate after actions")

    def test_hotkeys(self):
        win = self.make_window()
        p = self.load(win, "Basketball")
        win.tabs.setCurrentIndex(0)
        win.activateWindow()
        self.wait(100)
        if QApplication.activeWindow() is not win:
            self.skipTest("This platform does not activate windows offscreen")
        target = win.operate
        target.setFocus()
        ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, " ")
        QApplication.sendEvent(target, ev)
        self.wait(50)
        self.assertTrue(p.engine.field("clock.game").clock.running)
        rep = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, " ", True)
        QApplication.sendEvent(target, rep)                    # auto-repeat must not toggle
        self.wait(30)
        self.assertTrue(p.engine.field("clock.game").clock.running)
        # typing in a text box: plain keys type, they do not score
        from telescore.ui.operate import TextCard
        tc = next(c for c in win.operate.cards if isinstance(c, TextCard))
        tc.edit.setFocus()
        before = p.engine.snapshot().values["home.score"]
        QTest.keyClicks(tc.edit, "OP")
        self.wait(30)
        self.assertEqual(p.engine.snapshot().values["home.score"], before)

    def test_builder_edit_undo_redo(self):
        win = self.make_window()
        self.load(win, "General scoreboard")
        win.tabs.setCurrentIndex(1)
        self.wait(100)
        bt = win.tabs.widget(1)
        board = bt.board
        n = len(board.elements)
        bt.add_element("text")
        self.assertEqual(len(board.elements), n + 1)
        new = board.elements[-1]
        self.assertEqual(bt.canvas.selected_ids(), [new.id])
        # drag it 100 px right with snapping on
        x0 = new.x
        bt.canvas.begin_move(QPointF(new.x + 5, new.y + 5))
        bt.canvas.drag_to(QPointF(new.x + 105, new.y + 5), Qt.KeyboardModifier.NoModifier)
        bt.canvas.end_move()
        self.wait(30)
        self.assertAlmostEqual(new.x, round((x0 + 100) / 10) * 10, delta=10)
        # inspector edit
        bt.inspector.t_text.setText("{home.score}")
        bt.inspector.t_text.editingFinished.emit()
        self.assertEqual(new.text, "{home.score}")
        bt.nudge(1, 0)
        moved = new.x
        bt.undo()
        self.wait(20)
        el = board.element(new.id)
        self.assertEqual(el.x, moved - 1)
        bt.redo()
        self.assertEqual(board.element(new.id).x, moved)
        # field drop
        bt.add_field_text("away.score", QPointF(300, 300))
        self.assertEqual(board.elements[-1].text, "{away.score}")
        # align + distribute + reorder do not crash and change the model
        ids = [e.id for e in board.elements[-3:]]
        bt.canvas.select_ids(ids)
        bt.arrange(lambda b, i: b.align(i, "top"))
        self.assertEqual(len({board.element(i).y for i in ids}), 1)
        bt.reorder("back")
        self.assertEqual(board.elements[0].id, ids[0])
        bt.duplicate()
        bt.copy()
        bt.paste()
        bt.delete_selected()
        bt.canvas.fit()
        self.wait(50)
        self.shot(win, "builder after edits")
        self.assertTrue(win.session.dirty)

    def test_data_and_buttons_tabs(self):
        win = self.make_window()
        p = self.load(win, "Hockey")
        e = p.engine
        from telescore.core.fields import CounterField
        e.add_field(CounterField("home.hits", "Home hits"))
        win.session.fields_changed()
        self.wait(50)
        from telescore.ui.operate import CounterCard
        self.assertTrue(any(isinstance(c, CounterCard) and c.f.key == "home.hits" for c in win.operate.cards))
        win.tabs.setCurrentIndex(2)
        self.wait(50)
        n = win.session.rename_key_everywhere("home.penalties", "home.pen")
        self.assertGreater(n, 0)
        self.wait(50)
        win.tabs.setCurrentIndex(5)
        self.wait(50)
        bt = win.tabs.widget(5)
        self.assertEqual(win.tabs.tabText(5), "Buttons")
        bt.add_button()
        self.wait(30)
        self.assertEqual(p.panels[0].buttons[-1].label, "New button")
        bt.add_step()
        self.assertEqual(p.panels[0].buttons[-1].action["do"], "batch")
        bt.try_it()
        self.shot(win, "buttons tab")

    def test_save_reopen_outputs_and_server(self):
        win = self.make_window()
        port = free_port()
        p = self.load(win, "Hockey", port)
        p.engine.perform({"do": "add", "field": "home.score", "amount": 2})
        self.wait(300)
        folder = p.outputs.folder
        with open(os.path.join(folder, "text", "home.score.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "2")
        self.assertTrue(os.path.isfile(os.path.join(folder, "vmix.xml")))
        # web server answers, and remote actions run on the GUI thread
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/action?do=add&field=away.score&amount=5",
                                    timeout=5):
            pass
        start = time.monotonic()
        result = None
        import threading

        def call():
            nonlocal result
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/action?do=add&field=away.score&amount=1",
                                        timeout=5) as r:
                result = json.loads(r.read())
        t = threading.Thread(target=call)
        t.start()
        while t.is_alive() and time.monotonic() - start < 5:
            self.wait(20)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(p.engine.snapshot().values["away.score"], "6")
        # PNG output
        p.outputs.image_boards = [p.boards[0].id]
        win.session.outputs_changed()
        self.wait(700)
        pngs = os.listdir(os.path.join(folder, "images"))
        self.assertTrue(pngs)
        # save and reopen
        path = os.path.join(self.tmp, "hockey.tsproj")
        p.path = path
        self.assertTrue(win.save())
        self.assertFalse(win.session.dirty)
        win.open_project(path)
        self.wait(150)
        self.assertEqual(win.session.project.engine.snapshot().values["home.score"], "2")
        self.assertIn(os.path.abspath(path), win.recent())

    def test_projector_window(self):
        win = self.make_window()
        p = self.load(win, "Basketball")
        win.open_projector(p.boards[1].id)
        self.wait(100)
        self.assertEqual(len(win.projectors), 1)
        pw = win.projectors[0]
        p.engine.perform({"do": "add", "field": "home.score", "amount": 7})
        self.wait(50)
        self.shot(pw, "projector")
        pw.close()
        self.wait(50)
        self.assertEqual(win.projectors, [])

    def test_legacy_import_flow(self):
        from tests.test_legacy import LEGACY
        win = self.make_window()
        path = os.path.join(self.tmp, "old.json")
        with open(path, "w") as fh:
            json.dump(LEGACY, fh)
        from PyQt6.QtWidgets import QMessageBox
        orig = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
        try:
            win.open_project(path)
        finally:
            QMessageBox.information = orig
        self.wait(100)
        self.assertEqual(win.session.project.name, "Friday Hockey")
        self.assertTrue(win.notice.isVisible())
        self.shot(win, "imported 1x project")

    def test_logic_tab_conditions(self):
        from telescore.core.logic import Condition
        win = self.make_window()
        p = self.load(win, "Hockey")
        lt = win.tabs.widget(3)
        self.assertEqual(win.tabs.tabText(3), "Logic")
        win.tabs.setCurrentIndex(3)
        self.wait(50)
        lt.add()
        self.wait(30)
        c = p.engine.logic.conditions[-1]
        bug = p.boards[0]
        c.principal, c.op, c.target, c.action, c.arg = "home.score", "changes", bug.elements[2].id, "animate", "Pulse"
        win.session.conditions_changed()
        self.wait(30)
        lt.list.setCurrentRow(0)
        self.wait(30)
        self.shot(win, "logic tab")
        p.engine.perform({"do": "add", "field": "home.score"})
        self.wait(50)
        self.assertEqual(p.engine.snapshot().fx[bug.elements[2].id]["anim"]["name"], "Pulse")
        # field-target condition reaches the XML file
        p.engine.logic.conditions.append(Condition(principal="clock.game", op="equals", value="20:00",
                                                   target_kind="field", target="home.name", action="rule",
                                                   arg="Home=PREGAME"))
        win.session.conditions_changed()
        self.wait(400)
        with open(os.path.join(p.outputs.folder, "text", "home.name.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "PREGAME")
        lt.duplicate()
        lt.move(-1)
        lt.delete()
        self.wait(30)

    def test_live_tab_and_binding(self):
        win = self.make_window()
        p = self.load(win, "Basketball")
        path = os.path.join(self.tmp, "live.xml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("<info><Hscore>42</Hscore><Vscore>30</Vscore><period>2</period></info>")
        tab = win.tabs.widget(4)
        self.assertEqual(win.tabs.tabText(4), "Live data")
        win.tabs.setCurrentIndex(4)
        tab.kind.setCurrentIndex(tab.kind.findData("livexml"))
        tab._kind_changed()
        tab.path.setText(path)
        tab.poll.setValue(50)
        tab.apply()
        end = time.monotonic() + 5
        while time.monotonic() < end and "Hscore" not in win.live.keys():
            self.wait(50)
        self.assertEqual(win.live.source.status.state, "live")
        from PyQt6.QtWidgets import QMessageBox
        orig = QMessageBox.question
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
        try:
            tab.automap()
        finally:
            QMessageBox.question = orig
        self.wait(200)
        v = p.engine.snapshot().values
        self.assertEqual((v["home.score"], v["away.score"], v["period"]), ("42", "30", "2nd"))
        win.tabs.setCurrentIndex(0)
        self.wait(100)
        from telescore.ui.operate import CounterCard
        card = next(c for c in win.operate.cards if isinstance(c, CounterCard) and c.f.key == "home.score")
        self.assertEqual(card.flag.text(), "LIVE")
        self.shot(win, "operate with live data")
        win.tabs.setCurrentIndex(4)
        self.wait(100)
        self.shot(win, "live data tab")
        self.assertIn(win.header.lights["live"]._state, ("live", "ok"))
        tab.disconnect()
        self.wait(100)

    def test_animations_dialog_and_inspector(self):
        from telescore.ui.animations_dialog import AnimationsDialog
        win = self.make_window()
        p = self.load(win, "General scoreboard")
        win.tabs.setCurrentIndex(1)
        bt = win.tabs.widget(1)
        self.wait(50)
        dlg = AnimationsDialog(win.session, win)
        dlg.show()
        dlg.new()
        self.assertEqual(len(p.animations), 1)
        dlg.sp_x.setValue(-300)
        self.assertEqual(p.animations[0].x, -300)
        dlg.name.setText("Sweep")
        dlg._rename()
        dlg.copy_current()
        self.assertEqual(len(p.animations), 2)
        self.wait(200)
        self.shot(dlg, "animations dialog")
        dlg.delete()
        dlg.close()
        el = bt.board.elements[3]
        bt.canvas.select_ids([el.id])
        self.wait(30)
        cb, _ = bt.inspector.m_combos["anim_in"]
        self.assertGreaterEqual(cb.findData("Sweep"), 0)
        cb.setCurrentIndex(cb.findData("Sweep"))
        cb.activated.emit(cb.currentIndex())
        self.assertEqual(el.anim_in, "Sweep")
        bt._try_anim("Sweep")
        self.wait(120)
        self.shot(win, "builder mid animation")
        self.wait(800)

    @classmethod
    def tearDownClass(cls):
        print(f"\nScreenshots: {SHOTS}")


if __name__ == "__main__":
    unittest.main()
