from __future__ import annotations

import datetime as dt, json, tempfile
from pathlib import Path
from typing import Any

from . import VERSION
from .capabilities import default_capability_profile
from .contracts import default_contract, evaluate_contract, resolve_mesh_contract, validate_contract
from .core import analyze_mesh, cube_triangles, read_stl, sha256_file, write_binary_stl
from .errors import GuardianError
from .evidence import default_evidence, gate
from .limits import DEFAULT_RESOURCE_LIMITS, ResourceLimits, tighten_limits

AUDIT_REPORT_SCHEMA_URI="https://raw.githubusercontent.com/alexd-za/codex-skills/main/skills/fusion-cad-guardian/schemas/audit-report.schema.json"
LIMITATIONS=[
    "STL analysis does not verify assembly joints, motion, interference, or component connectivity.",
    "Bounding-box dimensions do not prove local feature tolerances, hole positions, or wall thickness.",
    "Volume, mass, centre-of-mass, build-plate, and orientation results are geometric estimates, not structural or manufacturing validation.",
]

def utc_now()->str:return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
def load_json(path:Path)->Any:
    try:return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:raise GuardianError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:raise GuardianError(f"invalid JSON in {path}: {exc}") from exc

def write_json(path:Path,data:Any)->None:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def write_text(path:Path,text:str)->None:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding="utf-8")

def validate_audit_report(report:Any)->dict[str,Any]:
    if not isinstance(report,dict):raise GuardianError("audit report must be a JSON object")
    required={"guardian_version","generated_at","mesh","contract","metrics","checks","verdict","limitations"}
    if required-set(report):raise GuardianError(f"audit report is missing fields: {sorted(required-set(report))}")
    if report.get("verdict") not in {"PASS","FAIL","AUDIT_ONLY"}:raise GuardianError("audit report verdict is invalid")
    if not isinstance(report.get("mesh"),dict) or not isinstance(report["mesh"].get("sha256"),str):raise GuardianError("audit report mesh identity is invalid")
    return report

def audit_stl(mesh_path:Path,*,contract_path:Path|None=None,part_id:str|None=None,weld_tolerance_mm:float=1e-6,area_epsilon_mm2:float=1e-12,sliver_quality_threshold:float=.05,resource_limits:ResourceLimits|None=None)->dict[str,Any]:
    contract=validate_contract(load_json(contract_path)) if contract_path else None
    limits=resource_limits or DEFAULT_RESOURCE_LIMITS
    if contract:limits=tighten_limits(limits,contract.get("resource_limits"));rules,resolved,name=resolve_mesh_contract(contract,part_id)
    else:
        if part_id:raise GuardianError("--part-id requires --contract")
        rules,resolved,name={},None,""
    fmt,triangles,preflight=read_stl(mesh_path,limits=limits)
    orientation=rules.get("orientation",{})
    metrics=analyze_mesh(triangles,weld_tolerance_mm,area_epsilon_mm2,sliver_quality_threshold,orientation.get("build_axis","z"),float(orientation.get("severe_overhang_angle_degrees",45)))
    checks=evaluate_contract(metrics,contract,triangles,part_id=resolved) if contract else []
    verdict="AUDIT_ONLY" if not contract else "FAIL" if any(c["status"]=="FAIL" for c in checks) else "PASS"
    return {"$schema":AUDIT_REPORT_SCHEMA_URI,"guardian_version":VERSION,"generated_at":utc_now(),
        "mesh":{"path":str(mesh_path.resolve()),"sha256":sha256_file(mesh_path),"format":fmt,"size_bytes":mesh_path.stat().st_size},
        "contract":{"path":str(contract_path.resolve()) if contract_path else None,"sha256":sha256_file(contract_path) if contract_path else None,"schema_version":contract.get("schema_version") if contract else None,"schema_revision":contract.get("schema_revision") if contract else None,"part_id":resolved,"part_name":name or (contract.get("part_name") if contract else None)},
        "resource_limits":limits.to_dict(),"input_preflight":preflight,"metrics":metrics,"checks":checks,"verdict":verdict,"limitations":LIMITATIONS}

def render_audit_markdown(r:dict[str,Any])->str:
    r=validate_audit_report(r);m=r["metrics"];lines=["# Fusion CAD Guardian Mesh Report","",f"- **Verdict:** {r['verdict']}",f"- **Part:** `{r['contract'].get('part_id') or 'single-part contract'}`",f"- **Mesh:** `{r['mesh']['path']}`",f"- **SHA-256:** `{r['mesh']['sha256']}`","","## Metrics","",f"- Dimensions: {m['dimensions_mm']}",f"- Surface area: {m['surface_area_mm2']:.6g} mm²",f"- Absolute volume: {m['absolute_volume_mm3']:.6g} mm³",f"- Watertight: {m['watertight']}",f"- Shells: {m['shell_count']}",""]
    if r["checks"]:
        lines += ["## Contract checks","","| Check | Status | Actual | Expected |","|---|---|---:|---|"]+[f"| `{c['id']}` | {c['status']} | {c['actual']} | {c['expected']} |" for c in r["checks"]]+[""]
    lines += ["## Limitations",""]+[f"- {x}" for x in r["limitations"]]
    return "\n".join(lines)+"\n"

