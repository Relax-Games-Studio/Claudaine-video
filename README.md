# Claudaine: a nu-metal music video Claude built in Blender

**Watch:** https://youtu.be/u99amKAGWsE (3:39, 4K) · Short: https://youtube.com/shorts/8XChj2QFHuo

"Claudaine" is a nu-metal song about being addicted to Claude. Claude wrote the lyrics, and in Claude Code it wrote all of
the code in this repo: about 10,500 lines of Python that build the whole video in Blender.

There is no camera, no image or video generator and no hand animation. The scripts model a suburban street, a house and
a basement. In the basement a man turning into a mummy sits at six monitors on an IV drip, and monsters crawl out of the
screens. The scripts animate it all, cut the camera to the song's measured beat grid, draw every screen frame by frame
with Pillow and render 5,253 frames (EEVEE for most of the video, Cycles for the finale). An ffmpeg pass then adds the
glitches, flashes, grain and title card. The song audio was generated with Suno from Claude's lyrics. It is not
included here.

This repo is the source of that one video, not a general tool. Frame numbers, shots and lyric timings are hard-coded for
this song. It is most useful to read: to see how far "Claude, make a music video in Blender" can go, or to borrow a
piece of it.

## What's here

| Path | What |
|---|---|
| `scripts/` | The pipeline: scene builders, screen generator, camera, render and post scripts |
| `short/` | The 9:16 Short cut from the same scene (`edit.py` holds the edit) |
| `youtube/` | Thumbnails for the A/B test and a ~32 s teaser |
| `docs/` | `SPEC.md` (technical spec) and `TREATMENT.md` (shot-by-shot treatment): the plan Claude worked from, in Russian |
| `blend/mouse_grip.json` | The solved hand-on-mouse grip, kept so that `build_scene.py` runs before `solve_grip.py` can |

Not here: the song, third-party assets, `.blend` files and renders. You download the assets yourself (below), and the
scripts build the rest.

## Requirements

- macOS on Apple silicon. Cycles renders on the Metal GPU, and the screen and title scripts load macOS system fonts
  (Menlo, SF, Apple Symbols, Impact).
