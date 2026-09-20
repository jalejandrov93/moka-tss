# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays

import json
import unittest
import io
import contextlib
from moka import main


class TestDiagnosticsFlag(unittest.TestCase):
    def test_diagnostics_flag_produces_json(self):
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            try:
                main(["--diagnostics"])
            except SystemExit as e:
                self.assertEqual(e.code, 0)

        output = f.getvalue()

        # Will raise json.decoder.JSONDecodeError if not valid JSON
        data = json.loads(output)

        self.assertIn("app_name", data)
        self.assertIn("python_version", data)
        self.assertIn("args", data)

        args = data["args"]
        self.assertIn("tick_interval", args)
        self.assertIn("brightness", args)
        self.assertIn("port", args)

        self.assertIn("status_snapshot", data)
        status = data["status_snapshot"]
        self.assertIn("running", status)
        self.assertIn("tick", status)

        self.assertIn("config_files", data)
        files = data["config_files"]
        self.assertIn("config.yaml", files)
        self.assertIn("res/moka_tss/rules.yaml", files)
        self.assertIn("res/moka_tss/webconfig.json", files)

        self.assertIn("ports", data)
        ports = data["ports"]
        self.assertIn("codexbar", ports)
        self.assertIn("agenthub", ports)
        self.assertIn("panel", ports)

        self.assertIn("imports", data)
        imports = data["imports"]
        self.assertIn("library.moka_tss.host", imports)
        self.assertIn("library.moka_tss.app", imports)
        self.assertIn("library.moka_tss.render", imports)
        self.assertIn("library.moka_tss.rules", imports)
        self.assertIn("library.moka_tss.screen", imports)
