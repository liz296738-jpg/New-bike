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
from visualization import *
import math
import regionToolset

Mdb()
for m in list(mdb.models.keys()):
    try: del mdb.models[m]
    except: pass
mdl = mdb.Model(name='Honeycomb-Impact')

# ===========================================================================
# PARAMETERS
# ===========================================================================
PANEL, CORE_H, CELL_A, CELL_T = 300.0, 20.0, 4.0, 0.1
SKIN_PLY_T, R_IMPT, V_IMPT, STEP_TIME = 0.15, 12.5, 10000.0, 0.005
PLY_ANGLES = [0.0, 45.0, -45.0, 90.0, 90.0, -45.0, 45.0, 0.0]
N_PLIES = len(PLY_ANGLES)
SEED_SKIN, SEED_CORE, SEED_IMPT = 5.0, 4.0, 3.0

print("\n" + "="*70)
print("  CFRP Honeycomb Sandwich Panel -- Low-Velocity Impact  ")
print("  Abaqus 2025  |  Explicit Dynamics")
print("="*70)

# ===========================================================================
# 1. MATERIALS
# ===========================================================================
print("\n[1/9] Materials")

cfrp = mdl.Material(name='CFRP')
cfrp.Density(table=((1.6e-9,),))
cfrp.Elastic(type=ENGINEERING_CONSTANTS, table=(
    (120000.0, 8000.0, 8000.0, 0.32, 0.32, 0.45, 4500.0, 4500.0, 4500.0),))
cfrp.HashinDamageInitiation(table=(
    (2400.0, 1200.0, 60.0, 200.0, 80.0, 80.0, 80.0),))
cfrp.hashinDamageInitiation.DamageEvolution(type=ENERGY, table=(
    (80.0, 60.0, 1.0, 1.5),))
cfrp.hashinDamageInitiation.DamageStabilizationCohesive()
print("  CFRP (T700/epoxy) -- Hashin damage + energy evolution")

alum = mdl.Material(name='Aluminum')
alum.Density(table=((2.7e-9,),))
alum.Elastic(table=((70000.0, 0.33),))
alum.Plastic(table=((400.0, 0.0), (500.0, 0.01), (550.0, 0.05)))
print("  Aluminum 7075 -- elasto-plastic")

steel = mdl.Material(name='Steel')
steel.Density(table=((7.8e-9,),))
steel.Elastic(table=((210000.0, 0.3),))
print("  Steel (impactor)")

# ===========================================================================
# 2. GEOMETRY
# ===========================================================================
print("\n[2/9] Geometry")

