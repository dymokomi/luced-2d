import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SUFFIX = ".exe" if os.name == "nt" else ""
parser = argparse.ArgumentParser()
parser.add_argument("--base", type=Path, default=ROOT.parent / f"luce-base/build/luce-base{SUFFIX}")
parser.add_argument("--luce", type=Path, default=ROOT.parent / f"luce/build/luce{SUFFIX}")
parser.add_argument("--opt", type=int, choices=range(4), default=1)
args = parser.parse_args()
output = ROOT / f"build/luced-2d{SUFFIX}"
output.parent.mkdir(parents=True, exist_ok=True)
subprocess.run([str(args.luce.resolve()), "build", str(ROOT / "src/main.luc"),
                "--native", "--opt", str(args.opt), "-o", str(output)],
               cwd=ROOT, env=dict(os.environ, LUCE_BASE=str(args.base.resolve())), check=True)
