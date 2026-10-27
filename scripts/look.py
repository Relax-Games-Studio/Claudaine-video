"""When the clip's glitches fire, in clip seconds: post.py lays them over the clip, short/make_short.py over the
Short's shots that it renders in 9:16 (cut from the clip they came baked in)."""
RESETS = [149.896, 151.096, 152.296, 153.496, 154.696, 155.896]
MONSTERS = [110.3, 119.9, 124.5, 168.0]
HITS = [12.0, 20.45, 30.4, 45.9, 60.0, 100.0, 180.4, 206.3]

rgb = [(t, t + 0.25) for t in RESETS + MONSTERS] + [(t, t + 0.12) for t in HITS] + \
      [(132.5 + k * 0.6, 132.5 + k * 0.6 + 0.08) for k in range(11)]          # bridge stutter
flash = [(t, t + 1 / 24) for t in RESETS] + [(168.0, 168.0 + 2 / 24)]
slices = [(t, t + 0.17) for t in RESETS + MONSTERS] + [(136.1, 136.4), (138.5, 139.1)]
