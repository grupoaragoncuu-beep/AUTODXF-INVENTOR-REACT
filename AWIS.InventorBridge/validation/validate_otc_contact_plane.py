"""Usage: python validate_otc_contact_plane.py path/to/original.STEP
Offline geometry regression using cadquery/OCP; does not run Inventor COM.
"""
import sys,json,math
import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.gp import gp_Pln,gp_Pnt,gp_Dir
shape=cq.importers.importStep(sys.argv[1]).val()
solids=shape.Solids()
# Locate the physical wall from its geometry, not STEP solid order.
wall_faces=[f for b in solids for f in b.Faces() if f.geomType()=='PLANE' and f.Area()>1e6 and f.BoundingBox().ymin>3300 and f.normalAt().y>0.99]
assert len(wall_faces)==1
wall=wall_faces[0];origin=wall.Center();normal=wall.normalAt();plane=gp_Pln(gp_Pnt(*origin.toTuple()),gp_Dir(*normal.toTuple()))
loops=[w for w in wall.innerWires() if w.BoundingBox().xlen>400 and w.BoundingBox().zlen>400]
assert len(loops)==6
rings=[]
for b in solids:
 bb=b.BoundingBox()
 if not (519<bb.xlen<522 and 519<bb.zlen<523 and 70<bb.ylen<90 and bb.ymin>3300):continue
 circular=[e for e in b.Edges() if e.geomType()=='CIRCLE' and e.Length()>1600]
 if not circular:continue
 rim=min(circular,key=lambda e:e.BoundingBox().ymin)
 points=[rim.positionAt(i/200) for i in range(201)]
 real=[(p-origin).dot(normal) for p in points]
 canonical=[p.y-3415.718158987 for p in points]
 assert max(abs(v) for v in real)<1e-6
 section=BRepAlgoAPI_Section(b.wrapped,plane,False);section.Build();assert section.IsDone()
 edges=cq.Shape.cast(section.Shape()).Edges()
 curved=[e for e in edges if e.geomType()=='CIRCLE' and e.Length()>1500]
 assert len(curved)>=2,[(e.geomType(),e.Length()) for e in edges]
 # Verify UV lift preserves local X/Z while returning to the physical plane.
 max_lift_error=0
 for p in points:
  nominal=cq.Vector(p.x,3415.718158987,p.z)
  depth=(nominal-origin).dot(normal)
  lifted=nominal+cq.Vector(0,-depth/normal.y,0)
  max_lift_error=max(max_lift_error,(lifted-p).Length)
 assert max_lift_error<1e-6
 rings.append({'center_x_mm':round((bb.xmin+bb.xmax)/2,3),'actual_plane_max_error_mm':max(abs(v) for v in real),'canonical_depth_range_mm':[min(canonical),max(canonical)],'real_section_curved_lengths_mm':[e.Length() for e in curved],'uv_lift_max_error_mm':max_lift_error})
assert len(rings)==3
report={'step_solid_count':len(solids),'physical_wall_tilt_deg':math.degrees(math.acos(abs(normal.y))),'large_closed_wall_loops':len(loops),'rings':rings,'status':'PASS','scope':'OCCT geometry regression; Inventor COM build/export still required'}
print(json.dumps(report,indent=2))
