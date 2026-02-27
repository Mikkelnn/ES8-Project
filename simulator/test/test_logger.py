from simulator.src.simulator.logger import Logger, LoggerClientAsync, LoggerClientSync
from simulator.src.simulator.global_time import time_global
from simulator.src.custom_types import Severity, Area, LogMessage
import time
import asyncio
import pytest
try:
    from rich.table import Table
    from rich.console import Console
except ImportError:
    Table = None
    Console = None

def test_logger_singleton(tmp_path):
    Logger.reset()
    log_path = tmp_path / "singleton.log"
    logger1 = Logger(str(log_path))
    logger2 = Logger(None)
    assert logger1 is logger2, "Logger is not a singleton!"

def test_logger_start_stop(tmp_path):
    Logger.reset()
    log_path = tmp_path / "startstop.log"
    logger = Logger(str(log_path))
    logger.start()
    assert logger._logger_process is not None and logger._logger_process.is_alive()
    logger.stop()
    assert logger._logger_process is None or not logger._logger_process.is_alive()

def test_logger_add_and_basic_logging(tmp_path):
    Logger.reset()
    log_path = tmp_path / "basic.log"
    logger = Logger(str(log_path))
    logger.start()
    msg = LogMessage(time_global().get_time(), Severity.INFO, Area.SIMULATOR, "Basic log entry", data=None)
    logger.add(msg)
    time.sleep(0.2)
    logger.stop()
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    assert any("Basic log entry" in line for line in lines)

@pytest.mark.asyncio
async def test_loggerclientasync_add_and_basic_logging(tmp_path):
    Logger.reset()
    log_path = tmp_path / "client_basic.log"
    logger = Logger(str(log_path))
    logger.start()
    client = LoggerClientAsync(None)
    await client.start()
    msg = LogMessage(time_global().get_time(), Severity.INFO, Area.SIMULATOR, "Client log entry", data=None)
    await client.add(msg)
    await client.stop()
    logger.stop()
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    assert any("Client log entry" in line for line in lines)

@pytest.mark.asyncio
async def test_logger_and_clientasync_together(tmp_path):
    Logger.reset()
    log_path = tmp_path / "together.log"
    logger = Logger(str(log_path))
    logger.start()
    client = LoggerClientAsync(None)
    await client.start()
    msg1 = LogMessage(time_global().get_time(), Severity.INFO, Area.SIMULATOR, "Direct log entry", data=None)
    msg2 = LogMessage(time_global().get_time(), Severity.INFO, Area.SIMULATOR, "Client async entry", data=None)
    logger.add(msg1)
    await client.add(msg2)
    await client.stop()
    logger.stop()
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    assert any("Direct log entry" in line for line in lines)
    assert any("Client async entry" in line for line in lines)

_async_results = None

@pytest.mark.asyncio
async def test_loggerclientasync_performance_benchmark(tmp_path):
    Logger.reset()
    log_path = tmp_path / "async_bench.log"
    logger = Logger(str(log_path))
    logger.start()
    client = LoggerClientAsync(None)
    await client.start()
    num_logs = 1000
    send_times = []
    write_times = []
    start = time.perf_counter_ns()
    for i in range(num_logs):
        msg = LogMessage(time_global().get_time(), Severity.INFO, Area.SIMULATOR, f"Async bench log {i}", data=None)
        t0 = time.perf_counter_ns()
        await client.add(msg)
        t1 = time.perf_counter_ns()
        send_times.append(t1 - t0)
    mid = time.perf_counter_ns()
    await client.stop()
    logger.stop()
    end = time.perf_counter_ns()
    log_write_time = end - mid
    log_enqueue_time = mid - start
    logs_per_sec = num_logs / (log_enqueue_time / 1e9)
    logs_per_ns = num_logs / log_enqueue_time if log_enqueue_time > 0 else 0
    avg_send_delay = sum(send_times) / len(send_times)
    min_send = min(send_times)
    max_send = max(send_times)
    avg_send = avg_send_delay
    async_results = {
        "min_send": min_send,
        "avg_send": avg_send,
        "max_send": max_send,
        "write_min": log_write_time,
        "write_avg": log_write_time,
        "write_max": log_write_time,
        "logs_per_sec": logs_per_sec,
        "logs_per_ns": logs_per_ns
    }
    global _async_results
    _async_results = async_results
    assert logs_per_sec > 1000, "Async LoggerClientAsync enqueue rate is too slow!"
    #assert log_write_time < 5, f"Async LoggerClientAsync write delay is too high! (got {log_write_time:.3f}s)"

