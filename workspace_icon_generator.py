#!/usr/bin/env python3
"""Put a house-style Dock icon on a .code-workspace file.

Draws a macOS-style rounded square with a vertical gradient, a faint "{ }" and
a bold two-letter label, then stores it the way the other workspace icons are
stored: an 'icns' resource (ID -16455) in the file's resource fork, plus the
custom-icon flag in FinderInfo. Any existing resource fork on TARGET is
replaced, so only point this at workspace files, whose resource fork holds
nothing but the icon.

Usage:
  uv run workspace-icon-generator TARGET --abbr CI [--top HEX --bottom HEX] [--work DIR]

Needs Xcode CLT (Rez, DeRez, SetFile), iconutil, and rsvg-convert
(brew install librsvg). The Dock may keep the old icon until `killall Dock`.
"""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{top}"/>
      <stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
  </defs>
  <rect x="32" y="32" width="448" height="448" rx="100" ry="100" fill="url(#bg)"/>
  <text x="256" y="151" font-family="Helvetica Neue, Helvetica, Arial, sans-serif" font-weight="400" font-size="80" fill="#FFFFFF" fill-opacity="0.5" text-anchor="middle">{{ }}</text>
  <text x="256" y="335" font-family="Helvetica Neue, Helvetica, Arial, sans-serif" font-weight="700" font-size="{size}" fill="#FFFFFF" text-anchor="middle">{abbr}</text>
</svg>
"""

ICONSET = [
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]
CUSTOM_ICON_ID = -16455


def run(*args):
    # DeRez writes Mac Roman comments, so decode as Latin-1 (accepts any byte).
    return subprocess.run(args, check=True, capture_output=True, encoding="latin-1").stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", type=pathlib.Path)
    parser.add_argument("--abbr", required=True, help="label, usually the project's initials (2 letters preferred)")
    parser.add_argument("--top", default="#E4589F", help="gradient top colour")
    parser.add_argument("--bottom", default="#8F1B66", help="gradient bottom colour")
    parser.add_argument("--work", type=pathlib.Path, help="scratch dir (default: a new temp dir)")
    args = parser.parse_args()

    target = args.target.resolve()
    if not target.is_file():
        raise SystemExit(f"not a file: {target}")
    work = args.work or pathlib.Path(tempfile.mkdtemp(prefix="workspace-icon-"))
    iconset = work / "icon.iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    iconset.mkdir(parents=True)

    # Shrink long labels so they stay inside the squircle; 2 letters sit at 200pt.
    size = min(200, round(250 / (0.62 * len(args.abbr))))
    svg = work / "icon.svg"
    svg.write_text(SVG.format(top=args.top, bottom=args.bottom, abbr=args.abbr, size=size))
    for name, px in ICONSET:
        run("rsvg-convert", "-w", str(px), "-h", str(px), str(svg), "-o", str(iconset / name))
    icns = work / "icon.icns"
    run("iconutil", "-c", "icns", str(iconset), "-o", str(icns))

    preview = work / "preview-1024.png"
    shutil.copy(iconset / "icon_512x512@2x.png", preview)

    # Wrap the .icns bytes as a Rez 'icns' resource.
    data = icns.read_bytes()
    lines = [f'\t$"{data[i:i + 32].hex().upper()}"' for i in range(0, len(data), 32)]
    rsrc = work / "icon.r"
    rsrc.write_text(f"data 'icns' ({CUSTOM_ICON_ID}) {{\n" + "\n".join(lines) + "\n};\n")

    has_fork = subprocess.run(["xattr", "-p", "com.apple.ResourceFork", str(target)], capture_output=True).returncode == 0
    if has_fork:
        run("xattr", "-d", "com.apple.ResourceFork", str(target))
    run("Rez", "-append", str(rsrc), "-o", str(target))
    run("SetFile", "-a", "C", str(target))

    # Check the result: the icon resource is there and the custom-icon bit (0x0400 in FinderInfo) is set.
    resource_ok = f"'icns' ({CUSTOM_ICON_ID})" in run("DeRez", "-only", "icns", str(target))
    finder_info = bytes.fromhex("".join(run("xattr", "-px", "com.apple.FinderInfo", str(target)).split()))
    flag_ok = bool(finder_info[8] & 0x04)
    print(f"preview:           {preview}")
    print(f"icon resource:     {'ok' if resource_ok else 'MISSING'}")
    print(f"custom-icon flag:  {'ok' if flag_ok else 'MISSING'}")
    if not (resource_ok and flag_ok):
        raise SystemExit("icon did not apply cleanly")


if __name__ == "__main__":
    main()
