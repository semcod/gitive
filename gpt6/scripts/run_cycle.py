"""Translate fixed workflow environment fields into validated CLI arguments."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intuition_github.cli import main
from intuition_github.util import integer

args = ["cycle"]
if os.getenv("INTUITION_APPLY", "false").lower() == "true":
    args.append("--apply")
if os.getenv("INTUITION_RUN_ID", ""):
    args += ["--run-id", str(integer(os.environ["INTUITION_RUN_ID"]))]
if os.getenv("INTUITION_RESET_CIRCUIT", "false").lower() == "true":
    args.append("--reset-circuit")
raise SystemExit(main(args))
