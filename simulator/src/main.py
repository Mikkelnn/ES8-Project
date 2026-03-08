from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTextEdit, QPushButton, QComboBox, QSizePolicy, QCheckBox, QScrollArea, QGridLayout, QSpinBox, QLabel
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt, QTimer
from custom_types import Severity, Area, SimState
from simulator.engine import Engine
from simulator.global_time import GlobalTime
import multiprocessing
import datetime
import sys

class GUI(QMainWindow):

    def collect_input_state(self):
        """Collect all input state for engine setup."""
        # Check if any time field is > 0
        hours = self.left_bottom_hours_input.value()
        minutes = self.left_bottom_minutes_input.value()
        seconds = self.left_bottom_seconds_input.value()
        until_time = hours > 0 or minutes > 0 or seconds > 0
        run_duration = None
        if until_time:
            run_duration = hours * 3600 + minutes * 60 + seconds  # seconds
        severity = self.left_bottom_severity_dropdown.currentData()
        areas = [cb.text() for cb in self.right_area_checkboxes if cb.isChecked()]
        return {
            'until_time': until_time,
            'run_duration': run_duration,
            'severity': severity,
            'areas': areas
        }

    def lock_inputs(self, locked=True):
        """Lock or unlock all input widgets except control buttons, and shade them when locked."""
        widgets = [
            self.left_bottom_hours_input,
            self.left_bottom_minutes_input,
            self.left_bottom_seconds_input,
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

    def create_new_engine(self):
        """Create a NEW engine for a fresh simulation."""
        self.engine = Engine()
        self._sim_state = SimState.STOPPED
        self._latest_tick = 0
        self._target_tick = None

    def refresh_log_display(self):
        logs = self.engine.get_log(lines=100)
        chosen_severity = self.left_bottom_severity_dropdown.currentData()
        chosen_areas = [cb.text() for cb in self.right_area_checkboxes if cb.isChecked()]

        # Get current tick directly from engine (no log parsing needed)
        self._latest_tick = self.engine.get_current_tick()

        # Filter logs for display
        filtered_logs = []
        for log in logs:
            if log.startswith(f"[{chosen_severity}]"):
                start = log.find('(')
                end = log.find(')')
                if start != -1 and end != -1:
                    area = log[start+1:end]
                    if area in chosen_areas:
                        filtered_logs.append(log)
        # Rolling window: always show last 100 filtered logs, never empty
        if len(filtered_logs) < 100:
            # Fill up with older logs if available
            all_logs = self.engine.get_log(lines=1000)
            extra = []
            for log in reversed(all_logs):
                if log not in filtered_logs and log.startswith(f"[{chosen_severity}]"):
                    start = log.find('(')
                    end = log.find(')')
                    if start != -1 and end != -1:
                        area = log[start+1:end]
                        if area in chosen_areas:
                            extra.append(log)
                if len(filtered_logs) + len(extra) >= 100:
                    break
            filtered_logs = extra[::-1] + filtered_logs
        filtered_logs = filtered_logs[-100:]
        # If still empty, show last 100 logs regardless of filter
        if not filtered_logs:
            logs = self.engine.get_log(lines=100)
            self.left_top.setPlainText(''.join(logs))
        else:
            self.left_top.setPlainText(''.join(filtered_logs))

        self.engine.log.flush(force=True)

        # Auto-pause when target tick is reached
        if (self._sim_state == SimState.RUNNING and
            self._target_tick is not None and
            self._latest_tick >= self._target_tick):
            self.pause_engine()
            self.est_time_label.setText(f"Target reached at {self._latest_tick} ticks. Paused. Press START/CONTINUE to continue or STOP to reset.")


    def update_est_time_label(self):
        # Initialize EWMA state and history
        if not hasattr(self, '_ewma_tps'):
            self._ewma_tps = None

        # Check if any time field is > 0
        hours = self.left_bottom_hours_input.value()
        minutes = self.left_bottom_minutes_input.value()
        seconds = self.left_bottom_seconds_input.value()
        until_time = hours > 0 or minutes > 0 or seconds > 0

        tps = self.engine.get_tps()
        latest_tick = getattr(self, '_latest_tick', None)

        # EWMA smoothing (alpha=0.3 gives weight to current and history)
        alpha = 0.3
        if self._ewma_tps is None or self._ewma_tps == 0:
            # Initialize with current TPS
            self._ewma_tps = tps if tps > 0 else 0.0
        else:
            # Apply EWMA only if tps is valid
            if tps > 0:
                self._ewma_tps = alpha * tps + (1 - alpha) * self._ewma_tps

        if until_time and hasattr(self, '_target_tick') and self._target_tick is not None:
            # Calculate progress based on delta from start_tick to target_tick
            start_tick = getattr(self, '_start_tick', 0)
            current_tick = latest_tick if latest_tick is not None else start_tick
            total_delta = self._target_tick - start_tick
            progress_delta = current_tick - start_tick

            progress_pct = min(100, int((progress_delta / total_delta * 100))) if total_delta > 0 else 0
            progress_bar = "█" * (progress_pct // 5) + "░" * (20 - progress_pct // 5)

            # Only update ETA when running (not paused)
            if self._sim_state == SimState.RUNNING:
                # Estimate completion time based on EWMA TPS
                remaining_ticks = max(0, self._target_tick - current_tick)
                remaining_seconds = remaining_ticks / self._ewma_tps if self._ewma_tps > 0 else 0
                est_completion = datetime.datetime.now() + datetime.timedelta(seconds=remaining_seconds)
                self._frozen_eta = est_completion.strftime('%Y-%m-%d %H:%M:%S')

            # Display frozen ETA if paused, otherwise current calculation
            eta_str = getattr(self, '_frozen_eta', '----')
            self.est_time_label.setText(
                f"ETA: {eta_str} (TPS: {self._ewma_tps:.1f}) [{progress_bar}] {progress_pct}%"
            )
        else:
            self.est_time_label.setText(f"TPS: {self._ewma_tps:.1f}")

    def start_engine(self):
        """Start new simulation or continue paused one."""
        state = self.collect_input_state()

        # Determine if we should start fresh or continue
        if self._sim_state == SimState.PAUSED:
            # CONTINUE from pause
            self.lock_inputs(True)
            self._sim_state = SimState.RUNNING

            # Calculate target tick if "run until" is set (add delta to current tick)
            if state['until_time']:
                gt = GlobalTime()
                delta_ticks = int(state['run_duration'] / gt.tick_pr_time_unit) if state['run_duration'] else 0
                current_tick = self.engine.get_current_tick()
                self._start_tick = current_tick
                self._target_tick = current_tick + delta_ticks
            else:
                self._target_tick = None
                self._start_tick = None

            # Resume the existing simulation
            self.engine.start_continue()
        else:
            # START NEW simulation
            self.lock_inputs(True)
            self.create_new_engine()
            self._sim_state = SimState.RUNNING
            self._latest_tick = 0

            # Calculate target tick if "run until" is set (add delta from tick 0)
            if state['until_time']:
                gt = GlobalTime()
                delta_ticks = int(state['run_duration'] / gt.tick_pr_time_unit) if state['run_duration'] else 0
                self._start_tick = 0
                self._target_tick = delta_ticks
            else:
                self._target_tick = None
                self._start_tick = None

            # Always start without run_ticks limit - let GUI handle pausing at target
            self.engine.start_continue()

        self.refresh_log_display()

    def pause_engine(self):
        """Pause current simulation - can be continued later."""
        if self._sim_state == SimState.RUNNING:
            self.engine.pause()
            self._sim_state = SimState.PAUSED
            self.unlock_inputs()
            self.refresh_log_display()

    def stop_engine(self):
        """Stop current simulation - next start will be a NEW simulation."""
        if self._sim_state in (SimState.RUNNING, SimState.PAUSED):
            self.engine.stop()
            self._sim_state = SimState.STOPPED
            self._latest_tick = 0
            self._target_tick = None
            self.unlock_inputs()
            self.refresh_log_display()

    def __init__(self):
        # Ensure QApplication is constructed before any QWidget
        if QApplication.instance() is None:
            self._app = QApplication(sys.argv)
        else:
            self._app = QApplication.instance()
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
        # Initialize engine and state before any UI updates
        self.engine = Engine()
        self._sim_state = SimState.STOPPED
        self._latest_tick = 0
        self._target_tick = None
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)

        # Main horizontal splitter
        splitter = QSplitter(Qt.Vertical)

        # Top: two split panes (left and right)
        top_splitter = QSplitter(Qt.Horizontal)
        self.left_top = QTextEdit()
        self.right_top = QTextEdit()
        top_splitter.addWidget(self.left_top)
        top_splitter.addWidget(self.right_top)
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

        # Relative duration input (hours/minutes/seconds)
        hours_input = QSpinBox()
        hours_input.setRange(0, 999)
        hours_input.setPrefix("Hours: ")
        hours_input.setMinimumHeight(28)
        minutes_input = QSpinBox()
        minutes_input.setRange(0, 59)
        minutes_input.setPrefix("Min: ")
        minutes_input.setMinimumHeight(28)
        seconds_input = QSpinBox()
        seconds_input.setRange(0, 59)
        seconds_input.setPrefix("Sec: ")
        seconds_input.setMinimumHeight(28)

        # Severity dropdown
        dropdown = QComboBox()
        for sev in Severity:
            dropdown.addItem(sev.name, sev.value)

        # Estimated real time label
        est_time_label = QLabel("Est: 0000-00-00 00:00:00")
        est_time_label.setMinimumHeight(28)

        # Add duration inputs, severity, and est time label (no area checkboxes here)
        for w in (hours_input, minutes_input, seconds_input, dropdown, est_time_label):
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            input_row.addWidget(w)
        controls_layout.addLayout(input_row)
        button_row = QHBoxLayout()
        button_row.setAlignment(Qt.AlignLeft)
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
        area_checkboxes = []
        max_columns = 4  # Adjust for how many checkboxes per row
        for idx, area in enumerate(Area):
            cb = QCheckBox(area.value)
            cb.setChecked(True)
            area_checkboxes.append(cb)
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
        self.left_bottom_inputs = []
        self.left_bottom_dropdown = dropdown
        self.right_area_checkboxes = area_checkboxes
        self.left_bottom_hours_input = hours_input
        self.left_bottom_minutes_input = minutes_input
        self.left_bottom_seconds_input = seconds_input
        self.left_bottom_severity_dropdown = dropdown
        self.est_time_label = est_time_label

        # Engine integration: connect buttons
        btn1.clicked.connect(self.start_engine)
        btn2.clicked.connect(self.pause_engine)
        btn3.clicked.connect(self.stop_engine)

        # Update estimated real time when duration changes
        hours_input.valueChanged.connect(self.update_est_time_label)
        minutes_input.valueChanged.connect(self.update_est_time_label)
        seconds_input.valueChanged.connect(self.update_est_time_label)
        self.update_est_time_label()

        # Timer to refresh log display and est every second
        self.log_refresh_timer = QTimer(self)
        self.log_refresh_timer.timeout.connect(self.refresh_log_display)
        self.log_refresh_timer.timeout.connect(self.update_est_time_label)
        self.log_refresh_timer.start(1000)

    @staticmethod
    def run():
        # Ensure QApplication is constructed before any QWidget
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
    gui = GUI()
    gui.run()