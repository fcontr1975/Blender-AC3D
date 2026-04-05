# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

# Most of this has been copied from the __init__.py file for the io_scene__xx
# folders of the standard 2.59 blender package and customised to
# act as a wrapper for the conventional AC3D importer/exporter

import time
import datetime
from math import radians
import re

import bpy
from bpy.types import Operator, Panel, PropertyGroup, TOPBAR_MT_file_import, TOPBAR_MT_file_export
from bpy.props import BoolProperty, EnumProperty, FloatProperty, \
    FloatVectorProperty, IntProperty, PointerProperty, StringProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper, axis_conversion
from mathutils import Euler

bl_info = {
    "name": "AC3D (.ac) format",
    "description": "Inivis AC3D model exporter for Blender.",
    "author": "Willian P Gerano, Chris Marr, Thomas Geymayer, Nikolai V. Chr., Scott Giese, Federico Contreras",
    "version": (7, 2, 1),
    "blender": (4, 0, 0),
    "category": "Import-Export",
    "location": "File > Import-Export",
    "warning": "",
    "doc_url": (
        "http://wiki.flightgear.org/Blender_AC3D_import_and_export"
        "#Majic79_addon"),
    "tracker_url": "https://github.com/NikolaiVChr/Blender-AC3D/issues"
}

# To support reload properly, try to access a package var, if it's there,
# reload everything
if "bpy" in locals():
    import importlib
    if 'import_ac3d' in locals():
        importlib.reload(import_ac3d)
    if 'export_ac3d' in locals():
        importlib.reload(export_ac3d)


def menu_func_import(self, context):
    self.layout.operator(AC3D_OT_Import.bl_idname, text='AC3D (.ac)')


def menu_func_export(self, context):
    self.layout.operator(AC3D_OT_Export.bl_idname, text='AC3D (.ac)')


def _get_material_output_shader_node(bl_mat):
    if not bl_mat or not bl_mat.use_nodes or not bl_mat.node_tree:
        return None

    output = next(
        (n for n in bl_mat.node_tree.nodes
         if n.type == 'OUTPUT_MATERIAL' and n.is_active_output),
        None)
    if output and 'Surface' in output.inputs and output.inputs['Surface'].links:
        return output.inputs['Surface'].links[0].from_node

    if bl_mat.node_tree.links:
        return bl_mat.node_tree.links[0].from_node

    return None


