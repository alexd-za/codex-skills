from __future__ import annotations

from collections import Counter, defaultdict
import hashlib, math, struct
from pathlib import Path
from typing import Any, Sequence

from .errors import GuardianError
from .limits import ResourceLimits, estimated_mesh_memory_mb

Vec3 = tuple[float, float, float]
Triangle = tuple[Vec3, Vec3, Vec3]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sub(a: Vec3, b: Vec3) -> Vec3: return a[0]-b[0], a[1]-b[1], a[2]-b[2]
def _cross(a: Vec3, b: Vec3) -> Vec3: return a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]
def _dot(a: Vec3, b: Vec3) -> float: return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def _norm(a: Vec3) -> float: return math.sqrt(_dot(a, a))
def _area(t: Triangle) -> float: return .5 * _norm(_cross(_sub(t[1], t[0]), _sub(t[2], t[0])))
def _volume6(t: Triangle) -> float: return _dot(t[0], _cross(t[1], t[2]))
def _q(v: Vec3, tol: float) -> tuple[int, int, int]: return tuple(int(round(x / tol)) for x in v)  # type: ignore[return-value]


def _check_vertex(v: Vec3, limits: ResourceLimits, label: str) -> None:
    if not all(math.isfinite(x) for x in v):
        raise GuardianError(f"{label} contains invalid coordinates")
    if any(abs(x) > limits.max_coordinate_abs_mm for x in v):
        raise GuardianError(f"{label} exceeds max_coordinate_abs_mm={limits.max_coordinate_abs_mm:g}")


def preflight_stl(path: Path, limits: ResourceLimits) -> dict[str, Any]:
    limits.validate()
    if not path.is_file(): raise GuardianError(f"STL file not found: {path}")
    size = path.stat().st_size
    if size > limits.max_file_size_mb * 1024 * 1024: raise GuardianError(f"STL size {size} bytes exceeds max_file_size_mb={limits.max_file_size_mb:g}")
    if size < 15: raise GuardianError(f"STL file is too small to be valid: {path}")
    head = path.read_bytes()[:84]
    count = expected = None
    if len(head) == 84:
        c = struct.unpack_from("<I", head, 80)[0]; e = 84 + c * 50
        if c > 0 and e <= size and size - e <= 1024:
            count, expected = c, e
            if c > limits.max_triangles: raise GuardianError(f"binary STL declares {c} triangles, exceeding max_triangles={limits.max_triangles}")
            if estimated_mesh_memory_mb(c) > limits.max_estimated_memory_mb: raise GuardianError("estimated analysis memory exceeds limit")
    return {"size_bytes": size, "binary_triangle_count": count, "binary_expected_size": expected, "limits": limits.to_dict()}


def read_stl(path: Path, *, limits: ResourceLimits | None = None) -> tuple[str, list[Triangle], dict[str, Any]]:
    limits = (limits or ResourceLimits()).validate(); pre = preflight_stl(path, limits)
    if pre["binary_triangle_count"] is not None:
        triangles: list[Triangle] = []
        with path.open("rb") as f:
            f.seek(84)
            for i in range(int(pre["binary_triangle_count"])):
                rec = f.read(50)
                if len(rec) != 50: raise GuardianError(f"binary STL ended at triangle {i}")
                vals = struct.unpack("<12fH", rec)
                t: Triangle = ((float(vals[3]),float(vals[4]),float(vals[5])),(float(vals[6]),float(vals[7]),float(vals[8])),(float(vals[9]),float(vals[10]),float(vals[11])))
                for j,v in enumerate(t): _check_vertex(v, limits, f"triangle {i} vertex {j}")
                triangles.append(t)
        return "binary", triangles, {**pre, "triangle_count":len(triangles), "estimated_memory_mb":estimated_mesh_memory_mb(len(triangles))}
    triangles=[]; pending: list[Vec3]=[]
    try:
        with path.open("r", encoding="utf-8-sig", errors="strict") as f:
            for line_no,line in enumerate(f,1):
                parts=line.strip().split()
                if not parts or parts[0].lower()!="vertex": continue
                if len(parts)!=4: raise GuardianError(f"invalid vertex at line {line_no}")
                try: v=(float(parts[1]),float(parts[2]),float(parts[3]))
                except ValueError as exc: raise GuardianError(f"invalid numeric vertex at line {line_no}") from exc
                _check_vertex(v,limits,f"line {line_no}"); pending.append(v)
                if len(pending)==3:
                    triangles.append((pending[0],pending[1],pending[2])); pending=[]
                    if len(triangles)>limits.max_triangles: raise GuardianError(f"ASCII STL exceeds max_triangles={limits.max_triangles}")
                    if estimated_mesh_memory_mb(len(triangles))>limits.max_estimated_memory_mb: raise GuardianError("estimated analysis memory exceeds limit")
    except UnicodeDecodeError as exc: raise GuardianError("file is neither valid binary nor ASCII STL") from exc
    if pending or not triangles: raise GuardianError("ASCII STL has no complete triangle records")
    return "ascii",triangles,{**pre,"triangle_count":len(triangles),"estimated_memory_mb":estimated_mesh_memory_mb(len(triangles))}


class DSU:
    def __init__(self,n:int): self.p=list(range(n))
    def find(self,x:int)->int:
        while self.p[x]!=x: self.p[x]=self.p[self.p[x]]; x=self.p[x]
        return x
    def union(self,a:int,b:int)->None:
        a,b=self.find(a),self.find(b)
        if a!=b:self.p[b]=a


