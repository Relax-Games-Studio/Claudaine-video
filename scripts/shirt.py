"""Keep the skin under the shirt.

In some poses (the slumped outro above all) the subdivided body comes out through the subdivided shirt around
the collar and the chest. A Shrinkwrap on the body, right after its Subdivision (before it, the smoothing brings
the skin at the collarbone back out by 5 mm), projects the skin the shirt covers along its normal onto the cloth
and keeps it OFFSET inside. Projecting along the normal (not to the nearest point) leaves the skin at the openings
alone: its nearest cloth point is the hem, which would pull it in."""
import bpy
from mathutils.bvhtree import BVHTree

OFFSET = 0.003          # skin kept this far inside the cloth
REACH = 0.04            # rest pose: skin counts as covered when the cloth is this close along its normal
LIMIT = 0.02            # animated: the projection looks this far either way


def covered(rig, body, clothes):
    """body vertices the shirt covers at the rest pose (shape keys on, no modifiers): a ray along the skin
    normal, outward or inward, meets the cloth from its inner side within REACH"""
    pose = rig.data.pose_position
    rig.data.pose_position = 'REST'
    saved = [(m, m.show_viewport) for ob in (body, clothes) for m in ob.modifiers]
    for m, _ in saved:
        m.show_viewport = False
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()

    def world(ob):
        e = ob.evaluated_get(dg)
        me = e.to_mesh()
        mw = e.matrix_world
        R = mw.to_3x3()
        r = ([mw @ v.co for v in me.vertices], [(R @ v.normal).normalized() for v in me.vertices],
             [tuple(p.vertices) for p in me.polygons])
        e.to_mesh_clear()
        return r

    bco, bno, _ = world(body)
    cco, _, cps = world(clothes)
    for m, s in saved:
        m.show_viewport = s
    rig.data.pose_position = pose
    bpy.context.view_layer.update()
    bvh = BVHTree.FromPolygons(cco, cps)
    ids = set()
    for i, (p, n) in enumerate(zip(bco, bno)):
        for d in (n, -n):
            hit = bvh.ray_cast(p, d, REACH)
            if hit[0] is not None and hit[1].dot(n) > 0.3:      # the cloth faces the same way as the skin
                ids.add(i)
                break
    # two more rings, so the subdivision does not fade the weight out on skin the shirt still covers
    # (skin the cloth is not over is left alone by the projection anyway)
    for _ in range(2):
        ids |= {v for e in body.data.edges for v in e.vertices if e.vertices[0] in ids or e.vertices[1] in ids}
    return sorted(ids)


def setup(rig, body, clothes):
    ids = covered(rig, body, clothes)
    g = body.vertex_groups.new(name='UnderShirt')
    g.add(ids, 1.0, 'REPLACE')
    sw = body.modifiers.new('KeepUnderShirt', 'SHRINKWRAP')
    sw.target = clothes
    sw.vertex_group = g.name
    sw.wrap_method = 'PROJECT'
    sw.use_negative_direction = sw.use_positive_direction = True
    sw.cull_face = 'OFF'
    sw.project_limit = LIMIT
    sw.wrap_mode = 'INSIDE'
    sw.offset = OFFSET
    body.modifiers.move(len(body.modifiers) - 1, [m.type for m in body.modifiers].index('SUBSURF') + 1)
    return len(ids)
