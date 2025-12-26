"""
System resource monitoring for benchmark runs.
"""

import psutil
import threading
import time
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


class ResourceMonitor:
    """
    Monitor system resources (CPU, memory, etc.) during benchmark runs.
    """

    def __init__(self, interval: float = 1.0):
        """
        Initialize resource monitor.

        Args:
            interval: Sampling interval in seconds
        """
        self.interval = interval
        self.running = False
        self.data: List[Dict[str, Any]] = []
        self.thread = None

    def start(self):
        """Start monitoring in background thread."""
        self.running = True
        self.data = []
        self.thread = threading.Thread(target=self._collect, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop monitoring."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _collect(self):
        """Collect resource metrics."""
        process = psutil.Process()

        while self.running:
            try:
                # Get system-wide metrics
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()

                # Get process-specific metrics
                process_cpu = process.cpu_percent()
                process_memory = process.memory_info()

                self.data.append({
                    "timestamp": datetime.now().isoformat(),
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_used_mb": memory.used / 1024 / 1024,
                    "memory_available_mb": memory.available / 1024 / 1024,
                    "process_cpu_percent": process_cpu,
                    "process_memory_mb": process_memory.rss / 1024 / 1024,
                    "process_threads": process.num_threads(),
                })

                time.sleep(self.interval)
            except Exception as e:
                print(f"Error collecting metrics: {e}")
                break

    def save(self, filepath: Path):
        """Save collected data to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.data, f, indent=2)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of collected data."""
        if not self.data:
            return {}

        import numpy as np

        cpu_values = [d["cpu_percent"] for d in self.data]
        memory_values = [d["memory_used_mb"] for d in self.data]

        return {
            "duration_seconds": len(self.data) * self.interval,
            "samples": len(self.data),
            "cpu": {
                "avg": np.mean(cpu_values),
                "max": np.max(cpu_values),
                "min": np.min(cpu_values),
                "p95": np.percentile(cpu_values, 95),
            },
            "memory_mb": {
                "avg": np.mean(memory_values),
                "max": np.max(memory_values),
                "min": np.min(memory_values),
                "p95": np.percentile(memory_values, 95),
            },
        }
