import sys
import os
import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLineEdit, QLabel, QSizePolicy, QFrame, QCheckBox, QApplication
)
from PySide6.QtCore import QTimer
from simulator.engine import Engine
from simulator.logger import LOG_PATH

class SimulatorGUI(QWidget):
    def closeEvent(self, event):
        # Robustly stop timer and disconnect update_log to prevent post-delete calls
        if hasattr(self, 'timer') and self.timer:
            try:
                self.timer.stop()
                self.timer.timeout.disconnect()
            except Exception:
                pass
        self.log_display = None
        super().closeEvent(event)
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulator Control Panel")
        self._paused = False
        self._debug_count = 0
        self._info_count = 0
        self._warning_count = 0
        self._error_count = 0
        self._critical_count = 0
        self.status_label = QLabel()
        self.status_label.setStyleSheet('color: #ff7e7e; font-size: 14px;')
        # Area subscription state and data storage
        self.subscribed_areas = {"BATTERY": True, "CLOCK": True}
        self.data_buffer = {"BATTERY": [], "CLOCK": []}  # {area: [(timestamp, value), ...]}
        self._setup_simulation_files()
        self._setup_logger()
        self.engine = Engine()
        self._build_ui()
        self._setup_signals()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_log)
        # Timer will be started after showEvent

    def _setup_simulation_files(self):
        import datetime
        import pathlib
        now = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.sim_folder = pathlib.Path('results') / f'simulation_{now}'
        self.sim_folder.mkdir(parents=True, exist_ok=True)
        self.sim_log_path = self.sim_folder / 'simulation.log'
        self.sim_csv_path = self.sim_folder / 'results.csv'
        self.sim_svg_path = self.sim_folder / 'result.svg'
        self.sim_log_path.unlink(missing_ok=True)
        self.sim_log_path.write_text('')
        self.sim_csv_path.touch(exist_ok=True)
        self.sim_svg_path.touch(exist_ok=True)

    def _setup_logger(self):
        from simulator.logger import Logger
        Logger.set_log_file(str(self.sim_log_path))

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        # --- Left: Simulator controls and log ---
        simulator_widget = QWidget()
        simulator_layout = QVBoxLayout(simulator_widget)
        simulator_title = QLabel("Simulator")
        simulator_title.setStyleSheet('''
            font-weight: bold;
            font-size: 18px;
            background: #232629;
            color: #f0f0f0;
            border-bottom: 2px solid #444;
            padding: 0;
            min-height: 36px;
            max-height: 36px;
            qproperty-alignment: AlignCenter;
        ''')
        simulator_layout.addWidget(simulator_title)
        # Area subscription checkboxes
        area_layout = QHBoxLayout()
        self.battery_checkbox = QCheckBox("Battery")
        self.battery_checkbox.setChecked(True)
        self.clock_checkbox = QCheckBox("Clock")
        self.clock_checkbox.setChecked(True)
        area_layout.addWidget(QLabel("Subscribe to:"))
        area_layout.addWidget(self.battery_checkbox)
        area_layout.addWidget(self.clock_checkbox)
        area_layout.addStretch()
        simulator_layout.addLayout(area_layout)
        # Log counters
        counter_layout = QHBoxLayout()
        self.counter_debug = QLabel("DEBUG: 0")
        self.counter_info = QLabel("INFO: 0")
        self.counter_warning = QLabel("WARNING: 0")
        self.counter_error = QLabel("ERROR: 0")
        self.counter_critical = QLabel("CRITICAL: 0")
        self.counter_debug.setStyleSheet('color: #7ecfff; font-size: 16px;')
        self.counter_info.setStyleSheet('color: #b3ff7e; font-size: 16px;')
        self.counter_warning.setStyleSheet('color: #ffe97e; font-size: 16px;')
        self.counter_error.setStyleSheet('color: #ffb37e; font-size: 16px;')
        self.counter_critical.setStyleSheet('color: #ff7e7e; font-size: 16px;')
        for c in [self.counter_debug, self.counter_info, self.counter_warning, self.counter_error, self.counter_critical]:
            counter_layout.addWidget(c)
        counter_layout.addStretch()
        simulator_layout.addLayout(counter_layout)
        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log_display.setText("Simulator GUI loaded. If you see this, the GUI is working.")
        simulator_layout.addWidget(self.log_display)
        # Time input
        time_layout = QHBoxLayout()
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("Time units (leave empty for infinite)")
        time_layout.addWidget(QLabel("Run for time:"))
        time_layout.addWidget(self.time_input)
        simulator_layout.addLayout(time_layout)
        # Buttons
        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run/Continue")
        self.pause_btn = QPushButton("Pause")
        self.export_btn = QPushButton("Export")
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.pause_btn)
        btn_layout.addWidget(self.export_btn)
        simulator_layout.addLayout(btn_layout)
        simulator_layout.addWidget(self.status_label)
        # --- Matplotlib live plot ---
        self.figure = Figure(figsize=(5, 3))
        self.canvas = FigureCanvas(self.figure)
        # --- Right: Results ---
        result_widget = QWidget()
        result_layout = QVBoxLayout(result_widget)
        result_title = QLabel("Result")
        result_title.setStyleSheet('''
            font-weight: bold;
            font-size: 18px;
            background: #232629;
            color: #f0f0f0;
            border-bottom: 2px solid #444;
            padding: 0;
            min-height: 36px;
            max-height: 36px;
            qproperty-alignment: AlignCenter;
        ''')
        result_layout.addWidget(result_title)
        # Remove placeholder, make plot fill results panel
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        result_layout.addWidget(self.canvas)
        # --- Layout with divider ---
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setFrameShadow(QFrame.Sunken)
        divider.setStyleSheet('background: #444; width: 2px;')
        main_layout.addWidget(simulator_widget, 1)
        main_layout.addWidget(divider)
        main_layout.addWidget(result_widget, 1)
        self.setLayout(main_layout)
        # --- Stylesheet ---
        self.setStyleSheet('''
            QWidget, QMainWindow, QDialog, QMenuBar, QMenu, QStatusBar {
                background-color: #181a1b;
                color: #f0f0f0;
                font-size: 16px;
            }
            QTextEdit, QLineEdit {
                background-color: #232629;
                color: #f0f0f0;
                border: 1px solid #444;
                font-size: 16px;
            }
            QPushButton {
                background-color: #232629;
                color: #f0f0f0;
                border: 1px solid #555;
                padding: 9px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #333;
            }
            QLabel {
                color: #f0f0f0;
                font-size: 16px;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: #232629;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #444;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                background: none;
            }
            QScrollBar::add-page, QScrollBar::sub-page {
                background: none;
            }
        ''')

    def _setup_signals(self):
        self.run_btn.clicked.connect(self.handle_run)
        self.pause_btn.clicked.connect(self.handle_pause)
        self.export_btn.clicked.connect(self.handle_export)
        self.battery_checkbox.stateChanged.connect(self._update_area_subscription)
        self.clock_checkbox.stateChanged.connect(self._update_area_subscription)

    def _update_area_subscription(self):
        self.subscribed_areas["BATTERY"] = self.battery_checkbox.isChecked()
        self.subscribed_areas["CLOCK"] = self.clock_checkbox.isChecked()

    def showEvent(self, event):
        super().showEvent(event)
        # Start timer only after window is shown
        if not hasattr(self, '_timer_started'):
            self.timer.start(1000)
            self.update_log()
            self._timer_started = True

    def init_ui(self):
        print("init_ui start")
        main_layout = QHBoxLayout()

        # Simulator submodule (left)
        simulator_widget = QWidget()
        simulator_layout = QVBoxLayout()
        simulator_widget.setLayout(simulator_layout)
        simulator_title = QLabel("Simulator")
        simulator_title.setStyleSheet('''
            font-weight: bold;
            font-size: 18px;
            background: #232629;
            color: #f0f0f0;
            border-bottom: 2px solid #444;
            padding: 0;
            min-height: 36px;
            max-height: 36px;
            qproperty-alignment: AlignCenter;
        ''')
        simulator_layout.addWidget(simulator_title)

        # Log counter and display
        self.log_lines_to_show = 40
        self.counter_label = QLabel()
        self.counter_debug = QLabel()
        self.counter_info = QLabel()
        self.counter_warning = QLabel()
        self.counter_error = QLabel()
        self.counter_critical = QLabel()
        self.counter_debug.setStyleSheet('color: #7ecfff; font-size: 16px;')
        self.counter_info.setStyleSheet('color: #b3ff7e; font-size: 16px;')
        self.counter_warning.setStyleSheet('color: #ffe97e; font-size: 16px;')
        self.counter_error.setStyleSheet('color: #ffb37e; font-size: 16px;')
        self.counter_critical.setStyleSheet('color: #ff7e7e; font-size: 16px;')
        counter_layout = QHBoxLayout()
        counter_layout.addWidget(self.counter_debug)
        counter_layout.addWidget(self.counter_info)
        counter_layout.addWidget(self.counter_warning)
        counter_layout.addWidget(self.counter_error)
        counter_layout.addWidget(self.counter_critical)
        counter_layout.addStretch()
        simulator_layout.addLayout(counter_layout)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log_display.setText("Simulator GUI loaded. If you see this, the GUI is working.")
        simulator_layout.addWidget(self.log_display)

        # Time input
        time_layout = QHBoxLayout()
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("Time units (leave empty for infinite)")
        time_layout.addWidget(QLabel("Run for time:"))
        time_layout.addWidget(self.time_input)
        simulator_layout.addLayout(time_layout)

        # Buttons

        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run/Continue")
        self.pause_btn = QPushButton("Pause")
        self.export_btn = QPushButton("Export")
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.pause_btn)
        btn_layout.addWidget(self.export_btn)
        simulator_layout.addLayout(btn_layout)

        self.run_btn.clicked.connect(self.handle_run)
        self.pause_btn.clicked.connect(self.handle_pause)
        self.export_btn.clicked.connect(self.handle_export)

    def handle_export(self):
        # Only create CSV and SVG when export is pressed
        self._export_csv()
        self._export_svg()
        self.status_label.setText("Exported results to CSV and SVG.")

    def _export_csv(self):
        # Save subscribed area data to CSV
        import csv
        with open(self.sim_csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            header = ["timestamp"] + [area.lower() for area in self.data_buffer if self.subscribed_areas.get(area, False)]
            writer.writerow(header)
            # Merge data by timestamp
            merged = {}
            for area, data in self.data_buffer.items():
                if not self.subscribed_areas.get(area, False):
                    continue
                for timestamp, value in data:
                    merged.setdefault(timestamp, {})[area] = value
            for timestamp in sorted(merged.keys()):
                row = [timestamp]
                for area in header[1:]:
                    row.append(merged[timestamp].get(area.upper(), ""))
                writer.writerow(row)

    def _export_svg(self):
        # Save current matplotlib figure to SVG
        self.figure.savefig(self.sim_svg_path, format='svg')

        # Result submodule (right)
        result_widget = QWidget()
        result_layout = QVBoxLayout()
        result_widget.setLayout(result_layout)
        result_title = QLabel("Result")
        result_title.setStyleSheet('''
            font-weight: bold;
            font-size: 18px;
            background: #232629;
            color: #f0f0f0;
            border-bottom: 2px solid #444;
            padding: 0;
            min-height: 36px;
            max-height: 36px;
            qproperty-alignment: AlignCenter;
        ''')
        result_layout.addWidget(result_title)
        # Placeholder for result content
        result_placeholder = QLabel("(Result output will appear here)")
        result_placeholder.setStyleSheet('color: #888; font-size: 16px;')
        result_layout.addWidget(result_placeholder)

        # Add both widgets to main layout with a vertical divider
        from PySide6.QtWidgets import QFrame
        main_layout.addWidget(simulator_widget, 1)
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setFrameShadow(QFrame.Sunken)
        divider.setStyleSheet('background: #444; width: 2px;')
        main_layout.addWidget(divider)
        main_layout.addWidget(result_widget, 1)
        self.setLayout(main_layout)
        print("init_ui end")

        # Apply comprehensive dark mode stylesheet
        self.setStyleSheet('''
            QWidget, QMainWindow, QDialog, QMenuBar, QMenu, QStatusBar {
                background-color: #181a1b;
                color: #f0f0f0;
                font-size: 16px;
            }
            QTextEdit, QLineEdit {
                background-color: #232629;
                color: #f0f0f0;
                border: 1px solid #444;
                font-size: 16px;
            }
            QPushButton {
                background-color: #232629;
                color: #f0f0f0;
                border: 1px solid #555;
                padding: 9px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #333;
            }
            QLabel {
                color: #f0f0f0;
                font-size: 16px;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: #232629;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #444;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                background: none;
            }
            QScrollBar::add-page, QScrollBar::sub-page {
                background: none;
            }
        ''')

    def setup_timer(self):
        print("setup_timer start")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_log)
        self.timer.start(1000)  # Update every second
        self.update_log()
        print("setup_timer end")

    def update_log(self):
        # Prevent update if widget is being deleted
        log_display = getattr(self, 'log_display', None)
        if log_display is None:
            return
        # Robustly check if widget is still valid
        try:
            if not log_display.isWidgetType() or not log_display.isVisible():
                if hasattr(self, 'timer') and self.timer:
                    try:
                        self.timer.stop()
                    except Exception:
                        pass
                self.log_display = None
                return
        except RuntimeError:
            self.log_display = None
            return
        log_path = str(self.sim_log_path)
        log_display = getattr(self, 'log_display', None)
        if os.path.exists(log_path) and log_display is not None:
            N = 200
            lines = []
            with open(log_path, 'rb') as f:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                block_size = 4096
                data = b''
                n_lines = 0
                while file_size > 0 and n_lines < N:
                    read_size = min(block_size, file_size)
                    f.seek(file_size - read_size)
                    data = f.read(read_size) + data
                    file_size -= read_size
                    n_lines = data.count(b'\n')
                lines = data.decode(errors='replace').splitlines()[-N:]
            self._debug_count = 0
            self._info_count = 0
            self._warning_count = 0
            self._error_count = 0
            self._critical_count = 0
            try:
                log_display.clear()
            except RuntimeError:
                self.log_display = None
                return
            import re, ast
            for line in lines:
                # Log coloring and counters
                if '[DEBUG]' in line:
                    color = '#7ecfff'
                    self._debug_count += 1
                elif '[INFO]' in line:
                    color = '#b3ff7e'
                    self._info_count += 1
                elif '[WARNING]' in line:
                    color = '#ffe97e'
                    self._warning_count += 1
                elif '[ERROR]' in line:
                    color = '#ffb37e'
                    self._error_count += 1
                elif '[CRITICAL]' in line:
                    color = '#ff7e7e'
                    self._critical_count += 1
                else:
                    color = '#f0f0f0'
                try:
                    log_display.append(f'<span style="font-family:monospace;color:{color}">{line.rstrip()}</span>')
                except RuntimeError:
                    self.log_display = None
                    return
                # --- Area data extraction for live plot ---
                m = re.match(r"\[t=(\d+)] \[INFO] \((BATTERY|CLOCK)\): (\{.*\})", line)
                if m:
                    timestamp = int(m.group(1))
                    area = m.group(2)
                    if self.subscribed_areas.get(area, False):
                        try:
                            data_dict = ast.literal_eval(m.group(3))
                            if area == "BATTERY":
                                value = data_dict.get("level")
                            elif area == "CLOCK":
                                value = data_dict.get("tick")
                            else:
                                value = None
                            if value is not None:
                                self.data_buffer.setdefault(area, []).append((timestamp, value))
                        except Exception:
                            pass
            self.counter_debug.setText(f"DEBUG: {self._debug_count}")
            self.counter_info.setText(f"INFO: {self._info_count}")
            self.counter_warning.setText(f"WARNING: {self._warning_count}")
            self.counter_error.setText(f"ERROR: {self._error_count}")
            self.counter_critical.setText(f"CRITICAL: {self._critical_count}")
            try:
                log_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            except RuntimeError:
                self.log_display = None
                return
            self._update_plot()
    def _update_plot(self):
        # Live update matplotlib plot for subscribed areas
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        plotted = False
        for area, enabled in self.subscribed_areas.items():
            if enabled and self.data_buffer.get(area):
                # Remove duplicate timestamps (keep last value for each timestamp)
                seen = {}
                for t, v in self.data_buffer[area]:
                    seen[t] = v
                x, y = zip(*sorted(seen.items())) if seen else ([], [])
                if x and y:
                    ax.plot(x, y, label=area)
                    plotted = True
        ax.set_xlabel("Time")
        ax.set_ylabel("Value")
        ax.set_title("Live Data Plot")
        if plotted:
            ax.legend()
        self.canvas.draw()
    def handle_run(self):
        # Do not force scroll; allow user to control cursor position
        time_str = self.time_input.text().strip()
        if time_str.isdigit():
            self.engine.run_for(int(time_str))
        else:
            self.engine.run()

    def handle_pause(self):
        self.engine.pause()

    def handle_stop(self):
        self.engine.stop()

def main():    
    app = QApplication(sys.argv)
    gui = SimulatorGUI()
    gui.resize(600, 400)
    gui.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
