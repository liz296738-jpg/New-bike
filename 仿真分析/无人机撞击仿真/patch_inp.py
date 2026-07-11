import re

INP_IN  = r'C:\Users\ASUA\OneDrive\Desktop\cc\Job-DroneImpact.inp'
INP_OUT = r'C:\Users\ASUA\OneDrive\Desktop\cc\Job-DroneImpact_patched.inp'
NODES_FILE = r'C:\Users\ASUA\OneDrive\Desktop\cc\_drone_nodes.txt'
V_DRONE = 600000.0

print("="*70)
print("  INP Patcher: Inject Initial Velocity")
print("="*70)

with open(NODES_FILE, 'r') as f:
    drone_labels = [line.strip() for line in f if line.strip()]
print("Drone nodes: %d" % len(drone_labels))

with open(INP_IN, 'r') as f:
    inp = f.read()

# ========== 1) Insert DroneSet before *End Assembly ==========
# Build *Nset with comma-separated labels, 8 per line
lines = []
per_line = 8
for i in range(0, len(drone_labels), per_line):
    chunk = drone_labels[i:i+per_line]
    s = ', '.join(chunk)
    if i + per_line < len(drone_labels):
        s += ','
    lines.append(s)

# The labels are instance-local (Drone part node labels).
# In dependent instances, Abaqus assigns assembly node labels differently.
# Let me verify: in the INP, assembly node numbers start from the wall part.
# The drone instance nodes will have instance-prefixed labels.
#
# Actually with dependent ON, nodes are assembly-level numbers.
# The part nodes of Wall = 1..902, then Drone = 903..(902+119)=1021
#
# Check: how does INP reference nodes after *End Instance?
# In Abaqus with dependent instances, part nodes are separate.
# Assembly-level references use instance-qualified names.
#
# But for *Nset at assembly level with dependent instances,
# the node labels are internal assembly labels.
#
# Let me look at the actual INP to understand numbering.
# The *_PickedSet2* Nset uses "generate" which means:
# *Nset, nset=_PickedSet2, internal, generate
#  1, 902, 1
# This references nodes 1-902 (wall part nodes, since dependent=ON).

# For dependent instances at assembly level:
# *Initial Conditions requires the assembly node set name.
# But *Nset in assembly uses internal numbering.
# Since dependent=ON, drone part nodes might have their own numbering
# (1..119) that maps through the instance.
#
# Actually, for *Initial Conditions, we need to create an
# assembly-level Nset. With dependent instances, the node labels
# in the Drone instance context might be different.

# Let me check if there's a better way: inject *Initial Conditions
# in the Drone *Instance block using the part's node numbering.
#
# In dependent mode:
# *Instance, name=Drone, part=Drone
# -> Uses part-level node numbers for element/node definitions
# -> Assembly-level references use "Drone.n" qualified names
#
# For *Initial Conditions at assembly level:
# We need to define a *Nset in the assembly that uses
# instance-qualified node references: Drone.1, Drone.2, etc.
# OR use the "internal" numbering with generate.

# Best approach: create assembly-level Nset using
# instance.part_node format
drone_nodes_str = '\n** Drone instance node set\n'
drone_nodes_str += '*Nset, nset=DroneSet, instance=Drone\n'
lines = []
for i in range(0, len(drone_labels), per_line):
    chunk = drone_labels[i:i+per_line]
    s = ', '.join(chunk)
    if i + per_line < len(drone_labels):
        s += ','
    lines.append(s)
drone_nodes_str += '\n'.join(lines) + '\n'

# Also need element set for Drone if elements referenced
# But for initial velocity only nodes are needed

droneset_block = '** Drone node set for initial velocity\n'
droneset_block += '*Nset, nset=DroneSet, instance=Drone\n'
lines2 = []
for i in range(0, len(drone_labels), per_line):
    chunk = drone_labels[i:i+per_line]
    s = ', '.join(chunk)
    if i + per_line < len(drone_labels):
        s += ','
    lines2.append(s)
droneset_block += '\n'.join(lines2) + '\n'

# Insert before *End Assembly
inp = inp.replace('*End Assembly', droneset_block + '*End Assembly', 1)
print("Inserted DroneSet (instance=Drone) before *End Assembly")

# ========== 2) Insert Initial Conditions ==========
iv_block = (
    '** ----------------------------------------------------------------\n'
    '** INITIAL CONDITIONS - DRONE VELOCITY\n'
    '*Initial Conditions, type=VELOCITY\n'
    'DroneSet, 1, %.1f\n'
    'DroneSet, 2, 0.0\n'
    'DroneSet, 3, 0.0\n'
    '**\n'
) % V_DRONE

step_marker = '** STEP: Impact'
inp = inp.replace(step_marker, iv_block + step_marker, 1)
print("Inserted Initial Conditions before STEP: Impact")

with open(INP_OUT, 'w') as f:
    f.write(inp)

print("Patched INP: %s" % INP_OUT)

# Verify
with open(INP_OUT, 'r') as f:
    patched = f.read()
has_droneset = 'DroneSet' in patched
has_iv = 'Initial Conditions' in patched and 'VELOCITY' in patched
print("  DroneSet present: %s" % has_droneset)
print("  Initial Conditions present: %s" % has_iv)

# Show relevant sections
for line in patched.split('\n'):
    if 'DroneSet' in line or 'Initial Conditions' in line or 'VELOCITY' in line:
        print("    %s" % line.strip())
