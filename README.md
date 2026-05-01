# Blender-AC3D - Version 7.2

## About
It's a few python scripts to import/export Inivis AC3D data into and out of Blender 2.63 to Blender 4.3.

## Download

| Blender Version                                                                                         | 
|---------------------------------------------------------------------------------------------------------|
| [Download for Blender 4.3](https://github.com/NikolaiVChr/Blender-AC3D/archive/refs/heads/4.3.zip)      |
| [Download for Blender 4.1](https://github.com/NikolaiVChr/Blender-AC3D/archive/refs/heads/4.1.zip)      |
| [Download for Blender 4.0](https://github.com/NikolaiVChr/Blender-AC3D/archive/refs/heads/4.0.zip)      |
| [Download for Blender 3.2](https://github.com/NikolaiVChr/Blender-AC3D/archive/refs/heads/3.2.zip)      | 
| [Download for Blender 3.0](https://github.com/NikolaiVChr/Blender-AC3D/archive/refs/heads/3.0.zip)      |
| [Download for Blender 2.80](https://github.com/NikolaiVChr/Blender-AC3D/archive/refs/heads/2.80.zip)    |
| [Download for Blender 2.7.9](https://github.com/NikolaiVChr/Blender-AC3D/archive/refs/heads/2.79.zip)   |
| [Download for Blender 2.6.x](https://github.com/NikolaiVChr/Blender-AC3D/archive/refs/heads/bl2.6.zip)  |

## How do I install it?
Know that the auto-install feature in Blender is not supported, you will have to do it manually:

Open the blender/x.x/scripts/addons folder, then pull the io_scene_ac3d folder into the addons folder of blender. There's an alternative location you can drop it, at ~/.blender/x.x/scripts/addons (linux) or c:\Users\[username]\AppData\Roaming\Blender Foundation\Blender\x.x\scrips\addons (Windows 7+), where x.x is the version of Blender and [username] is the Windows user name. Notice AppData per default is hidden in Windows, but you can just write it in the address bar.

## I can't see it in the import/export menu!
You'll need to enable the script in the user preferences window after installing it - open the user preferences window (Edit->Preferences) and then go to the Add-on tab, click the button for Import-Export and then check the box on the right of "Import-Export: AC3D (.ac)"

## Uh, I've done all that how do I use it?
Go to File->Import->AC3D (.ac), select a file, adapt the import settings to your liking, and let it do the work.

## AC3D Material Panel (Blender Material tab)
A dedicated AC3D panel is available in the Blender Material Properties tab.

It lets you set AC3D material properties explicitly per material:
- AC3D Name
- RGB (diffuse)
- Ambient
- Emissive
- Specular
- Shininess (0-128)
- Transparency (0-1)

Panel controls:
- `Use AC3D Values`: exporter uses the panel values directly.
- `Auto Mirror To Blender`: changing AC3D values updates supported Blender material values.
- `Read Blender Material`: copies current Blender shader/material values into AC3D values.
- `Write To Blender Material`: applies AC3D values back to supported Blender material/shader fields.

Importer/exporter integration:
- Imported AC3D materials populate this panel automatically.
- Export can use either Blender-derived values (default) or explicit AC3D panel values.

## FlightGear XML Panels
A separate FlightGear XML workflow is available alongside the plain AC3D exporter.

Scene Properties:
- Main FlightGear XML model wrapper settings
- Relative AC path written into the XML
- `nopreview`, wrapper offsets, wrapper scale (`x-scale/y-scale/z-scale`), and axis-order defaults
- Scene-level submodel definitions
- Optional extra XML snippet via a Blender Text datablock

Object Properties:
- Per-object FlightGear effects
- Per-object FlightGear animations
- Per-object particle systems
- Optional extra XML snippet via a Blender Text datablock

Export:
- `File > Export > FlightGear (.xml + .ac)` writes a FlightGear XML file and delegates `.ac` generation to the existing AC3D exporter.
- The AC3D and FlightGear XML code paths stay separate; the FlightGear exporter calls the AC3D exporter as a black box and only adds the XML sidecar.
- The FlightGear export dialog now includes an `XML Data` section for scene wrapper metadata plus quick helper animations for fixed scale and simple rotate/spin XML output.
- Quick helper object targets now use searchable pickers backed by a cached scene-object list that is populated when the export dialog opens and refreshed only after scene updates.
- Quick rotation property presets are filtered by animation type, so `rotate` and `spin` show different suggested FlightGear properties.
- Quick rotation helper presets now include `Radar Sweep`, `Retail Sign`, `Beacon Spinner`, `Propeller`, `Main Rotor`, and `Tail Rotor`, and selecting one auto-fills the quick rotation helper values.

## AC3D versions
AC3Db supported for import and export.
AC3Dc supported for import.

## Known Issues:
If exporting when in Edit mode, it will not export the last edits done in Edit mode. Best is to export when in Object mode.

When importing lines, they cannot be assigned UV coordinates as Blender does not support that.

When exporting lines, they will always be smooth shaded, due to limitations in Blender.

When exporting lines they will have the DefaultWhite material, except if their Blender object has only 1 and only 1 material, then they will be assigned that. This is due to Blender limitation.

Exporter will export all materials in object material slots, even if they are not referenced. Good if you had a material you might want to assign to something later. Also annoying cause it potentially can clutter up the AC3D file with unused materials.

## Recent compatibility fixes
- Importer handles AC3D material shininess values that are written as floats and safely maps them to panel properties.
- Importer no longer requires `Mesh.set_sharp_from_angle` to exist; it falls back to auto-smooth properties when needed on older/different Blender APIs.
- Import/export now preserve AC3D object `data`, `url`, `locked`, `folded`, and explicit `crease` values through Blender custom properties when Blender has no native field for them.
- Importer now skips unsupported object/surface extension tokens instead of treating them as implicit end-of-section markers, which makes it more tolerant of newer AC3D dialects.
- Exporter now emits one-axis `texrep` values correctly and always quotes `url` strings.
- FlightGear XML scene wrapper export now supports optional `x-scale`, `y-scale`, and `z-scale` model tags when scene wrapper scale differs from the default.
- FlightGear XML quick-helper UI and export paths now guard optional operator properties more defensively to avoid stale-session attribute errors after add-on updates.

## Things to come:
* I want to have an option to overwrite, or to prompt the operator if they want to overwrite textures on an export

## Follow the discussion at:

https://forum.flightgear.org/viewtopic.php?f=18&t=36194

## Complete file format specification, anno 2019

https://sites.google.com/view/ac3dfileformat/home

## Acknowledgments:

The Blender team: (http://www.blender.org) for such a fine piece of software
Willian P Gerano for his original work (the very first version of this script was a port of his original work)
Rene Negree for his help with the importer, tips on the texture mapping and materials and user settings saving
The FlightGear community for their help in testing and feedback for development

- BEGIN GPL LICENSE BLOCK -

  This program is free software; you can redistribute it and/or
  modify it under the terms of the GNU General Public License
  as published by the Free Software Foundation; either version 2
  of the License, or (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program; if not, write to the Free Software Foundation,
  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

- END GPL LICENSE BLOCK -
