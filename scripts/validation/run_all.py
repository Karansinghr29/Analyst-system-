"""
run_all.py -- runs every validate_*.py script in a fixed, deterministic order so
validation_summary.csv and monthly_validation/*.csv are rebuilt identically every time.
validate_ledger.py MUST run first (append=False there resets validation_summary.csv).
"""
import subprocess
import sys
import os

HERE = os.path.dirname(__file__)
ORDER = [
    "validate_ledger.py",
    "validate_revenue.py",
    "validate_expenses.py",
    "validate_profit.py",
    "validate_owner_payments.py",
    "validate_receivables.py",
    "validate_deposits.py",
    "validate_occupancy.py",
    "validate_maintenance.py",
    "validate_eb.py",
    "validate_collections.py",
    "validate_data_quality.py",
]

for script in ORDER:
    print(f"\n{'='*90}\nRUNNING {script}\n{'='*90}")
    r = subprocess.run([sys.executable, os.path.join(HERE, script)])
    if r.returncode != 0:
        print(f"FAILED: {script}", file=sys.stderr)
        sys.exit(1)

print("\nAll 12 validation scripts completed. See ../../validation_summary.csv and "
      "../../monthly_validation/*.csv")
