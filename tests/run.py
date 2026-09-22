#!/usr/bin/env python3
"""Run luced-2d behavior in a temporary package without a native window."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, default=ROOT.parent / ('luce-base/build/luce-base.exe' if os.name == 'nt' else 'luce-base/build/luce-base'))
parser.add_argument('--luce', type=Path, default=ROOT.parent / ('luce/build/luce.exe' if os.name == 'nt' else 'luce/build/luce'))
arguments = parser.parse_args()
environment = dict(os.environ, LUCE_BASE=str(arguments.base.resolve()))
with tempfile.TemporaryDirectory(prefix='luced-2d-tests-') as temp:
    project = Path(temp) / 'application'
    shutil.copytree(ROOT / 'src', project / 'src')
    shutil.copy2(ROOT / 'tests/main.luc', project / 'src/main.luc')
    (project / 'package.prisma').write_text('#prisma 4.0\ndef package "luced-2d-tests" {\n    str owner = "dymokomi"\n    str version = "0.0.0"\n    str kind = "tool"\n    str language = "luce"\n    str entry = "src/main.luc"\n    def dependency "luce-ui" {\n        str owner = "dymokomi"\n        str version = "^0.5.0"\n        str path = ' + json.dumps(str(ROOT.parent / 'luce-ui')) + '\n    }\n    def dependency "luce-config" {\n        str owner = "dymokomi"\n        str version = "^0.1.0"\n        str path = ' + json.dumps(str(ROOT.parent / 'luce-config')) + '\n    }\n    def dependency "luce-image" {\n        str owner = "dymokomi"\n        str version = "^0.4.0"\n        str path = ' + json.dumps(str(ROOT.parent / 'luce-image')) + '\n    }\n}\n')
    binary = Path(temp) / ('tests.exe' if os.name == 'nt' else 'tests')
    subprocess.run([str(arguments.luce.resolve()), 'build', str(project / 'src/main.luc'), '--native', '--opt', '0', '-o', str(binary)], env=environment, check=True, timeout=180)
    subprocess.run([str(binary)], env=environment, check=True, timeout=90)
