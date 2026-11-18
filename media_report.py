#!/usr/bin/env python3
"""
media_report.py - command-line entry point (kept for the original usage).

    py media_report.py "D:\\Movies" "D:\\TV" [-o out.xlsx] [--max-audio 3] [--max-subs 6]

All logic lives in the mediareport package. For the GUI, run MediaReport.pyw.
"""
import sys

from mediareport.cli import main

if __name__ == "__main__":
    sys.exit(main())