def _ac3d_values_from_blender_material(bl_mat):
    values = {
        'name': re.sub('["]', '', bl_mat.name),
        'rgb': [1.0, 1.0, 1.0],
        'amb': [0.2, 0.2, 0.2],
        'emis': [0.0, 0.0, 0.0],
        'spec': [0.5, 0.5, 0.5],
        'shi': 64,
        'trans': 0.0,
    }

    rough = 0.5
    try:
        curr_shader = _get_material_output_shader_node(bl_mat)
        if curr_shader and curr_shader.type == 'BSDF_PRINCIPLED':
            principled = curr_shader
            emis_color = principled.inputs['Emission Color']
            emis_strength = principled.inputs['Emission Strength'].default_value
            if emis_strength == 0.0:
                values['emis'] = [0.0, 0.0, 0.0]
            else:
                values['emis'] = [
                    emis_color.default_value[0],
                    emis_color.default_value[1],
                    emis_color.default_value[2],
                ]

            alpha = principled.inputs['Alpha']
            values['trans'] = 1.0 - alpha.default_value
            rough = 1.0 - principled.inputs['Roughness'].default_value

            base = principled.inputs['Base Color']
            if not base.links:
                values['rgb'] = [
                    base.default_value[0],
                    base.default_value[1],
                    base.default_value[2],
                ]

            specu = principled.inputs['Specular Tint']
            values['spec'] = [
                specu.default_value[0],
                specu.default_value[1],
                specu.default_value[2],
            ]

        elif curr_shader and curr_shader.type == 'BSDF_DIFFUSE':
            diffuse = curr_shader
            rough = 1.0 - diffuse.inputs['Roughness'].default_value
            base = diffuse.inputs['Color']
            if not base.links:
                values['rgb'] = [
                    base.default_value[0],
                    base.default_value[1],
                    base.default_value[2],
                ]

        elif curr_shader and curr_shader.type == 'EEVEE_EMISSION':
            emission = curr_shader
            emis = emission.inputs['Strength'].default_value
            base = emission.inputs['Color'].default_value
            values['emis'] = [emis * base[0], emis * base[1], emis * base[2]]
            values['rgb'] = [0.0, 0.0, 0.0]
            values['amb'] = [0.0, 0.0, 0.0]
            values['spec'] = [0.0, 0.0, 0.0]
            rough = 0.5
            values['trans'] = 0.0

        elif curr_shader and curr_shader.type == 'EEVEE_SPECULAR':
            specular = curr_shader
            emis_color = specular.inputs['Emissive Color'].default_value
            values['emis'] = [emis_color[0], emis_color[1], emis_color[2]]
            values['trans'] = specular.inputs['Transparency'].default_value
            rough = 1.0 - specular.inputs['Roughness'].default_value

            base = specular.inputs['Base Color']
            if not base.links:
                values['rgb'] = [
                    base.default_value[0],
                    base.default_value[1],
                    base.default_value[2],
                ]

            specu = specular.inputs['Specular'].default_value
            values['spec'] = [specu[0], specu[1], specu[2]]

        else:
            values['spec'] = list(bl_mat.specular_intensity * bl_mat.specular_color)
            rough = 1.0 - bl_mat.roughness
            values['rgb'] = [
                bl_mat.diffuse_color[0],
                bl_mat.diffuse_color[1],
                bl_mat.diffuse_color[2],
            ]
            values['trans'] = 1.0 - bl_mat.diffuse_color[3]

    except Exception:
        values['spec'] = list(bl_mat.specular_intensity * bl_mat.specular_color)
        rough = 1.0 - bl_mat.roughness
        values['rgb'] = [
            bl_mat.diffuse_color[0],
            bl_mat.diffuse_color[1],
            bl_mat.diffuse_color[2],
        ]
        values['trans'] = 1.0 - bl_mat.diffuse_color[3]

    rough = min(1.0, max(0.0, rough))
    values['shi'] = int(round(rough * 128.0, 0))
    return values


def _apply_ac3d_values_to_blender_material(bl_mat, ac3d_props):
    roughness = 1.0 - (float(ac3d_props.shi) / 128.0)
    roughness = min(1.0, max(0.0, roughness))
    alpha = 1.0 - ac3d_props.trans
    alpha = min(1.0, max(0.0, alpha))

    bl_mat.roughness = roughness
    bl_mat.diffuse_color = (
        ac3d_props.rgb[0],
        ac3d_props.rgb[1],
        ac3d_props.rgb[2],
        alpha,
    )
    bl_mat.specular_intensity = (
        ac3d_props.spec[0] + ac3d_props.spec[1] + ac3d_props.spec[2]) / 3.0

    shader = _get_material_output_shader_node(bl_mat)
    if not shader:
        return

    if shader.type == 'BSDF_PRINCIPLED':
        shader.inputs['Base Color'].default_value = (
            ac3d_props.rgb[0],
            ac3d_props.rgb[1],
            ac3d_props.rgb[2],
            1.0,
        )
        shader.inputs['Emission Color'].default_value = (
            ac3d_props.emis[0],
            ac3d_props.emis[1],
            ac3d_props.emis[2],
            1.0,
        )
        shader.inputs['Emission Strength'].default_value = 0.0 if (
            ac3d_props.emis[0] == 0.0 and
            ac3d_props.emis[1] == 0.0 and
            ac3d_props.emis[2] == 0.0) else 1.0
        shader.inputs['Alpha'].default_value = alpha
        shader.inputs['Roughness'].default_value = roughness
        shader.inputs['Specular Tint'].default_value = (
            ac3d_props.spec[0],
            ac3d_props.spec[1],
            ac3d_props.spec[2],
            1.0,
        )
    elif shader.type == 'EEVEE_SPECULAR':
        shader.inputs['Base Color'].default_value = (
            ac3d_props.rgb[0],
            ac3d_props.rgb[1],
            ac3d_props.rgb[2],
            1.0,
        )
        shader.inputs['Emissive Color'].default_value = (
            ac3d_props.emis[0],
            ac3d_props.emis[1],
            ac3d_props.emis[2],
            1.0,
        )
        shader.inputs['Transparency'].default_value = ac3d_props.trans
        shader.inputs['Roughness'].default_value = roughness
        shader.inputs['Specular'].default_value = (
            ac3d_props.spec[0],
            ac3d_props.spec[1],
            ac3d_props.spec[2],
            1.0,
        )


