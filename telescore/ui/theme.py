"""
The operator UI look, built the Keystone way and dressed in either Keystone
or Rally colours.

Fundamentals taken from the Keystone Scorebook system:
  * a scheme is nine colours (accent, head, hi, mark, user, alert, bg, panel,
    ink); every other colour is derived by the same recipe, so a scheme can be
    swapped without touching a widget;
  * flat surfaces, 1px ``rule`` hairlines, no shadows, small functional corners
    (3px inputs, 4px buttons, 6px panels);
  * one family (Archivo, bundled); 900-weight tracked capitals for anything
    that labels, 400-500 for anything you read; tabular figures everywhere;
  * ``accent`` only for the main action and the selected state, ``hi`` for
    "where you are" (focus ring, the 4px underline under the active tab),
    ``alert`` only for errors and destructive actions, ``user`` (amber) for
    warnings and busy states;
  * words on buttons, not icons; status lights are 8-10px dots.

From Rally:
  * a status is always colour *and* a word (RUNNING, STOPPED, LIVE, OFF);
  * one accent, kept scarce so it reads as "the thing to press";
  * chips and pills with a 1px light border rather than shadows.

The on-air look of boards is separate (see core.presets.ONAIR) and never
follows the operator scheme.
"""

from __future__ import annotations

import os
from typing import Dict

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PyQt6.QtWidgets import QApplication

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
FAMILY = "Archivo"

from .colors import DEFAULT_SCHEME, SCHEMES, Palette, contrast, derive, ink_on, mix  # noqa: F401

# The palette in use; widgets that paint read it at paint time.
CURRENT: Palette = derive(DEFAULT_SCHEME)


# ----- fonts -------------------------------------------------------------------

def load_fonts() -> str:
    """Register the bundled Archivo faces. Returns the family to use."""
    ok = False
    for f in ("Archivo.ttf", "Archivo-Italic.ttf"):
        path = os.path.join(ASSETS, "fonts", f)
        if os.path.isfile(path) and QFontDatabase.addApplicationFont(path) >= 0:
            ok = True
    return FAMILY if ok else QFont().defaultFamily()


def font(px: float, weight: int = 400, caps: bool = False, tracking_em: float = 0.0,
         tabular: bool = True, family: str = FAMILY) -> QFont:
    """A font in the house style. ``tracking_em`` is letter spacing in em."""
    f = QFont(family)
    f.setPixelSize(max(1, round(px)))
    f.setWeight(QFont.Weight(max(100, min(900, round(weight / 100) * 100))))
    if caps:
        f.setCapitalization(QFont.Capitalization.AllUppercase)
    if tracking_em:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking_em * px)
    if tabular:
        set_tabular(f)
    return f


def set_tabular(f: QFont) -> None:
    """Tabular figures so scores and clocks never jiggle (Qt 6.7+)."""
    try:
        f.setFeature(QFont.Tag("tnum"), 1)
    except (AttributeError, TypeError):
        pass


# Type scale (Keystone names, pixel sizes)
TYPE = {
    "count": (54, 900, False, 0.02),
    "figure": (32, 900, False, 0.0),
    "dialog-title": (17, 900, True, 0.04),
    "title": (17, 700, False, 0.0),
    "entry": (17, 500, False, 0.0),
    "body": (14.5, 400, False, 0.0),
    "brand": (14, 900, True, 0.05),
    "cell": (13.5, 500, False, 0.0),
    "small": (12.5, 400, False, 0.0),
    "tab": (12, 900, True, 0.06),
    "section": (11.5, 900, True, 0.08),
    "label": (10.5, 900, True, 0.09),
}


def tfont(style: str) -> QFont:
    px, w, caps, tr = TYPE[style]
    return font(px, w, caps, tr)


# ----- style sheet -------------------------------------------------------------

def _icons(p: Palette) -> Dict[str, str]:
    """Write the few indicator glyphs Qt style sheets need as SVG files."""
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation) or ASSETS
    folder = os.path.join(base, "theme", p.name.replace(" ", "_"))
    os.makedirs(folder, exist_ok=True)
    svgs = {
        "check": f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><path d="M3.5 8.5l3 3 6-7" '
                 f'fill="none" stroke="{p["accent-ink"]}" stroke-width="2.2" stroke-linecap="square"/></svg>',
        "down": f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><path d="M1 3l4 4 4-4" '
                f'fill="none" stroke="{p["muted"]}" stroke-width="1.6"/></svg>',
        "up": f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><path d="M1 7l4-4 4 4" '
              f'fill="none" stroke="{p["muted"]}" stroke-width="1.6"/></svg>',
    }
    out = {}
    for name, body in svgs.items():
        path = os.path.join(folder, name + ".svg")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
        except OSError:
            continue
        out[name] = path.replace("\\", "/")
    return out


