#!/bin/zsh
# Whole clip, resumable: EEVEE 0 - 188.1 s, Cycles finale 188.1 - 214.24 s, black under the title card,
# then the ffmpeg pass with the song. Re-run to continue after a stop (frames on disk are skipped).
# env: RES=WxH, FMT=PNG|JPEG, TAG (frames dir renders/frames$TAG, video renders/Claudaine_clip$TAG.mp4),
#      EEVEE_SAMPLES (24), CYCLES_SAMPLES (64)
# Run: nohup caffeinate -is zsh scripts/render_all.sh > renders/render_all.log 2>&1 &
#      RES=1280x720 FMT=JPEG TAG=_720p EEVEE_SAMPLES=16 nohup caffeinate -is zsh scripts/render_all.sh > renders/render_all_720p.log 2>&1 &
#      RES=3840x2160 FMT=JPEG TAG=_4k nohup caffeinate -is zsh scripts/render_all.sh > renders/render_all_4k.log 2>&1 &
#      (4K as JPEG q95: PNG frames would take ~60 GB)
set -e
cd "$(dirname "$0")/.."
BL=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
export RES=${RES:-1920x1080} FMT=${FMT:-PNG} TAG=${TAG:-}
EEVEE_SAMPLES=${EEVEE_SAMPLES:-24} CYCLES_SAMPLES=${CYCLES_SAMPLES:-64}
EXT=png; [[ $FMT == JPEG ]] && EXT=jpg
FR=renders/frames$TAG
mkdir -p $FR
find $FR -name "f_*.$EXT" -size 0 -delete          # placeholders of frames cut short by a stop
echo "eevee start $(date)"
SAMPLES=$EEVEE_SAMPLES $BL -b blend/claudaine.blend --python scripts/render_range.py -- eevee 1 4514 > renders/eevee_stdout$TAG.log 2>&1
echo "cycles start $(date)"
# a fresh Blender every 50 frames: one Cycles process grows frame after frame (at 4K it reached ~98 GB,
# filled the disk with swap, and its late frames lost the reflections in the glasses)
: > renders/cycles_stdout$TAG.log
for c in $(seq 4515 50 5142); do
  SAMPLES=$CYCLES_SAMPLES $BL -b blend/claudaine.blend --python scripts/render_range.py -- cycles $c $(( c + 49 < 5142 ? c + 49 : 5142 )) >> renders/cycles_stdout$TAG.log 2>&1
done
python3 -c "
from PIL import Image
im = Image.new('RGB', tuple(map(int, '$RES'.split('x'))))
for f in range(5143, 5255):
    im.save(f'$FR/f_{f:04d}.$EXT', quality=95)"
echo "post start $(date)"
python3 scripts/post.py $FR renders/Claudaine_clip$TAG.mp4 > renders/post$TAG.log 2>&1
echo "DONE $(date)"