def _ac3d_props_update(self, context):
    bl_mat = self.id_data
    if not isinstance(bl_mat, bpy.types.Material):
        return
    if self.mirror_to_blender:
        _apply_ac3d_values_to_blender_material(bl_mat, self)


class AC3D_MaterialProperties(PropertyGroup):
    use_ac3d_properties: BoolProperty(
        name="Use AC3D Values",
        description="Use explicit AC3D values from this panel during export",
        default=False,
    )
    mirror_to_blender: BoolProperty(
        name="Auto Mirror To Blender",
        description="When enabled, AC3D edits update the Blender material where supported",
        default=False,
        update=_ac3d_props_update,
    )
    name: StringProperty(
        name="AC3D Name",
        description="Name written to MATERIAL in AC3D",
        default="",
        update=_ac3d_props_update,
    )
    rgb: FloatVectorProperty(
        name="RGB",
        description="Diffuse RGB",
        subtype='COLOR',
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
        update=_ac3d_props_update,
    )
    amb: FloatVectorProperty(
        name="Ambient",
        description="Ambient RGB",
        subtype='COLOR',
        min=0.0,
        max=1.0,
        default=(0.2, 0.2, 0.2),
        update=_ac3d_props_update,
    )
    emis: FloatVectorProperty(
        name="Emissive",
        description="Emissive RGB",
        subtype='COLOR',
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0),
        update=_ac3d_props_update,
    )
    spec: FloatVectorProperty(
        name="Specular",
        description="Specular RGB",
        subtype='COLOR',
        min=0.0,
        max=1.0,
        default=(0.5, 0.5, 0.5),
        update=_ac3d_props_update,
    )
    shi: IntProperty(
        name="Shininess",
        description="AC3D shininess (0-128)",
        min=0,
        max=128,
        default=64,
        update=_ac3d_props_update,
    )
    trans: FloatProperty(
        name="Transparency",
        description="AC3D transparency (0-1)",
        min=0.0,
        max=1.0,
        default=0.0,
        update=_ac3d_props_update,
    )


class AC3D_OT_MaterialSyncFromBlender(Operator):
    bl_idname = 'ac3d.material_sync_from_blender'
    bl_label = 'Read Blender Material'
    bl_description = 'Populate AC3D values from current Blender material setup'

    def execute(self, context):
        bl_mat = context.material
        if not bl_mat:
            return {'CANCELLED'}

        props = bl_mat.ac3d_material
        values = _ac3d_values_from_blender_material(bl_mat)
        props.name = values['name']
        props.rgb = values['rgb']
        props.amb = values['amb']
        props.emis = values['emis']
        props.spec = values['spec']
        props.shi = values['shi']
        props.trans = values['trans']
        props.use_ac3d_properties = True

        self.report({'INFO'}, 'AC3D values read from Blender material')
        return {'FINISHED'}


