"""Download Poly Haven assets (CC0) into assets/polyhaven/{models,textures,hdris}."""
import json, os, sys, urllib.request, concurrent.futures as cf

ROOT = os.path.join(os.path.dirname(__file__), '..', 'assets', 'polyhaven')
API = 'https://api.polyhaven.com/files/'

MODELS = """street_lamp_01 street_lamp_02 fire_hydrant water_manhole_cover metal_trash_can covered_car
garden_gnome utility_box_01 exterior_aircon_unit shrub_01 shrub_02 shrub_04 potted_plant_01 painted_wooden_bench
side_table_tall_01 hanging_picture_frame_01 hanging_picture_frame_02 hanging_picture_frame_03 potted_plant_02
modern_ceiling_lamp_01 wall_clock steel_frame_shelves_01 cardboard_box_01 trashbag old_tyre modular_pipes
mounted_fluorescent_lights plastic_crate_01 wooden_ladder street_rat desk_lamp_arm_01 metal_office_desk
cigarette_pack can_rusted plastic_bottle_gallon medical_box medical_tape round_spectacles power_box_01
modular_electric_cables gamepad pine_tree_01 fir_tree_01 tree_small_02 planter_box_01 sofa_02 television_02
gaming_console throw_pillows_01 dining_chair_02 side_table_01 steel_frame_shelves_02 plastic_crate_02 metal_jerrycan
lightbulb_01 pull_chain_light_socket utility_box_02 security_light old_gas_mask wooden_crate_01""".split()
TEXTURES = """asphalt_02 concrete_pavement sparse_grass weathered_plank_siding white_planks_clean wood_floor
plastered_wall concrete_floor_worn_001 concrete_block_wall stair_planks grey_roof_01 painted_concrete
dirty_concrete wood_peeling_paint_weathered""".split()
HDRIS = {'moonless_golf': '2k', 'preller_drive': '4k'}
TEX_MAPS = {'Diffuse': 'jpg', 'nor_gl': 'jpg', 'Rough': 'jpg', 'Displacement': 'png', 'AO': 'jpg'}
UA = {'User-Agent': 'claudaine-pipeline/1.0 (Blender asset fetch)'}

def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA))

def get(url, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + '.part'
    with fetch(url) as r, open(tmp, 'wb') as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, dst)
    return os.path.getsize(dst)

def files(asset):
    with fetch(API + asset) as r:
        return json.load(r)

def jobs():
    for m in MODELS:
        f = files(m)
        b = f['blend']['2k']['blend']
        d = os.path.join(ROOT, 'models', m)
        yield b['url'], os.path.join(d, os.path.basename(b['url']))
        for rel, inc in b.get('include', {}).items():
            yield inc['url'], os.path.join(d, rel)
    for t in TEXTURES:
        f = files(t)
        for mp, fmt in TEX_MAPS.items():
            if mp in f and '2k' in f[mp] and fmt in f[mp]['2k']:
                u = f[mp]['2k'][fmt]['url']
                yield u, os.path.join(ROOT, 'textures', t, os.path.basename(u))
    for h, res in HDRIS.items():
        f = files(h)
        u = f['hdri'][res]['hdr']['url']
        yield u, os.path.join(ROOT, 'hdris', os.path.basename(u))

if __name__ == '__main__':
    todo = list(jobs())
    print(len(todo), 'files', flush=True)
    total = 0
    with cf.ThreadPoolExecutor(8) as ex:
        for n in ex.map(lambda a: get(*a), todo):
            total += n
    print('downloaded MB', round(total / 1e6, 1))
