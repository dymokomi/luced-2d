#!/usr/bin/env python3
"""Run luced-2d behavior in a temporary package without a native window."""
import argparse
import json
import re
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# Crash reports carry app.luc's version: it must be the package's.
package_version = re.search(r'^    str version = "([^"]+)"', (ROOT / 'package.prisma').read_text(), re.M).group(1)
app_version = re.search(r'pub let version: str = "([^"]+)"', (ROOT / 'src/app.luc').read_text()).group(1)
if app_version != package_version:
    raise SystemExit(f'src/app.luc says {app_version}; package.prisma says {package_version}')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, default=ROOT.parent / ('luce-base/build/luce-base.exe' if os.name == 'nt' else 'luce-base/build/luce-base'))
parser.add_argument('--luce', type=Path, default=ROOT.parent / ('luce/build/luce.exe' if os.name == 'nt' else 'luce/build/luce'))
arguments = parser.parse_args()
environment = dict(os.environ, LUCE_BASE=str(arguments.base.resolve()))
with tempfile.TemporaryDirectory(prefix='luced-2d-tests-') as temp:
    project = Path(temp) / 'application'
    shutil.copytree(ROOT / 'src', project / 'src')
    shutil.copy2(ROOT / 'tests/main.luc', project / 'src/main.luc')
    # The application's own dependencies, each taken from the checkout beside this one.
    manifest = (ROOT / 'package.prisma').read_text()
    dependencies = ''.join('    def dependency "%s" {\n        str owner = "dymokomi"\n        str version = "%s"\n        str path = %s\n    }\n' % (name, version, json.dumps(str(ROOT.parent / name)))
                           for name, version in re.findall(r'def dependency "([^"]+)" \{\s*str owner = "[^"]*"\s*str version = "([^"]+)"', manifest))
    (project / 'package.prisma').write_text('#prisma 4.0\ndef package "luced-2d-tests" {\n    str owner = "dymokomi"\n    str version = "0.0.0"\n    str kind = "tool"\n    str language = "luce"\n    str entry = "src/main.luc"\n' + dependencies + '}\n')
    binary = Path(temp) / ('tests.exe' if os.name == 'nt' else 'tests')
    subprocess.run([str(arguments.luce.resolve()), 'build', str(project / 'src/main.luc'), '--native', '--opt', '0', '-o', str(binary)], env=environment, check=True, timeout=180)
    subprocess.run([str(binary)], env=environment, check=True, timeout=90)
