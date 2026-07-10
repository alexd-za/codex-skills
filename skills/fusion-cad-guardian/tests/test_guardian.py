from __future__ import annotations

import json, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"scripts"))
from guardian_lib.capabilities import build_verification_plan, default_capability_profile, set_capability
from guardian_lib.contracts import default_contract, validate_contract
from guardian_lib.core import analyze_mesh, cube_triangles, sha256_file, write_binary_stl
from guardian_lib.errors import GuardianError
from guardian_lib.evidence import default_evidence, gate, validate_evidence
from guardian_lib.limits import ResourceLimits
from guardian_lib.reports import audit_stl, compare_reports, create_project, run_self_test, validate_audit_report, write_json


class GuardianTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.mesh=self.root/"cube.stl"; write_binary_stl(self.mesh,cube_triangles())
    def tearDown(self): self.tmp.cleanup()
    def contract(self):
        c=default_contract("Cube"); c["mesh"]["expected_dimensions_mm"]={a:{"target":10.,"tolerance":.01} for a in "xyz"}; c["mesh"]["max_sliver_triangles"]=12; return c
    def contract_path(self,c=None):
        p=self.root/"contract.json"; write_json(p,c or self.contract()); return p
    def complete_evidence(self,c):
        e=default_evidence(c); e["design"].update({"document":"Cube","checkpoint":"V1","fusion_mcp_server":"Fusion MCP"})
        for x in e["checks"]:
            if x["required"]: x.update(status="PASS",method="Fusion MCP",evidence="Verified")
            else: x.update(status="NOT_APPLICABLE",evidence="Optional")
        e["exports"]=[{"mesh":str(self.mesh),"mesh_sha256":sha256_file(self.mesh),"component":"Cube","body":"Body","document":"Cube","checkpoint":"V1","method":"Fusion export"}]
        return e

    def test_01_cube_metrics(self):
        m=analyze_mesh(cube_triangles()); self.assertEqual(m["triangle_count"],12); self.assertTrue(m["watertight"]); self.assertAlmostEqual(m["absolute_volume_mm3"],1000)
    def test_02_audit_only(self): self.assertEqual(audit_stl(self.mesh)["verdict"],"AUDIT_ONLY")
    def test_03_contract_pass(self): self.assertEqual(audit_stl(self.mesh,contract_path=self.contract_path())["verdict"],"PASS")
    def test_04_contract_fail(self):
        c=self.contract(); c["mesh"]["expected_dimensions_mm"]["x"]={"target":20.,"tolerance":.01}; self.assertEqual(audit_stl(self.mesh,contract_path=self.contract_path(c))["verdict"],"FAIL")
    def test_05_unknown_contract_field(self):
        with self.assertRaises(GuardianError): validate_contract({"schema_version":2,"units":"mm","magic":True})
    def test_06_v1_compatible(self):
        c={"schema_version":1,"part_name":"Cube","units":"mm","expected_dimensions_mm":{"x":{"target":10.,"tolerance":.1}}}; self.assertEqual(validate_contract(c)["schema_version"],1)
    def test_07_resource_triangle_limit(self):
        with self.assertRaises(GuardianError): audit_stl(self.mesh,resource_limits=ResourceLimits(max_triangles=1))
    def test_08_resource_coordinate_limit(self):
        p=self.root/"huge.stl"; write_binary_stl(p,[((0.,0.,0.),(2000.,0.,0.),(0.,1.,0.))])
        with self.assertRaises(GuardianError): audit_stl(p,resource_limits=ResourceLimits(max_coordinate_abs_mm=1000))
    def test_09_contract_tightens_limit(self):
        c=self.contract(); c["resource_limits"]["max_triangles"]=5
        with self.assertRaises(GuardianError): audit_stl(self.mesh,contract_path=self.contract_path(c),resource_limits=ResourceLimits(max_triangles=100))
    def test_10_capability_discovery(self):
        p=build_verification_plan(self.contract(),default_capability_profile()); self.assertEqual(p["readiness"],"DISCOVERY_REQUIRED")
    def test_11_capability_ready(self):
        c=self.contract(); p=default_capability_profile()
        for r in c["fusion_requirements"]: p=set_capability(p,r["capability"],"available",tool="tool")
        self.assertEqual(build_verification_plan(c,p)["readiness"],"READY")
    def test_12_capability_blocked(self):
        p=set_capability(default_capability_profile(),"export_stl","unavailable",notes="missing")
        self.assertEqual(build_verification_plan(self.contract(),p)["readiness"],"BLOCKED")
    def test_13_pass_evidence_requires_details(self):
        e=default_evidence(self.contract()); e["checks"][0]["status"]="PASS"
        with self.assertRaises(GuardianError): validate_evidence(e)
    def test_14_required_not_applicable_incomplete(self):
        c=self.contract(); e=self.complete_evidence(c); e["checks"][0].update(status="NOT_APPLICABLE",method="",evidence="Not applicable")
        r=audit_stl(self.mesh,contract_path=self.contract_path(c)); self.assertEqual(gate(c,e,[r],expected_contract_sha256=sha256_file(self.root/"contract.json"))["overall_verdict"],"INCOMPLETE")
    def test_15_gate_pass(self):
        c=self.contract(); cp=self.contract_path(c); e=self.complete_evidence(c); r=audit_stl(self.mesh,contract_path=cp)
        self.assertEqual(gate(c,e,[r],expected_contract_sha256=sha256_file(cp))["overall_verdict"],"PASS")
    def test_16_gate_rejects_audit_only(self):
        c=self.contract(); e=self.complete_evidence(c); self.assertEqual(gate(c,e,[audit_stl(self.mesh)])["overall_verdict"],"INCOMPLETE")
    def test_17_gate_rejects_stale_contract(self):
        c=self.contract(); cp=self.contract_path(c); e=self.complete_evidence(c); r=audit_stl(self.mesh,contract_path=cp); c["notes"].append("changed"); cp.write_text(json.dumps(c))
        self.assertEqual(gate(c,e,[r],expected_contract_sha256=sha256_file(cp))["overall_verdict"],"INCOMPLETE")
    def test_18_multi_part_requires_id(self):
        c=default_contract("Assembly","assembly",parts=[("a","A"),("b","B")]); cp=self.contract_path(c)
        with self.assertRaises(GuardianError): audit_stl(self.mesh,contract_path=cp)
    def test_19_multi_part_gate_completeness(self):
        c=default_contract("Assembly","assembly",parts=[("a","A"),("b","B")])
        for part in c["parts"]: part["mesh"]["expected_dimensions_mm"]={a:{"target":10.,"tolerance":.01} for a in "xyz"}; part["mesh"]["max_sliver_triangles"]=12
        cp=self.contract_path(c); e=self.complete_evidence(c); e["exports"][0]["part_id"]="a"
        r=audit_stl(self.mesh,contract_path=cp,part_id="a"); self.assertEqual(gate(c,e,[r],expected_contract_sha256=sha256_file(cp))["overall_verdict"],"INCOMPLETE")
    def test_20_compare_part_identity(self):
        c=default_contract("Assembly","assembly",parts=[("a","A"),("b","B")])
        for part in c["parts"]: part["mesh"]["max_sliver_triangles"]=12
        cp=self.contract_path(c); a=audit_stl(self.mesh,contract_path=cp,part_id="a"); b=audit_stl(self.mesh,contract_path=cp,part_id="b")
        with self.assertRaises(GuardianError): compare_reports(a,b)
    def test_21_project_and_self_test(self):
        p=create_project(self.root/"project","Assembly","assembly",parts=[("a","A"),("b","B")]); self.assertTrue(Path(p["capabilities"]).is_file()); self.assertTrue(run_self_test()["passed"])
    def test_22_schema_files_and_report_validation(self):
        self.assertEqual(len(list((ROOT/"schemas").glob("*.json"))),5); self.assertEqual(validate_audit_report(audit_stl(self.mesh))["verdict"],"AUDIT_ONLY")


if __name__=="__main__": unittest.main()
