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
from simulator.logger import Logger

from PySide6.QtCore import QThread, Signal, QObject

class PlotWorker(QObject):
    finished = Signal(dict, dict)
    def __init__(self, data_buffer, subscribed_areas):
        super().__init__()
        self.data_buffer = data_buffer
        self.subscribed_areas = subscribed_areas
    def run(self):
        # Prepare plot data in background
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        label_plots = {}
        label_units = {}
        for area, enabled in self.subscribed_areas.items():
            if enabled and self.data_buffer.get(area):
                for t, v, label, unit in self.data_buffer[area]:
                    label_plots.setdefault(label, []).append((t, v, area))
                    if unit:
                        label_units[label] = unit
        figures = {}
        canvases = {}
        for label, points in label_plots.items():
            fig = Figure(figsize=(5, 3))
            ax = fig.add_subplot(111)
            area_groups = {}
            area_title = None
            for t, v, area in points:
                area_groups.setdefault(area, []).append((t, v))
                area_title = area
            min_time, max_time = None, None
            for area, area_points in area_groups.items():
                x, y = zip(*sorted(area_points)) if area_points else ([], [])
                if x and y:
                    ax.plot(x, y)
                    if min_time is None or min(x) < min_time:
                        min_time = min(x)
                    if max_time is None or max(x) > max_time:
                        max_time = max(x)
            if min_time is not None and max_time is not None:
                ax.set_xlim(min_time, max_time)
            fig.set_size_inches(9, 3)
            fig.subplots_adjust(bottom=0.22)
            ax.set_xlabel("Time [ms]")
            unit = label_units.get(label, None)
            if unit:
                ax.set_ylabel(f"{label} [{unit}]")
            else:
                ax.set_ylabel(f"{label}")
            if area_title:
                ax.set_title(area_title)
            else:
                ax.set_title(label)
            ax.legend(loc='upper right')
            figures[label] = fig
            canvases[label] = FigureCanvas(fig)
        self.finished.emit(figures, canvases)