def _buttons(c) -> str:
    rules = [
        ("QPushButton, QToolButton",
         f"background: {c['panel']}; color: {c['ink']}; border: 1px solid {c['rule-strong']}; border-radius: 4px;"
         " padding: 5px 10px; min-height: 22px; font-weight: 600;"),
        ("QPushButton:hover, QToolButton:hover", f"border-color: {c['accent-text']};"),
        ("QPushButton:pressed, QToolButton:pressed", f"background: {c['sel']};"),
        ("QPushButton:checked, QToolButton:checked",
         f"background: {c['accent']}; color: {c['accent-ink']}; border-color: {c['accent']};"),
        ('QPushButton[role="accent"]',
         f"background: {c['accent']}; color: {c['accent-ink']}; border-color: {c['accent']}; font-weight: 800;"),
        ('QPushButton[role="accent"]:hover', f"border-color: {c['ink']};"),
        ('QPushButton[role="alert"]', f"color: {c['alert-text']}; border-color: {c['alert']};"),
        ('QPushButton[role="alert"]:hover', f"background: {c['alert-soft']};"),
        ('QPushButton[role="danger"]',
         f"background: {c['alert']}; color: {c['alert-ink']}; border-color: {c['alert']}; font-weight: 800;"),
        ('QPushButton[role="user"]', f"color: {c['user-text']}; border-color: {c['user']};"),
        ('QPushButton[role="hi"]', f"color: {c['ink']}; border-color: {c['hi']};"),
        ('QPushButton[role="ghost"]', f"background: transparent; border-color: transparent; color: {c['accent-text']};"),
        ('QPushButton[role="ghost"]:hover', f"border-color: {c['rule-strong']};"),
        # Disabled comes after the roles so a disabled green button reads as disabled, not as blank green.
        ("QPushButton:disabled, QToolButton:disabled",
         f"color: {c['muted']}; border-color: {c['rule']}; background: {c['field']};"),
        (", ".join(f'QPushButton[role="{r}"]:disabled' for r in ("accent", "danger", "alert", "user", "hi", "ghost")),
         f"color: {c['muted']}; border-color: {c['rule']}; background: {c['field']}; font-weight: 600;"),
        ("QPushButton:focus, QToolButton:focus", f"outline: none; border: 2px solid {c['hi']}; padding: 4px 9px;"),
        ('QPushButton[big="true"]', "font-size: 16px; font-weight: 800; min-height: 40px; padding: 6px 14px;"),
        ('QPushButton[seg="true"]', "border-radius: 4px; padding: 4px 10px;"),
        # Section switches (Design: Boards / Logic / Animations): quiet words, hi underline when current.
        ('QPushButton[nav="true"]',
         f"background: transparent; color: {c['muted']}; border: 0; border-bottom: 3px solid transparent;"
         " border-radius: 0; padding: 6px 12px 4px 12px; font-weight: 800;"),
        ('QPushButton[nav="true"]:hover', f"color: {c['ink']};"),
        ('QPushButton[nav="true"]:checked',
         f"background: transparent; color: {c['accent-text']}; border-bottom: 3px solid {c['hi']};"),
        ('QPushButton[nav="true"]:focus', f"border: 0; border-bottom: 3px solid {c['hi']}; padding: 6px 12px 4px 12px;"),
    ]
    out = []
    for sel, body in rules:
        scoped = ", ".join(f'QFrame[panel="true"] {part.strip()}' for part in sel.split(","))
        out.append(f"{sel}, {scoped} {{ {body} }}")
    return "\n".join(out)


