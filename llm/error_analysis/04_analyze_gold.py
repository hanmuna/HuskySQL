"""Step 3: structural analysis (AST/BNF/relational algebra) of the corresponding GOLD SQL."""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from error_analysis.analyze_run import run

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()
    run("gold", threads=args.threads)
