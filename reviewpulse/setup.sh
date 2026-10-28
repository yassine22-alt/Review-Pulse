#!/usr/bin/env bash
# ReviewPulse setup for macOS and Linux. Run from this folder:
#     ./setup.sh             app + tests (vector plans: PDF, DXF, SVG)
#     ./setup.sh --scans     also scanned plans (PyTorch CPU + PaddleOCR, about 2 GB more)
# It creates .venv, installs ReviewPulse into it, then runs the self-check (rp doctor).
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for v in python3.11 python3.12; do
  if command -v "$v" >/dev/null 2>&1; then PY="$v"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11 or 3.12 is needed (python.org, or your package manager), then run this again."
  exit 1
fi
echo "Using $PY"

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[app,dev]"

if [ "${1:-}" = "--scans" ]; then
  .venv/bin/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
  .venv/bin/python -m pip install -e ".[raster]"
  .venv/bin/python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
fi

echo
.venv/bin/python -m reviewpulse.selfcheck
echo
echo "Done. Next:"
echo "  source .venv/bin/activate        (once per terminal)"
echo "  rp serve                         then open http://127.0.0.1:8000"
echo "  rp check path/to/plan.pdf        check a plan from the command line"
