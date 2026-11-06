import sys
from reviewpulse.xeval import run
from reviewpulse.xeval.progress import Tracker
run.step_baseline(Tracker(), "qwen2.5:7b", 60, ("expr_verify",), tid="E5", name="expr5")