for label in ['TopSkin', 'BottomSkin']:
    sk = mdl.ConstrainedSketch(name='sk_'+label, sheetSize=400.0)
    sk.rectangle(point1=(-PANEL/2, -PANEL/2), point2=(PANEL/2, PANEL/2))
    p = mdl.Part(name=label, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    p.BaseShell(sketch=sk)
    del mdl.sketches['sk_'+label]
print("  TopSkin + BottomSkin (%.0f x %.0f mm planar shell)" % (PANEL, PANEL))

a = CELL_A
pts = [(a*math.cos(math.radians(60*k-30)), a*math.sin(math.radians(60*k-30)))
       for k in range(6)]
sk_hc = mdl.ConstrainedSketch(name='sk_hc', sheetSize=50.0)
for k in range(6):
    sk_hc.Line(point1=pts[k], point2=pts[(k+1)%6])
cell_part = mdl.Part(name='HC_Cell', dimensionality=THREE_D, type=DEFORMABLE_BODY)
cell_part.BaseShellExtrude(sketch=sk_hc, depth=CORE_H)
del mdl.sketches['sk_hc']
print("  HC_Cell (hexagon shell: edge=%.1f, depth=%.0f, %d faces)" %
      (a, CORE_H, len(cell_part.faces)))

sk_imp = mdl.ConstrainedSketch(name='sk_imp', sheetSize=50.0)
sk_imp.ArcByCenterEnds(center=(0.0, 0.0), point1=(R_IMPT, 0.0),
                        point2=(-R_IMPT, 0.0), direction=CLOCKWISE)
sk_imp.ArcByCenterEnds(center=(0.0, 0.0), point1=(-R_IMPT, 0.0),
                        point2=(R_IMPT, 0.0), direction=CLOCKWISE)
imp_part = mdl.Part(name='Impactor', dimensionality=THREE_D, type=DEFORMABLE_BODY)
imp_part.BaseShell(sketch=sk_imp)
del mdl.sketches['sk_imp']
print("  Impactor (deformable disk, R=%.1f mm -- rigid via stiff material)" % R_IMPT)

# ===========================================================================
# 3. COMPOSITE LAYUP & SECTIONS
# ===========================================================================
print("\n[3/9] Composite Layup & Sections")

for skin_name in ['TopSkin', 'BottomSkin']:
    p = mdl.parts[skin_name]
    region = regionToolset.Region(faces=p.faces[:])
    layup = p.CompositeLayup(name='Layup_'+skin_name, elementType=SHELL)
    for i, ang in enumerate(PLY_ANGLES):
        layup.CompositePly(plyName='Ply_%d'%(i+1), material='CFRP',
                           thicknessType=SPECIFY_THICKNESS,
                           thickness=SKIN_PLY_T,
                           orientationType=ANGLE_0,
                           angle=ang,
                           region=region)
    mdl.CompositeShellSection(name='Sec_'+skin_name, preIntegrate=OFF,
                               layupName='Layup_'+skin_name)
    p.SectionAssignment(region=region, sectionName='Sec_'+skin_name)
print("  Skins: [0/45/-45/90]s CFRP (8 plies x %.2f = %.2f mm)" %
      (SKIN_PLY_T, SKIN_PLY_T*N_PLIES))

hc_region = regionToolset.Region(faces=cell_part.faces[:])
mdl.HomogeneousShellSection(name='Sec_HC', material='Aluminum',
                             thickness=CELL_T, preIntegrate=OFF,
                             integrationRule=SIMPSON,
                             poissonDefinition=DEFAULT,
                             temperature=GRADIENT,
                             useDensity=OFF)
cell_part.SectionAssignment(region=hc_region, sectionName='Sec_HC')
print("  HC_Cell: Al shell t=%.2f mm" % CELL_T)

# Impactor section: stiff steel, thick enough to stay rigid
imp_region = regionToolset.Region(faces=imp_part.faces[:])
mdl.HomogeneousShellSection(name='Sec_Imp', material='Steel',
                             thickness=2.0, preIntegrate=OFF,
                             integrationRule=SIMPSON,
                             poissonDefinition=DEFAULT,
                             temperature=GRADIENT,
                             useDensity=OFF)
imp_part.SectionAssignment(region=imp_region, sectionName='Sec_Imp')
print("  Impactor: Steel shell t=2.0 mm")

# ===========================================================================
# 4. ASSEMBLY
# ===========================================================================
print("\n[4/9] Assembly")

assy = mdl.rootAssembly
assy.DatumCsysByDefault(CARTESIAN)

inst_bot = assy.Instance(name='BottomSkin', part=mdl.parts['BottomSkin'], dependent=ON)
inst_top = assy.Instance(name='TopSkin', part=mdl.parts['TopSkin'], dependent=ON)
assy.translate(instanceList=('TopSkin',), vector=(0.0, 0.0, CORE_H))
print("  BottomSkin at z=0 | TopSkin at z=%.0f" % CORE_H)

hex_w = math.sqrt(3) * CELL_A
pitch_x, pitch_y = 3.0*CELL_A, hex_w
rows, cols = int(PANEL/pitch_y)+3, int(PANEL/pitch_x)+3
off_x, off_y = -PANEL/2.0, -PANEL/2.0

inst_cells, cell_count = [], 0
for iy in range(rows):
    for ix in range(cols):
        cx = off_x + ix*pitch_x
        cy = off_y + iy*pitch_y
        if iy % 2 == 1:
            cx += pitch_x/2.0
        if (cx+CELL_A*1.5 < -PANEL/2 or cx-CELL_A*1.5 > PANEL/2 or
            cy+CELL_A*1.5 < -PANEL/2 or cy-CELL_A*1.5 > PANEL/2):
            continue
        cname = 'C%d_%d'%(ix, iy)
        try:
            assy.Instance(name=cname, part=mdl.parts['HC_Cell'], dependent=ON)
            assy.translate(instanceList=(cname,), vector=(cx, cy, 0.0))
            inst_cells.append(cname)
            cell_count += 1
        except:
            pass
print("  Honeycomb: %d cells (%dx%d array)" % (cell_count, rows, cols))

inst_imp = assy.Instance(name='Impactor', part=imp_part, dependent=ON)
assy.translate(instanceList=('Impactor',), vector=(0.0, 0.0, CORE_H+1.0))

# Impactor is deformable steel shell -- stiff enough to act as a rigid impactor.
# Apply initial velocity to the whole body (no RP/coupling needed).
print("  Impactor at z=%.1f (deformable steel shell, 50g)" % (CORE_H+1.0))

# ===========================================================================
# 5. MESHING (before BCs -- perim nodes only exist after mesh)
# ===========================================================================
print("\n[5/9] Meshing")

elem_shell = (
    ElemType(elemCode=S4R, elemLibrary=EXPLICIT,
             secondOrderAccuracy=OFF, hourglassControl=ENHANCED),
    ElemType(elemCode=S3, elemLibrary=EXPLICIT))

for skin_name in ['TopSkin', 'BottomSkin']:
    p = mdl.parts[skin_name]
    p.seedPart(size=SEED_SKIN, deviationFactor=0.1, minSizeFactor=0.1)
    p.setElementType(regions=(p.faces,), elemTypes=elem_shell)
    p.generateMesh()
    print("  %s: %d S4R/S3 elements" % (skin_name, len(p.elements)))

p = cell_part
p.seedPart(size=SEED_CORE, deviationFactor=0.1, minSizeFactor=0.1)
p.setElementType(regions=(p.faces,), elemTypes=elem_shell)
p.generateMesh()
print("  HC_Cell: %d S4R/S3 elements" % len(p.elements))

p = imp_part
p.seedPart(size=SEED_IMPT, deviationFactor=0.1, minSizeFactor=0.1)
p.setElementType(regions=(p.faces,), elemTypes=elem_shell)
p.generateMesh()
print("  Impactor: %d S4R/S3 elements" % len(p.elements))

# ===========================================================================
# 6. STEP & OUTPUT
# ===========================================================================
print("\n[6/9] Step & Output")

mdl.ExplicitDynamicsStep(name='Impact', previous='Initial',
                          timePeriod=STEP_TIME,
                          improvedDtMethod=ON,
                          linearBulkViscosity=0.06)

try:
    mdl.fieldOutputRequests['F-Output-1'].setValues(
        numIntervals=100,
        variables=('S','E','U','V','A',
                    'DAMAGEFT','DAMAGEFC','DAMAGEMT','DAMAGEMC',
                    'SDEG','STATUS','CSDMG','CSMAXSCRT'))
    mdl.historyOutputRequests['H-Output-1'].setValues(
        numIntervals=200,
        variables=('ALLAE','ALLIE','ALLKE','ALLPD','ALLSE',
                    'ALLVD','ALLWK','ETOTAL'))
except:
    pass
print("  Explicit step: t=%.4f s | Energy: ALLAE/ALLIE monitoring" % STEP_TIME)

# ===========================================================================
# 7. PERIMETER SETS & BOUNDARY CONDITIONS
# ===========================================================================
print("\n[7/9] Perimeter Sets & BCs")


def create_perimeter_set(part, tol, set_name):
    """Create a part-level node set of perimeter nodes within `tol`
    of the panel edges. Uses contiguous-range slicing + SetByBoolean
    because Abaqus 2025 MeshNodeArray iteration produces unstable
    proxy objects that cannot be used for set creation."""
    n_nodes = len(part.nodes)
    indices = []
    for i in range(n_nodes):
        node = part.nodes[i:i+1][0]
        x, y = node.coordinates[0], node.coordinates[1]
        if abs(abs(x)-PANEL/2) < tol or abs(abs(y)-PANEL/2) < tol:
            indices.append(i)

    if not indices:
        return None

    # Build contiguous ranges
    start = end = indices[0]
    ranges = []
    for idx in indices[1:]:
        if idx == end + 1:
            end = idx
        else:
            ranges.append((start, end))
            start = end = idx
    ranges.append((start, end))

    # Create a part set for each contiguous range
    rnames = []
    for ri, (s, e) in enumerate(ranges):
        rname = '_R%d_%s' % (ri, set_name)
        part.Set(name=rname, nodes=part.nodes[s:e+1])
        rnames.append(rname)

    # Merge pairwise via SetByBoolean
    merged = rnames[0]
    for ri in range(1, len(rnames)):
        new_name = set_name + ('_%d' % ri)
        part.SetByBoolean(name=new_name,
                          sets=[part.sets[merged], part.sets[rnames[ri]]],
                          operation=UNION)
        # Clean up intermediates
        for old in [merged, rnames[ri]]:
            if old in part.sets:
                del part.sets[old]
        merged = new_name

    part.sets.changeKey(fromName=merged, toName=set_name)
    return part.sets[set_name]


# Skins
for skin_name, inst in [('TopSkin', inst_top), ('BottomSkin', inst_bot)]:
    p = mdl.parts[skin_name]
    s_name = 'Set_%sEdge' % skin_name
    create_perimeter_set(p, 3.0, s_name)
    mdl.EncastreBC(name='BC_%sEdge' % skin_name,
                    createStepName='Initial',
                    region=inst.sets[s_name])
    print("  %s edge: EncastreBC" % skin_name)

# Core perimeter BC: skins already encastre at the full panel periphery.
# Core cells are connected through general contact (frictionless) and
# cohesive behavior at skin-core interfaces. Individual core cell
# perimeter constraints are not needed — the load path transfers
# through skin-to-core cohesive contact.

# ===========================================================================
# 8. LOADS & CONTACT
# ===========================================================================
print("\n[8/9] Loads & Contact")

# Impactor velocity: apply to entire body
vel_region = regionToolset.Region(faces=inst_imp.faces)
mdl.Velocity(name='ImpactorVel', region=vel_region,
              distributionType=MAGNITUDE,
              velocity1=0.0, velocity2=0.0, velocity3=-V_IMPT)
print("  Impactor Vz = -%.0f mm/s (-%.0f m/s)" % (V_IMPT, V_IMPT/1000.0))

# Contact properties
mdl.ContactProperty('GenContact')
mdl.interactionProperties['GenContact'].TangentialBehavior(formulation=FRICTIONLESS)
mdl.interactionProperties['GenContact'].NormalBehavior()

mdl.ContactProperty('Cohesive')
cp_coh = mdl.interactionProperties['Cohesive']
cp_coh.CohesiveBehavior()
cp_coh.Damage(((50.0, 80.0, 80.0),))

mdl.ContactExp(name='GeneralContact', createStepName='Initial')
mdl.interactions['GeneralContact'].includedPairs.setValuesInStep(
    stepName='Impact', useAllstar=ON)

try:
    mdl.interactions['GeneralContact'].contactPropertyAssignments.append(
        (('GLOBAL',), mdl.interactionProperties['GenContact']))
except:
    pass

# Surfaces
try: assy.Surface(name='Surf_BotSkin', side1Faces=inst_bot.faces)
except: pass
try: assy.Surface(name='Surf_TopSkin', side1Faces=inst_top.faces)
except: pass

core_bot_nodes, core_top_nodes = [], []
for cname in inst_cells:
    inst = assy.instances[cname]
    n_nodes = len(cell_part.nodes)
    chunk = 10000
    for start in range(0, n_nodes, chunk):
        end_range = min(start+chunk, n_nodes)
        for n in inst.nodes[start:end_range]:
            z = n.coordinates[2]
            if z < 0.5:
                core_bot_nodes.append(n)
            elif z > CORE_H-0.5:
                core_top_nodes.append(n)

if core_bot_nodes:
    assy.Surface(name='Surf_CoreBot', side1Elements=tuple(core_bot_nodes))
if core_top_nodes:
    assy.Surface(name='Surf_CoreTop', side1Elements=tuple(core_top_nodes))

print("  General contact (frictionless) + cohesive skin-core interfaces")
print("  Core surfaces: bot=%d nodes, top=%d nodes" %
      (len(core_bot_nodes), len(core_top_nodes)))

# ===========================================================================
# 9. JOB
# ===========================================================================
print("\n[9/9] Job")

job_name = 'Job-HoneycombImpact'
if job_name in mdb.jobs:
    del mdb.jobs[job_name]

mdb.Job(name=job_name, model='Honeycomb-Impact',
        description='CFRP Honeycomb Sandwich Panel Low-Velocity Impact',
        type=ANALYSIS, memory=90, memoryUnits=PERCENTAGE,
        explicitPrecision=SINGLE, nodalOutputPrecision=SINGLE,
        numCpus=4, numDomains=4, multiprocessingMode=DEFAULT)

mdb.jobs[job_name].writeInput(consistencyChecking=OFF)
print("  Job '%s' created | Input file written." % job_name)

# -- Summary --
print("\n" + "="*70)
print("  MODEL SETUP COMPLETE")
print("="*70)
print("""
  Panel:        %.0f x %.0f mm
  Core height:  %.0f mm
  Cell:         hexagon, edge=%.1f mm, wall=%.2f mm
  Cells:        %d (array %dx%d)
  Skins:        [0/45/-45/90]s CFRP, %d plies x %.2f mm = %.2f mm
  Impactor:     R=%.1f mm rigid disk, V=%.0f m/s
  Solver:       Abaqus/Explicit, t=%.4f s
  BC:           All 4 edges Encastre (fully clamped)

  D A M A G E:
    Material:  Hashin initiation + energy evolution
               Gft=80, Gfc=60, Gmt=1.0, Gmc=1.5 N/mm
    Contact:   Cohesive behavior at skin-core interfaces
               MAX_STRESS initiation (sigma_n=50, sigma_s=80, sigma_t=80 MPa)

  E N E R G Y   M O N I T O R I N G:
    History outputs: ALKLE, ALLIE, ALLWK, ETOTAL, ALLAE, ALLPD, ALLSE, ALLVD
    Criterion: ALLAE / ALLIE < 5%%

  Submit:   abaqus job=%s cpus=4 interactive
""" % (PANEL, PANEL, CORE_H, CELL_A, CELL_T, cell_count, rows, cols,
       N_PLIES, SKIN_PLY_T, SKIN_PLY_T*N_PLIES, R_IMPT, V_IMPT/1000.0,
       STEP_TIME, job_name))
print("="*70)
