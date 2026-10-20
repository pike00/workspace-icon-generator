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

Needs rsvg-convert (brew install librsvg). iconutil and xattr ship with macOS.
The Dock may keep the old icon until `killall Dock`.
"""
import argparse
import pathlib
import shutil
import struct
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
RESOURCE_FORK = "com.apple.ResourceFork"
FINDER_INFO = "com.apple.FinderInfo"


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def read_xattr(path, name):
    # Raw bytes of an extended attribute, or None if it is not set.
    result = subprocess.run(["xattr", "-px", name, str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return bytes.fromhex("".join(result.stdout.split()))


def write_xattr(path, name, value):
    run("xattr", "-w", "-x", name, value.hex(), str(path))


def resource_fork(icns):
    # Classic resource fork: 256-byte header, resource data, then the resource map.
    # The map holds one 'icns' type with one unnamed resource.
    data = struct.pack(">I", len(icns)) + icns
    type_list = struct.pack(">H4sHH", 0, b"icns", 0, 10)
    reference = struct.pack(">hH", CUSTOM_ICON_ID, 0xFFFF) + bytes(8)  # attributes, data offset, handle: all 0
    map_header = bytes(24) + struct.pack(">HH", 28, 28 + len(type_list) + len(reference))
    resource_map = map_header + type_list + reference
    header = struct.pack(">IIII", 256, 256 + len(data), len(data), len(resource_map))
    return header + bytes(240) + data + resource_map


def read_resource(fork, res_type, res_id):
    # Return the bytes of one resource in a resource fork, or None if it is absent.
    data_start, map_start = struct.unpack(">II", fork[:8])
    type_list = map_start + struct.unpack(">H", fork[map_start + 24:map_start + 26])[0]
    (type_count,) = struct.unpack(">H", fork[type_list:type_list + 2])
    for i in range(type_count + 1):
        code, ref_count, ref_offset = struct.unpack(">4sHH", fork[type_list + 2 + 8 * i:type_list + 10 + 8 * i])
        if code != res_type:
            continue
        for j in range(ref_count + 1):
            ref = type_list + ref_offset + 12 * j
            if struct.unpack(">h", fork[ref:ref + 2])[0] == res_id:
                start = data_start + int.from_bytes(fork[ref + 5:ref + 8], "big")
                (length,) = struct.unpack(">I", fork[start:start + 4])
                return fork[start + 4:start + 4 + length]
    return None


def set_custom_icon_flag(target):
    # FinderInfo is 32 bytes. The custom-icon bit (0x0400) is 0x04 in the high byte of the flags at offset 8.
    info = bytearray((read_xattr(target, FINDER_INFO) or b"").ljust(32, b"\0"))
    info[8] |= 0x04
    write_xattr(target, FINDER_INFO, bytes(info))


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

    # Write the .icns bytes as the 'icns' resource, replacing any existing resource fork, then set the custom-icon bit.
    data = icns.read_bytes()
    write_xattr(target, RESOURCE_FORK, resource_fork(data))
    set_custom_icon_flag(target)

    # Check the result: read the icon resource and the custom-icon bit (0x0400 in FinderInfo) back from the file.
    fork = read_xattr(target, RESOURCE_FORK) or b""
    resource_ok = bool(fork) and read_resource(fork, b"icns", CUSTOM_ICON_ID) == data
    finder_info = read_xattr(target, FINDER_INFO) or b""
    flag_ok = len(finder_info) > 8 and bool(finder_info[8] & 0x04)
    print(f"preview:           {preview}")
    print(f"icon resource:     {'ok' if resource_ok else 'MISSING'}")
    print(f"custom-icon flag:  {'ok' if flag_ok else 'MISSING'}")
    if not (resource_ok and flag_ok):
        raise SystemExit("icon did not apply cleanly")


if __name__ == "__main__":
    main()