class AC3D_OT_MaterialSyncToBlender(Operator):
    bl_idname = 'ac3d.material_sync_to_blender'
    bl_label = 'Write To Blender Material'
    bl_description = 'Apply AC3D values to current Blender material where supported'

    def execute(self, context):
        bl_mat = context.material
        if not bl_mat:
            return {'CANCELLED'}

        props = bl_mat.ac3d_material
        _apply_ac3d_values_to_blender_material(bl_mat, props)
        self.report({'INFO'}, 'AC3D values applied to Blender material')
        return {'FINISHED'}


class AC3D_PT_MaterialPanel(Panel):
    bl_label = 'AC3D Material'
    bl_idname = 'AC3D_PT_material_panel'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'material'

    @classmethod
    def poll(cls, context):
        return context.material is not None

    def draw(self, context):
        layout = self.layout
        bl_mat = context.material
        props = bl_mat.ac3d_material

        layout.prop(props, 'use_ac3d_properties')
        layout.prop(props, 'mirror_to_blender')

        row = layout.row(align=True)
        row.operator(AC3D_OT_MaterialSyncFromBlender.bl_idname, icon='IMPORT')
        row.operator(AC3D_OT_MaterialSyncToBlender.bl_idname, icon='EXPORT')

        layout.prop(props, 'name')
        layout.prop(props, 'rgb')
        layout.prop(props, 'amb')
        layout.prop(props, 'emis')
        layout.prop(props, 'spec')
        layout.prop(props, 'shi')
        layout.prop(props, 'trans')


class AC3D_OT_Import(Operator, ImportHelper):
    """Import from AC3D file format (.ac)"""
    bl_idname = 'import_scene.import_ac3d'
    bl_label = 'Import AC3D'
    bl_options = {'PRESET'}

    filename_ext = '.ac'

    filter_glob: StringProperty(
        default='*.ac',
        options={'HIDDEN'})

    axis_forward: EnumProperty(
        name="Forward",
        items=(
            ('X', "X Forward", ""),
            ('Y', "Y Forward", ""),
            ('Z', "Z Forward", ""),
            ('-X', "-X Forward", ""),
            ('-Y', "-Y Forward", ""),
            ('-Z', "-Z Forward", "")),
        default='-Z')

    axis_up: EnumProperty(
        name="Up",
        items=(
            ('X', "X Up", ""),
            ('Y', "Y Up", ""),
            ('Z', "Z Up", ""),
            ('-X', "-X Up", ""),
            ('-Y', "-Y Up", ""),
            ('-Z', "-Z Up", "")),
        default='Y')

    transparency_method: EnumProperty(
        name="Transparency Method",
        description="The transparency method that will be set in materials.",
        items=(
            ('MASK', "Mask", ""),
            ('Z_TRANSPARENCY', "Z Transparency", ""),
            ('RAYTRACE', "RayTrace", "")),
        default='Z_TRANSPARENCY')

#    use_emis_as_mircol: BoolProperty(
#        name="Set Emis to Mirror colour",
#        description="Set AC3D Emission colour into Blender Mirror colour",
#        default=False)

#    use_amb_as_mircol: BoolProperty(
#        name="Set Amb to Mirror colour",
#        description="Set AC3D Ambient colour into Blender Mirror colour",
#        default=False)

#    display_textured_solid: BoolProperty(
#        name="Display textured solid",
#        description=(
#            "Show textures applied when in Solid view (notice that "
#            "transparency for materials is then only seen in Material "
#            "view and Render view)"),
#        default=False)
        
#    useEeveeSpecular: BoolProperty(
#        name="Use Eevee Specular",
#        description="Set materials to use Eevee Specular instead of Principled BSDF",
#        default=False)


    rotation: FloatVectorProperty(
        description="Import Rotation",
        subtype="XYZ",
        unit="ROTATION",
        default=(0.0, 0.0, 0.0))

    translation: FloatVectorProperty(
        description="Import Location",
        subtype="TRANSLATION",
        unit="NONE",
        default=(0.0, 0.0, 0.0))

    parent_to: StringProperty(
        default="")

    collection_name: StringProperty(
        default="")

