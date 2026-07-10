from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import VALID_STATUSES, iter_requirements, validate_contract
from .core import sha256_file
from .errors import GuardianError

EVIDENCE_SCHEMA_URI = "https://raw.githubusercontent.com/alexd-za/codex-skills/main/skills/fusion-cad-guardian/schemas/evidence.schema.json"
SOURCES = {"fusion_mcp", "human_review", "calculation", "simulation", "physical_test", "slicer", "other"}
EXPORT_KEYS = {"mesh", "mesh_sha256", "part_id", "component", "body", "document", "checkpoint", "method"}


def default_evidence(contract: dict[str, Any]) -> dict[str, Any]:
    contract = validate_contract(contract)
    return {
        "$schema": EVIDENCE_SCHEMA_URI, "schema_version": 1,
        "design": {"document":"", "checkpoint":"", "units":contract.get("units","mm"), "fusion_mcp_server":"", "capability_profile":"capabilities.json"},
        "checks": [{
            "id":r["qualified_id"], "part_id":r.get("part_id") or "", "required":bool(r.get("required",True)),
            "status":"NOT_VERIFIED", "method":"", "evidence":"",
            "source":"fusion_mcp" if r["category"] in {"fusion","assembly"} else "human_review", "timestamp":"",
        } for r in iter_requirements(contract)],
        "exports": [],
        "notes": ["Record only evidence actually gathered; screenshots alone do not prove dimensions or function."],
    }


def validate_export_record(item: Any, *, index: int | None=None) -> dict[str, Any]:
    label=f"evidence.exports[{index}]" if index is not None else "export record"
    if not isinstance(item,dict) or set(item)-EXPORT_KEYS: raise GuardianError(f"{label} is invalid")
    if not isinstance(item.get("mesh"),str) or not item["mesh"].strip(): raise GuardianError(f"{label}.mesh must be non-empty")
    for key,value in item.items():
        if key in EXPORT_KEYS and not isinstance(value,str): raise GuardianError(f"{label}.{key} must be a string")
    h=item.get("mesh_sha256","")
    if h and (len(h)!=64 or any(c not in "0123456789abcdefABCDEF" for c in h)): raise GuardianError(f"{label}.mesh_sha256 is invalid")
    return item


def validate_evidence(data: Any) -> dict[str, Any]:
    if not isinstance(data,dict) or set(data)-{"$schema","schema_version","design","checks","exports","notes"}: raise GuardianError("invalid evidence ledger")
    if data.get("schema_version",1)!=1 or not isinstance(data.get("design",{}),dict): raise GuardianError("invalid evidence schema/design")
    checks=data.get("checks",[])
    if not isinstance(checks,list): raise GuardianError("evidence.checks must be an array")
    seen=set()
    for i,c in enumerate(checks):
        if not isinstance(c,dict) or set(c)-{"id","status","method","evidence","source","required","timestamp","part_id"}: raise GuardianError(f"evidence check {i} is invalid")
        cid=c.get("id")
        if not isinstance(cid,str) or not cid or cid in seen: raise GuardianError(f"invalid or duplicate evidence check id: {cid}")
        seen.add(cid); status=c.get("status")
        if status not in VALID_STATUSES or not isinstance(c.get("required",True),bool): raise GuardianError(f"evidence check {cid} has invalid status/required")
        if c.get("source","") not in SOURCES: raise GuardianError(f"evidence check {cid} has invalid source")
        if status in {"PASS","FAIL"} and (not str(c.get("method","")).strip() or not str(c.get("evidence","")).strip()): raise GuardianError(f"evidence check {cid} requires method and evidence")
        if status=="NOT_APPLICABLE" and not str(c.get("evidence","")).strip(): raise GuardianError(f"evidence check {cid} requires rationale")
    exports=data.get("exports",[])
    if not isinstance(exports,list): raise GuardianError("evidence.exports must be an array")
    for i,item in enumerate(exports): validate_export_record(item,index=i)
    if not isinstance(data.get("notes",[]),list): raise GuardianError("evidence.notes must be an array")
    return data


def populate_export_hashes(data: dict[str, Any], base: Path) -> dict[str, Any]:
    data=validate_evidence(data)
    for item in data["exports"]:
        path=Path(item["mesh"]); path=path if path.is_absolute() else base/path
        if not path.is_file(): raise GuardianError(f"export mesh not found: {path}")
        item["mesh_sha256"]=sha256_file(path)
    return validate_evidence(data)


