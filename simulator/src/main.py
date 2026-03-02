from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTextEdit, QPushButton, QLineEdit, QComboBox, QSizePolicy, QDateTimeEdit, QCheckBox, QScrollArea, QGridLayout
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt, QDateTime
import sys
import multiprocessing
from src.custom_types import TimeScales, Severity, Area
from src.simulator.engine import Engine
class GUI(QMainWindow):

    def collect_input_state(self):
        """Collect all input state for engine setup."""
        # Time mode: True = until time, False = indefinite
        until_time = self.left_bottom_cross_toggle.isChecked()
        run_until = self.left_bottom_datetime_input.dateTime().toPython() if until_time else None
        timescale = self.left_bottom_timescale_dropdown.currentData()
        severity = self.left_bottom_severity_dropdown.currentData()
        areas = [cb.text() for cb in self.right_area_checkboxes if cb.isChecked()]
        return {
            'until_time': until_time,
            'run_until': run_until,
            'timescale': timescale,
            'severity': severity,
            'areas': areas
        }

    def lock_inputs(self, locked=True):
        """Lock or unlock all input widgets except control buttons, and shade them when locked."""
        widgets = [
            self.left_bottom_datetime_input,
            self.left_bottom_cross_toggle,
            self.left_bottom_timescale_dropdown,
            self.left_bottom_severity_dropdown,
        ] + self.right_area_checkboxes
        for w in widgets:
            w.setEnabled(not locked)
            # Shade (dim) when locked, restore when unlocked
            if locked:
                w.setStyleSheet(w.styleSheet() + ";opacity:0.5;background-color:#222;" if isinstance(w, QCheckBox) else w.styleSheet() + ";opacity:0.5;background-color:#333;")
            else:
                # Remove only the added shading, keep other styles
                orig = w.styleSheet()
                orig = orig.replace(";opacity:0.5;background-color:#222;", "")
                orig = orig.replace(";opacity:0.5;background-color:#333;", "")
                w.setStyleSheet(orig)

    def unlock_inputs(self):
        self.lock_inputs(False)

    def setup(self):
        """Create and configure the Engine instance."""
        
        state = self.collect_input_state()
        self.engine = Engine()

    def start_engine(self):
        """Start or continue the engine based on toggle state."""
        self.lock_inputs(True)
        state = self.collect_input_state()
        if not hasattr(self, 'engine') or self.engine is None:
            self.setup()
        if state['until_time'] and state['run_until']:
            self.engine.run_for(state['run_until'])
        else:
            self.engine.run()

    def pause_engine(self):
        if hasattr(self, 'engine') and self.engine is not None:
            self.engine.pause()
        self.unlock_inputs()

    def stop_engine(self):
        if hasattr(self, 'engine') and self.engine is not None:
            self.engine.stop()
        self.unlock_inputs()

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

        # Main horizontal splitter
        splitter = QSplitter(Qt.Vertical)

        # Top: two split panes (left and right)
        top_splitter = QSplitter(Qt.Horizontal)
        left_top = QTextEdit()
        right_top = QTextEdit()
        top_splitter.addWidget(left_top)
        top_splitter.addWidget(right_top)
        top_splitter.setSizes([600, 400])

        # Bottom: controls and area checkboxes in one pane
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)

        # Controls (left side of bottom pane)
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(5)
        input_row = QHBoxLayout()
        datetime_input = QDateTimeEdit()
        datetime_input.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        datetime_input.setDateTime(QDateTime.currentDateTime())
        datetime_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        datetime_input.setMinimumHeight(28)

        # Standard QCheckBox toggle for indefinite/timed run, placed left of datetime
        toggle_checkbox = QCheckBox("Run until enable")
        toggle_checkbox.setChecked(False)
        toggle_checkbox.setToolTip("Check to run until selected time, uncheck for indefinite run")
        toggle_checkbox.setMinimumHeight(28)

        input1 = QComboBox()
        for ts in TimeScales:
            input1.addItem(ts.name, ts.value)
        dropdown = QComboBox()
        for sev in Severity:
            dropdown.addItem(sev.name, sev.value)
        # Add toggle left of datetime, then rest
        for w in (toggle_checkbox, datetime_input, input1, dropdown):
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            w.setMinimumHeight(28)
            input_row.addWidget(w)
        controls_layout.addLayout(input_row)
        button_row = QHBoxLayout()
        btn1 = QPushButton("START/CONTINUE")
        btn2 = QPushButton("PAUSE")
        btn3 = QPushButton("STOP")
        for b in (btn1, btn2, btn3):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setMinimumHeight(28)
            button_row.addWidget(b)
        controls_layout.addLayout(button_row)
        controls_widget.setMaximumWidth(350)
        controls_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        controls_widget.adjustSize()
        bottom_layout.addWidget(controls_widget)

        # Area checkboxes (right side of bottom pane)
        area_checkbox_widget = QWidget()
        area_checkbox_layout = QGridLayout(area_checkbox_widget)
        area_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        area_checkbox_layout.setSpacing(8)
        self.area_checkboxes = []
        max_columns = 4  # Adjust for how many checkboxes per row
        for idx, area in enumerate(Area):
            cb = QCheckBox(area.value)
            cb.setChecked(True)
            self.area_checkboxes.append(cb)
            row = idx // max_columns
            col = idx % max_columns
            area_checkbox_layout.addWidget(cb, row, col)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(area_checkbox_widget)
        bottom_layout.addWidget(scroll)

        # Make controls_widget (buttons and fields) fill 1/3 of the width
        controls_widget.setMaximumWidth(16777215)
        controls_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bottom_layout.setStretch(0, 1)
        bottom_layout.setStretch(1, 2)

        # Set bottom_widget height to fit controls_widget height
        bottom_widget.setMaximumHeight(controls_widget.sizeHint().height())
        bottom_widget.setMinimumHeight(controls_widget.sizeHint().height())
        bottom_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Add top and bottom to main vertical splitter
        splitter.addWidget(top_splitter)
        splitter.addWidget(bottom_widget)
        splitter.setSizes([500, 100])

        layout.addWidget(splitter)

        # Expose controls for easy function connection
        self.left_bottom_buttons = [btn1, btn2, btn3]
        self.left_bottom_inputs = [input1]
        self.left_bottom_dropdown = dropdown
        self.right_area_checkboxes = self.area_checkboxes
        self.left_bottom_datetime_input = datetime_input
        self.left_bottom_severity_dropdown = dropdown
        self.left_bottom_timescale_dropdown = input1
        self.left_bottom_cross_toggle = toggle_checkbox  # Expose toggle for indefinite/timed run

        # Engine integration: connect buttons
        btn1.clicked.connect(self.start_engine)
        btn2.clicked.connect(self.pause_engine)
        btn3.clicked.connect(self.stop_engine)

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