- [Blender 5.2.1 LTS](https://www.blender.org/download/) with the
  [MPFB extension](https://extensions.blender.org/add-ons/mpfb/) enabled in your preferences.
- Python 3 with `numpy` and `Pillow`.
- `ffmpeg` and `ffprobe` on `PATH`, or set `FFMPEG` / `FFPROBE` to their paths.
- Disk: ~3.5 GB of assets. A 4K render adds ~3.5 GB of JPEG frames and a ~10 GB master video.
- The video was rendered on a Mac with 36 GB of RAM. Two scripts exist only because of that limit: `tex8.py` and the
  50-frame Cycles chunks in `render_all.sh` (see [Lessons](#lessons)).

## Assets you download

All paths are relative to the repo root.

1. **The song**, as `Claudaine.mp3`. It isn't distributed here. Without it, `gen_screens.py` (which reads the beat from
   it) and `post.py` (which muxes it) won't run, and any other song would need its own timings.
2. **Poly Haven** models, textures and HDRIs (CC0), about 2.4 GB:
   `python3 scripts/ph_download.py` puts them in `assets/polyhaven/`.
3. **MakeHuman asset packs** (CC0) for MPFB:
   [MakeHuman system assets](https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html),
   [Skins 02](https://static.makehumancommunity.org/assets/assetpacks/skins02.html) and
   [Glasses 01](https://static.makehumancommunity.org/assets/assetpacks/glasses01.html).
   Install each zip through MPFB, which loads asset packs from zip files.
4. **Mixamo** FBX files in `assets/mixamo/`. Adobe's terms don't allow redistributing them, so download them from
   [mixamo.com](https://www.mixamo.com/) (FBX Binary; the retarget expects 30 fps):
   - The typist, all on the X Bot character: `human_typing.fbx`, `human_seated_idle.fbx`, `human_sit_to_type.fbx`.
   - The monsters, one Mixamo creature each, an idle clip "With Skin" plus a roar or scream clip of the same creature:
     `mutant_idle_skin` + `mutant_roar`, `warrok_idle_skin` + `warrok_roar`, `parasite_idle_skin` + `parasite_scream`,
     `maw_idle_skin` + `maw_roar`, `demon_idle_skin` + `demon_roar`, `skeleton_idle_skin` + `skeleton_scream`.
5. **UnifrakturCook Bold** (SIL OFL) from [Google Fonts](https://fonts.google.com/specimen/UnifrakturCook), as
   `assets/fonts/UnifrakturCook-Bold.ttf`. It sets the title card.

## Build

Run from the repo root, in this order. Every step writes a file that a later one reads.

```bash
BL=/Applications/Blender.app/Contents/MacOS/Blender

python3 scripts/ph_download.py           # Poly Haven -> assets/polyhaven/
python3 scripts/gen_keycaps.py           # keycap legends -> assets/keycaps_atlas.png
python3 scripts/gen_screens.py encode    # 6 monitor videos + phone + per-frame screen light -> screens/

$BL -b --factory-startup --python scripts/build_env.py                      # street, house, basement -> blend/env.blend
# the human: MPFB has to be enabled, so no --factory-startup for stages 1 and 3
$BL -b --python scripts/build_human.py -- blend/human_stage1.blend          # body, clothes, Mixamo rig
$BL -b blend/human_stage1.blend --python scripts/build_human_anim.py -- blend/human_stage2.blend   # retarget, Tremor loop
$BL -b blend/human_stage2.blend --python scripts/build_human_look.py -- blend/human.blend          # corpse face, skin, glasses
$BL -b --factory-startup --python scripts/build_monsters.py                 # -> blend/monsters.blend

$BL -b blend/env.blend --python scripts/build_scene.py                      # everything together -> blend/claudaine.blend
$BL -b blend/claudaine.blend --python scripts/tex8.py                       # 8-bit texture copies -> assets/tex8/

zsh scripts/render_all.sh                # frames + post -> renders/Claudaine_clip.mp4
```

`render_all.sh` can resume: frames already on disk are skipped, so after a stop just run it again. Options are
environment variables:

```bash
RES=1280x720 FMT=JPEG TAG=_720p EEVEE_SAMPLES=16 zsh scripts/render_all.sh   # quick 720p pass
RES=3840x2160 FMT=JPEG TAG=_4k zsh scripts/render_all.sh                     # 4K, JPEG q95 (PNG would be ~60 GB)
```

`BLENDER` overrides the Blender path. `scripts/storyboard.py` renders a few low-quality frames to check the framing
before a long render.

## Make your own

Rendering this exact video won't get you far: the song isn't here and every timing belongs to it. The easier route is
the way this one was made. Open Claude Code in a folder with your song and give it this repo as a reference, for
example:

```
Read https://github.com/Relax-Games-Studio/Claudaine-video. Make a music video for song.mp3 the same way:
measure the beat grid from the audio, write a treatment, then build every scene in Blender with Python scripts.
```

Good places to start reading: `docs/` (the plan), `scripts/camera_rig.py` (cuts on the beat) and
`scripts/gen_screens.py` (the animated screens).

## How it fits together

- **Plan.** `docs/TREATMENT.md` describes every shot against the song. `docs/SPEC.md` fixes the shared rules: 24 fps,
  frame `f` = time `(f - 1) / 24`, the beat grid, axes, where the workstation stands and which monitor shows what.
- **Environment.** `build_env.py` builds the street, house, hallway, stairs and basement. `lib_build.py` holds the
  helpers (meshes, UVs, materials, Poly Haven appends).
- **Workstation.** `desk.py` builds the desk, six monitors, keyboard, mouse, chair, syringes, puddles and IV stand.
  `keyboard_layout.py` is the ANSI layout shared with `gen_keycaps.py`. `drop.py` is the slow-motion drop from the syringe.
- **The human.** Three stages: `build_human.py` (MPFB body), `build_human_anim.py` (Mixamo retarget plus a procedural
  tremor), `build_human_look.py` (corpse shape keys, drying skin, glasses). `build_scene.py` then adds `hair.py`
  (~95k strands), `shirt.py` (keeps skin inside the shirt), `catheter.py` (IV cannula riding on the skin),
  `grip_rig.py` / `solve_grip.py` (the hand on the mouse) and `tremor_hands.py` (hands kept close to the keys).
- **Monsters.** `build_monsters.py` builds the six Mixamo creatures and the `MonsterGlitch` geometry-nodes effect that
  materialises them out of the screens as voxels.
- **Screens.** `gen_screens.py` (numpy + Pillow) draws the monitor and phone content: Claude CLI sessions, usage-limit
  timers, the $20 → $100 → $200 receipts, the crab band, lyrics. It encodes them as videos and writes each monitor's
  mean colour per frame to `screens/mon_light.json`. `screens_rig.py` maps the videos onto the screens and drives one
  area light per monitor from that file.
- **Camera.** `camera_rig.py` holds the shot list: keys of time, position, target and lens, smoothed with monotone
  Hermite splines, plus handheld noise, stair steps and shakes on the beats. Shot borders are the cuts.
- **Render and post.** `render_range.py` renders a frame range and `cycles_setup.py` switches the finale to Cycles.
  `post.py` adds RGB-split glitches and white flashes on the hits, grain, vignette and the title card; `look.py` says
  when the glitches fire.
- **Checks.** `render_tests.py`, `test_desk.py`, `test_monsters.py` and `build_human_test.py` render test frames
  without saving the scene.
- **Extras.** `short/render_short_src.py` renders the Short's shots straight from the scene in 9:16, and
  `short/make_short.py` cuts them to the edit in `short/edit.py`. `youtube/make_thumb.py` and `youtube/make_teaser.py`
  work from the rendered 4K master.

## Lessons

- **Cycles kept growing.** One Cycles process grew frame after frame: at 4K it reached ~98 GB on a 36 GB machine,
  filled the disk with swap, and its late frames lost the reflections in the glasses. `render_all.sh` starts a fresh
  Blender every 50 frames.
- **Float textures cost 4x.** Blender holds EXR and 16-bit PNG maps as float32 RGBA: ~230 2K maps took 12.5 GB, and one
  render process grew to ~22 GB. The 8-bit copies from `tex8.py` look the same at a quarter of the memory.
- **Measure the beat, don't assume it.** The cuts sit on a beat grid measured from the audio's onsets, not on one
  counted from zero at the nominal tempo.
- **Screens light the room.** The monitors are video textures, and each one also drives an area light from its own
  mean colour per frame, so the basement flickers with what is on the screens.
- **ffmpeg without drawtext.** That ffmpeg build had no `drawtext`, so the title card is drawn with Pillow and overlaid.

## Licenses and credits

- **Code:** see [LICENSE](LICENSE).
- **Poly Haven** assets: CC0. **MakeHuman** asset packs: CC0. **Mixamo**: Adobe's terms, not redistributed.
  **UnifrakturCook**: SIL Open Font License.
- **Song:** generated with Suno from Claude's lyrics. Not included.
- Claude, Claude Code and Opus are trademarks of Anthropic. This is an unofficial fan project, not affiliated with or
  endorsed by Anthropic. The Claude name and logo appear in the video only as its subject.