#    hide_hidden_objects : BoolProperty(
#        name="Hide hidden objects",
#        description=(
#            "Newer AC3D format supports hiding objects. If checked those "
#            "objects will be Restrict viewport visibility in Blender (wont "
#            "be seen until the small eye in Outliner is clicked)."
#        ),
#        default=True)

    def execute(self, context):
        from . import import_ac3d
        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "filter_glob",
                                            "rotation",
                                            "translation",
                                            "hide_props_region"))

        eul = Euler((radians(self.rotation[0]),
                     radians(self.rotation[1]),
                     radians(self.rotation[2])), 'XYZ')

        global_matrix = eul.to_matrix().to_4x4() @ \
            axis_conversion(from_forward=self.axis_forward,
                            from_up=self.axis_up).to_4x4()

        keywords["global_matrix"] = global_matrix

        t = time.mktime(datetime.datetime.now().timetuple())

        import_ac3d.AC3D_OT_Import(self, context, **keywords)

        t = time.mktime(datetime.datetime.now().timetuple()) - t
        print('Finished importing in', t, 'seconds')

        return {'FINISHED'}


#
#   The error message operator. When invoked, pops up a dialog
#   window with the given message.
#

class AC3D_OT_Message(Operator):
    bl_idname = "error.message"
    bl_label = "Message"
    type: StringProperty()
    message: StringProperty()

    def execute(self, context):
        self.report({'INFO'}, self.message)
        print(self.message)
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_popup(self, width=400)

    def draw(self, context):
        self.layout.label(text="A message has arrived")
        row = self.layout.split(factor=0.25)
        row.prop(self, "type")
        row.prop(self, "message")
        row = self.layout.split(factor=0.80)
        row.label(text="")
        row.operator("error")


#
#   The OK button in the error dialog
#

class AC3D_OT_Ok(Operator):
    bl_idname = "error.ok"
    bl_label = "OK"

    def execute(self, context):
        return {'FINISHED'}


class AC3D_OT_Export(Operator, ExportHelper):
    """Export to AC3D file format (.ac)"""
    bl_idname = 'export_scene.export_ac3d'
    bl_label = 'Export AC3D'
    bl_options = {'PRESET'}

    filename_ext = '.ac'

    v_info = bl_info["version"]

    filter_glob: StringProperty(
        default='*.ac',
        options={'HIDDEN'})

    axis_forward: EnumProperty(
        name="Forward",
        items=(('X', "X Forward", ""),
               ('Y', "Y Forward", ""),
               ('Z', "Z Forward", ""),
               ('-X', "-X Forward", ""),
               ('-Y', "-Y Forward", ""),
               ('-Z', "-Z Forward", "")),
        default='-Z'
    )

    axis_up: EnumProperty(
        name="Up",
        items=(('X', "X Up", ""),
               ('Y', "Y Up", ""),
               ('Z', "Z Up", ""),
               ('-X', "-X Up", ""),
               ('-Y', "-Y Up", ""),
               ('-Z', "-Z Up", "")),
        default='Y'
    )

    export_rots: EnumProperty(
        name="Matrices",
        description=(
            "Some loaders interpret the matrices wrong, to be safe, "
            "use Apply before Export."),
        items=(
            ('apply', "Apply before export", ""),
            ('export', "Export", "")),
        default='apply',
    )
    use_render_layers: BoolProperty(
        name="Only View Layers",
        description="Only export from selected view layers",
        default=True,
    )
    use_selection: BoolProperty(
        name="Selection Only",
        description="Export selected objects only",
        default=False,
    )
    merge_materials: BoolProperty(
        name="Merge materials",
        description="Merge materials that are identical",
        default=False,
    )
    global_doublesided: BoolProperty(
        name="Double sided",
        description="If all geometry in AC3D will be double sided or backface culled.",
        default=False,
    )