def test_logger_performance_benchmark(tmp_path):
    # Bridged (sync-to-async) benchmark (sync client wraps async client)
    Logger.reset()
    log_path_bridged = tmp_path / "bridged_bench.log"
    logger_bridged = Logger(str(log_path_bridged))
    logger_bridged.start()
    client_bridged = LoggerClientSync(None)
    num_logs = 1000
    send_times_bridged = []
    start_bridged = time.perf_counter_ns()
    for i in range(num_logs):
        msg = LogMessage(time_global().get_time(), Severity.INFO, Area.SIMULATOR, f"Bridged bench log {i}", data=None)
        t0 = time.perf_counter_ns()
        client_bridged.add(msg)
        t1 = time.perf_counter_ns()
        send_times_bridged.append(t1 - t0)
    mid_bridged = time.perf_counter_ns()
    client_bridged.stop()
    logger_bridged.stop()
    end_bridged = time.perf_counter_ns()
    log_write_time_bridged = end_bridged - mid_bridged
    log_enqueue_time_bridged = mid_bridged - start_bridged
    logs_per_sec_bridged = num_logs / (log_enqueue_time_bridged / 1e9)
    logs_per_ns_bridged = num_logs / log_enqueue_time_bridged if log_enqueue_time_bridged > 0 else 0
    avg_send_delay_bridged = sum(send_times_bridged) / len(send_times_bridged)
    min_send_bridged = min(send_times_bridged)
    max_send_bridged = max(send_times_bridged)
    avg_send_bridged = avg_send_delay_bridged
    bridged_results = {
        "min_send": min_send_bridged,
        "avg_send": avg_send_bridged,
        "max_send": max_send_bridged,
        "write_min": log_write_time_bridged,
        "write_avg": log_write_time_bridged,
        "write_max": log_write_time_bridged,
        "logs_per_sec": logs_per_sec_bridged,
        "logs_per_ns": logs_per_ns_bridged
    }

    Logger.reset()
    log_path = tmp_path / "sync_bench.log"
    logger = Logger(str(log_path))
    logger.start()
    num_logs = 1000
    send_times = []
    write_times = []
    start = time.perf_counter_ns()
    for i in range(num_logs):
        msg = LogMessage(time_global().get_time(), Severity.INFO, Area.SIMULATOR, f"Sync bench log {i}", data=None)
        t0 = time.perf_counter_ns()
        w0 = time.perf_counter_ns()
        logger.add(msg)
        w1 = time.perf_counter_ns()
        t1 = time.perf_counter_ns()
        send_times.append(t1 - t0)
        write_times.append(w1 - w0)
    mid = time.perf_counter_ns()
    logger.stop()
    end = time.perf_counter_ns()
    log_write_time = end - mid
    log_enqueue_time = mid - start
    logs_per_sec = num_logs / (log_enqueue_time / 1e9)
    logs_per_ns = num_logs / log_enqueue_time if log_enqueue_time > 0 else 0
    avg_send_delay = sum(send_times) / len(send_times)
    min_send = min(send_times)
    max_send = max(send_times)
    avg_send = avg_send_delay
    min_write = min(write_times)
    max_write = max(write_times)
    avg_write = (sum(write_times) / len(write_times))
    sync_results = {
        "min_send": min_send,
        "avg_send": avg_send,
        "max_send": max_send,
        "write_min": min_write,
        "write_avg": avg_write,
        "write_max": max_write,
        "logs_per_sec": logs_per_sec,
        "logs_per_ns": logs_per_ns
    }
    # Print rich table comparing async and sync
    global _async_results
    async_results = _async_results
    if Table is not None and Console is not None:
        table = Table(title="Logger Benchmark: Async vs Sync vs Bridged (all times ns, logs/ns = logs processed per nanosecond)")
        table.add_column("Mode", justify="left")
        table.add_column("Send Min (ns)", justify="right")  # Fastest single log enqueue (client to queue)
        table.add_column("Send Avg (ns)", justify="right")  # Average log enqueue time
        table.add_column("Send Max (ns)", justify="right")  # Slowest single log enqueue
        table.add_column("Write Min (ns)", justify="right") # Fastest write phase (see below)
        table.add_column("Write Avg (ns)", justify="right") # Average write phase (see below)
        table.add_column("Write Max (ns)", justify="right") # Slowest write phase (see below)
        table.add_column("Logs/ns", justify="right")        # Throughput: logs processed per nanosecond
        #
        # Column meanings:
        # Send Min/Avg/Max: min/avg/max time to enqueue a log (client to logger queue)
        # Write Min/Avg/Max: min/avg/max time to flush logs to disk (for async/bridged: total write phase, for sync: per-call)
        # Logs/sec: num_logs / total enqueue time (seconds)
        # Logs/ns: num_logs / total enqueue time (nanoseconds)
        # All times are measured with time.perf_counter_ns() for nanosecond precision.
        def sci(val):
            try:
                return f"{float(val):.2e}"
            except Exception:
                return str(val)
        table.add_row(
            "Async",
            sci(async_results['min_send']) if async_results else "-",
            sci(async_results['avg_send']) if async_results else "-",
            sci(async_results['max_send']) if async_results else "-",
            sci(async_results['write_min']) if async_results else "-",
            sci(async_results['write_avg']) if async_results else "-",
            sci(async_results['write_max']) if async_results else "-",
            sci(async_results['logs_per_ns']) if async_results else "-",
        )
        table.add_row(
            "Sync",
            sci(sync_results['min_send']),
            sci(sync_results['avg_send']),
            sci(sync_results['max_send']),
            sci(sync_results['write_min']),
            sci(sync_results['write_avg']),
            sci(sync_results['write_max']),
            sci(sync_results['logs_per_ns']),
        )
        table.add_row(
            "Bridged",
            sci(bridged_results['min_send']),
            sci(bridged_results['avg_send']),
            sci(bridged_results['max_send']),
            sci(bridged_results['write_min']),
            sci(bridged_results['write_avg']),
            sci(bridged_results['write_max']),
            sci(bridged_results['logs_per_ns']),
        )
        console = Console()
        console.print(table)
    else:
        print("[Logger Benchmark: Async vs Sync vs Bridged]")
        print("rich not installed, skipping table output.")
    assert logs_per_sec > 1000, "Sync Logger enqueue rate is too slow!"
    #assert log_write_time < 5, f"Sync Logger write delay is too high! (got {log_write_time:.3f}s)"

