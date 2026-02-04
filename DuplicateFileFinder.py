#!/usr/bin/env python3
"""
duplicatefinder.py

A Python implementation of the duplicate file finder.
Finds duplicate files based on content (SHA-256).

Features:
 - Recursive directory scanning
 - Content-based duplicate detection (SHA-256)
 - Friendly, human-readable output
 - Cross-platform
"""

import sys
import os

# Ensure UTF-8 output for emojis/colors on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
import hashlib
import argparse
from collections import defaultdict
from pathlib import Path

# ============================================================================
# ANSI Colors
# ============================================================================
GREEN = "\033[32m"
RED = "\033[31m"
BLUE = "\033[34m"
YELLOW = "\033[33m"
RESET = "\033[0m"

# ============================================================================
# Helpers
# ============================================================================

def format_size(size_bytes: int) -> str:
    """Formats file size into a human-readable string (e.g., 4.2 MB)."""
    s = float(size_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while s >= 1024 and i < 4:
        s /= 1024
        i += 1
    
    # Match C++ precision logic: 0 decimals for Bytes, 2 for others
    if i == 0:
        return f"{int(s)} {units[i]}"
    else:
        return f"{s:.2f} {units[i]}"

def compute_file_hash(path: str) -> str:
    """Computes the SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    buffer_size = 8192
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(buffer_size)
                if not chunk:
                    break
                sha256.update(chunk)
    except OSError as e:
        print(f"Warning: Skipping {path} ({e})", file=sys.stderr)
        return ""
    
    return sha256.hexdigest()

def print_progress_bar(current: int, total: int, bar_length: int = 30):
    """Displays a green progress bar in the terminal."""
    fraction = current / total if total > 0 else 1.0
    percentage = int(fraction * 100)
    filled_length = int(bar_length * fraction)
    bar = "█" * filled_length + "-" * (bar_length - filled_length)
    
    # \r is carriage return to update the line in-place
    sys.stdout.write(f"\r{GREEN}[{bar}] {current}/{total} ({percentage}%){RESET}")
    sys.stdout.flush()

# ============================================================================
# Scanning Logic
# ============================================================================

def run_scan(directory_path: str):
    target_dir = Path(directory_path).resolve()
    
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"Error: Directory not found or invalid: {target_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Counting files in {target_dir} ...")
    
    all_files = []
    try:
        for root, _, files in os.walk(target_dir):
            for name in files:
                filepath = Path(root) / name
                # Simple check for regular file (excluding symlinks as per previous logic)
                if not filepath.is_symlink():
                    all_files.append(filepath)
    except Exception as e:
        print(f"Error during directory traversal: {e}", file=sys.stderr)
        sys.exit(1)

    total_count = len(all_files)
    if total_count == 0:
        print("\nNo files found to scan.")
        # We still print footer as requested
        print(f"\n{YELLOW}Don't worry: all duplicate files have been verified using SHA-256 and you can be 100% confident that files detected as duplicates are identical.{RESET}")
        print(f"{BLUE}If you want to support development, you can make a donation here: https://www.paypal.com/paypalme/EnricoArama{RESET}")
        return

    print(f"Processing {total_count} files ...")
    
    # Step 1: Group files by size
    files_by_size = defaultdict(list)
    processed_count = 0
    
    # Temporary list for files that actually need hashing
    potential_duplicates_by_size = defaultdict(list)
    
    for filepath in all_files:
        try:
            size = filepath.stat().st_size
            files_by_size[size].append(filepath)
        except OSError:
            pass
        
        # We count it as processed for the size check stage
        # But we only reach 100% after hashing, so we'll redistribute the progress.
        # Actually, let's just use a single continuous counter.
        # To make it smooth, we show progress here, but we'll continue the same counter in the hashing phase.
        # However, it's better to:
        # 1. Quick size scan (optional bar)
        # 2. Hashing (the real slow part)
        
    # Let's refine the progress: 
    # Files that don't need hashing reach "processed" state during hashing loop.
    # Files that DO need hashing reach "processed" state AFTER hashing.
    
    # To keep total_count accurate:
    # 1. Identify files that ARE NOT potential duplicates (unique size).
    # 2. Increment progress for them immediately.
    # 3. Increment progress for the rest as they are hashed.

    unique_sized_files_count = sum(1 for paths in files_by_size.values() if len(paths) < 2)
    processed_count = unique_sized_files_count
    
    # Show initial progress for skipping unique sizes
    print_progress_bar(processed_count, total_count)

    duplicates = []
    
    for size, paths in files_by_size.items():
        if len(paths) < 2:
            continue
        
        # Optimization: empty files
        if size == 0:
            duplicates.append({
                'file_size': 0,
                'files': paths
            })
            processed_count += len(paths)
            print_progress_bar(processed_count, total_count)
            continue

        files_by_hash = defaultdict(list)
        for p in paths:
            h = compute_file_hash(str(p))
            processed_count += 1
            print_progress_bar(processed_count, total_count)
            
            if h: # if hash computation succeeded
                files_by_hash[h].append(p)
        
        for h, final_paths in files_by_hash.items():
            if len(final_paths) > 1:
                duplicates.append({
                    'file_size': size,
                    'files': final_paths
                })

    # Clear progress bar line
    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()

    # ============================================================================
    # Output Generation
    # ============================================================================

    if not duplicates:
        print("\nNo duplicate files found.")
    else:
        print("\nFound duplicate files (same content):\n")

    total_files = 0
    total_wasted_bytes = 0

    for group in duplicates:
        files = group['files']
        size = group['file_size']
        count = len(files)
        
        if count == 0: continue

        rep_name = files[0].name
        
        # First file is GREEN (Keep)
        print(f"📄 {GREEN}{rep_name} (x{count}){RESET} — identical content")

        for i, fpath in enumerate(files):
            is_last = (i == count - 1)
            prefix = "└─ " if is_last else "├─ "
            
            # First file (index 0) gets GREEN, others RED
            color = GREEN if i == 0 else RED
            print(f" {prefix}{color}{fpath}{RESET}")
        
        # Advice message in BLUE
        print(f"{BLUE}Tip: keep only the file {files[0].name} and remove those highlighted in red.{RESET}")
        print()

        total_files += count
        total_wasted_bytes += (count - 1) * size

    if duplicates:
        print(f"Total duplicate groups: {len(duplicates)}")
        print(f"Total duplicated files: {total_files}")
        print(f"Total wasted space: {format_size(total_wasted_bytes)}")
    
    # Final footer messages (always displayed)
    print()
    print(f"{YELLOW}Don't worry: all duplicate files have been verified using SHA-256 and you can be 100% confident that files detected as duplicates are identical.{RESET}")
    print(f"{BLUE}If you want to support development, you can make a donation here: https://www.paypal.com/paypalme/EnricoArama{RESET}")

# ============================================================================
# Main Helper
# ============================================================================

def print_help(prog_name: str):
    print(f"Usage: {prog_name} <command> [options]\n")
    print("Commands:")
    print("  scan \"DIRECTORY_PATH\"    Scan the directory recursively for duplicate files.")
    print("  --help                   Show this help message.\n")
    print("Description:")
    print("  DuplicateFinder detects file duplicates based on EXACT CONTENT.")
    print("  File names and timestamps are ignored.")
    print("  It uses file size grouping and SHA-256 hashing for accuracy.\n")
    print("Example:")
    print(f"  {prog_name} scan \"C:\\Users\\MyUser\\Documents\"")

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print_help(sys.argv[0])
        sys.exit(1)

    arg1 = sys.argv[1]

    if arg1 in ("--help", "-h"):
        print_help(sys.argv[0])
        sys.exit(0)

    if arg1 == "scan":
        if len(sys.argv) < 3:
            print("Error: Missing directory path.", file=sys.stderr)
            print(f"Usage: {sys.argv[0]} scan \"DIRECTORY_PATH\"")
            sys.exit(1)
        
        run_scan(sys.argv[2])
        sys.exit(0)

    print(f"Unknown command: {arg1}", file=sys.stderr)
    print_help(sys.argv[0])
    sys.exit(1)

if __name__ == "__main__":
    main()
