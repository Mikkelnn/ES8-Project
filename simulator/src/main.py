from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTextEdit, QPushButton, QLineEdit, QComboBox, QSizePolicy
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt
import sys
import multiprocessing
from src.custom_types import TimeScales

class GUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulator")
        self.setGeometry(100, 100, 800, 600)
        self.set_dark_theme()
        self.init_ui()

    def set_dark_theme(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        QApplication.setPalette(dark_palette)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)

        splitter = QSplitter(Qt.Horizontal)

        # Left pane with vertical splitter for top, center, bottom
        left_splitter = QSplitter(Qt.Vertical)
        left_top = QTextEdit()
        left_top.setPlaceholderText("Top Pane (small)")
        left_center = QTextEdit()
        left_center.setPlaceholderText("Main Left Pane")

        # Bottom left pane with controls
        left_bottom_widget = QWidget()
        left_bottom_layout = QVBoxLayout(left_bottom_widget)
        left_bottom_layout.setContentsMargins(0, 0, 0, 0)
        left_bottom_layout.setSpacing(5)

        # Input fields and dropdown
        input_row = QHBoxLayout()
        input1 = QLineEdit()
        input2 = QLineEdit()
        dropdown = QComboBox()
        # Populate dropdown with TimeScales enum
        for ts in TimeScales:
            dropdown.addItem(ts.name, ts.value)
        for w in (input1, input2, dropdown):
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            w.setMinimumHeight(28)
            input_row.addWidget(w)
        left_bottom_layout.addLayout(input_row)

        # Buttons row
        button_row = QHBoxLayout()
        btn1 = QPushButton("Button 1")
        btn2 = QPushButton("Button 2")
        btn3 = QPushButton("Button 3")
        for b in (btn1, btn2, btn3):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setMinimumHeight(28)
            button_row.addWidget(b)
        left_bottom_layout.addLayout(button_row)
        left_bottom_layout.addStretch()

        left_splitter.addWidget(left_top)
        left_splitter.addWidget(left_center)
        left_splitter.addWidget(left_bottom_widget)
        left_splitter.setSizes([75, 350, 75])

        # Right pane as before
        right_pane = QTextEdit()
        right_pane.setPlaceholderText("Right Pane")

        splitter.addWidget(left_splitter)
        splitter.addWidget(right_pane)
        splitter.setSizes([600, 400])

        layout.addWidget(splitter)

        # Expose controls for easy function connection
        self.left_bottom_buttons = [btn1, btn2, btn3]
        self.left_bottom_inputs = [input1, input2]
        self.left_bottom_dropdown = dropdown

    @staticmethod
    def run():
        app = QApplication.instance() or QApplication(sys.argv)
        window = GUI()
        window.show()
        return app.exec()

def start_gui_process():
    multiprocessing.set_start_method('spawn', force=True)
    p = multiprocessing.Process(target=GUI.run)
    p.start()
    return p

if __name__ == "__main__":
    start_gui_process()