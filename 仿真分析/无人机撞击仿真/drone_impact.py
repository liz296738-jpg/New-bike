from abaqus import *
from abaqusConstants import *
from caeModules import *
from part import *
from material import *
from section import *
from assembly import *
from step import *
from interaction import *
from load import *
from mesh import *
from job import *
from sketch import *
import regionToolset
import sys

Mdb()
for m_name in list(mdb.models.keys()):
    try: del mdb.models[m_name]
    except: pass
mdl = mdb.Model(name='Drone-Impact')

V_DRONE = 600000.0
STEP_TIME = 0.10     # 100 ms - longer to see full impact
NOSE_X = -1000.0

def log(msg):
    with open('C:/Users/ASUA/OneDrive/Desktop/cc/_run_log.txt', 'a') as lf:
        lf.write(msg + '\n')

log("="*70)
log("  DRONE IMPACT SCRIPT START")
log("="*70)

# ---- Materials ----
log("[1] Materials")
alu = mdl.Material(name='Aluminum_7075')
alu.Density(table=((2.81e-9,),))
alu.Elastic(table=((71700.0, 0.33),))
alu.Plastic(table=((503.0, 0.0), (572.0, 0.05), (610.0, 0.10)))

conc = mdl.Material(name='Concrete_C40')
conc.Density(table=((2.4e-9,),))
conc.Elastic(table=((32500.0, 0.2),))
conc.ConcreteDamagedPlasticity(table=((38.0, 0.1, 1.16, 0.667, 0.0),))
conc.concreteDamagedPlasticity.ConcreteCompressionHardening(table=(
    (20.0, 0.0), (38.0, 0.0030), (10.0, 0.0100)))
conc.concreteDamagedPlasticity.ConcreteTensionStiffening(table=(
    (3.2, 0.0), (1.0, 0.0005), (0.1, 0.0020)))
conc.concreteDamagedPlasticity.ConcreteCompressionDamage(table=(
    (0.0, 0.0), (0.5, 0.0050), (0.9, 0.0100)))
conc.concreteDamagedPlasticity.ConcreteTensionDamage(table=(
    (0.0, 0.0), (0.7, 0.0005), (0.95, 0.0020)))

# ---- Drone ----
log("[2] Drone (cyl R=500, L=8000mm)")
sk_drone = mdl.ConstrainedSketch(name='sk_drone', sheetSize=10000.0)
sk_drone.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(0.0, 500.0))
drone = mdl.Part(name='Drone', dimensionality=THREE_D, type=DEFORMABLE_BODY)
drone.BaseSolidExtrude(sketch=sk_drone, depth=8000.0)
del mdl.sketches['sk_drone']
log("  Drone cells: %d" % len(drone.cells))

# ---- Wall (tall building: 5000x20000x500mm, Z direction is height) ----
log("[3] Building wall (W=5000 H=20000 D=500mm)")
sk_wall = mdl.ConstrainedSketch(name='sk_wall', sheetSize=25000.0)
# Sketch in X-Z plane: 5000mm wide (X), 20000mm tall (Z)
sk_wall.rectangle(point1=(-2500.0, -10000.0), point2=(2500.0, 10000.0))
wall = mdl.Part(name='Wall', dimensionality=THREE_D, type=DEFORMABLE_BODY)
wall.BaseSolidExtrude(sketch=sk_wall, depth=500.0)
del mdl.sketches['sk_wall']
log("  Wall cells: %d" % len(wall.cells))
# ---- Sections ----
log("[4] Sections")
mdl.HomogeneousSolidSection(name='Sec_Drone', material='Aluminum_7075')
drone.SectionAssignment(region=regionToolset.Region(cells=drone.cells[:]), sectionName='Sec_Drone')
mdl.HomogeneousSolidSection(name='Sec_Wall', material='Concrete_C40')
wall.SectionAssignment(region=regionToolset.Region(cells=wall.cells[:]), sectionName='Sec_Wall')

# ---- MESH BEFORE ASSEMBLY ----
log("[5] Mesh")
# Use same element type for both - C3D8R
e_hex = ElemType(elemCode=C3D8R, elemLibrary=EXPLICIT, secondOrderAccuracy=OFF, hourglassControl=ENHANCED)
e_tet = ElemType(elemCode=C3D4, elemLibrary=EXPLICIT)

log("  Meshing wall...")
wall.seedPart(size=250.0)  # finer mesh: 500mm -> 250mm
try:
    wall.setMeshControls(regions=wall.cells[:], elemShape=HEX)
    wall.setElementType(regions=(wall.cells,), elemTypes=(e_hex,))
    log("  Wall: using C3D8R")
except Exception as e_wall:
    log("  Wall HEX failed: %s, falling back to C3D4" % str(e_wall)[:100])
    wall.setElementType(regions=(wall.cells,), elemTypes=(e_tet,))
    log("  Wall: using C3D4")
wall.generateMesh()
log("  Wall: %d elements, %d nodes" % (len(wall.elements), len(wall.nodes)))

log("  Meshing drone...")
drone.seedPart(size=250.0)  # finer mesh: 500mm -> 250mm
try:
    drone.setMeshControls(regions=drone.cells[:], elemShape=HEX)
    drone.setElementType(regions=(drone.cells,), elemTypes=(e_hex,))
    log("  Drone: using C3D8R")
except Exception as e_drone:
    log("  Drone HEX failed: %s, falling back to C3D4" % str(e_drone)[:100])
    drone.setElementType(regions=(drone.cells,), elemTypes=(e_tet,))
    log("  Drone: using C3D4")
