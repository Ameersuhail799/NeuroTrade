DARK_STYLE = """
QWidget {
    background-color: #111418;
    color: #d5d8dc;
    font-size: 12px;
}

QMainWindow,
QDialog {
    background-color: #111418;
}

QTabWidget::pane {
    border: 1px solid #2a2f36;
    background: #15191f;
}

QTabBar::tab {
    background: #1a1f26;
    padding: 6px 12px;
    border: 1px solid #2a2f36;
    border-bottom: 0;
}

QTabBar::tab:selected {
    background: #15191f;
    color: #ffffff;
}

QGroupBox {
    border: 1px solid #2a2f36;
    margin-top: 12px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}

QPlainTextEdit,
QTextEdit,
QTextBrowser {
    background-color: #0d1013;
    border: 1px solid #2a2f36;
}

QLabel {
    background: transparent;
}

QStatusBar {
    background: #1a1f26;
}

QMenuBar {
    background: #1a1f26;
}

QMenuBar::item:selected {
    background: #2a2f36;
}

QMenu {
    background: #1a1f26;
    border: 1px solid #2a2f36;
}

QMenu::item:selected {
    background: #2a2f36;
}

QPushButton {
    background: #2a2f36;
    border: 1px solid #3a4048;
    padding: 5px 10px;
}

QPushButton:hover {
    background: #3a4048;
}
"""