class SimulatorGUI(QWidget):
    def _auto_export_if_needed(self):
        # Always export after each update
        self._export_csv()
        self._export_svg()

    def closeEvent(self, event):
        # Robustly stop timer and disconnect update_log to prevent post-delete calls
        if hasattr(self, 'timer') and self.timer:
            try:
                self.timer.stop()
                self.timer.timeout.disconnect()
            except Exception:
                pass
        # Only save the log file on close for speed
        try:
            with open(self.sim_log_path, 'w', encoding='utf-8') as f:
                for log in self.logger.get():
                    f.write(str(log) + '\n')
        except Exception:
            pass
        self.log_display = None
        super().closeEvent(event)
    def __init__(self):
        super().__init__()
        self.logger = Logger()
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
        from custom_types import Area
        self.area_enum = Area
        self.subscribed_areas = {area.value: True for area in Area}
        self.data_buffer = {area.value: [] for area in Area}  # {area: [(timestamp, value), ...]}
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
        Logger().set_log_file(str(self.sim_log_path))

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
        area_layout.addWidget(QLabel("Subscribe to:"))
        self.area_checkboxes = {}
        for area in self.area_enum:
            checkbox = QCheckBox(area.value.title())
            checkbox.setChecked(True)
            area_layout.addWidget(checkbox)
            self.area_checkboxes[area.value] = checkbox
            checkbox.stateChanged.connect(self._update_area_subscription)
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
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.pause_btn)
        simulator_layout.addLayout(btn_layout)
        simulator_layout.addWidget(self.status_label)
        # --- Matplotlib live plots ---
        self.figures = {}
        self.canvases = {}
        from PySide6.QtWidgets import QScrollArea
        self.plot_layout = QVBoxLayout()
        self.plot_widget = QWidget()
        self.plot_widget.setLayout(self.plot_layout)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.plot_widget)
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
        # Add plot_widget to results panel
        result_layout.addWidget(self.scroll_area)
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
        # Area checkboxes are connected in _build_ui

    def _update_area_subscription(self):
        for area, checkbox in self.area_checkboxes.items():
            self.subscribed_areas[area] = checkbox.isChecked()

    def showEvent(self, event):
        super().showEvent(event)
        # Start timer only after window is shown
        if not hasattr(self, '_timer_started'):
            self.timer.start(1000)
            self.update_log()
            self._timer_started = True

    def init_ui(self):
        print("init_ui start")

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


    def _export_csv(self):
        # Save only data logs to CSV
        import csv
        with open(self.sim_csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            header = ["timestamp", "area", "label", "data"]
            writer.writerow(header)
            for log in self.logger.get_data():
                writer.writerow([log['sim_time'], log['area'], log['label'], log['data']])

    def _export_svg(self):
        # Save each label's figure to a separate SVG file
        for label, fig in self.figures.items():
            svg_path = os.path.join(os.path.dirname(self.sim_svg_path), f'result_{label}.svg')
            fig.savefig(svg_path, format='svg')

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
        log_display = getattr(self, 'log_display', None)
        if log_display is not None:
            try:
                log_display.clear()
            except RuntimeError:
                self.log_display = None
                return
            # Only show the 40 latest logs for subscribed areas, fast
            all_logs = self.logger.get()
            filtered_logs = []
            count = 0
            for log in reversed(all_logs):
                if log.get('area') in self.subscribed_areas and self.subscribed_areas[log.get('area')]:
                    filtered_logs.append(log)
                    count += 1
                    if count >= 40:
                        break
            latest_logs = list(reversed(filtered_logs))
            # Display logs and update severity counters
            severity_counts = {
                'DEBUG': 0,
                'INFO': 0,
                'WARNING': 0,
                'ERROR': 0,
                'CRITICAL': 0,
            }
            for log in latest_logs:
                if 'severity' in log:
                    sev = log['severity']
                    if sev in severity_counts:
                        severity_counts[sev] += 1
                    color = {
                        'DEBUG': '#7ecfff',
                        'INFO': '#b3ff7e',
                        'WARNING': '#ffe97e',
                        'ERROR': '#ffb37e',
                        'CRITICAL': '#ff7e7e',
                    }.get(sev, '#f0f0f0')
                    log_display.append(f'<span style="font-family:monospace;color:{color}">[t={log["sim_time"]}] [{sev}] ({log["area"]}): {log["msg"]}</span>')
                elif 'label' in log and 'data' in log:
                    log_display.append(f'<span style="font-family:monospace;color:#b3ff7e">[t={log["sim_time"]}] (DATA) ({log["area"]}) [{log["label"]}]: {log["data"]}</span>')
            # Update severity counter labels (only for visible logs)
            self.counter_debug.setText(f"DEBUG: {severity_counts['DEBUG']}")
            self.counter_info.setText(f"INFO: {severity_counts['INFO']}")
            self.counter_warning.setText(f"WARNING: {severity_counts['WARNING']}")
            self.counter_error.setText(f"ERROR: {severity_counts['ERROR']}")
            self.counter_critical.setText(f"CRITICAL: {severity_counts['CRITICAL']}")
            # Only plot and save CSV with data logs
            data_logs = [log for log in self.logger.get_data() if log.get('area') in self.subscribed_areas and self.subscribed_areas[log.get('area')]]
            # Rebuild self.data_buffer from data logs
            self.data_buffer = {area: [] for area in self.subscribed_areas}
            for log in data_logs:
                area = log['area']
                unit = log.get('unit', None)
                if self.subscribed_areas.get(area, False):
                    self.data_buffer[area].append((log['sim_time'], log['data'], log['label'], unit))
            self._auto_export_if_needed()
            self._update_plot()
    def _update_plot(self):
        # Run plot update in a background thread
        if hasattr(self, '_plot_thread') and self._plot_thread is not None:
            try:
                if self._plot_thread.isRunning():
                    return  # Avoid overlapping plot updates
            except RuntimeError:
                self._plot_thread = None
        self._plot_thread = QThread()
        self._plot_worker = PlotWorker(self.data_buffer.copy(), self.subscribed_areas.copy())
        self._plot_worker.moveToThread(self._plot_thread)
        self._plot_thread.started.connect(self._plot_worker.run)
        self._plot_worker.finished.connect(self._on_plot_ready)
        self._plot_worker.finished.connect(self._plot_thread.quit)
        self._plot_worker.finished.connect(self._plot_worker.deleteLater)
        self._plot_thread.finished.connect(self._plot_thread.deleteLater)
        self._plot_thread.finished.connect(self._clear_plot_thread)
        self._plot_thread.start()

    def _clear_plot_thread(self):
        self._plot_thread = None

    def _on_plot_ready(self, figures, canvases):
        # Remove old plots
        for canvas in self.canvases.values():
            self.plot_layout.removeWidget(canvas)
            canvas.setParent(None)
        self.figures.clear()
        self.canvases.clear()
        # Add new plots
        for label, canvas in canvases.items():
            canvas.setFixedSize(900, 300)
            self.plot_layout.addWidget(canvas)
            self.figures[label] = figures[label]
            self.canvases[label] = canvas
        # Mark thread as done
        self._plot_thread = None
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
    import signal
    app = QApplication(sys.argv)
    gui = SimulatorGUI()
    gui.resize(600, 400)
    gui.show()
    # Handle Ctrl+C gracefully: quit app on SIGINT
    def handle_sigint(*args):
        app.quit()
    signal.signal(signal.SIGINT, handle_sigint)
    try:
        sys.exit(app.exec())
    except Exception:
        # Try to save data if simulator fails
        try:
            gui._export_csv()
            gui._export_svg()
        except Exception:
            pass
        raise

if __name__ == "__main__":
    main()