drone.generateMesh()
log("  Drone: %d elements, %d nodes" % (len(drone.elements), len(drone.nodes)))

# ---- Assembly ----
log("[6] Assembly & BCs")
assy = mdl.rootAssembly
assy.DatumCsysByDefault(CARTESIAN)

inst_wall = assy.Instance(name='Wall', part=wall, dependent=ON)
assy.translate(instanceList=('Wall',), vector=(-250.0, 0.0, 0.0))

inst_drone = assy.Instance(name='Drone', part=drone, dependent=ON)
assy.rotate(instanceList=('Drone',), axisPoint=(0.,0.,0.), axisDirection=(0.,1.,0.), angle=90.0)
# Wall Z-extent: 0 to 500mm. Place drone center at z=250.
# Drone flies +X; nose starts at x=-1000, wall front face at x=-250 => 750mm gap
assy.translate(instanceList=('Drone',), vector=(NOSE_X, 0.0, 250.0))

# Fix wall back face and edges
log("  Finding wall fix nodes...")
n_wnodes = len(wall.nodes)
fix_idx = []
for i in range(n_wnodes):
    n = wall.nodes[i:i+1][0]
    x, y, z = n.coordinates[0], n.coordinates[1], n.coordinates[2]
    if (abs(abs(x)-250.0) < 5.0 or abs(abs(z)-10000.0) < 10.0 or abs(abs(y)-2500.0) < 5.0):
        fix_idx.append(i)

log("  Fix nodes: %d" % len(fix_idx))

if fix_idx:
    fix_idx.sort()
    ranges = []; s = e = fix_idx[0]
    for idx in fix_idx[1:]:
        if idx == e+1: e = idx
        else: ranges.append((s, e)); s = e = idx
    ranges.append((s, e))
    rnames = []
    for ri,(s,e) in enumerate(ranges):
        wall.Set(name='_R%d'%ri, nodes=wall.nodes[s:e+1]); rnames.append('_R%d'%ri)
    merged = rnames[0]
    for ri in range(1,len(rnames)):
        wall.SetByBoolean(name='W%d'%ri, sets=[wall.sets[merged], wall.sets[rnames[ri]]], operation=UNION)
        for old in [merged, rnames[ri]]:
            if old in wall.sets: del wall.sets[old]
        merged = 'W%d'%ri
    wall.sets.changeKey(fromName=merged, toName='FixSet')
    mdl.EncastreBC(name='BC_Fix', createStepName='Initial', region=inst_wall.sets['FixSet'])
    log("  Encastre BC applied")

# ---- Collect drone node labels ----
log("[7] Collect drone node labels for INP injection")
drone_labels = []
n_total = len(inst_drone.nodes)
for start in range(0, n_total, 10000):
    end = min(start+10000, n_total)
    for n in inst_drone.nodes[start:end]:
        drone_labels.append(n.label)
log("  Drone instance nodes: %d" % len(drone_labels))

if drone_labels:
    with open('C:/Users/ASUA/OneDrive/Desktop/cc/_drone_nodes.txt', 'w') as f:
        for label in drone_labels:
            f.write('%d\n' % label)
    log("  Written to _drone_nodes.txt")
else:
    log("  WARNING: No drone nodes collected!")

# ---- Step & Contact ----
log("[8] Step, Contact, Output")
mdl.ExplicitDynamicsStep(name='Impact', previous='Initial', timePeriod=STEP_TIME,
                          improvedDtMethod=ON, linearBulkViscosity=0.06)

try:
    mdl.fieldOutputRequests['F-Output-1'].setValues(
        numIntervals=50,
        variables=('S','E','U','V','A','DAMAGEC','DAMAGET','SDEG','STATUS','PEEQ'))
    mdl.historyOutputRequests['H-Output-1'].setValues(
        numIntervals=100,
        variables=('ALLAE','ALLIE','ALLKE','ALLPD','ALLSE','ALLVD','ALLWK','ETOTAL'))
except Exception as e_fo:
    log("FO warning: " + str(e_fo)[:100])

mdl.ContactProperty('GenContact')
mdl.interactionProperties['GenContact'].TangentialBehavior(formulation=FRICTIONLESS)
mdl.interactionProperties['GenContact'].NormalBehavior()
mdl.ContactExp(name='GeneralContact', createStepName='Initial')
mdl.interactions['GeneralContact'].includedPairs.setValuesInStep(stepName='Impact', useAllstar=ON)
try:
    mdl.interactions['GeneralContact'].contactPropertyAssignments.append(
        (('GLOBAL',), mdl.interactionProperties['GenContact']))
except: pass

# ---- Write INP ----
log("[9] Write INP")
job_name = 'Job-DroneImpact'
if job_name in mdb.jobs: del mdb.jobs[job_name]
mdb.Job(name=job_name, model='Drone-Impact',
        description='MQ-1 Drone 600m/s Building Impact',
        type=ANALYSIS, memory=90, memoryUnits=PERCENTAGE,
        explicitPrecision=SINGLE, nodalOutputPrecision=SINGLE,
        numCpus=4, numDomains=4, multiprocessingMode=DEFAULT)
mdb.jobs[job_name].writeInput(consistencyChecking=OFF)

log("")
log("="*70)
log("  MODEL COMPLETE")
log("  Drone nodes for injection: %d" % len(drone_labels))
log("  Run: abaqus job=Job-DroneImpact_patched cpus=4 interactive")
log("="*70)
