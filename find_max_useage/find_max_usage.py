#!/usr/bin/env python3
import re
import sys
import os
from collections import defaultdict

CONFIG_TOP_N = 10

def parse_time(value_str):
    try:
        return float(value_str)
    except ValueError:
        return None

def main():
    logs = []
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        with open(sys.argv[1], 'r', encoding='utf-8', errors='ignore') as f:
            logs = f.readlines()
    else:
        logs = sys.stdin.readlines()

    pattern = re.compile(r" took (\d+\.?\d*) seconds")

    results = []
    for line in logs:
        line = line.rstrip('\n')
        match = pattern.search(line)
        if match:
            time_val = parse_time(match.group(1))
            if time_val is not None:
                results.append((time_val, line))

    results.sort(key=lambda x: x[0], reverse=True)

    print(f"Top {CONFIG_TOP_N} slowest operations:")
    for i, (time_val, line) in enumerate(results[:CONFIG_TOP_N], 1):
        print(f"{i}. [{time_val:.2f}s] {line}")

if __name__ == "__main__":
    main()