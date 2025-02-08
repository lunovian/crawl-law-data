import psutil
import time
from datetime import datetime
import os
import json
from collections import defaultdict
import signal

class ProcessMonitor:
    def __init__(self):
        self.stats = defaultdict(list)
        self.start_time = datetime.now()
        self.stop_monitoring = False
        
    def handle_stop(self, signum, frame):
        """Handle stop signal"""
        self.stop_monitoring = True
        
    def get_process_stats(self):
        """Get stats for all Python processes"""
        python_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                if 'python' in proc.info['name'].lower():
                    proc.cpu_percent()  # First call to initialize CPU monitoring
                    python_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return python_processes

    def monitor(self, duration=60, interval=1):
        """Monitor process performance for specified duration"""
        # Set up signal handler for this process
        signal.signal(signal.SIGTERM, self.handle_stop)
        signal.signal(signal.SIGINT, self.handle_stop)
        
        processes = self.get_process_stats()
        end_time = time.time() + duration
        
        print("\nMonitoring process performance...")
        print(f"Found {len(processes)} Python processes")
        
        while time.time() < end_time and not self.stop_monitoring:
            timestamp = datetime.now()
            for proc in processes:
                try:
                    with proc.oneshot():
                        cpu = proc.cpu_percent()
                        mem = proc.memory_percent()
                        threads = proc.num_threads()
                        
                        self.stats[proc.pid].append({
                            'timestamp': timestamp,
                            'cpu': cpu,
                            'memory': mem,
                            'threads': threads
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            try:
                time.sleep(interval)
            except (KeyboardInterrupt, SystemExit):
                break
        
        self.save_report()
        self.print_summary()

    def save_report(self):
        """Save monitoring results to file"""
        report = {
            'start_time': self.start_time.isoformat(),
            'end_time': datetime.now().isoformat(),
            'process_stats': {str(pid): stats for pid, stats in self.stats.items()}
        }
        
        with open('performance_report.json', 'w') as f:
            json.dump(report, f, indent=2)

    def print_summary(self):
        """Print performance summary"""
        print("\nPerformance Summary:")
        for pid, measurements in self.stats.items():
            if not measurements:
                continue
                
            avg_cpu = sum(m['cpu'] for m in measurements) / len(measurements)
            avg_mem = sum(m['memory'] for m in measurements) / len(measurements)
            avg_threads = sum(m['threads'] for m in measurements) / len(measurements)
            
            print(f"\nProcess {pid}:")
            print(f"  Average CPU: {avg_cpu:.1f}%")
            print(f"  Average Memory: {avg_mem:.1f}%")
            print(f"  Average Threads: {avg_threads:.1f}")
            print(f"  Measurements: {len(measurements)}")

def main():
    monitor = ProcessMonitor()
    try:
        monitor.monitor(duration=300)  # Monitor for 5 minutes
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
        monitor.save_report()
        monitor.print_summary()

if __name__ == "__main__":
    main()
