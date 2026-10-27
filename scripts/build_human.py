"""Stage 1: create the wasted male body with MPFB (Mixamo rig, body parts, clothes).

Run: Blender -b --python scripts/build_human.py -- <out.blend>
MPFB must be enabled in the user's preferences (do not use --factory-startup).
"""
import bpy, sys, os

from bl_ext.blender_org.mpfb.services import HumanService, AssetService

OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else '/tmp/human_stage1.blend'

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)

info = HumanService._create_default_human_info_dict()
info['name'] = 'Human'
# MakeHuman age: 0.5 = 25 y, 1.0 = 90 y  ->  ~30 y
info['phenotype'] = {
    'gender': 1.0, 'age': 0.54, 'muscle': 0.12, 'weight': 0.02,
    'proportions': 0.55, 'height': 0.55, 'cupsize': 0.5, 'firmness': 0.5,
    'race': {'asian': 0.05, 'caucasian': 0.9, 'african': 0.05},
}
# Gaunt but still "alive" base shape; the corpse face is a separate shape key added later.
info['targets'] = [
    {'target': 'head-fat-decr', 'value': 0.6},
    {'target': 'l-cheek-volume-decr', 'value': 0.5},
    {'target': 'r-cheek-volume-decr', 'value': 0.5},
    {'target': 'l-cheek-bones-incr', 'value': 0.4},
    {'target': 'r-cheek-bones-incr', 'value': 0.4},
    {'target': 'neck-scale-horiz-decr', 'value': 0.4},
]
info['rig'] = 'mixamo'
info['eyes'] = 'high-poly.mhclo'
info['eyebrows'] = 'eyebrow001.mhclo'
info['eyelashes'] = 'eyelashes01.mhclo'
info['teeth'] = 'teeth_base.mhclo'
info['tongue'] = 'tongue01.mhclo'
info['hair'] = 'short02.mhclo'
info['clothes'] = ['male_casualsuit06.mhclo']
info['skin_mhmat'] = 'young_caucasian_male.mhmat'
info['skin_material_type'] = 'ENHANCED_SSS'
info['eyes_material_type'] = 'MAKESKIN'

settings = HumanService.get_default_deserialization_settings()
settings['subdiv_levels'] = 1
basemesh = HumanService.deserialize_from_dict(info, settings)

rig = basemesh.parent
rig.name = rig.data.name = 'HumanRig'
basemesh.name = 'Body'
for ob in bpy.data.objects:
    if ob.type == 'MESH' and ob is not basemesh:
        print('asset', ob.name, len(ob.data.vertices), [m.type for m in ob.modifiers])
print('body verts', len(basemesh.data.vertices), 'shape keys', len(basemesh.data.shape_keys.key_blocks))
print('bones', len(rig.data.bones), [b.name for b in rig.data.bones][:8])

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print('saved', OUT)
