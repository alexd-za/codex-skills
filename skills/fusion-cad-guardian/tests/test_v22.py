from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "guardian.py"
SPEC = importlib.util.spec_from_file_location("guardian_v22", SCRIPT)
assert SPEC and SPEC.loader
GUARDIAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARDIAN)

from guardian_lib.bundle import create_bundle, validate_bundle_manifest, verify_bundle
from guardian_lib.contracts import default_contract
from guardian_lib.core import cube_triangles, sha256_file, write_binary_stl
from guardian_lib.errors import GuardianError
from guardian_lib.evidence import default_evidence
from guardian_lib.html_report import render_audit_html
from guardian_lib.limits import ResourceLimits
from guardian_lib.meshio import inspect_3mf, read_3mf
from guardian_lib.reports import audit_mesh, run_gate, write_json
from guardian_lib.slicer import build_slicer_report, parse_gcode_metadata


def write_3mf(path: Path, *, unit: str = "millimeter", objects: list[dict] | None = None, build: list[dict] | None = None) -> None:
    objects = objects or [{
        "id": "1", "name": "cube", "vertices": [
            (0,0,0),(10,0,0),(10,10,0),(0,10,0),(0,0,10),(10,0,10),(10,10,10),(0,10,10)
        ], "triangles": [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(3,7,6),(3,6,2),(0,4,7),(0,7,3),(1,2,6),(1,6,5)]
    }]
    build = build or [{"objectid": objects[0]["id"]}]
    object_xml=[]
    for obj in objects:
        if "components" in obj:
            components=''.join(f'<component objectid="{item["objectid"]}" transform="{item.get("transform","")}"/>' for item in obj["components"])
            payload=f'<components>{components}</components>'
        else:
            vertices=''.join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x,y,z in obj.get("vertices",[]))
            triangles=''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a,b,c in obj.get("triangles",[]))
            payload=f'<mesh><vertices>{vertices}</vertices><triangles>{triangles}</triangles></mesh>'
        object_xml.append(f'<object id="{obj["id"]}" name="{obj.get("name","")}">{payload}</object>')
    build_xml=''.join(f'<item objectid="{item["objectid"]}" transform="{item.get("transform","")}"/>' for item in build)
    model=f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="{unit}" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