def qss(p: Palette) -> str:
    c = p.c
    i = _icons(p)
    check = f"image: url({i['check']});" if "check" in i else ""
    down = f"image: url({i['down']});" if "down" in i else ""
    up = f"image: url({i['up']});" if "up" in i else ""
    return f"""
* {{ font-family: "{FAMILY}"; }}
QWidget {{ background: {c['bg']}; color: {c['ink']}; font-size: 14px; }}
QMainWindow::separator {{ background: {c['rule']}; width: 1px; height: 1px; }}
QToolTip {{ background: {c['ink']}; color: {c['bg']}; border: 0; padding: 4px 6px; border-radius: 4px; }}

/* Panels: flat, hairline, no shadow */
QFrame[panel="true"] {{ background: {c['panel']}; border: 1px solid {c['rule']}; border-radius: 6px; }}
QFrame[panel="true"] QWidget {{ background: transparent; }}
QFrame[panel="true"] QLineEdit, QFrame[panel="true"] QSpinBox, QFrame[panel="true"] QDoubleSpinBox,
QFrame[panel="true"] QComboBox, QFrame[panel="true"] QPlainTextEdit, QFrame[panel="true"] QKeySequenceEdit QLineEdit
    {{ background: {c['field']}; }}
QFrame[headbar="true"] {{ background: {c['head']}; border: 0; }}
QFrame[headbar="true"] QLabel {{ background: transparent; color: {c['head-ink']}; }}
QFrame[notice="true"] {{ background: {c['warn-soft']}; border: 0; border-radius: 4px; }}
QFrame[notice="alert"] {{ background: {c['alert-soft']}; border: 0; border-radius: 4px; }}
QFrame[notice="alert"] QLabel {{ color: {c['alert-text']}; }}

QLabel {{ background: transparent; }}
QLabel[muted="true"] {{ color: {c['muted']}; }}
QLabel[accenttext="true"] {{ color: {c['accent-text']}; }}
QLabel[alerttext="true"] {{ color: {c['alert-text']}; }}

/* Buttons: words, panel fill, hairline; hover turns the border accent.
   Every button rule is also written scoped to panels: the panel rule above
   makes children transparent and would otherwise outrank a role's fill. */
{_buttons(c)}
QFrame[headbar="true"] QPushButton {{
    background: {c['menu-fill']}; color: {c['head-ink']}; border: 1px solid {c['menu-border']};
}}

/* Inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QKeySequenceEdit QLineEdit {{
    background: {c['field']}; color: {c['ink']}; border: 1px solid {c['rule-strong']}; border-radius: 3px;
    padding: 4px 6px; selection-background-color: {c['sel']}; selection-color: {c['ink']};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 2px solid {c['hi']}; padding: 3px 5px;
}}
QLineEdit[error="true"] {{ border: 2px solid {c['alert']}; padding: 3px 5px; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {c['muted']}; }}
QComboBox::drop-down {{ border: 0; width: 18px; }}
QComboBox::down-arrow {{ {down} width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {c['panel']}; border: 1px solid {c['rule-strong']};
    selection-background-color: {c['sel']}; selection-color: {c['ink']}; outline: 0; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ border: 0; width: 16px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ border: 0; width: 16px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ {up} width: 9px; height: 9px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ {down} width: 9px; height: 9px; }}

QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {c['rule-strong']}; border-radius: 3px; background: {c['field']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; {check} }}
QCheckBox::indicator:focus {{ border: 2px solid {c['hi']}; }}
QTreeView::indicator, QListView::indicator, QTableView::indicator {{
    width: 14px; height: 14px; border: 1px solid {c['rule-strong']}; border-radius: 3px; background: {c['field']};
}}
QTreeView::indicator:checked, QListView::indicator:checked, QTableView::indicator:checked {{
    background: {c['accent']}; border-color: {c['accent']}; {check}
}}
QRadioButton {{ background: transparent; }}

/* Tabs: capitals, 4px hi underline under the active one */
QTabWidget::pane {{ border: 0; border-top: 1px solid {c['rule']}; background: {c['bg']}; }}
QTabBar {{ background: {c['panel']}; }}
QTabBar::tab {{
    background: {c['panel']}; color: {c['muted']}; padding: 10px 16px 8px 16px; margin-right: 2px;
    border: 0; border-bottom: 4px solid transparent; font-size: 12px; font-weight: 900;
}}
QTabBar::tab:selected {{ color: {c['accent-text']}; border-bottom: 4px solid {c['hi']}; }}
QTabBar::tab:hover:!selected {{ color: {c['ink']}; }}

/* Workspace sections: a quiet bar of switches (Design) or a list down the left (Setup) */
QFrame[sectionbar="true"] {{ background: {c['bg']}; border: 0; border-bottom: 1px solid {c['rule']}; }}
QFrame[vrule="true"] {{ background: {c['rule']}; border: 0; }}
QListWidget[sectionlist="true"] {{ background: {c['panel']}; border: 0; border-radius: 0; padding-top: 10px; }}
QListWidget[sectionlist="true"]::item {{ padding: 9px 16px; color: {c['muted']}; border: 0; border-left: 3px solid transparent; }}
QListWidget[sectionlist="true"]::item:hover {{ color: {c['ink']}; background: {c['hover']}; }}
QListWidget[sectionlist="true"]::item:selected {{
    background: {c['sel']}; color: {c['ink']}; border-left: 3px solid {c['hi']}; font-weight: 700;
}}

/* Lists and tables: dense, hairlines, sel + hi edge for the selected row */
QListWidget, QTreeWidget, QTableWidget, QTableView, QTreeView, QListView {{
    background: {c['panel']}; alternate-background-color: {c['row-alt']}; border: 1px solid {c['rule']};
    border-radius: 6px; outline: 0; gridline-color: {c['rule']};
}}
QListWidget::item, QTreeWidget::item, QTableWidget::item {{ padding: 3px 6px; border: 0; }}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{
    background: {c['sel']}; color: {c['ink']}; border-left: 3px solid {c['hi']};
}}
QListWidget::item:hover, QTreeWidget::item:hover, QTableWidget::item:hover {{ background: {c['hover']}; }}
/* In a table the edge would repeat in every cell of the row, so tables mark the row with fill only */
QTableWidget::item:selected, QTableView::item:selected {{ border-left: 0; }}
QHeaderView {{ background: {c['panel']}; border: 0; }}
QHeaderView::section {{
    background: {c['panel']}; color: {c['muted']}; border: 0; border-bottom: 1px solid {c['rule']};
    padding: 5px 6px; font-size: 10.5px; font-weight: 900;
}}
QTableCornerButton::section {{ background: {c['panel']}; border: 0; }}

QScrollArea {{ border: 0; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: {c['rule-strong']}; border-radius: 4px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {c['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: 0; width: 0; height: 0; }}

QMenuBar {{ background: {c['head']}; color: {c['head-ink']}; padding: 2px 6px; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {c['menu-fill']}; }}
QMenu {{ background: {c['panel']}; border: 1px solid {c['rule-strong']}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['sel']}; }}
QMenu::item:disabled {{ color: {c['muted']}; }}
QMenu::separator {{ height: 1px; background: {c['rule']}; margin: 4px 6px; }}

QStatusBar {{ background: {c['panel']}; color: {c['muted']}; border-top: 1px solid {c['rule']}; }}
QStatusBar QLabel {{ color: {c['muted']}; }}
QSplitter::handle {{ background: {c['rule']}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QGraphicsView {{ background: {c['field']}; border: 1px solid {c['rule']}; border-radius: 6px; }}
QDialog {{ background: {c['bg']}; }}
QSlider::groove:horizontal {{ height: 4px; background: {c['rule-strong']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; margin: -6px 0; border-radius: 7px; background: {c['accent']}; }}
"""


