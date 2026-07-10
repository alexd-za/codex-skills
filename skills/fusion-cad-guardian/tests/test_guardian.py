from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "guardian.py"
SPEC = importlib.util.spec_from_file_location("guardian", SCRIPT)
assert SPEC and SPEC.loader
GUARDIAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARDIAN)

from guardian_lib.core import sha256_file
from guardian_lib.evidence import evaluate_evidence, gate


class GuardianTests(unittest.TestCase):
    def _write_cube(self, root: Path, size: float = 10.0) -> Path:
        mesh = root / "cube.stl"
        GUARDIAN._write_binary_stl(mesh, GUARDIAN._cube_triangles(size))
        return mesh

    def _contract(self, name: str = "Cube") -> dict:
        contract = GUARDIAN._default_contract(name, "part")
        contract["mesh"]["expected_dimensions_mm"] = {
            axis: {"target": 10.0, "tolerance": 0.01} for axis in "xyz"
        }
        contract["mesh"]["max_sliver_triangles"] = 12
        return contract

    def _complete_evidence(self, contract: dict, mesh: Path) -> dict:
        evidence = GUARDIAN.default_evidence(contract)
        evidence["design"].update({
            "document": "Cube Design",
            "checkpoint": "Version 3",
            "units": "mm",
            "fusion_mcp_server": "Autodesk Fusion MCP",
        })
        for check in evidence["checks"]:
            if check["required"]:
                check.update({
                    "status": "PASS",
                    "method": "Fusion MCP inspection",
                    "evidence": f"Verified {check['id']} in the live Fusion design",
                    "source": "fusion_mcp",
                })
            else:
                check.update({
                    "status": "NOT_APPLICABLE",
                    "method": "",
                    "evidence": "Not required for this geometry-only self-contained test",
                    "source": "human_review",
                })
        evidence["exports"] = [{
            "mesh": str(mesh),
            "mesh_sha256": sha256_file(mesh),
            "component": "Cube_Component",
            "body": "Cube_Body",
            "document": "Cube Design",
            "checkpoint": "Version 3",
            "method": "Fusion MCP STL export in millimetres",
        }]
        return evidence

    def test_self_test(self) -> None:
        result = GUARDIAN.run_self_test()
        self.assertTrue(result["passed"], result)

    def test_cube_metrics_include_center_of_mass_and_quality(self) -> None:
        metrics = GUARDIAN.analyze_mesh(GUARDIAN._cube_triangles(10.0))
        self.assertEqual(metrics["triangle_count"], 12)
        self.assertEqual(metrics["boundary_edge_count"], 0)
        self.assertEqual(metrics["nonmanifold_edge_count"], 0)
        self.assertEqual(metrics["shell_count"], 1)
        self.assertTrue(metrics["watertight"])
        self.assertAlmostEqual(metrics["absolute_volume_mm3"], 1000.0, places=6)
        self.assertAlmostEqual(metrics["center_of_mass_mm"]["x"], 5.0, places=6)
        self.assertGreater(metrics["triangle_quality"]["minimum"], 0.0)

    def test_v2_contract_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = self._write_cube(root)
            contract_path = root / "contract.json"
            contract = self._contract()
            contract["mesh"]["expected_dimensions_mm"]["x"] = {"target": 11.0, "tolerance": 0.01}
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            report = GUARDIAN.audit_stl(mesh, contract_path=contract_path)
            self.assertEqual(report["verdict"], "FAIL")
            self.assertIn("dimension_x", {c["id"] for c in report["checks"] if c["status"] == "FAIL"})

    def test_v1_contract_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = self._write_cube(root)
            contract_path = root / "legacy.json"
            contract = {
                "schema_version": 1,
                "part_name": "Legacy cube",
                "units": "mm",
                "expected_dimensions_mm": {"x": {"target": 10.0, "tolerance": 0.01}},
                "require_watertight": True,
                "max_boundary_edges": 0,
            }
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            self.assertEqual(GUARDIAN.audit_stl(mesh, contract_path=contract_path)["verdict"], "PASS")

    def test_pass_or_fail_evidence_requires_details(self) -> None:
        evidence = {
            "schema_version": 1,
            "design": {},
            "checks": [{
                "id": "critical_parameters", "required": True, "status": "PASS",
                "method": "", "evidence": "", "source": "fusion_mcp",
            }],
            "exports": [],
            "notes": [],
        }
        with self.assertRaises(GUARDIAN.GuardianError):
            GUARDIAN.validate_evidence(evidence)

    def test_required_not_applicable_is_incomplete(self) -> None:
        contract = self._contract()
        evidence = GUARDIAN.default_evidence(contract)
        for check in evidence["checks"]:
            if check["required"]:
                check.update({
                    "status": "NOT_APPLICABLE",
                    "evidence": "Attempted bypass",
                    "source": "human_review",
                })
        self.assertEqual(evaluate_evidence(contract, evidence)["verdict"], "INCOMPLETE")

    def test_gate_passes_only_with_current_contract_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = self._write_cube(root)
            contract_path = root / "contract.json"
            contract = self._contract()
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            report = GUARDIAN.audit_stl(mesh, contract_path=contract_path)
            evidence = self._complete_evidence(contract, mesh)
            result = gate(
                contract,
                evidence,
                [report],
                expected_contract_sha256=sha256_file(contract_path),
            )
            self.assertEqual(result["overall_verdict"], "PASS", result)

    def test_gate_rejects_audit_only_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = self._write_cube(root)
            contract = self._contract()
            evidence = self._complete_evidence(contract, mesh)
            report = GUARDIAN.audit_stl(mesh)
            result = gate(contract, evidence, [report], expected_contract_sha256="0" * 64)
            self.assertEqual(result["overall_verdict"], "INCOMPLETE")

    def test_gate_rejects_stale_contract_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = self._write_cube(root)
            contract_path = root / "contract.json"
            contract = self._contract()
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            report = GUARDIAN.audit_stl(mesh, contract_path=contract_path)
            evidence = self._complete_evidence(contract, mesh)
            result = gate(contract, evidence, [report], expected_contract_sha256="f" * 64)
            self.assertEqual(result["overall_verdict"], "INCOMPLETE")

    def test_incomplete_export_metadata_blocks_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mesh = self._write_cube(root)
            contract_path = root / "contract.json"
            contract = self._contract()
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            report = GUARDIAN.audit_stl(mesh, contract_path=contract_path)
            evidence = self._complete_evidence(contract, mesh)
            evidence["exports"][0]["checkpoint"] = ""
            result = gate(contract, evidence, [report], expected_contract_sha256=sha256_file(contract_path))
            self.assertEqual(result["overall_verdict"], "INCOMPLETE")

    def test_project_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "guardian-project"
            result = GUARDIAN.create_project(project, "Test Assembly", "assembly")
            self.assertTrue(Path(result["contract"]).is_file())
            self.assertTrue(Path(result["evidence"]).is_file())
            contract = json.loads(Path(result["contract"]).read_text(encoding="utf-8"))
            ids = {item["id"] for item in contract["fusion_requirements"]}
            self.assertIn("interference_checked", ids)

    def test_unknown_contract_field_rejected(self) -> None:
        with self.assertRaises(GUARDIAN.GuardianError):
            GUARDIAN.validate_contract({"schema_version": 2, "units": "mm", "magic": True})


if __name__ == "__main__":
    unittest.main()
