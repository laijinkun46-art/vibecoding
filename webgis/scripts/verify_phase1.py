"""验证已运行的前后端与项目资料契约；只使用标准库和项目后端依赖。"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import main
from fastapi import HTTPException

API = os.environ.get("WEBGIS_API_URL", "http://127.0.0.1:8000")
FRONTEND = os.environ.get("WEBGIS_FRONTEND_URL", "http://127.0.0.1:4173")


def read_json(url):
    with urlopen(url, timeout=8) as response:
        return json.load(response)


class Phase1Checks(unittest.TestCase):
    def test_health_over_http(self):
        response = read_json(API + "/api/health")
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["service"], "nanning-flood-webgis")

    def test_project_matches_real_validation(self):
        response = read_json(API + "/api/project")
        expected = json.loads((ROOT / "docs/phase0_validation.json").read_text(encoding="utf-8"))
        self.assertEqual(response["study_area"]["bbox_wsen"], expected["aoi"]["bbox_wsen"])
        self.assertEqual(response["datasets"]["rainfall"]["date_labels"], expected["rainfall"]["date_labels"])
        self.assertEqual(response["datasets"]["rainfall"]["cell_count"], 6)
        self.assertIn("20:00", response["datasets"]["rainfall"]["daily_window"])

    def test_frontend_serves_page(self):
        with urlopen(FRONTEND, timeout=8) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("邕江洪水 WebGIS", response.read().decode())

    def test_frontend_proxy_reaches_backend(self):
        self.assertEqual(read_json(FRONTEND + "/api/health"), read_json(API + "/api/health"))
        self.assertEqual(read_json(FRONTEND + "/api/project"), read_json(API + "/api/project"))

    def test_cesium_assets_available(self):
        with urlopen(FRONTEND + "/cesium/Assets/Textures/NaturalEarthII/tilemapresource.xml", timeout=8) as response:
            self.assertIn(b"TileMap", response.read())

    def test_missing_metadata_returns_503(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(main, "PROJECT_ROOT", Path(directory)):
            with self.assertRaises(HTTPException) as raised:
                main.project()
            self.assertEqual(raised.exception.status_code, 503)

    def test_invalid_metadata_returns_503(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs/phase0_validation.json").write_text("{broken", encoding="utf-8")
            with patch.object(main, "PROJECT_ROOT", root), self.assertRaises(HTTPException) as raised:
                main.project()
            self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Phase1Checks))
    report = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "passed": result.wasSuccessful()}
    (ROOT / "docs/phase1_api_checks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