import threading

@pytest.mark.asyncio
async def test_multiple_logger_clients_concurrent(tmp_path):
    """
    Test that multiple Logger, LoggerClientAsync, and LoggerClientSync instances can log concurrently to the same Logger singleton.
    Measures performance for each client type.
    """
    Logger.reset()
    log_path = tmp_path / "multi_clients.log"
    logger = Logger(str(log_path))
    logger.start()

    num_logs = 500
    num_clients = 3
    # Prepare messages
    def make_msg(i, tag):
        return LogMessage(time_global().get_time(), Severity.INFO, Area.SIMULATOR, f"{tag} log {i}", data=None)

    # LoggerClientAsync
    async def async_client_task(idx, results):
        client = LoggerClientAsync(None)
        await client.start()
        send_times = []
        for i in range(num_logs):
            msg = make_msg(i, f"Async{idx}")
            t0 = time.perf_counter_ns()
            await client.add(msg)
            t1 = time.perf_counter_ns()
            send_times.append(t1 - t0)
        await client.stop()
        results[idx] = send_times

    # LoggerClientSync
    def sync_client_task(idx, results):
        client = LoggerClientSync(None)
        send_times = []
        for i in range(num_logs):
            msg = make_msg(i, f"Sync{idx}")
            t0 = time.perf_counter_ns()
            client.add(msg)
            t1 = time.perf_counter_ns()
            send_times.append(t1 - t0)
        results[idx] = send_times

    # Logger direct
    def logger_task(idx, results):
        send_times = []
        for i in range(num_logs):
            msg = make_msg(i, f"Logger{idx}")
            t0 = time.perf_counter_ns()
            logger.add(msg)
            t1 = time.perf_counter_ns()
            send_times.append(t1 - t0)
        results[idx] = send_times

    # Run async clients
    async_results = [{} for _ in range(num_clients)]
    async_tasks = [async_client_task(i, async_results) for i in range(num_clients)]
    await asyncio.gather(*async_tasks)


    # Run sync clients in threads and keep references to clients
    sync_results = [{} for _ in range(num_clients)]
    sync_clients = [LoggerClientSync(None) for _ in range(num_clients)]
    def sync_client_task_with_ref(idx, results, client):
        send_times = []
        for i in range(num_logs):
            msg = make_msg(i, f"Sync{idx}")
            t0 = time.perf_counter_ns()
            client.add(msg)
            t1 = time.perf_counter_ns()
            send_times.append(t1 - t0)
        results[idx] = send_times

    sync_threads = [threading.Thread(target=sync_client_task_with_ref, args=(i, sync_results, sync_clients[i])) for i in range(num_clients)]
    for t in sync_threads:
        t.start()
    for t in sync_threads:
        t.join()
    # Stop all sync clients to flush logs
    for client in sync_clients:
        client.stop()

    # Run logger direct in threads
    logger_results = [{} for _ in range(num_clients)]
    logger_threads = [threading.Thread(target=logger_task, args=(i, logger_results)) for i in range(num_clients)]
    for t in logger_threads:
        t.start()
    for t in logger_threads:
        t.join()

    logger.stop()

    # Check log file for all tags
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.read()
    for idx in range(num_clients):
        assert f"Async{idx} log" in lines
        assert f"Sync{idx} log" in lines
        assert f"Logger{idx} log" in lines

    # Print performance summary
    def perf_stats(times):
        flat = [item for sublist in times for item in sublist]
        return min(flat), sum(flat)/len(flat), max(flat)
    if Table is not None and Console is not None:
        table = Table(title="Multi-Client Logger Performance (ns per log)")
        table.add_column("Client Type")
        table.add_column("Min (ns)")
        table.add_column("Avg (ns)")
        table.add_column("Max (ns)")
        amin, aavg, amax = perf_stats(async_results)
        smin, savg, smax = perf_stats(sync_results)
        lmin, lavg, lmax = perf_stats(logger_results)
        table.add_row("LoggerClientAsync", f"{amin:.2e}", f"{aavg:.2e}", f"{amax:.2e}")
        table.add_row("LoggerClientSync", f"{smin:.2e}", f"{savg:.2e}", f"{smax:.2e}")
        table.add_row("Logger (direct)", f"{lmin:.2e}", f"{lavg:.2e}", f"{lmax:.2e}")
        console = Console()
        console.print(table)
    else:
        print("[Multi-Client Logger Performance]")
        print("LoggerClientAsync:", perf_stats(async_results))
        print("LoggerClientSync:", perf_stats(sync_results))
        print("Logger (direct):", perf_stats(logger_results))