def apply(app: QApplication, scheme: str = DEFAULT_SCHEME) -> Palette:
    """Apply a scheme to the whole application and remember it as CURRENT."""
    global CURRENT
    p = derive(scheme if scheme in SCHEMES else DEFAULT_SCHEME)
    CURRENT = p
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: "bg", QPalette.ColorRole.WindowText: "ink",
        QPalette.ColorRole.Base: "field", QPalette.ColorRole.AlternateBase: "row-alt",
        QPalette.ColorRole.Text: "ink", QPalette.ColorRole.Button: "panel",
        QPalette.ColorRole.ButtonText: "ink", QPalette.ColorRole.Highlight: "sel",
        QPalette.ColorRole.HighlightedText: "ink", QPalette.ColorRole.ToolTipBase: "ink",
        QPalette.ColorRole.ToolTipText: "bg", QPalette.ColorRole.PlaceholderText: "muted",
        QPalette.ColorRole.Link: "accent-text", QPalette.ColorRole.BrightText: "alert-text",
    }
    for role, key in roles.items():
        pal.setColor(role, QColor(p[key]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(p["muted"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(p["muted"]))
    app.setPalette(pal)
    base = font(14, 400)
    app.setFont(base)
    app.setStyleSheet(qss(p))
    return p


def repolish(w) -> None:
    """Re-evaluate dynamic properties (role, error, ...) after changing them."""
    st = w.style()
    st.unpolish(w)
    st.polish(w)
    w.update()
