#!/usr/bin/env python3
"""
Main benchmark orchestration script.

Usage:
    python run_benchmark.py --target sync --scenario realistic --users 300 --duration 10m
    python run_benchmark.py --target async_native --scenario concurrent_read --users 500 --duration 10m
    python run_benchmark.py --compare  # Run both sync and async for comparison
"""

import subprocess
import json
import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitoring.resource_monitor import ResourceMonitor


class BenchmarkRunner:
    """Orchestrates benchmark execution and result collection."""

    def __init__(self, target: str):
        """
        Initialize benchmark runner.

        Args:
            target: 'sync' or 'async_native'
        """
        self.target = target
        self.benchmarks_dir = Path(__file__).parent.parent
        self.results_dir = self.benchmarks_dir / "results"
        self.results_dir.mkdir(exist_ok=True)

    def run_scenario(
        self,
        scenario: str,
        users: int,
        duration: str,
        spawn_rate: int
    ) -> Path:
        """
        Run a single benchmark scenario.

        Args:
            scenario: Scenario name (e.g., 'realistic', 'concurrent_read')
            users: Number of concurrent users
            duration: Test duration (e.g., '10m', '5m')
            spawn_rate: Users spawned per second

        Returns:
            Path to results directory
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = self.results_dir / f"{self.target}_{scenario}_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine API host based on target
        api_host = f"http://localhost:{'8000' if self.target == 'sync' else '8001'}"

        print(f"\n{'='*60}")
        print(f"Running {scenario} - {self.target.upper()}")
        print(f"Users: {users}, Duration: {duration}, Spawn Rate: {spawn_rate}/s")
        print(f"API Host: {api_host}")
        print(f"Results: {output_dir}")
        print(f"{'='*60}\n")

        # Start resource monitoring
        monitor = ResourceMonitor(interval=1.0)
        monitor.start()

        # Run Locust in headless mode
        cmd = [
            "locust",
            "-f", str(self.benchmarks_dir / "load_tests" / "scenarios" / f"{scenario}.py"),
            "--headless",
            "--users", str(users),
            "--spawn-rate", str(spawn_rate),
            "--run-time", duration,
            "--html", str(output_dir / "report.html"),
            "--csv", str(output_dir / "results"),
            "--host", api_host,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)

            # Save output
            with open(output_dir / "stdout.log", "w") as f:
                f.write(result.stdout)
            with open(output_dir / "stderr.log", "w") as f:
                f.write(result.stderr)

        except Exception as e:
            print(f"Error running Locust: {e}")
        finally:
            # Stop monitoring and save results
            monitor.stop()
            monitor.save(output_dir / "resources.json")

        # Save metadata
        metadata = {
            "target": self.target,
            "scenario": scenario,
            "timestamp": timestamp,
            "config": {
                "users": users,
                "duration": duration,
                "spawn_rate": spawn_rate,
                "api_host": api_host,
            },
            "exit_code": result.returncode if "result" in locals() else -1,
            "resource_summary": monitor.get_summary(),
        }

        with open(output_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        print(f"\nResults saved to: {output_dir}")
        return output_dir

    def run_comparison(self):
        """Run both sync and async benchmarks for comparison."""
        scenarios = [
            ("realistic", 300, "10m", 15),
            ("concurrent_read", 500, "10m", 20),
        ]

        results = {"sync": [], "async_native": []}

        # Run sync benchmarks
        self.target = "sync"
        for scenario, users, duration, spawn_rate in scenarios:
            result_dir = self.run_scenario(scenario, users, duration, spawn_rate)
            results["sync"].append(result_dir)

        # Run async benchmarks
        self.target = "async_native"
        for scenario, users, duration, spawn_rate in scenarios:
            result_dir = self.run_scenario(scenario, users, duration, spawn_rate)
            results["async_native"].append(result_dir)

        print(f"\n{'='*60}")
        print("Comparison Complete!")
        print(f"{'='*60}")
        print("\nSync Results:")
        for r in results["sync"]:
            print(f"  - {r}")
        print("\nAsync Results:")
        for r in results["async_native"]:
            print(f"  - {r}")

        return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run MongoEngine benchmarks")
    parser.add_argument("--target", choices=["sync", "async_native"], help="Benchmark target")
    parser.add_argument("--scenario", default="realistic", help="Scenario name")
    parser.add_argument("--users", type=int, default=300, help="Number of concurrent users")
    parser.add_argument("--duration", default="10m", help="Test duration (e.g., 5m, 10m)")
    parser.add_argument("--spawn-rate", type=int, default=15, help="Users spawned per second")
    parser.add_argument("--compare", action="store_true", help="Run comparison between sync and async")

    args = parser.parse_args()

    if args.compare:
        runner = BenchmarkRunner("sync")  # Will be changed internally
        runner.run_comparison()
    elif args.target:
        runner = BenchmarkRunner(args.target)
        runner.run_scenario(
            args.scenario,
            args.users,
            args.duration,
            args.spawn_rate
        )
    else:
        parser.error("Either --target or --compare must be specified")


if __name__ == "__main__":
    main()
