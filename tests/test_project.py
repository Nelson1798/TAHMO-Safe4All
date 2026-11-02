import ast
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from safe4all.aoi import aoi_label
from safe4all.config import (CLASS_LABELS, COUNTRIES, DEFAULT_WEIGHTS, class_label, country_settings,
                             normalise_weights)
from safe4all.export import FIELD_DESCRIPTIONS
from safe4all.gee import initialise_earth_engine
from safe4all.model import assign_classes, rank_descending
from safe4all.validation import rainfall_metrics

ROOT = Path(__file__).resolve().parents[1]


class ProjectTests(unittest.TestCase):
    def test_supported_countries_have_map_settings(self):
        self.assertEqual(set(COUNTRIES), {"Kenya", "Zimbabwe", "Ghana"})
        for country in COUNTRIES:
            settings = country_settings(country)
            self.assertIn("iso3", settings)
            self.assertIn("center", settings)

    def test_unsupported_country_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "Unsupported country"):
            country_settings("Uganda")

    def test_rainfall_metrics(self):
        metrics = rainfall_metrics(observed=[1.0, 2.0, 3.0], estimated=[1.0, 3.0, 5.0])
        self.assertEqual(metrics['n'], 3.0)
        self.assertGreater(metrics['rmse_mm'], 0)

    def test_earth_engine_requires_a_project(self):
        # Earth Engine has required every request to name a Cloud project
        # since November 2024; fail fast with a clear message instead of a
        # cryptic error from the `ee` library.
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "EE_PROJECT"):
                initialise_earth_engine()

    def test_earth_engine_uses_a_service_account_key_when_configured(self):
        # Headless/workshop auth path: a service account key file (never
        # committed to the repo) should be used instead of interactive
        # ee.Authenticate() when EE_SERVICE_ACCOUNT_KEY is set.
        fake_ee = mock.MagicMock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            key_path = Path(tmp_dir) / "key.json"
            key_path.write_text(json.dumps({"client_email": "bot@example.iam.gserviceaccount.com"}))
            env = {"EE_PROJECT": "some-project", "EE_SERVICE_ACCOUNT_KEY": str(key_path)}
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.dict(sys.modules, {"ee": fake_ee}):
                initialise_earth_engine()

        fake_ee.ServiceAccountCredentials.assert_called_once_with(
            "bot@example.iam.gserviceaccount.com", str(key_path)
        )
        fake_ee.Authenticate.assert_not_called()
        fake_ee.Initialize.assert_called_once_with(
            fake_ee.ServiceAccountCredentials.return_value, project="some-project"
        )

    def test_earth_engine_service_account_key_must_exist(self):
        env = {"EE_PROJECT": "some-project", "EE_SERVICE_ACCOUNT_KEY": "/no/such/key.json"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.dict(sys.modules, {"ee": mock.MagicMock()}):
            with self.assertRaises(FileNotFoundError):
                initialise_earth_engine()


class RiskWorkflowTests(unittest.TestCase):
    def test_countries_define_flood_dry_and_rainy_seasons(self):
        for country in COUNTRIES:
            settings = country_settings(country)
            for key in ("flood_months", "dry_months", "rainy_months"):
                self.assertTrue(set(settings[key]) <= set(range(1, 13)), (country, key))
            self.assertFalse(set(settings["flood_months"]) & set(settings["dry_months"]), country)

    def test_country_settings_returns_independent_copies(self):
        country_settings("Ghana")["flood_months"].append(1)
        self.assertNotIn(1, country_settings("Ghana")["flood_months"])

    def test_weights_drop_missing_layers_and_rescale(self):
        weights = normalise_weights({"a": 0.5, "b": 0.25, "c": 0.25}, available=["a", "b"])
        self.assertEqual(set(weights), {"a", "b"})
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["a"], 2 / 3)
        with self.assertRaises(ValueError):
            normalise_weights({"a": -0.1, "b": 1.1})
        with self.assertRaises(ValueError):
            normalise_weights({"a": 1.0}, available=[])

    def test_default_weight_groups_sum_to_one(self):
        for group, weights in DEFAULT_WEIGHTS.items():
            self.assertAlmostEqual(sum(weights.values()), 1.0, msg=group)
        for k in (1, 3, 6):
            self.assertIn(f"spi{k}", DEFAULT_WEIGHTS["drought_hazard"])

    def test_five_risk_classes_with_inclusive_upper_breaks(self):
        self.assertEqual(CLASS_LABELS, ["Very Low", "Low", "Moderate", "High", "Very High"])
        self.assertEqual([class_label(v) for v in (0.0, 0.2, 0.21, 0.5, 0.8, 0.95)],
                         ["Very Low", "Very Low", "Low", "Moderate", "High", "Very High"])

    def test_aoi_label_and_validation(self):
        self.assertEqual(aoi_label("Ghana"), "Ghana")
        self.assertEqual(aoi_label("Ghana", "admin1", admin1="Upper East"), "Ghana_Upper_East")
        with self.assertRaises(ValueError):
            aoi_label("Ghana", "district")
        with self.assertRaises(ValueError):
            aoi_label("Ghana", "watershed")

    def test_district_classes_and_ranks(self):
        values = [0.1, 0.9, float("nan"), 0.5, 0.5]
        self.assertEqual(assign_classes(values), ["Very Low", "Very High", "No data", "Moderate", "Moderate"])
        self.assertEqual(rank_descending(values), [4, 1, None, 2, 2])
        quantile = assign_classes([0.1, 0.2, 0.3, 0.4, 0.5], method="quantile")
        self.assertEqual(quantile, CLASS_LABELS)

    def test_shapefile_field_names_fit_the_dbf_limit(self):
        for field in FIELD_DESCRIPTIONS:
            self.assertLessEqual(len(field), 10, field)

    @unittest.skipUnless(importlib.util.find_spec("shapely"), "shapely not installed")
    def test_district_geometries_keep_only_polygons(self):
        from shapely.geometry import GeometryCollection, LineString, Polygon

        from safe4all.export import polygon_parts

        square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        mixed = polygon_parts(GeometryCollection([square, LineString([(2, 2), (3, 3)])]))
        self.assertEqual(mixed.geom_type, "MultiPolygon")
        self.assertAlmostEqual(mixed.area, 1.0)
        self.assertIsNone(polygon_parts(LineString([(0, 0), (1, 1)])))

    def test_notebook_follows_the_ten_step_workflow(self):
        notebook = json.loads((ROOT / "SAFE4ALL_Climate_Risk_Assessment_Workshop.ipynb").read_text(encoding="utf-8"))
        markdown = "\n".join("".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "markdown")
        for step in ("STEP 1–2", "STEP 3", "STEP 4", "STEP 5", "STEP 6", "STEP 7", "STEP 8", "STEP 9", "STEP 10"):
            self.assertIn(f"# {step} ·", markdown)
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                ast.parse("".join(cell["source"]))
                self.assertEqual(cell["outputs"], [])


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
