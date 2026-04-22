"""
run_pipeline.py
---------------
Pipeline orchestrator. Place this in the same folder as the other scripts.

Steps
-----
1. Delete any existing node_outputs.json, node_outputs.svg, selected_roads.json
   from the script directory.
2. Launch displayed_gui.py (starts the map GUI server).
3. Watch the script directory for selected_roads.json to appear.
4. Once found, shut down the GUI server and run node_generation.py.

Usage
-----
    python run_pipeline.py

Optional flags
    --host  HOST   GUI server host  (default: 127.0.0.1)
    --port  PORT   GUI server port  (default: 8000)
    --poll  SECS   File-watch poll interval in seconds (default: 1.0)
"""

import argparse
import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# ── Resolve every file relative to THIS script's directory ───────────────────
HERE = Path(__file__).resolve().parent

PROCESSED_ROADS = HERE / "processedRoads.js"

PRE_PROCESS      = HERE / "pre_process.py"
DISPLAYED_GUI    = HERE / "displayed_gui.py"
NODE_GENERATION  = HERE / "node_generation.py"

# Files to delete before starting and to watch for after the GUI runs
FILES_TO_DELETE = [
    HERE / "selected_roads.json",
    HERE / "node_outputs.json",
    HERE / "node_outputs.svg",
]
WATCH_FILE = HERE / "selected_roads.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print(msg: str, prefix: str = "►") -> None:
    print(f"[pipeline] {prefix} {msg}", flush=True)

def step_pre_process():
    """
    Step 0 — run pre_process.py in the foreground and return its exit code.
    """
    if Path(PROCESSED_ROADS).exists():
        return
    
    _print("Running pre_process.py ...")
    result = subprocess.run(
        [sys.executable, str(PRE_PROCESS)],
        check=False,
    )
    if result.returncode == 0:
        _print("pre_process.py completed successfully ✓", prefix="✓")
    else:
        _print(
            f"pre_process.py exited with code {result.returncode}",
            prefix="✗",
        )
    return result.returncode

def step_clean() -> None:
    """Step 1 — delete previous output files."""
    _print("Cleaning previous output files...")
    deleted = []
    for f in FILES_TO_DELETE:
        if f.exists():
            f.unlink()
            deleted.append(f.name)
    if deleted:
        _print(f"Deleted: {', '.join(deleted)}")
    else:
        _print("Nothing to delete — directory already clean.")


def step_gui(host: str, port: int) -> subprocess.Popen:
    """
    Step 2 — launch displayed_gui.py as a subprocess.
    Returns the Popen handle so the caller can shut it down later.
    """
    _print(f"Starting GUI server on http://{host}:{port}/map_generator_gui.html")
    _print("Open the URL in your browser, select roads, then click Save.")

    proc = subprocess.Popen(
        [sys.executable, str(DISPLAYED_GUI), "--host", host, "--port", str(port)],
        # Let the server's own stdout/stderr flow through so the user sees it
        stdout=None,
        stderr=None,
    )
    return proc


def step_watch(poll: float) -> None:
    """
    Step 3 — block until selected_roads.json appears in the script directory.
    Polls every `poll` seconds.
    """
    _print(f"Watching for {WATCH_FILE.name} ... (press Ctrl+C to abort)")
    while not WATCH_FILE.exists():
        time.sleep(poll)
    # Give the GUI server a moment to finish writing the file
    time.sleep(0.5)
    _print(f"{WATCH_FILE.name} detected ✓", prefix="✓")


def step_node_generation() -> int:
    """
    Step 4 — run node_generation.py in the foreground and return its exit code.
    """
    _print("Running node_generation.py ...")
    result = subprocess.run(
        [sys.executable, str(NODE_GENERATION)],
        check=False,
    )
    if result.returncode == 0:
        _print("node_generation.py completed successfully ✓", prefix="✓")
    else:
        _print(
            f"node_generation.py exited with code {result.returncode}",
            prefix="✗",
        )
    return result.returncode


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline: clean → GUI → wait for JSON → generate nodes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host",  default="127.0.0.1", help="GUI server host")
    parser.add_argument("--port",  default=8000, type=int, help="GUI server port")
    parser.add_argument(
        "--poll", default=1.0, type=float,
        help="Seconds between file-existence checks",
    )
    args = parser.parse_args()

    # Verify required scripts exist
    for script in (DISPLAYED_GUI, NODE_GENERATION):
        if not script.exists():
            print(f"[pipeline] ✗ Required script not found: {script}", file=sys.stderr)
            sys.exit(1)

    gui_proc = None
    exit_code = 0

    try:
        # ── Step 0: pre_process ────────────────────────────────────────────────────
        step_pre_process()

        # ── Step 1: clean ────────────────────────────────────────────────────
        step_clean()

        # ── Step 2: start GUI ────────────────────────────────────────────────
        gui_proc = step_gui(args.host, args.port)

        # ── Step 3: wait for selected_roads.json ─────────────────────────────
        step_watch(args.poll)

    except KeyboardInterrupt:
        _print("Aborted by user.", prefix="✗")
        exit_code = 1

    finally:
        # Always shut down the GUI server cleanly
        if gui_proc is not None and gui_proc.poll() is None:
            _print("Shutting down GUI server...")
            # Send SIGTERM (works on all platforms via Popen.terminate())
            gui_proc.terminate()
            try:
                gui_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gui_proc.kill()
            _print("GUI server stopped.")

    if exit_code != 0:
        sys.exit(exit_code)

    # ── Step 4: run node_generation.py ───────────────────────────────────────
    sys.exit(step_node_generation())


if __name__ == "__main__":
    main()