#    mircol_as_emis: BoolProperty(
#        name="Mirror col to Emis",
#        description="Export Blender mirror colour to AC3D emissive colour",
#        default=False,
#    )
#    mircol_as_amb: BoolProperty(
#        name="Mirror col to Amb",
#        description="Export Blender mirror colour to AC3D ambient colour",
#        default=False,
#    )
    amb_as_diff: BoolProperty(
        name="Amb same as Diff",
        description="Export AC3D ambient colour to be like Diffuse color",
        default=False,
    )
    
    ambient: FloatVectorProperty(
        name="Set amb",
        description="Ambient color",
        subtype="COLOR",
        unit="NONE",
        default=(0.5, 0.5, 0.5),
        max=1.0,
        min=0.0,
    )
        
    export_lines: BoolProperty(
        name="Export lines",
        description=(
            "Export standalone edges, bezier curves etc. as AC3D lines. "
            "Will make export take longer."),
        default=False,
    )
    export_hidden: BoolProperty(
        name="Export hidden objects",
        description=(
            "Newer AC3D format supports hiding objects. If checked "
            "those objects will be exported as hidden. (notice that in older "
            "loaders they might show up, or the loader might choke on those "
            "new tokens)"),
        default=False,
    )
    export_lights: BoolProperty(
        name="Export lights",
        description=(
            "With this checked lights will also be exported. Notice "
            "they will all become pointlights. If not checked, any geometry "
            "that might have lamps as parent wont be output."),
        default=False,
    )
    crease_angle: FloatProperty(
        name="Crease Angle",
        description=(
            "Crease/smooth angle for all exported .ac faces."),
        default=radians(40.0),
        options={"ANIMATABLE"},
        unit="ROTATION",
        subtype="ANGLE",
    )

    def execute(self, context):
        if context.active_object:
            if context.active_object.mode == 'EDIT':
                print("AC3D was not exported due to being in edit mode.")
                bpy.ops.error.message(
                    'INVOKE_DEFAULT',
                    type="Error",
                    message='Cannot export AC3D in edit mode.')
                return {'FINISHED'}
        from . import export_ac3d
        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "filter_glob",
                                            "check_existing",
                                            "export_rots",
                                            ))

        global_matrix = axis_conversion(to_forward=self.axis_forward,
                                        to_up=self.axis_up,
                                        )
        keywords["global_matrix"] = global_matrix
        ex_rot = False
        if self.export_rots == 'export':
            ex_rot = True
        keywords["export_rot"] = ex_rot
        t = time.mktime(datetime.datetime.now().timetuple())
        export_ac3d.AC3D_OT_Export(self, context, **keywords)
        t = time.mktime(datetime.datetime.now().timetuple()) - t
        print('Finished exporting in', t, 'seconds')

        return {'FINISHED'}


__classes__ = (
    AC3D_MaterialProperties,
    AC3D_OT_MaterialSyncFromBlender,
    AC3D_OT_MaterialSyncToBlender,
    AC3D_PT_MaterialPanel,
    AC3D_OT_Export,
    AC3D_OT_Import,
    AC3D_OT_Message,
    AC3D_OT_Ok)


def register():
    for c in __classes__:
        bpy.utils.register_class(c)
    bpy.types.Material.ac3d_material = PointerProperty(type=AC3D_MaterialProperties)
    TOPBAR_MT_file_export.append(menu_func_export)
    TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    if hasattr(bpy.types.Material, 'ac3d_material'):
        del bpy.types.Material.ac3d_material
    for c in reversed(__classes__):
        bpy.utils.unregister_class(c)
    TOPBAR_MT_file_export.remove(menu_func_export)
    TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
    register()