def compare_reports(before:dict[str,Any],after:dict[str,Any])->dict[str,Any]:
    validate_audit_report(before);validate_audit_report(after);bp=before["contract"].get("part_id");ap=after["contract"].get("part_id")
    if bp!=ap:raise GuardianError(f"cannot compare different part identities: {bp!r} vs {ap!r}")
    bm,am=before["metrics"],after["metrics"];tracked=["boundary_edge_count","nonmanifold_edge_count","degenerate_triangle_count","duplicate_triangle_count","inconsistent_winding_edge_count","shell_count","sliver_triangle_count"]
    deltas={k:am[k]-bm[k] for k in tracked};reg=[k for k,v in deltas.items() if v>0]
    if before["verdict"]=="PASS" and after["verdict"]!="PASS":reg.append("contract_verdict")
    return {"guardian_version":VERSION,"generated_at":utc_now(),"part_id":bp,"before":before["mesh"],"after":after["mesh"],"before_verdict":before["verdict"],"after_verdict":after["verdict"],"metric_deltas":deltas,"regressions":reg,"comparison_verdict":"REGRESSION" if reg else "NO_REGRESSION"}

def render_compare_markdown(c:dict[str,Any])->str:
    lines=["# Fusion CAD Guardian Regression Report","",f"- **Verdict:** {c['comparison_verdict']}",f"- **Part:** `{c.get('part_id') or 'single-part contract'}`","","| Metric | Delta |","|---|---:|"]+[f"| `{k}` | {v} |" for k,v in c["metric_deltas"].items()]+["","## Regressions"]+([f"- {x}" for x in c["regressions"]] or ["- None"])
    return "\n".join(lines)+"\n"

def render_gate_markdown(r:dict[str,Any])->str:
    lines=["# Fusion CAD Guardian Acceptance Report","",f"- **Overall verdict:** {r['overall_verdict']}",f"- **Evidence verdict:** {r['evidence']['verdict']}",f"- **Export provenance:** {r['export_provenance']['verdict']}","","## Evidence","","| Check | Part | Required | Status | Evidence |","|---|---|---|---|---|"]
    lines += [f"| `{x['id']}` | `{x.get('part_id') or ''}` | {x['required']} | {x['status']} | {x.get('evidence',x.get('reason',''))} |" for x in r["evidence"]["checks"]]
    lines += ["","## Mesh reports","","| Part | Mesh | Verdict | Status |","|---|---|---|---|"]+[f"| `{x.get('part_id') or ''}` | `{x['path']}` | {x['verdict']} | {x['status']} |" for x in r["mesh_reports"]]
    lines += ["","## Missing required parts",""]+([f"- `{x}`" for x in r.get("missing_required_parts",[])] or ["- None"])
    return "\n".join(lines)+"\n"

def create_project(directory:Path,name:str,task_type:str,*,parts:list[tuple[str,str]]|None=None)->dict[str,Any]:
    if directory.exists() and any(directory.iterdir()):raise GuardianError(f"project directory is not empty: {directory}")
    directory.mkdir(parents=True,exist_ok=True)
    for child in ("exports","reports","snapshots","schemas"):(directory/child).mkdir(exist_ok=True)
    contract=default_contract(name,task_type,parts=parts);write_json(directory/"contract.json",contract);write_json(directory/"evidence.json",default_evidence(contract));write_json(directory/"capabilities.json",default_capability_profile());write_json(directory/"batch.json",{"jobs":[]})
    write_text(directory/"TASK.md",f"# {name}\n\nUse Fusion MCP for all live CAD operations. Use Guardian for capability routing, contracts, evidence, exported-mesh checks, and the final gate.\n")
    return {"guardian_version":VERSION,"directory":str(directory.resolve()),"contract":str((directory/"contract.json").resolve()),"evidence":str((directory/"evidence.json").resolve()),"capabilities":str((directory/"capabilities.json").resolve()),"task":str((directory/"TASK.md").resolve())}

def run_gate(contract_path:Path,evidence_path:Path,mesh_report_paths:list[Path])->dict[str,Any]:
    return gate(validate_contract(load_json(contract_path)),load_json(evidence_path),[validate_audit_report(load_json(p)) for p in mesh_report_paths],expected_contract_sha256=sha256_file(contract_path))

def run_self_test()->dict[str,Any]:
    results=[]
    with tempfile.TemporaryDirectory(prefix="guardian-self-test-") as d:
        root=Path(d);cube=root/"cube.stl";write_binary_stl(cube,cube_triangles());report=audit_stl(cube);results.append({"name":"cube_audit","passed":report["metrics"]["watertight"] and report["metrics"]["triangle_count"]==12})
        contract=default_contract("Cube");contract["mesh"]["expected_dimensions_mm"]={a:{"target":10.0,"tolerance":.01} for a in "xyz"};contract["mesh"]["max_sliver_triangles"]=12;cp=root/"contract.json";write_json(cp,contract);cr=audit_stl(cube,contract_path=cp);results.append({"name":"contract_pass","passed":cr["verdict"]=="PASS"})
        project=create_project(root/"project","Test Assembly","assembly",parts=[("base","Base"),("arm","Arm")]);results.append({"name":"multi_part_project_scaffold","passed":Path(project["capabilities"]).is_file()})
        try:audit_stl(cube,resource_limits=ResourceLimits(max_triangles=1));limited=False
        except GuardianError:limited=True
        results.append({"name":"resource_limit","passed":limited})
    return {"guardian_version":VERSION,"generated_at":utc_now(),"passed":all(x["passed"] for x in results),"tests":results}
