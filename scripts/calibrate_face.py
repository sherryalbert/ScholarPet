"""Measure the avatar's facial features and write ``assets/haibara_head.rig.json``.

The desktop pet animates a *still* portrait: it blinks, talks and looks around
by compositing pieces of the one PNG we ship.  That only works if we know where
the eyes and the mouth are, and hand-guessing pixel boxes for a 1254px artwork
is both tedious and fragile -- swap the artwork and every box is wrong.

So we measure them instead, straight from the pixels:

* the **irises** are the only strongly *coloured* (blue-grey) blobs on the face,
  while the sclera is near-white and the lash lines are near-black;
* the **eye** box is the iris box grown outwards until the near-white sclera and
  the dark lash stroke are included again;
* the **mouth** is the widest dark thin stroke on the lower face, which survives
  hair strands because we keep the largest connected blob near the centre line.

Run it after replacing ``assets/haibara_head.png``::

    python scripts/calibrate_face.py --report
    python scripts/calibrate_face.py --overlay docs/face-rig.png
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets" / "haibara_head.png"
RIG = ROOT / "assets" / "haibara_head.rig.json"


def _bbox(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def _norm(box, width, height):
    x0, y0, x1, y1 = box
    return [round(x0 / width, 4), round(y0 / height, 4),
            round((x1 - x0) / width, 4), round((y1 - y0) / height, 4)]


def _largest_blob(mask):
    """Keep the biggest 8-connected component of ``mask`` (numpy only)."""
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return mask
    labels = np.zeros(mask.shape, np.int32)
    stack, current, best, best_size = [], 0, 0, 0
    occupied = mask.copy()
    for sy, sx in zip(ys[::7], xs[::7]):
        if not occupied[sy, sx]:
            continue
        current += 1
        size = 0
        stack.append((sy, sx))
        occupied[sy, sx] = False
        while stack:
            y, x = stack.pop()
            labels[y, x] = current
            size += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and occupied[ny, nx]:
                        occupied[ny, nx] = False
                        stack.append((ny, nx))
        if size > best_size:
            best, best_size = current, size
    if not best:
        return mask
    return labels == best


def measure(path: Path):
    image = Image.open(path).convert("RGBA")
    width, height = image.size
    rgba = np.asarray(image).astype(np.int32)
    rgb, alpha = rgba[..., :3], rgba[..., 3]
    opaque = alpha > 200
    chroma = rgb.max(2) - rgb.min(2)
    luma = (rgb[..., 0] * 299 + rgb[..., 1] * 587 + rgb[..., 2] * 114) // 1000
    yy, xx = np.mgrid[0:height, 0:width]
    ny, nx = yy / height, xx / width

    # --- irises: the only blue-grey (cool, mid-bright, saturated) blobs -----
    iris = opaque & (rgb[..., 2] >= rgb[..., 0] - 4) & (chroma >= 25) & (ny > 0.50) & (ny < 0.80)
    boxes = {}
    for side, half in (("left", nx < 0.5), ("right", nx >= 0.5)):
        box = _bbox(_largest_blob(iris & half))
        if box is None:
            raise SystemExit(f"{path.name}: no {side} iris found -- is the artwork a front facing head?")
        boxes[f"{side}_iris"] = box

    # --- eyes: grow the iris box until sclera + lash line come along --------
    for side in ("left", "right"):
        ix0, iy0, ix1, iy1 = boxes[f"{side}_iris"]
        iw, ih = ix1 - ix0, iy1 - iy0
        x0 = max(0, int(ix0 - iw * 0.62))
        x1 = min(width, int(ix1 + iw * 0.55))
        y0 = max(0, int(iy0 - ih * 0.95))
        y1 = min(height, int(iy1 + ih * 0.26))
        boxes[f"{side}_eye"] = [x0, y0, x1, y1]

    # --- mouth: the dark stroke just below the nose -------------------------
    # The window has to miss the nose (a small dot higher up) and the chin
    # silhouette (a long dark arc lower down), so it stays tight: inside it the
    # only dark pixels left are the mouth curve, which is why a plain bounding
    # box beats blob selection here -- the stroke thins out at both corners and
    # would otherwise be cut in half.
    mouth_band = (ny > 0.785) & (ny < 0.845) & (nx > 0.40) & (nx < 0.66)
    dark = opaque & mouth_band & (luma < 220)
    box = _bbox(dark)
    if box is None:
        raise SystemExit(f"{path.name}: no mouth stroke found.")
    boxes["mouth"] = box

    rig = {"source": path.name, "size": [width, height]}
    for key in ("left_eye", "right_eye", "mouth", "left_iris", "right_iris"):
        rig[key] = _norm(boxes[key], width, height)
    # A couple of skin sample points (cheek below each eye, plus the chin) give
    # the compositor a colour it can trust when it has to cover an eye.
    for key, (fx, fy) in (("cheek_left", (boxes["left_eye"][0] + (boxes["left_eye"][2] - boxes["left_eye"][0]) * 0.5, boxes["left_eye"][3] + 18)),
                          ("cheek_right", (boxes["right_eye"][0] + (boxes["right_eye"][2] - boxes["right_eye"][0]) * 0.5, boxes["right_eye"][3] + 18))):
        x = int(min(max(fx, 0), width - 1))
        y = int(min(max(fy, 0), height - 1))
        sample = rgb[y - 6:y + 7, x - 6:x + 7].reshape(-1, 3).mean(0)
        rig[key] = [round(v) for v in sample]
    return rig, boxes


def _dilate(mask, radius):
    out = mask.copy()
    for _ in range(radius):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def _trim(grown_box, seed):
    """Tighten a dilated blob back onto the original stroke."""
    x0, y0, x1, y1 = grown_box
    inner = seed[y0:y1, x0:x1]
    tight = _bbox(inner)
    if tight is None:
        return grown_box
    return [x0 + tight[0], y0 + tight[1], x0 + tight[2], y0 + tight[3]]


def overlay(path: Path, boxes, destination: Path):
    image = Image.open(path).convert("RGBA")
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    colours = {"left_eye": (0, 200, 255, 255), "right_eye": (0, 200, 255, 255),
               "mouth": (255, 90, 60, 255)}
    for key, box in boxes.items():
        colour = colours.get(key, (255, 210, 0, 255))
        draw.rectangle(box, outline=colour, width=4)
    for key, box in boxes.items():
        draw.text((box[0] + 6, box[1] + 6), key, fill=(0, 0, 0, 255))
    result = Image.alpha_composite(image, layer).convert("RGB")
    result = result.crop((0, int(image.height * 0.45), image.width, int(image.height * 1.0)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.save(destination)
    print(f"wrote {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, default=ASSET)
    parser.add_argument("--out", type=Path, default=RIG)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--dry", action="store_true", help="do not write the rig json")
    args = parser.parse_args()

    rig, boxes = measure(args.asset)
    if not args.dry:
        args.out.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(f"wrote {args.out}")
    if args.report:
        print(json.dumps(rig, ensure_ascii=False, indent=2))
        print("pixels:", json.dumps(boxes))
    if args.overlay:
        overlay(args.asset, boxes, args.overlay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
