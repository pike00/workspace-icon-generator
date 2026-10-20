# workspace-icon-generator

Gives a VS Code `.code-workspace` file its own Dock icon on macOS: a rounded square with a vertical gradient, a faint `{ }` glyph, and a bold two-letter label.

The icon is stored the way macOS expects custom file icons: an `icns` resource in the file's resource fork, plus the custom-icon flag in Finder info. Once both are set, the Dock shows the workspace's icon instead of the generic VS Code document icon.

## Quick start

```sh
git clone https://github.com/willpike-suki/workspace-icon-generator
cd workspace-icon-generator
uv run workspace-icon-generator path/to/my-project.code-workspace --abbr MP
killall Dock   # make the Dock drop its cached icon
```

Without cloning, `uvx` can run it straight from GitHub:

```sh
uvx --from git+https://github.com/willpike-suki/workspace-icon-generator workspace-icon-generator path/to/my-project.code-workspace --abbr MP
```

## Requirements

- macOS. The script uses `Rez`, `DeRez`, and `SetFile` from the Xcode command line tools, plus `iconutil`.
- Xcode command line tools: `xcode-select --install`
- `rsvg-convert`: `brew install librsvg`
- [uv](https://docs.astral.sh/uv/): `brew install uv`

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `TARGET` | required | The `.code-workspace` file to give an icon to |
| `--abbr` | required | The label, usually two initials. Longer labels are shrunk to fit. |
| `--top` | `#E4589F` | Gradient colour at the top |
| `--bottom` | `#8F1B66` | Gradient colour at the bottom |
| `--work` | a new temp dir | Scratch directory for the SVG, PNGs, and `.icns` |

The script prints the path of a 1024 px preview PNG, then checks that the icon resource and the custom-icon flag are both in place. It exits with an error if either is missing.

## Caveats

- The script replaces the target's entire resource fork. Only run it on workspace files, whose fork holds nothing but the icon.
- Copying or archiving the file with a tool that drops resource forks loses the icon. Run the script again after copying.
- The Dock may keep showing the old icon until you run `killall Dock`.

## How it works

1. Renders an SVG template at each size an iconset needs, using `rsvg-convert`.
2. Packs the iconset into an `.icns` file with `iconutil`.
3. Wraps the `.icns` bytes as an `'icns'` resource with ID -16455 and appends it to the target's resource fork with `Rez`.
4. Sets the custom-icon bit (0x0400 in FinderInfo) with `SetFile -a C`.
5. Reads the resource and the flag back to confirm they applied.