<resources>{''.join(object_xml)}</resources><build>{build_xml}</build></model>'''
    rels='''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'''
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("3D/3dmodel.model",model)
        archive.writestr("_rels/.rels",rels)
        archive.writestr("[Content_Types].xml",'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')


class GuardianV22Tests(unittest.TestCase):
    def test_3mf_units_convert_to_mm(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"inch.3mf"
            obj={"id":"1","name":"inch","vertices":[(0,0,0),(1,0,0),(0,1,0)],"triangles":[(0,1,2)]}
            write_3mf(path,unit="inch",objects=[obj])
            triangles, preflight, metadata=read_3mf(path)
            self.assertAlmostEqual(triangles[0][1][0],25.4)
            self.assertEqual(preflight["unit"],"inch")
            self.assertEqual(metadata["object_name"],"inch")

    def test_3mf_multiple_objects_require_selector(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"multi.3mf"
            tri={"vertices":[(0,0,0),(1,0,0),(0,1,0)],"triangles":[(0,1,2)]}
            objects=[{"id":"1","name":"one",**tri},{"id":"2","name":"two",**tri}]
            write_3mf(path,objects=objects,build=[{"objectid":"1"},{"objectid":"2"}])
            with self.assertRaises(GuardianError): read_3mf(path)
            triangles,_,meta=read_3mf(path,object_name="two")
            self.assertEqual(len(triangles),1)
            self.assertEqual(meta["object_id"],"2")

    def test_3mf_component_and_build_transforms(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"component.3mf"
            base={"id":"1","name":"triangle","vertices":[(0,0,0),(1,0,0),(0,1,0)],"triangles":[(0,1,2)]}
            assembly={"id":"2","name":"assembly","components":[{"objectid":"1","transform":"1 0 0 0 1 0 0 0 1 2 0 0"}]}
            write_3mf(path,objects=[base,assembly],build=[{"objectid":"2","transform":"1 0 0 0 1 0 0 0 1 0 3 0"}])
            triangles,_,_=read_3mf(path)
            self.assertEqual(triangles[0][0],(2.0,3.0,0.0))

    def test_3mf_archive_traversal_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"bad.3mf"
            with zipfile.ZipFile(path,"w") as archive: archive.writestr("../evil.model","x")
            with self.assertRaises(GuardianError): inspect_3mf(path)

    def test_3mf_archive_ratio_limit(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ratio.3mf"
            with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as archive: archive.writestr("3D/3dmodel.model","0"*100000)
            with self.assertRaises(GuardianError): inspect_3mf(path,limits=ResourceLimits(max_compression_ratio=2))

    def test_gcode_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"part.gcode"
            path.write_text("; generated by OrcaSlicer\n; estimated printing time (normal mode) = 2h 3m 4s\n; filament used [mm] = 1000, 500\n; filament used [g] = 3.2, 1.8\n; layer_height = 0.2\n; nozzle_diameter = 0.4,0.6\n; total layer number: 123\n",encoding="utf-8")
            metadata,_=parse_gcode_metadata(path)
            self.assertEqual(metadata["estimated_print_time_seconds"],7384.0)
            self.assertAlmostEqual(metadata["filament_used_mm"],1500.0)
            self.assertAlmostEqual(metadata["filament_used_g"],5.0)
            self.assertEqual(metadata["nozzle_diameters_mm"],[0.4,0.6])
            self.assertEqual(metadata["layer_count"],123)

    def test_slicer_contract_pass_and_fail(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); mesh=root/"cube.stl"; write_binary_stl(mesh,cube_triangles())
            gcode=root/"part.gcode"; gcode.write_text("; estimated printing time (normal mode) = 1h\n; filament used [g] = 4\n; nozzle_diameter = 0.4\n",encoding="utf-8")
            rules={"print_time_seconds":{"max":4000},"filament_g":{"max":5},"allowed_nozzle_diameters_mm":[0.4]}
            report=build_slicer_report(gcode,source_mesh_path=mesh,slicer_rules=rules)
            self.assertEqual(report["verdict"],"PASS")
            rules["filament_g"]={"max":3}
            self.assertEqual(build_slicer_report(gcode,source_mesh_path=mesh,slicer_rules=rules)["verdict"],"FAIL")

    def _gate_fixture(self, root: Path, *, require_slicer: bool=True):
        mesh=root/"cube.stl"; write_binary_stl(mesh,cube_triangles())
        contract=default_contract("Cube")
        contract["mesh"]["expected_dimensions_mm"]={axis:{"target":10,"tolerance":0.01} for axis in "xyz"}
        contract["mesh"]["max_sliver_triangles"]=12
        contract["slicer"]={"required":require_slicer,"require_source_mesh_hash":True,"print_time_seconds":{"max":4000}}
        contract_path=root/"contract.json"; write_json(contract_path,contract)
        audit=audit_mesh(mesh,contract_path=contract_path)
        report_path=root/"mesh.json"; write_json(report_path,audit)
        evidence=default_evidence(contract)
        for check in evidence["checks"]:
            check.update({"status":"PASS" if check["required"] else "NOT_APPLICABLE","method":"test" if check["required"] else "","evidence":"verified" if check["required"] else "not needed"})
        evidence["exports"]=[{"mesh":str(mesh),"mesh_sha256":sha256_file(mesh),"component":"Cube","body":"Body","document":"Doc","checkpoint":"v1","method":"Fusion export"}]
        evidence_path=root/"evidence.json"; write_json(evidence_path,evidence)
        return mesh,contract_path,evidence_path,report_path

    def test_gate_requires_slicer_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); _,contract,evidence,mesh_report=self._gate_fixture(root)
            result=run_gate(contract,evidence,[mesh_report])
            self.assertEqual(result["overall_verdict"],"INCOMPLETE")
            self.assertEqual(result["missing_required_slicer_parts"],["__single_part__"])

    def test_gate_accepts_linked_slicer_report(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); mesh,contract,evidence,mesh_report=self._gate_fixture(root)
            gcode=root/"part.gcode"; gcode.write_text("; estimated printing time (normal mode) = 30m\n",encoding="utf-8")
            slicer=build_slicer_report(gcode,source_mesh_path=mesh,contract_path=contract)
            slicer_path=root/"slicer.json"; write_json(slicer_path,slicer)
            result=run_gate(contract,evidence,[mesh_report],[slicer_path])
            self.assertIn(result["overall_verdict"],{"PASS","CONDITIONAL_PASS"})
            self.assertEqual(result["slicer_reports"][0]["status"],"PASS")

    def test_gate_rejects_wrong_slicer_source(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); _,contract,evidence,mesh_report=self._gate_fixture(root)
            other=root/"other.stl"; write_binary_stl(other,cube_triangles(9))
            gcode=root/"part.gcode"; gcode.write_text("; estimated printing time (normal mode) = 30m\n",encoding="utf-8")
            slicer=build_slicer_report(gcode,source_mesh_path=other,contract_path=contract)
            path=root/"slicer.json"; write_json(path,slicer)
            result=run_gate(contract,evidence,[mesh_report],[path])
            self.assertEqual(result["overall_verdict"],"INCOMPLETE")

    def test_html_escapes_paths(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"<cube>.stl"; write_binary_stl(path,cube_triangles())
            html=render_audit_html(audit_mesh(path))
            self.assertIn("&lt;cube&gt;.stl",html)
            self.assertNotIn("<cube>.stl",html)

    def test_bundle_verification_and_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/"a.txt"; source.write_text("hello",encoding="utf-8")
            bundle=root/"bundle.zip"; create_bundle(bundle,[("a.txt",source)])
            self.assertTrue(verify_bundle(bundle)["passed"])
            with zipfile.ZipFile(bundle,"a") as archive: archive.writestr("extra.txt","tamper")
            self.assertFalse(verify_bundle(bundle)["passed"])

    def test_audit_3mf_contract(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); path=root/"cube.3mf"; write_3mf(path)
            contract=default_contract("Cube"); contract["mesh"]["expected_dimensions_mm"]={axis:{"target":10,"tolerance":0.01} for axis in "xyz"}; contract["mesh"]["max_sliver_triangles"]=12
            cpath=root/"contract.json"; write_json(cpath,contract)
            report=audit_mesh(path,contract_path=cpath)
            self.assertEqual(report["verdict"],"PASS")
            self.assertEqual(report["mesh"]["format"],"3mf")

    def test_resource_limits_include_archive_fields(self) -> None:
        limits=ResourceLimits()
        self.assertGreater(limits.max_archive_entries,0)
        self.assertIn("max_compression_ratio",limits.to_dict())

    def test_bundle_archive_limits(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/"a.txt"; source.write_text("A"*100000,encoding="utf-8")
            bundle=root/"bundle.zip"; create_bundle(bundle,[("a.txt",source)])
            with self.assertRaises(GuardianError):
                verify_bundle(bundle, limits=ResourceLimits(max_compression_ratio=2))

    def test_bundle_manifest_validation(self) -> None:
        valid={"guardian_version":"2.2.0","generated_at":"2026-07-10T00:00:00+00:00","metadata":{},"files":[{"path":"a.txt","sha256":"0"*64,"size_bytes":1}]}
        self.assertEqual(validate_bundle_manifest(valid),valid)
        invalid=json.loads(json.dumps(valid)); invalid["files"][0]["path"]="../a.txt"
        with self.assertRaises(GuardianError): validate_bundle_manifest(invalid)

    def test_slicer_report_validator_rejects_contract_part_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); gcode=root/"part.gcode"; gcode.write_text("; generated by test\n",encoding="utf-8")
            report=build_slicer_report(gcode,part_id="part_a")
            report["contract"]["part_id"]="part_b"
            with self.assertRaises(GuardianError): GUARDIAN.validate_slicer_report(report)

    def test_default_capability_profile_includes_3mf_export(self) -> None:
        profile=GUARDIAN.default_capability_profile("Fusion MCP")
        self.assertIn("export_stl",profile["capabilities"])
        self.assertIn("export_3mf",profile["capabilities"])
        self.assertEqual(profile["capabilities"]["export_3mf"]["status"],"unknown")

    def test_missing_gcode_metadata_remains_missing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"plain.gcode"; path.write_text("G1 X1 Y1 Z0.2\n",encoding="utf-8")
            metadata,_=parse_gcode_metadata(path)
            self.assertIsNone(metadata["estimated_print_time_seconds"])
            self.assertIsNone(metadata["filament_used_g"])
            self.assertEqual(metadata["max_z_mm"],0.2)

    def test_bundle_creation_respects_entry_limit(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); a=root/"a"; b=root/"b"; a.write_text("a"); b.write_text("b")
            with self.assertRaises(GuardianError):
                create_bundle(root/"bundle.zip",[("a",a),("b",b)],limits=ResourceLimits(max_archive_entries=2))


if __name__ == "__main__":
    unittest.main()