def evaluate_evidence(contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    contract=validate_contract(contract); evidence=validate_evidence(evidence)
    by_id={x["id"]:x for x in evidence["checks"]}; checks=[]
    for req in iter_requirements(contract):
        cid=req["qualified_id"]; item=by_id.get(cid)
        if item is None:
            checks.append({"id":cid,"part_id":req.get("part_id"),"required":bool(req.get("required",True)),"status":"NOT_VERIFIED","reason":"missing evidence entry"})
        else:
            checks.append({"id":cid,"part_id":req.get("part_id"),"required":bool(req.get("required",True)),"status":item["status"],"method":item.get("method",""),"evidence":item.get("evidence",""),"source":item.get("source","")})
    required_failures=[c["id"] for c in checks if c["required"] and c["status"]=="FAIL"]
    required_missing=[c["id"] for c in checks if c["required"] and c["status"] in {"NOT_VERIFIED","NOT_APPLICABLE"}]
    optional_open=[c["id"] for c in checks if not c["required"] and c["status"] == "NOT_VERIFIED"]
    verdict="FAIL" if required_failures else "INCOMPLETE" if required_missing else "CONDITIONAL_PASS" if optional_open else "PASS"
    return {"verdict":verdict,"checks":checks,"required_failures":required_failures,"required_missing":required_missing,"optional_open":optional_open}


def _complete_export(item: dict[str,Any], require_part: bool) -> tuple[bool,list[str]]:
    missing=[k for k in ("mesh","mesh_sha256","document","checkpoint","method") if not str(item.get(k,"")).strip()]
    if require_part and not str(item.get("part_id","")).strip(): missing.append("part_id")
    if not str(item.get("component","")).strip() and not str(item.get("body","")).strip(): missing.append("component_or_body")
    return not missing,missing


def verify_export_provenance(contract: dict[str,Any], evidence: dict[str,Any], reports: list[dict[str,Any]]) -> dict[str,Any]:
    required=bool(contract.get("export_provenance_required",False)) if contract.get("schema_version")==2 else False
    multi=bool(contract.get("parts")); results=[]
    for report in reports:
        h=str(report.get("mesh",{}).get("sha256") or ""); pid=report.get("contract",{}).get("part_id")
        matches=[e for e in evidence.get("exports",[]) if e.get("mesh_sha256","").lower()==h.lower() and (not pid or e.get("part_id")==pid)]
        complete=[]; incomplete=[]
        for item in matches:
            ok,missing=_complete_export(item,multi); (complete if ok else incomplete).append({"record":item,"missing":missing})
        if complete: status,reason="PASS","matching export record with complete provenance"
        elif incomplete: status,reason="INCOMPLETE","matching export record is missing provenance fields"
        else: status,reason=("INCOMPLETE" if required else "NOT_APPLICABLE"),"no export record matches the audited mesh SHA-256 and part identity"
        results.append({"mesh":report.get("mesh",{}).get("path"),"part_id":pid,"sha256":h,"status":status,"reason":reason,"matches":complete or incomplete})
    verdict="INCOMPLETE" if any(x["status"]=="INCOMPLETE" for x in results) else "PASS"
    return {"verdict":verdict,"required":required,"checks":results}


def gate(contract: dict[str,Any], evidence: dict[str,Any], reports: list[dict[str,Any]], *, expected_contract_sha256: str|None=None) -> dict[str,Any]:
    contract=validate_contract(contract); evidence=validate_evidence(evidence)
    ev=evaluate_evidence(contract,evidence); provenance=verify_export_provenance(contract,evidence,reports)
    required_parts={p["id"] for p in contract.get("parts",[]) if p.get("required",True)}
    reported_parts={r.get("contract",{}).get("part_id") for r in reports if r.get("contract",{}).get("part_id")}
    missing_parts=sorted(required_parts-reported_parts); mesh=[]
    for r in reports:
        verdict=r.get("verdict"); h=r.get("contract",{}).get("sha256")
        if verdict=="FAIL": status,reason="FAIL","mesh contract failed"
        elif verdict=="AUDIT_ONLY": status,reason="INCOMPLETE","audit-only report cannot satisfy final gate"
        elif expected_contract_sha256 and h!=expected_contract_sha256: status,reason="INCOMPLETE","mesh report is linked to a stale or different contract"
        else: status,reason="PASS","mesh report passed and is linked to the current contract"
        mesh.append({"path":r.get("mesh",{}).get("path"),"part_id":r.get("contract",{}).get("part_id"),"sha256":r.get("mesh",{}).get("sha256"),"verdict":verdict,"contract_sha256":h,"status":status,"reason":reason})
    if any(x["status"]=="FAIL" for x in mesh) or ev["verdict"]=="FAIL": overall="FAIL"
    elif not mesh or missing_parts or any(x["status"]=="INCOMPLETE" for x in mesh) or ev["verdict"]=="INCOMPLETE" or provenance["verdict"]=="INCOMPLETE": overall="INCOMPLETE"
    elif ev["verdict"]=="CONDITIONAL_PASS": overall="CONDITIONAL_PASS"
    else: overall="PASS"
    return {"overall_verdict":overall,"evidence":ev,"export_provenance":provenance,"mesh_reports":mesh,"required_parts":sorted(required_parts),"reported_parts":sorted(reported_parts),"missing_required_parts":missing_parts}
