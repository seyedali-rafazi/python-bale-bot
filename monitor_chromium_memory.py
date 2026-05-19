#!/usr/bin/env python3
"""
Monitor Chromium browser process memory usage and count.
Helps verify the RAM optimization is working.
"""

import subprocess
import time
from datetime import datetime
from collections import deque
import sys

def get_chromium_processes():
    """Get all Chromium processes and their memory usage."""
    try:
        # Get process info
        cmd = "ps aux | grep chromium | grep -v grep"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        lines = result.stdout.strip().split('\n')
        lines = [l for l in lines if l.strip()]  # Remove empty lines
        
        processes = []
        total_memory = 0
        
        for line in lines:
            parts = line.split()
            if len(parts) >= 6:
                pid = parts[1]
                memory_mb = int(parts[5]) / 1024  # Convert KB to MB
                command = ' '.join(parts[10:13]) if len(parts) > 10 else 'unknown'
                
                processes.append({
                    'pid': pid,
                    'memory_mb': memory_mb,
                    'command': command,
                })
                total_memory += memory_mb
        
        return processes, total_memory
    
    except Exception as e:
        print(f"Error: {e}")
        return [], 0

def get_system_memory():
    """Get system memory usage."""
    try:
        cmd = "free -m | grep Mem"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        parts = result.stdout.split()
        
        if len(parts) >= 3:
            total = int(parts[1])
            used = int(parts[2])
            available = int(parts[6])
            percent = (used / total) * 100
            
            return {
                'total': total,
                'used': used,
                'available': available,
                'percent': percent,
            }
    except Exception as e:
        print(f"Error: {e}")
    
    return None

def print_header():
    """Print monitoring header."""
    print("\n" + "="*80)
    print(f"Chromium Memory Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

def print_metrics():
    """Print current metrics."""
    processes, chromium_total = get_chromium_processes()
    sys_memory = get_system_memory()
    
    print_header()
    
    # System memory
    if sys_memory:
        print(f"\n📊 System Memory:")
        print(f"   Total: {sys_memory['total']:,} MB")
        print(f"   Used:  {sys_memory['used']:,} MB")
        print(f"   Available: {sys_memory['available']:,} MB")
        print(f"   Usage: {sys_memory['percent']:.1f}%")
    
    # Chromium processes
    print(f"\n🔶 Chromium Processes: {len(processes)}")
    print(f"   Total Memory: {chromium_total:.1f} MB")
    print(f"   Avg per Process: {chromium_total/len(processes):.1f} MB" if processes else "   (None running)")
    
    if processes:
        print(f"\n   PID      Memory (MB)")
        print(f"   {'─'*20}")
        for proc in sorted(processes, key=lambda x: x['memory_mb'], reverse=True):
            print(f"   {proc['pid']:8} {proc['memory_mb']:>10.1f}")
    
    # Status
    print(f"\n✅ Status:")
    if len(processes) <= 2:
        print(f"   ✓ Chromium processes within expected range (≤2)")
    else:
        print(f"   ⚠ WARNING: {len(processes)} Chromium processes (expected ≤2)")
    
    if chromium_total < 800:
        print(f"   ✓ Memory usage good (<800 MB)")
    elif chromium_total < 1500:
        print(f"   ⚠ Memory usage moderate (800-1500 MB)")
    else:
        print(f"   ✗ Memory usage HIGH (>1500 MB)")

def main():
    """Main monitoring loop."""
    interval = 30  # Check every 30 seconds
    max_samples = 120  # Keep last 2 hours of data
    
    history = deque(maxlen=max_samples)
    
    print("\n🚀 Starting Chromium Memory Monitor")
    print(f"📍 Updating every {interval} seconds")
    print(f"🎯 Press Ctrl+C to stop\n")
    
    try:
        while True:
            processes, chromium_total = get_chromium_processes()
            history.append(chromium_total)
            
            print_metrics()
            
            if len(history) > 1:
                avg = sum(history) / len(history)
                max_val = max(history)
                min_val = min(history)
                
                print(f"\n📈 Historical Stats (last {len(history)} samples):")
                print(f"   Average: {avg:.1f} MB")
                print(f"   Max: {max_val:.1f} MB")
                print(f"   Min: {min_val:.1f} MB")
                print(f"   Trend: {'↑ Increasing' if history[-1] > avg else '↓ Decreasing' if history[-1] < avg else '→ Stable'}")
            
            time.sleep(interval)
    
    except KeyboardInterrupt:
        print("\n\n✅ Monitor stopped")
        if history:
            print(f"\nSummary:")
            print(f"  Average Memory: {sum(history)/len(history):.1f} MB")
            print(f"  Peak Memory: {max(history):.1f} MB")
            print(f"  Minimum Memory: {min(history):.1f} MB")

if __name__ == '__main__':
    main()