def build_plate_contact(triangles: Sequence[Triangle], axis: str, plane_mm: float, tolerance_mm: float) -> dict[str, Any]:
    idx={"x":0,"y":1,"z":2}[axis]; vertices=set(); area=0.0; tris=0
    for t in triangles:
        near=[abs(v[idx]-plane_mm)<=tolerance_mm for v in t]
        for v,n in zip(t,near):
            if n: vertices.add(v)
        if all(near): area+=_area(t); tris+=1
    return {"vertex_count":len(vertices),"triangle_count":tris,"area_mm2":area}


def analyze_mesh(triangles: Sequence[Triangle], weld_tolerance_mm: float=1e-6, area_epsilon_mm2: float=1e-12, sliver_quality_threshold: float=.05, build_axis: str="z", severe_overhang_angle_degrees: float=45.0) -> dict[str, Any]:
    if not triangles: raise GuardianError("mesh contains no triangles")
    if weld_tolerance_mm<=0: raise GuardianError("weld tolerance must be positive")
    verts=[v for t in triangles for v in t]; mins=[min(v[i] for v in verts) for i in range(3)]; maxs=[max(v[i] for v in verts) for i in range(3)]
    edge_uses: dict[tuple[Any,Any],list[tuple[int,Any,Any]]]=defaultdict(list); duplicates=Counter(); dsu=DSU(len(triangles))
    deg=0; surface=0.0; signed=0.0; qualities=[]; lengths=[]; slivers=0
    centroid_num=[0.0,0.0,0.0]
    axis_idx={"x":0,"y":1,"z":2}[build_axis]; severe_area=0.0; angle=math.radians(severe_overhang_angle_degrees)
    for i,t in enumerate(triangles):
        qv=[_q(v,weld_tolerance_mm) for v in t]; duplicates[tuple(sorted(qv))]+=1
        ar=_area(t); surface+=ar; vol6=_volume6(t); signed+=vol6/6
        if abs(vol6)>0:
            c=[sum(v[j] for v in t)/4 for j in range(3)]
            for j in range(3): centroid_num[j]+=c[j]*vol6/6
        if ar<=area_epsilon_mm2: deg+=1
        lens=[_norm(_sub(t[(j+1)%3],t[j])) for j in range(3)]; lengths+=lens
        denom=sum(x*x for x in lens); quality=4*math.sqrt(3)*ar/denom if denom else 0.0; qualities.append(quality); slivers+=quality<sliver_quality_threshold
        normal=_cross(_sub(t[1],t[0]),_sub(t[2],t[0])); nlen=_norm(normal)
        if nlen and normal[axis_idx]/nlen < -math.cos(angle): severe_area+=ar
        for a,b in ((0,1),(1,2),(2,0)):
            qa,qb=qv[a],qv[b]; key=tuple(sorted((qa,qb))); edge_uses[key].append((i,qa,qb))
    for uses in edge_uses.values():
        for k in range(1,len(uses)): dsu.union(uses[0][0],uses[k][0])
    boundary=sum(len(u)==1 for u in edge_uses.values()); nonmanifold=sum(len(u)>2 for u in edge_uses.values())
    inconsistent=0
    for uses in edge_uses.values():
        if len(uses)==2 and not (uses[0][1]==uses[1][2] and uses[0][2]==uses[1][1]): inconsistent+=1
    shell_count=len({dsu.find(i) for i in range(len(triangles))}); duplicate_count=sum(c-1 for c in duplicates.values() if c>1)
    watertight=boundary==0 and nonmanifold==0 and deg==0
    absvol=abs(signed); com=None
    if watertight and abs(signed)>1e-15: com={"x":centroid_num[0]/signed,"y":centroid_num[1]/signed,"z":centroid_num[2]/signed}
    def stats(values:list[float])->dict[str,float]:
        return {"minimum":min(values),"maximum":max(values),"mean":sum(values)/len(values)} if values else {"minimum":0.0,"maximum":0.0,"mean":0.0}
    return {
        "triangle_count":len(triangles),"unique_vertex_count":len({_q(v,weld_tolerance_mm) for v in verts}),
        "bounds_mm":{"min":{"x":mins[0],"y":mins[1],"z":mins[2]},"max":{"x":maxs[0],"y":maxs[1],"z":maxs[2]}},
        "dimensions_mm":{"x":maxs[0]-mins[0],"y":maxs[1]-mins[1],"z":maxs[2]-mins[2]},
        "surface_area_mm2":surface,"signed_volume_mm3":signed,"absolute_volume_mm3":absvol,"center_of_mass_mm":com,
        "boundary_edge_count":boundary,"nonmanifold_edge_count":nonmanifold,"inconsistent_winding_edge_count":inconsistent,
        "degenerate_triangle_count":deg,"duplicate_triangle_count":duplicate_count,"shell_count":shell_count,"watertight":watertight,
        "triangle_quality":stats(qualities),"edge_length_mm":stats(lengths),"sliver_triangle_count":slivers,
        "severe_downward_area":{"axis":build_axis,"threshold_degrees":severe_overhang_angle_degrees,"area_mm2":severe_area},
    }


def cube_triangles(size: float=10.0) -> list[Triangle]:
    s=float(size); p=[(0.,0.,0.),(s,0.,0.),(s,s,0.),(0.,s,0.),(0.,0.,s),(s,0.,s),(s,s,s),(0.,s,s)]
    faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return [(p[a],p[b],p[c]) for a,b,c in faces]


def write_binary_stl(path: Path, triangles: Sequence[Triangle]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("wb") as f:
        f.write(b"Fusion CAD Guardian".ljust(80,b"\0")); f.write(struct.pack("<I",len(triangles)))
        for t in triangles:
            n=_cross(_sub(t[1],t[0]),_sub(t[2],t[0])); nl=_norm(n); n=(n[0]/nl,n[1]/nl,n[2]/nl) if nl else (0.,0.,0.)
            f.write(struct.pack("<12fH",*n,*t[0],*t[1],*t[2],0))
