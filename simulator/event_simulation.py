#!/usr/bin/env python3
"""
Simulation script for 50 scheduled events.
Records local time, global time, next scheduled event times, and clock trend.
"""

import sys
import csv
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from logger.simple_logger import SimpleLogger
from medium.medium_service import MediumService
from node.node import Node


class DummyMediumService:
    """Minimal medium service for standalone simulation."""
    def transmit(self, *args, **kwargs):
        pass
    
    def cancel_transmission(self, *args, **kwargs):
        pass
    
    def receive(self, *args, **kwargs):
        return []


def run_simulation(num_events: int = 50, event_interval_local: int = 5000) -> None:
    """
    Run a simulation with scheduled events based on local time intervals.
    Clock drift accumulates, showing how local time intervals map to global time.
    
    Args:
        num_events: Number of events to record (default 50)
        event_interval_local: Local time interval between events in ms (default 5000)
    """
    # Setup
    second_to_global_tick = 0.001
    log_file = Path(__file__).parent / "event_simulation.log"
    logger = SimpleLogger(str(log_file))
    medium_service = DummyMediumService()
    
    # Create a single node
    node_id = 0
    node = Node(node_id, second_to_global_tick, medium_service, logger)
    
    # Prepare CSV output
    output_file = Path(__file__).parent / "event_simulation_results.csv"
    
    # Data collection
    events_recorded = []
    current_event_index = 0
    current_global_tick = 0
    
    # Get initial trend value
    initial_trend = node.clock.trend
    
    print(f"Starting simulation with {num_events} events...")
    print(f"Local time interval between events: {event_interval_local} ms")
    print(f"Initial clock trend: {initial_trend:.2e}")
    print()
    
    # Schedule first event at global tick 0
    next_event_local_time = event_interval_local  # First event is at local_interval ms
    predicted_next_global_time = None  # Will be set after first event
    
    # Run simulation
    while current_event_index < num_events:
        # Tick the node
        node.tick(current_global_tick)
        
        # Check if local time has reached the next scheduled event
        if node.clock.localtime >= next_event_local_time:
            # Record the event
            current_local_time = node.clock.localtime
            # Use the predicted time from last event, or actual global time for first event
            if predicted_next_global_time is not None:
                current_global_time = int(predicted_next_global_time)
            else:
                current_global_time = current_global_tick
            current_trend = node.clock.trend
            
            # Calculate next scheduled local time
            next_local_time_scheduled = next_event_local_time + event_interval_local
            
            # Calculate expected global time to next event
            # The next event should occur when local time = next_local_time_scheduled
            # We need to estimate how many global ticks until that happens
            if current_event_index < num_events - 1:
                time_diff_local = next_local_time_scheduled - current_local_time
                rate = 1 + node.clock.alpha + current_trend
                expected_global_ticks = time_diff_local / rate if rate > 0 else 0
                calculated_next_global_time = current_global_time + expected_global_ticks
                predicted_next_global_time = calculated_next_global_time
            else:
                next_local_time_scheduled = "N/A"
                calculated_next_global_time = "N/A"
                predicted_next_global_time = None
            
            # Record event
            event_data = {
                "event_number": current_event_index + 1,
                "scheduled_local_time": next_event_local_time,
                "actual_local_time": current_local_time,
                "actual_global_time": current_global_time,
                "next_scheduled_local_time": next_local_time_scheduled,
                "calculated_next_global_time": calculated_next_global_time,
                "trend": current_trend,
                "alpha": node.clock.alpha,
            }
            events_recorded.append(event_data)
            current_event_index += 1
            
            # Update next event time
            next_event_local_time = next_local_time_scheduled
            
            print(f"Event {current_event_index}/{num_events}")
            print(f"  Local time: {current_local_time} ms, Global time: {current_global_time}")
            print(f"  Drift from perfect: {current_global_time - (current_event_index * event_interval_local):.2f} ms")
            print(f"  Next scheduled local: {next_local_time_scheduled}, Est. global: {calculated_next_global_time}")
            print()
        
        current_global_tick += 1
        
        # Safety limit to prevent infinite loops (very generous for long simulations)
        if current_global_tick > 50000000:  # ~50M ticks for very long simulations
            print("Warning: Reached maximum simulation time!")
            break
    
    # Write results to CSV
    write_csv_results(output_file, events_recorded, initial_trend)
    print(f"\nSimulation complete! Results written to: {output_file}")


def write_csv_results(output_file: Path, events: list, trend: float) -> None:
    """
    Write event data to CSV file.
    
    Args:
        output_file: Path to output CSV file
        events: List of event dictionaries
        trend: Clock trend value for header
    """
    if not events:
        print("No events recorded!")
        return
    
    with open(output_file, 'w', newline='') as f:
        # Write header with trend info
        f.write(f"# Simulation Results - Initial Trend: {trend:.2e}\n")
        
        # Define fieldnames
        fieldnames = [
            "event_number",
            "scheduled_local_time",
            "actual_local_time",
            "actual_global_time",
            "next_scheduled_local_time",
            "calculated_next_global_time",
            "trend",
            "alpha",
        ]
        
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)
    
    print(f"Wrote {len(events)} events to CSV")


if __name__ == "__main__":
    run_simulation(num_events=50, event_interval_local=50000)
