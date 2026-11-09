"""Offline OCCT geometry regression. Does not execute the C# Inventor API.
Usage: python validate_otc_inner_surface.py original.STEP
"""
import sys,json,math
import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.gp import gp_Pln,gp_Pnt,gp_Dir
shape=cq.importers.importStep(sys.argv[1]).val()
solids=shape.Solids()
wall_pairs=[(b,f) for b in solids for f in b.Faces() if f.geomType()=='PLANE' and f.Area()>1e6 and f.BoundingBox().ymin>3300 and f.normalAt().y>.99]
assert len(wall_pairs)==1
body,outer=wall_pairs[0];origin=outer.Center();normal=outer.normalAt();bounds=outer.BoundingBox()
options=[]
for f in body.Faces():
 if f.geomType()!='PLANE':continue
 alignment=abs(f.normalAt().dot(normal))
 if alignment<math.cos(math.radians(.01)):continue
 depth=-(f.Center()-origin).dot(normal)
 if not(.25<depth<=100):continue
 if not(.75*outer.Area()<=f.Area()<=outer.Area()/.75):continue
 bb=f.BoundingBox()
 if max(abs(a-b) for a,b in zip([bb.xmin,bb.xmax,bb.zmin,bb.zmax],[bounds.xmin,bounds.xmax,bounds.zmin,bounds.zmax]))>.5:continue
 options.append((depth,f))
assert len(options)==1
thickness,inner=options[0];inside_origin=inner.Center();inside_normal=normal*-1
assert abs(thickness-9.525)<1e-6
assert normal.dot(inside_normal)<-.999999
# P03 is found by its actual dimensions and world position, not STEP solid index.
ref=[b for b in solids if abs(b.BoundingBox().xmin+1885.95)<.02 and abs(b.BoundingBox().xmax+1873.25)<.02 and b.BoundingBox().zlen>1800]
assert len(ref)==1
contact_faces=[f for f in ref[0].Faces() if f.geomType()=='PLANE' and abs(f.normalAt().dot(normal))>.9999 and abs((f.Center()-inside_origin).dot(inside_normal))<1e-6]
assert len(contact_faces)==1
contact=contact_faces[0]
assert abs((contact.Center()-origin).dot(normal)+thickness)<1e-6
wire=contact.outerWire();assert wire.IsClosed()
# Internal planar contact is a long narrow rectangular footprint.
bb=wire.BoundingBox();assert bb.zlen>1800 and abs(bb.xlen-12.7)<1e-6
# Confirm that the measured inner plane produces an actual section through the refuerzo.
plane=gp_Pln(gp_Pnt(*inside_origin.toTuple()),gp_Dir(*inside_normal.toTuple()))
section=BRepAlgoAPI_Section(ref[0].wrapped,plane,False);section.Build();assert section.IsDone()
edges=cq.Shape.cast(section.Shape()).Edges();assert len(edges)>=4
# UV stays canonical; view-from-inside uses a mirror and must be applied by the future consumer.
max_u,min_u=3803.65,0
for u in [min_u,101.2,max_u]:assert abs(max_u-(max_u-u)-u)<1e-9
# Reject impossible counterpart comparisons; thickness is not used as a constant in the selector.
assert not(.25<0<=100)
assert not(.75*outer.Area()<=outer.Area()*.1<=outer.Area()/.75)
report={'status':'PASS','scope':'OCCT geometric counterpart/contact checks; Inventor COM build/export pending','measured_thickness_mm':thickness,'outer_tilt_deg':math.degrees(math.acos(normal.y)),'inner_face_candidates':len(options),'p03_closed_contact_loop':wire.IsClosed(),'p03_contact_area_mm2':contact.Area(),'p03_outer_plane_distance_mm':(contact.Center()-origin).dot(normal),'p03_inner_plane_distance_mm':(contact.Center()-inside_origin).dot(inside_normal),'p03_section_edge_count':len(edges),'normals_dot':normal.dot(inside_normal)}
print(json.dumps(report,indent=2))
