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

import os
import xml.etree.ElementTree as ET
from math import radians

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, \
    FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, \
    StringProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList
from bpy_extras.io_utils import ExportHelper, axis_conversion


ANIMATION_TYPES = (
    ('rotate', 'Rotate', ''),
    ('translate', 'Translate', ''),
    ('scale', 'Scale', ''),
    ('dist-scale', 'Dist Scale', ''),
    ('spin', 'Spin', ''),
    ('shader', 'Shader', ''),
    ('select', 'Select', ''),
    ('range', 'Range', ''),
    ('alpha-test', 'Alpha Test', ''),
    ('blend', 'Blend', ''),
    ('billboard', 'Billboard', ''),
    ('flash', 'Flash', ''),
    ('noshadow', 'No Shadow', ''),
    ('textranslate', 'Tex Translate', ''),
    ('texrotate', 'Tex Rotate', ''),
    ('interaction', 'Interaction', ''),
    ('timed', 'Timed', ''),
    ('material', 'Material', ''),
    ('pbr', 'PBR', ''),
)

CONDITION_OPERATORS = (
    ('equals', 'Equals', ''),
    ('greater-than', 'Greater Than', ''),
    ('greater-than-equals', 'Greater Than Equals', ''),
    ('less-than', 'Less Than', ''),
    ('less-than-equals', 'Less Than Equals', ''),
)

PARTICLE_TYPES = (
    ('normal', 'Normal', ''),
    ('trail', 'Trail', ''),
)

PARTICLE_ATTACH = (
    ('world', 'World', ''),
    ('local', 'Local', ''),
)

PARTICLE_ALIGN = (
    ('billboard', 'Billboard', ''),
    ('fixed', 'Fixed', ''),
)

AXIS_MODES = (
    ('vector', 'Vector', ''),
    ('points', 'Two Points', ''),
    ('object', 'Axis Object', ''),
)

INTERACTION_TYPES = (
    ('carrier-catapult', 'Carrier Catapult', ''),
    ('carrier-wire', 'Carrier Wire', ''),
)

DEFAULT_AXIS_ORDER = (
    ('none', 'None', ''),
    ('xyz', 'XYZ', ''),
    ('x', 'X', ''),
)

QUICK_PROPERTY_PRESETS = (
    ('sim/time/elapsed-sec', 'Elapsed Time', 'Continuous motion based on elapsed seconds'),
    ('sim/time/sun-angle-rad', 'Sun Angle', 'Drive animation from sun angle'),
    ('controls/lighting/beacon', 'Beacon Switch', 'Drive animation from beacon light switch'),
    ('controls/lighting/nav-lights', 'Nav Lights Switch', 'Drive animation from navigation light switch'),
    ('controls/lighting/landing-lights', 'Landing Lights Switch', 'Drive animation from landing light switch'),
    ('gear/gear[0]/position-norm', 'Gear Position', 'Drive animation from gear position'),
    ('__CUSTOM__', 'Custom...', 'Enter a custom FlightGear property path'),
)


def _quick_object_items(self, context):
    items = [
        ('__ACTIVE__', 'Active Object', 'Use the current active object'),
        ('__CUSTOM__', 'Custom...', 'Enter an object name manually'),
    ]

    seen = set()
    if context is None or context.scene is None:
        return items

    for obj in sorted(context.scene.objects, key=lambda item: item.name.lower()):
        if obj.name in seen:
            continue
        items.append((obj.name, obj.name, 'Use AC object {0}'.format(obj.name)))
        seen.add(obj.name)

    return items


def _float_text(value):
    return ('{0:.6f}'.format(float(value))).rstrip('0').rstrip('.') or '0'


def _vector_is_zero(vec):
    return all(abs(float(component)) < 1e-8 for component in vec)


def _vector_is_one(vec):
    return all(abs(float(component) - 1.0) < 1e-8 for component in vec)


def _append_text(parent, tag, value):
    if value is None:
        return None
    node = ET.SubElement(parent, tag)
    node.text = str(value)
    return node


def _append_float(parent, tag, value):
    return _append_text(parent, tag, _float_text(value))


def _append_bool(parent, tag, value):
    node = ET.SubElement(parent, tag)
    node.set('type', 'bool')
    node.text = 'true' if value else 'false'
    return node


def _append_offsets(parent, location, rotation):
    if _vector_is_zero(location) and _vector_is_zero(rotation):
        return
    offsets = ET.SubElement(parent, 'offsets')
    _append_float(offsets, 'x-m', location[0])
    _append_float(offsets, 'y-m', location[1])
    _append_float(offsets, 'z-m', location[2])
    if not _vector_is_zero(rotation):
        _append_float(offsets, 'pitch-deg', rotation[0])
        _append_float(offsets, 'roll-deg', rotation[1])
        _append_float(offsets, 'heading-deg', rotation[2])


def _append_center(parent, center):
    if _vector_is_zero(center):
        return
    center_node = ET.SubElement(parent, 'center')
    _append_float(center_node, 'x-m', center[0])
    _append_float(center_node, 'y-m', center[1])
    _append_float(center_node, 'z-m', center[2])


def _append_model_scale(parent, scale):
    if _vector_is_one(scale):
        return
    _append_float(parent, 'x-scale', scale[0])
    _append_float(parent, 'y-scale', scale[1])
    _append_float(parent, 'z-scale', scale[2])


def _append_axis(parent, item):
    axis = ET.SubElement(parent, 'axis')
    if item.axis_mode == 'object' and len(item.axis_object_name.strip()):
        _append_text(axis, 'object-name', item.axis_object_name.strip())
    elif item.axis_mode == 'points':
        _append_float(axis, 'x1-m', item.axis_point_1[0])
        _append_float(axis, 'y1-m', item.axis_point_1[1])
        _append_float(axis, 'z1-m', item.axis_point_1[2])
        _append_float(axis, 'x2-m', item.axis_point_2[0])
        _append_float(axis, 'y2-m', item.axis_point_2[1])
        _append_float(axis, 'z2-m', item.axis_point_2[2])
    else:
        _append_float(axis, 'x', item.axis_vector[0])
        _append_float(axis, 'y', item.axis_vector[1])
        _append_float(axis, 'z', item.axis_vector[2])

    if item.swap_axis_direction:
        ET.SubElement(axis, 'swap-axis-direction')


def _append_condition(parent, prop_path, operator_name, value):
    if not len(prop_path.strip()):
        return
    condition = ET.SubElement(parent, 'condition')
    op = ET.SubElement(condition, operator_name)
    _append_text(op, 'property', prop_path.strip())
    _append_float(op, 'value', value)


def _append_interpolation(parent, entries_text, report_warning):
    entries_text = entries_text.strip()
    if not entries_text:
        return

    interpolation = ET.SubElement(parent, 'interpolation')
    added = 0
    for raw_entry in entries_text.split(';'):
        raw_entry = raw_entry.strip()
        if not raw_entry:
            continue

        if ':' in raw_entry:
            parts = [part.strip() for part in raw_entry.split(':', 1)]
        elif ',' in raw_entry:
            parts = [part.strip() for part in raw_entry.split(',', 1)]
        else:
            parts = raw_entry.split()

        if len(parts) != 2:
            report_warning('Skipping invalid interpolation entry: {0}'.format(
                raw_entry))
            continue

        try:
            ind = float(parts[0])
            dep = float(parts[1])
        except ValueError:
            report_warning('Skipping invalid interpolation entry: {0}'.format(
                raw_entry))
            continue

        entry = ET.SubElement(interpolation, 'entry')
        _append_float(entry, 'ind', ind)
        _append_float(entry, 'dep', dep)
        added += 1

    if not added:
        parent.remove(interpolation)


def _append_text_block_children(parent, text_block, report_warning):
    if text_block is None:
        return

    xml_text = text_block.as_string().strip()
    if not xml_text:
        return

    try:
        wrapper = ET.fromstring('<wrapper>{0}</wrapper>'.format(xml_text))
    except ET.ParseError as exc:
        report_warning('Skipping invalid extra XML block {0}: {1}'.format(
            text_block.name, exc))
        return

    for child in wrapper:
        parent.append(child)


def _default_item_label(collection_name, length):
    labels = {
        'effects': 'Effect',
        'animations': 'Animation',
        'particles': 'Particle',
        'submodels': 'Submodel',
    }
    return '{0} {1}'.format(labels.get(collection_name, 'Item'), length)


def _iter_export_objects(context, selection_only):
    for obj in bpy.data.objects:
        if obj.library:
            continue
        if selection_only and not obj.select_get():
            continue
        yield obj


def _has_object_xml_data(props):
    return (
        props.enabled or
        len(props.effects) > 0 or
        len(props.animations) > 0 or
        len(props.particles) > 0 or
        props.extra_xml_text is not None
    )


class FGEffectItem(PropertyGroup):
    enabled: BoolProperty(name='Enabled', default=True)
    label: StringProperty(name='Label', default='Effect')
    effect_path: StringProperty(
        name='Effect Path',
        description='Value written to <inherits-from>',
        default='')
    object_name: StringProperty(
        name='Object Name',
        description='Override the target AC object name',
        default='')


class FGAnimationItem(PropertyGroup):
    enabled: BoolProperty(name='Enabled', default=True)
    label: StringProperty(name='Label', default='Animation')
    type: EnumProperty(name='Type', items=ANIMATION_TYPES, default='rotate')
    object_name: StringProperty(
        name='Object Name',
        description='Override the target AC object name',
        default='')
    property: StringProperty(name='Property', default='')
    property_base: StringProperty(name='Property Base', default='')
    factor: FloatProperty(name='Factor', default=1.0)
    offset: FloatProperty(name='Offset', default=0.0)
    offset_deg: FloatProperty(name='Offset Deg', default=0.0)
    offset_m: FloatProperty(name='Offset M', default=0.0)
    bias: FloatProperty(name='Bias', default=0.0)
    step: FloatProperty(name='Step', default=0.0)
    min_value: FloatProperty(name='Min', default=0.0)
    max_value: FloatProperty(name='Max', default=1.0)
    min_m: FloatProperty(name='Min M', default=0.0)
    max_m: FloatProperty(name='Max M', default=0.0)
    min_property: StringProperty(name='Min Property', default='')
    max_property: StringProperty(name='Max Property', default='')
    shader: StringProperty(name='Shader', default='')
    texture: StringProperty(name='Texture', default='')
    interaction_type: EnumProperty(
        name='Interaction', items=INTERACTION_TYPES,
        default='carrier-wire')
    alpha_factor: FloatProperty(name='Alpha Factor', default=0.01)
    power: IntProperty(name='Power', default=2, min=0)
    spherical: BoolProperty(name='Spherical', default=False)
    two_sides: BoolProperty(name='Two Sides', default=False)
    use_personality: BoolProperty(name='Use Personality', default=False)
    branch_durations: StringProperty(
        name='Branch Durations',
        description='Semicolon separated seconds, e.g. 0.8;0.2',
        default='')
    condition_property: StringProperty(name='Condition Property', default='')
    condition_operator: EnumProperty(
        name='Condition Operator', items=CONDITION_OPERATORS,
        default='greater-than')
    condition_value: FloatProperty(name='Condition Value', default=0.0)
    interpolation: StringProperty(
        name='Interpolation',
        description='Semicolon separated ind:dep pairs, e.g. 0:0;300:4',
        default='')
    axis_mode: EnumProperty(name='Axis Mode', items=AXIS_MODES, default='vector')
    axis_vector: FloatVectorProperty(
        name='Axis Vector', subtype='XYZ', default=(0.0, 1.0, 0.0), size=3)
    axis_point_1: FloatVectorProperty(
        name='Axis Point 1', subtype='TRANSLATION', default=(0.0, 0.0, 0.0),
        size=3)
    axis_point_2: FloatVectorProperty(
        name='Axis Point 2', subtype='TRANSLATION', default=(0.0, 1.0, 0.0),
        size=3)
    axis_object_name: StringProperty(name='Axis Object', default='')
    swap_axis_direction: BoolProperty(name='Swap Axis Direction', default=False)
    center: FloatVectorProperty(
        name='Center', subtype='TRANSLATION', default=(0.0, 0.0, 0.0), size=3)
    x_min: FloatProperty(name='X Min', default=1.0)
    y_min: FloatProperty(name='Y Min', default=1.0)
    z_min: FloatProperty(name='Z Min', default=1.0)
    x_factor: FloatProperty(name='X Factor', default=0.0)
    y_factor: FloatProperty(name='Y Factor', default=0.0)
    z_factor: FloatProperty(name='Z Factor', default=0.0)
    x_offset: FloatProperty(name='X Offset', default=0.0)
    y_offset: FloatProperty(name='Y Offset', default=0.0)
    z_offset: FloatProperty(name='Z Offset', default=0.0)


class FGParticleItem(PropertyGroup):
    enabled: BoolProperty(name='Enabled', default=True)
    label: StringProperty(name='Label', default='Particle')
    name: StringProperty(name='Name', default='')
    type: EnumProperty(name='Type', items=PARTICLE_TYPES, default='normal')
    attach: EnumProperty(name='Attach', items=PARTICLE_ATTACH, default='local')
    align: EnumProperty(name='Align', items=PARTICLE_ALIGN, default='billboard')
    texture: StringProperty(name='Texture', default='')
    emissive: BoolProperty(name='Emissive', default=False)
    lighting: BoolProperty(name='Lighting', default=False)
    offsets_location: FloatVectorProperty(
        name='Offsets', subtype='TRANSLATION', default=(0.0, 0.0, 0.0), size=3)
    offsets_rotation: FloatVectorProperty(
        name='Rotation', subtype='XYZ', default=(0.0, 0.0, 0.0), size=3)
    condition_property: StringProperty(name='Condition Property', default='')
    condition_operator: EnumProperty(
        name='Condition Operator', items=CONDITION_OPERATORS,
        default='greater-than')
    condition_value: FloatProperty(name='Condition Value', default=0.0)


class FGSubmodelItem(PropertyGroup):
    enabled: BoolProperty(name='Enabled', default=True)
    label: StringProperty(name='Label', default='Submodel')
    name: StringProperty(name='Name', default='')
    model: StringProperty(name='Model', default='')
    trigger: StringProperty(name='Trigger', default='')
    speed: FloatProperty(name='Speed', default=0.0)
    repeat: BoolProperty(name='Repeat', default=False)
    delay: FloatProperty(name='Delay', default=0.0)
    count: IntProperty(name='Count', default=1)
    x_offset: FloatProperty(name='X Offset', default=0.0)
    y_offset: FloatProperty(name='Y Offset', default=0.0)
    z_offset: FloatProperty(name='Z Offset', default=0.0)
    yaw_offset: FloatProperty(name='Yaw Offset', default=0.0)
    pitch_offset: FloatProperty(name='Pitch Offset', default=0.0)
    life: FloatProperty(name='Life', default=0.0)
    buoyancy: FloatProperty(name='Buoyancy', default=0.0)
    wind: BoolProperty(name='Wind', default=False)
    cd: FloatProperty(name='Cd', default=0.0)
    eda: FloatProperty(name='Eda', default=0.0)
    weight: FloatProperty(name='Weight', default=0.0)
    contents: StringProperty(name='Contents', default='')


class FGSceneProperties(PropertyGroup):
    enabled: BoolProperty(
        name='Use Scene XML Data',
        description='Include scene-level FlightGear XML metadata such as wrapper offsets, scale, and submodels',
        default=True)
    ac_path: StringProperty(
        name='AC Path',
        description='Relative path written to <model><path>; defaults to a sibling .ac file',
        default='')
    no_preview: BoolProperty(name='No Preview', default=False)
    offsets_location: FloatVectorProperty(
        name='Offsets', subtype='TRANSLATION', default=(0.0, 0.0, 0.0), size=3)
    offsets_rotation: FloatVectorProperty(
        name='Rotation', subtype='XYZ', default=(0.0, 0.0, 0.0), size=3)
    model_scale: FloatVectorProperty(
        name='Scale',
        description='Scale written to <model> as x-scale/y-scale/z-scale',
        default=(1.0, 1.0, 1.0),
        size=3)
    defaults_axis_order: EnumProperty(
        name='Axis Defaults', items=DEFAULT_AXIS_ORDER, default='none')
    extra_xml_text: PointerProperty(name='Extra XML Snippet', type=bpy.types.Text)
    submodels: CollectionProperty(type=FGSubmodelItem)
    submodels_index: IntProperty(default=0)


class FGObjectProperties(PropertyGroup):
    enabled: BoolProperty(
        name='Use Object XML Data',
        description='Include object-level FlightGear XML metadata for this object',
        default=False)
    extra_xml_text: PointerProperty(name='Extra XML Snippet', type=bpy.types.Text)
    effects: CollectionProperty(type=FGEffectItem)
    effects_index: IntProperty(default=0)
    animations: CollectionProperty(type=FGAnimationItem)
    animations_index: IntProperty(default=0)
    particles: CollectionProperty(type=FGParticleItem)
    particles_index: IntProperty(default=0)


class FG_UL_Items(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            label = getattr(item, 'label', '')
            if not label:
                label = getattr(item, 'name', '')
            if not label:
                label = getattr(item, 'type', 'Item')
            layout.prop(item, 'enabled', text='')
            layout.label(text=label)
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text='')


class FG_OT_ListAdd(Operator):
    bl_idname = 'flightgear_xml.list_add'
    bl_label = 'Add FlightGear Entry'
    bl_options = {'INTERNAL'}

    owner_kind: EnumProperty(
        items=(('SCENE', 'Scene', ''), ('OBJECT', 'Object', '')),
        default='OBJECT')
    collection_name: StringProperty(default='')
    index_name: StringProperty(default='')

    def execute(self, context):
        owner = context.scene.flightgear_xml
        if self.owner_kind == 'OBJECT':
            if context.object is None:
                return {'CANCELLED'}
            owner = context.object.flightgear_xml

        collection = getattr(owner, self.collection_name)
        item = collection.add()
        count = len(collection)
        if hasattr(item, 'label'):
            item.label = _default_item_label(self.collection_name, count)
        if hasattr(item, 'name') and not item.name:
            item.name = _default_item_label(self.collection_name, count)
        setattr(owner, self.index_name, count - 1)
        return {'FINISHED'}


class FG_OT_ListRemove(Operator):
    bl_idname = 'flightgear_xml.list_remove'
    bl_label = 'Remove FlightGear Entry'
    bl_options = {'INTERNAL'}

    owner_kind: EnumProperty(
        items=(('SCENE', 'Scene', ''), ('OBJECT', 'Object', '')),
        default='OBJECT')
    collection_name: StringProperty(default='')
    index_name: StringProperty(default='')

    def execute(self, context):
        owner = context.scene.flightgear_xml
        if self.owner_kind == 'OBJECT':
            if context.object is None:
                return {'CANCELLED'}
            owner = context.object.flightgear_xml

        collection = getattr(owner, self.collection_name)
        index = getattr(owner, self.index_name)
        if 0 <= index < len(collection):
            collection.remove(index)
            setattr(owner, self.index_name, min(index, len(collection) - 1))
        return {'FINISHED'}


class FG_OT_Export(Operator, ExportHelper):
    """Export FlightGear XML sidecar and AC3D model"""
    bl_idname = 'export_scene.export_flightgear_ac3d'
    bl_label = 'Export FlightGear AC3D/XML'
    bl_options = {'PRESET'}

    filename_ext = '.xml'
    v_info = (7, 2, 1)

    filter_glob: StringProperty(default='*.xml', options={'HIDDEN'})

    axis_forward: EnumProperty(
        name='Forward',
        items=(('X', 'X Forward', ''),
               ('Y', 'Y Forward', ''),
               ('Z', 'Z Forward', ''),
               ('-X', '-X Forward', ''),
               ('-Y', '-Y Forward', ''),
               ('-Z', '-Z Forward', '')),
        default='-Z')

    axis_up: EnumProperty(
        name='Up',
        items=(('X', 'X Up', ''),
               ('Y', 'Y Up', ''),
               ('Z', 'Z Up', ''),
               ('-X', '-X Up', ''),
               ('-Y', '-Y Up', ''),
               ('-Z', '-Z Up', '')),
        default='Y')

    export_rots: EnumProperty(
        name='Matrices',
        description=(
            'Some loaders interpret the matrices wrong, to be safe, '
            'use Apply before Export.'),
        items=(('apply', 'Apply before export', ''),
               ('export', 'Export', '')),
        default='apply')

    use_render_layers: BoolProperty(
        name='Only View Layers',
        description='Only export from selected view layers',
        default=True)
    use_selection: BoolProperty(
        name='Selection Only',
        description='Export selected objects only',
        default=False)
    merge_materials: BoolProperty(
        name='Merge materials',
        description='Merge materials that are identical',
        default=False)
    global_doublesided: BoolProperty(
        name='Double sided',
        description='If all geometry in AC3D will be double sided or backface culled.',
        default=False)
    amb_as_diff: BoolProperty(
        name='Amb same as Diff',
        description='Export AC3D ambient colour to be like Diffuse color',
        default=False)
    ambient: FloatVectorProperty(
        name='Set amb',
        description='Ambient color',
        subtype='COLOR',
        unit='NONE',
        default=(0.5, 0.5, 0.5),
        max=1.0,
        min=0.0)
    export_lines: BoolProperty(
        name='Export lines',
        description='Export standalone edges, bezier curves etc. as AC3D lines.',
        default=False)
    export_hidden: BoolProperty(
        name='Export hidden objects',
        description='Export hidden objects using AC3D hidden tokens.',
        default=False)
    export_lights: BoolProperty(
        name='Export lights',
        description='Export Blender lights as AC3D point lights.',
        default=False)
    crease_angle: FloatProperty(
        name='Crease Angle',
        description='Crease/smooth angle for all exported .ac faces.',
        default=radians(40.0),
        options={'ANIMATABLE'},
        unit='ROTATION',
        subtype='ANGLE')
    xml_add_scale: BoolProperty(
        name='Add Scale Animation',
        description='Emit a simple FlightGear scale animation in the XML wrapper',
        default=False)
    xml_scale_object_choice: EnumProperty(
        name='Scale Object',
        description='Choose the AC object name to scale',
        items=_quick_object_items,
        default='__ACTIVE__')
    xml_scale_object_custom: StringProperty(
        name='Custom Scale Object',
        description='Custom AC object name to scale',
        default='')
    xml_scale_factors: FloatVectorProperty(
        name='Scale Factors',
        description='Fixed scale factors written as x-offset/y-offset/z-offset',
        default=(1.0, 1.0, 1.0),
        size=3)
    xml_scale_center: FloatVectorProperty(
        name='Scale Center',
        description='Optional center point for the scale animation',
        subtype='TRANSLATION',
        default=(0.0, 0.0, 0.0),
        size=3)
    xml_add_rotation: BoolProperty(
        name='Add Rotation Animation',
        description='Emit a simple FlightGear rotation/spin animation in the XML wrapper',
        default=False)
    xml_rotation_type: EnumProperty(
        name='Rotation Type',
        items=(('rotate', 'Rotate', ''), ('spin', 'Spin', '')),
        default='rotate')
    xml_rotation_object_choice: EnumProperty(
        name='Rotate Object',
        description='Choose the AC object name to animate',
        items=_quick_object_items,
        default='__ACTIVE__')
    xml_rotation_object_custom: StringProperty(
        name='Custom Rotate Object',
        description='Custom AC object name to animate',
        default='')
    xml_rotation_property_choice: EnumProperty(
        name='Property',
        description='Choose a common FlightGear property path',
        items=QUICK_PROPERTY_PRESETS,
        default='sim/time/elapsed-sec')
    xml_rotation_property_custom: StringProperty(
        name='Custom Property',
        description='Custom FlightGear property path that drives the rotation',
        default='')
    xml_rotation_factor: FloatProperty(
        name='Factor',
        description='Scale factor applied to the property value',
        default=1.0)
    xml_rotation_offset_deg: FloatProperty(
        name='Offset Deg',
        description='Offset in degrees for rotate animations',
        default=0.0)
    xml_rotation_axis: FloatVectorProperty(
        name='Axis',
        description='Axis vector for the rotation animation',
        subtype='XYZ',
        default=(0.0, 1.0, 0.0),
        size=3)
    xml_rotation_center: FloatVectorProperty(
        name='Center',
        description='Optional center point for the rotation animation',
        subtype='TRANSLATION',
        default=(0.0, 0.0, 0.0),
        size=3)

    def _has_operator_property(self, property_name):
        try:
            self.path_resolve(property_name, False)
            return True
        except (AttributeError, TypeError, ValueError):
            return False

    def _prop_if_available(self, layout, property_name):
        if self._has_operator_property(property_name):
            layout.prop(self, property_name)
            return True
        return False

    def draw(self, context):
        layout = self.layout
        scene_props = context.scene.flightgear_xml

        ac_box = layout.box()
        ac_box.label(text='AC3D Data')
        ac_box.prop(self, 'axis_forward')
        ac_box.prop(self, 'axis_up')
        ac_box.prop(self, 'export_rots')
        ac_box.prop(self, 'use_render_layers')
        ac_box.prop(self, 'use_selection')
        ac_box.prop(self, 'merge_materials')
        ac_box.prop(self, 'global_doublesided')
        ac_box.prop(self, 'amb_as_diff')
        if not self.amb_as_diff:
            ac_box.prop(self, 'ambient')
        ac_box.prop(self, 'export_lines')
        ac_box.prop(self, 'export_hidden')
        ac_box.prop(self, 'export_lights')
        ac_box.prop(self, 'crease_angle')

        xml_box = layout.box()
        xml_box.label(text='XML Data')
        xml_box.prop(scene_props, 'enabled')
        scene_col = xml_box.column()
        scene_col.enabled = scene_props.enabled
        scene_col.prop(scene_props, 'ac_path')
        scene_col.prop(scene_props, 'no_preview')
        scene_col.prop(scene_props, 'defaults_axis_order')
        scene_col.prop(scene_props, 'offsets_location')
        scene_col.prop(scene_props, 'offsets_rotation')
        scene_col.prop(scene_props, 'model_scale')

        helper_box = xml_box.box()
        helper_box.label(text='Quick XML Helpers')
        has_scale_toggle = self._prop_if_available(helper_box, 'xml_add_scale')
        if has_scale_toggle and getattr(self, 'xml_add_scale', False):
            has_scale_choice = self._prop_if_available(helper_box, 'xml_scale_object_choice')
            if has_scale_choice and getattr(self, 'xml_scale_object_choice', '') == '__CUSTOM__':
                self._prop_if_available(helper_box, 'xml_scale_object_custom')
            self._prop_if_available(helper_box, 'xml_scale_factors')
            self._prop_if_available(helper_box, 'xml_scale_center')

        has_rotation_toggle = self._prop_if_available(helper_box, 'xml_add_rotation')
        if not has_rotation_toggle:
            helper_box.label(text='Rotation helper unavailable. Reload add-on.', icon='ERROR')
        elif getattr(self, 'xml_add_rotation', False):
            self._prop_if_available(helper_box, 'xml_rotation_type')
            has_rotation_choice = self._prop_if_available(helper_box, 'xml_rotation_object_choice')
            if has_rotation_choice and getattr(self, 'xml_rotation_object_choice', '') == '__CUSTOM__':
                self._prop_if_available(helper_box, 'xml_rotation_object_custom')
            has_rotation_property = self._prop_if_available(helper_box, 'xml_rotation_property_choice')
            if has_rotation_property and getattr(self, 'xml_rotation_property_choice', '') == '__CUSTOM__':
                self._prop_if_available(helper_box, 'xml_rotation_property_custom')
            self._prop_if_available(helper_box, 'xml_rotation_factor')
            if getattr(self, 'xml_rotation_type', 'rotate') == 'rotate':
                self._prop_if_available(helper_box, 'xml_rotation_offset_deg')
            self._prop_if_available(helper_box, 'xml_rotation_axis')
            self._prop_if_available(helper_box, 'xml_rotation_center')

    def execute(self, context):
        if context.active_object and context.active_object.mode == 'EDIT':
            self.report({'ERROR'}, 'Cannot export FlightGear AC3D/XML in edit mode.')
            return {'CANCELLED'}

        scene_props = context.scene.flightgear_xml

        xml_path = self.filepath
        if not xml_path.lower().endswith('.xml'):
            xml_path = os.path.splitext(xml_path)[0] + '.xml'

        xml_dir = os.path.dirname(xml_path)
        if xml_dir:
            os.makedirs(xml_dir, exist_ok=True)

        ac_target = scene_props.ac_path.strip()
        if not ac_target:
            ac_target = os.path.splitext(os.path.basename(xml_path))[0] + '.ac'

        if os.path.isabs(ac_target):
            ac_path = os.path.normpath(ac_target)
            ac_xml_path = os.path.relpath(ac_path, xml_dir or '.')
        else:
            ac_path = os.path.normpath(os.path.join(xml_dir or '.', ac_target))
            ac_xml_path = ac_target

        ac_dir = os.path.dirname(ac_path)
        if ac_dir:
            os.makedirs(ac_dir, exist_ok=True)

        from . import export_ac3d

        global_matrix = axis_conversion(
            to_forward=self.axis_forward,
            to_up=self.axis_up)
        export_rot = self.export_rots == 'export'

        export_ac3d.AC3D_OT_Export(
            self,
            context,
            filepath=ac_path,
            global_matrix=global_matrix,
            export_rot=export_rot,
            use_render_layers=self.use_render_layers,
            use_selection=self.use_selection,
            merge_materials=self.merge_materials,
            amb_as_diff=self.amb_as_diff,
            ambient=self.ambient,
            export_lines=self.export_lines,
            export_hidden=self.export_hidden,
            export_lights=self.export_lights,
            crease_angle=self.crease_angle,
            global_doublesided=self.global_doublesided)

        document = self._build_xml_document(context, ac_xml_path.replace(os.sep, '/'))
        ET.indent(document, space='  ')
        document.write(xml_path, encoding='utf-8', xml_declaration=True)

        self.report(
            {'INFO'},
            'Exported FlightGear XML {0} and AC3D {1}'.format(
                os.path.basename(xml_path), os.path.basename(ac_path)))
        return {'FINISHED'}

    def _warn(self, message):
        self.report({'WARNING'}, message)

    def _resolve_target_object_name(self, context, choice, custom_name):
        if choice == '__CUSTOM__':
            return custom_name.strip()
        if choice == '__ACTIVE__':
            if context.active_object:
                return context.active_object.name
            return ''
        return choice.strip()

    def _resolve_rotation_property(self):
        property_choice = getattr(self, 'xml_rotation_property_choice', '')
        if property_choice == '__CUSTOM__':
            return getattr(self, 'xml_rotation_property_custom', '').strip()
        return property_choice.strip()

    def _append_quick_xml_data(self, context, root):
        if self.xml_add_scale:
            target_name = self._resolve_target_object_name(
                context,
                self.xml_scale_object_choice,
                self.xml_scale_object_custom)
            if not target_name:
                self._warn('Skipping quick scale animation because no target object name was provided.')
            else:
                animation_node = ET.SubElement(root, 'animation')
                _append_text(animation_node, 'type', 'scale')
                _append_text(animation_node, 'object-name', target_name)
                _append_float(animation_node, 'x-offset', self.xml_scale_factors[0])
                _append_float(animation_node, 'y-offset', self.xml_scale_factors[1])
                _append_float(animation_node, 'z-offset', self.xml_scale_factors[2])
                _append_center(animation_node, self.xml_scale_center)

        if getattr(self, 'xml_add_rotation', False):
            target_name = self._resolve_target_object_name(
                context,
                getattr(self, 'xml_rotation_object_choice', '__ACTIVE__'),
                getattr(self, 'xml_rotation_object_custom', ''))
            property_path = self._resolve_rotation_property()
            if not target_name:
                self._warn('Skipping quick rotation animation because no target object name was provided.')
            elif not property_path:
                self._warn('Skipping quick rotation animation because no FlightGear property path was provided.')
            else:
                animation_node = ET.SubElement(root, 'animation')
                _append_text(animation_node, 'type', getattr(self, 'xml_rotation_type', 'rotate'))
                _append_text(animation_node, 'object-name', target_name)
                _append_text(animation_node, 'property', property_path)
                rotation_factor = getattr(self, 'xml_rotation_factor', 1.0)
                if abs(rotation_factor - 1.0) > 1e-8:
                    _append_float(animation_node, 'factor', rotation_factor)

                rotation_type = getattr(self, 'xml_rotation_type', 'rotate')
                rotation_offset = getattr(self, 'xml_rotation_offset_deg', 0.0)
                if rotation_type == 'rotate' and abs(rotation_offset) > 1e-8:
                    _append_float(animation_node, 'offset-deg', rotation_offset)

                axis = ET.SubElement(animation_node, 'axis')
                rotation_axis = getattr(self, 'xml_rotation_axis', (0.0, 1.0, 0.0))
                _append_float(axis, 'x', rotation_axis[0])
                _append_float(axis, 'y', rotation_axis[1])
                _append_float(axis, 'z', rotation_axis[2])
                _append_center(animation_node, getattr(self, 'xml_rotation_center', (0.0, 0.0, 0.0)))

    def _build_xml_document(self, context, ac_xml_path):
        scene_props = context.scene.flightgear_xml
        root = ET.Element('PropertyList')

        if scene_props.enabled and scene_props.defaults_axis_order != 'none':
            defaults = ET.SubElement(root, 'defaults')
            if scene_props.defaults_axis_order == 'xyz':
                ET.SubElement(defaults, 'axis-animation-vertex-order-xyz')
            else:
                ET.SubElement(defaults, 'axis-animation-vertex-order-x')

        model = ET.SubElement(root, 'model')
        _append_text(model, 'path', ac_xml_path)
        if scene_props.enabled and scene_props.no_preview:
            ET.SubElement(model, 'nopreview')
        if scene_props.enabled:
            _append_offsets(model,
                            scene_props.offsets_location,
                            scene_props.offsets_rotation)
            _append_model_scale(model, scene_props.model_scale)

        for obj in _iter_export_objects(context, self.use_selection):
            props = obj.flightgear_xml
            if not _has_object_xml_data(props):
                continue

            default_name = obj.name

            for effect in props.effects:
                if not effect.enabled or not effect.effect_path.strip():
                    continue
                effect_node = ET.SubElement(root, 'effect')
                _append_text(effect_node, 'inherits-from', effect.effect_path.strip())
                _append_text(
                    effect_node,
                    'object-name',
                    effect.object_name.strip() or default_name)

            for animation in props.animations:
                if not animation.enabled:
                    continue
                animation_node = ET.SubElement(root, 'animation')
                _append_text(animation_node, 'type', animation.type)
                _append_text(
                    animation_node,
                    'object-name',
                    animation.object_name.strip() or default_name)

                if animation.property.strip():
                    _append_text(animation_node, 'property', animation.property.strip())
                if animation.property_base.strip():
                    _append_text(animation_node, 'property-base', animation.property_base.strip())

                if abs(animation.factor - 1.0) > 1e-8:
                    _append_float(animation_node, 'factor', animation.factor)
                if abs(animation.offset) > 1e-8:
                    _append_float(animation_node, 'offset', animation.offset)
                if abs(animation.offset_deg) > 1e-8:
                    _append_float(animation_node, 'offset-deg', animation.offset_deg)
                if abs(animation.offset_m) > 1e-8:
                    _append_float(animation_node, 'offset-m', animation.offset_m)
                if abs(animation.bias) > 1e-8:
                    _append_float(animation_node, 'bias', animation.bias)
                if abs(animation.step) > 1e-8:
                    _append_float(animation_node, 'step', animation.step)

                if animation.type in {'rotate', 'translate', 'spin', 'textranslate',
                                      'texrotate', 'flash'}:
                    _append_axis(animation_node, animation)
                if animation.type in {'rotate', 'spin', 'scale', 'dist-scale',
                                      'flash'}:
                    _append_center(animation_node, animation.center)

                if animation.type == 'shader':
                    if animation.shader.strip():
                        _append_text(animation_node, 'shader', animation.shader.strip())
                    if animation.texture.strip():
                        _append_text(animation_node, 'texture', animation.texture.strip())
                elif animation.type == 'interaction':
                    _append_text(
                        animation_node,
                        'interaction-type',
                        animation.interaction_type)
                elif animation.type == 'alpha-test':
                    _append_float(animation_node, 'alpha-factor', animation.alpha_factor)
                elif animation.type == 'billboard':
                    if animation.spherical:
                        _append_bool(animation_node, 'spherical', True)
                elif animation.type == 'flash':
                    _append_float(animation_node, 'power', animation.power)
                    _append_bool(animation_node, 'two-sides', animation.two_sides)
                    _append_float(animation_node, 'min', animation.min_value)
                    _append_float(animation_node, 'max', animation.max_value)
                elif animation.type == 'blend':
                    _append_float(animation_node, 'min', animation.min_value)
                    _append_float(animation_node, 'max', animation.max_value)
                elif animation.type == 'range':
                    if abs(animation.min_m) > 1e-8:
                        _append_float(animation_node, 'min-m', animation.min_m)
                    if animation.min_property.strip():
                        _append_text(animation_node, 'min-property', animation.min_property.strip())
                    if abs(animation.max_m) > 1e-8:
                        _append_float(animation_node, 'max-m', animation.max_m)
                    if animation.max_property.strip():
                        _append_text(animation_node, 'max-property', animation.max_property.strip())
                elif animation.type == 'scale':
                    for axis_name, minimum, factor, offset in (
                        ('x', animation.x_min, animation.x_factor, animation.x_offset),
                        ('y', animation.y_min, animation.y_factor, animation.y_offset),
                        ('z', animation.z_min, animation.z_factor, animation.z_offset),
                    ):
                        if abs(minimum - 1.0) > 1e-8:
                            _append_float(animation_node, '{0}-min'.format(axis_name), minimum)
                        if abs(factor) > 1e-8:
                            _append_float(animation_node, '{0}-factor'.format(axis_name), factor)
                        if abs(offset) > 1e-8:
                            _append_float(animation_node, '{0}-offset'.format(axis_name), offset)
                elif animation.type == 'timed' and animation.branch_durations.strip():
                    for entry in animation.branch_durations.split(';'):
                        entry = entry.strip()
                        if not entry:
                            continue
                        try:
                            duration = float(entry)
                        except ValueError:
                            self._warn('Skipping invalid branch duration: {0}'.format(entry))
                            continue
                        _append_float(animation_node, 'branch-duration-sec', duration)
                    if animation.use_personality:
                        _append_bool(animation_node, 'use-personality', True)

                _append_condition(
                    animation_node,
                    animation.condition_property,
                    animation.condition_operator,
                    animation.condition_value)
                _append_interpolation(animation_node, animation.interpolation, self._warn)

            for particle in props.particles:
                if not particle.enabled:
                    continue
                particle_node = ET.SubElement(root, 'particlesystem')
                _append_text(particle_node, 'type', particle.type)
                if particle.name.strip():
                    _append_text(particle_node, 'name', particle.name.strip())
                if particle.texture.strip():
                    _append_text(particle_node, 'texture', particle.texture.strip())
                _append_text(particle_node, 'attach', particle.attach)
                _append_text(particle_node, 'align', particle.align)
                if particle.emissive:
                    _append_bool(particle_node, 'emissive', True)
                if particle.lighting:
                    _append_bool(particle_node, 'lighting', True)
                _append_offsets(
                    particle_node,
                    particle.offsets_location,
                    particle.offsets_rotation)
                _append_condition(
                    particle_node,
                    particle.condition_property,
                    particle.condition_operator,
                    particle.condition_value)

            _append_text_block_children(root, props.extra_xml_text, self._warn)

        if scene_props.enabled:
            for submodel in scene_props.submodels:
                if not submodel.enabled or not submodel.model.strip():
                    continue
                submodel_node = ET.SubElement(root, 'submodel')
                if submodel.name.strip():
                    _append_text(submodel_node, 'name', submodel.name.strip())
                _append_text(submodel_node, 'model', submodel.model.strip())
                if submodel.trigger.strip():
                    _append_text(submodel_node, 'trigger', submodel.trigger.strip())
                _append_float(submodel_node, 'speed', submodel.speed)
                _append_bool(submodel_node, 'repeat', submodel.repeat)
                if abs(submodel.delay) > 1e-8:
                    _append_float(submodel_node, 'delay', submodel.delay)
                _append_text(submodel_node, 'count', submodel.count)
                _append_float(submodel_node, 'x-offset', submodel.x_offset)
                _append_float(submodel_node, 'y-offset', submodel.y_offset)
                _append_float(submodel_node, 'z-offset', submodel.z_offset)
                _append_float(submodel_node, 'yaw-offset', submodel.yaw_offset)
                _append_float(submodel_node, 'pitch-offset', submodel.pitch_offset)
                if abs(submodel.life) > 1e-8:
                    _append_float(submodel_node, 'life', submodel.life)
                if abs(submodel.buoyancy) > 1e-8:
                    _append_float(submodel_node, 'buoyancy', submodel.buoyancy)
                if submodel.wind:
                    _append_bool(submodel_node, 'wind', True)
                if abs(submodel.cd) > 1e-8:
                    _append_float(submodel_node, 'cd', submodel.cd)
                if abs(submodel.eda) > 1e-8:
                    _append_float(submodel_node, 'eda', submodel.eda)
                if abs(submodel.weight) > 1e-8:
                    _append_float(submodel_node, 'weight', submodel.weight)
                if submodel.contents.strip():
                    _append_text(submodel_node, 'contents', submodel.contents.strip())

            _append_text_block_children(root, scene_props.extra_xml_text, self._warn)

        self._append_quick_xml_data(context, root)
        return ET.ElementTree(root)


class FG_PT_ScenePanel(Panel):
    bl_label = 'FlightGear XML'
    bl_idname = 'FG_PT_scene_panel'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'scene'

    def draw(self, context):
        layout = self.layout
        props = context.scene.flightgear_xml

        layout.prop(props, 'enabled')
        layout.prop(props, 'ac_path')
        layout.prop(props, 'no_preview')
        layout.prop(props, 'defaults_axis_order')
        layout.prop(props, 'offsets_location')
        layout.prop(props, 'offsets_rotation')
        layout.prop(props, 'model_scale')
        layout.template_ID(props, 'extra_xml_text', new='text.new')


class FG_PT_SceneSubmodels(Panel):
    bl_label = 'Submodels'
    bl_idname = 'FG_PT_scene_submodels'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'scene'
    bl_parent_id = 'FG_PT_scene_panel'

    def draw(self, context):
        layout = self.layout
        props = context.scene.flightgear_xml

        row = layout.row()
        row.template_list(
            'FG_UL_Items', '', props, 'submodels', props, 'submodels_index')
        col = row.column(align=True)
        add_op = col.operator('flightgear_xml.list_add', text='', icon='ADD')
        add_op.owner_kind = 'SCENE'
        add_op.collection_name = 'submodels'
        add_op.index_name = 'submodels_index'
        remove_op = col.operator('flightgear_xml.list_remove', text='', icon='REMOVE')
        remove_op.owner_kind = 'SCENE'
        remove_op.collection_name = 'submodels'
        remove_op.index_name = 'submodels_index'

        if 0 <= props.submodels_index < len(props.submodels):
            item = props.submodels[props.submodels_index]
            box = layout.box()
            box.prop(item, 'label')
            box.prop(item, 'enabled')
            box.prop(item, 'name')
            box.prop(item, 'model')
            box.prop(item, 'trigger')
            box.prop(item, 'speed')
            box.prop(item, 'repeat')
            box.prop(item, 'delay')
            box.prop(item, 'count')
            box.prop(item, 'x_offset')
            box.prop(item, 'y_offset')
            box.prop(item, 'z_offset')
            box.prop(item, 'yaw_offset')
            box.prop(item, 'pitch_offset')
            box.prop(item, 'life')
            box.prop(item, 'buoyancy')
            box.prop(item, 'wind')
            box.prop(item, 'cd')
            box.prop(item, 'eda')
            box.prop(item, 'weight')
            box.prop(item, 'contents')


class FG_PT_ObjectPanel(Panel):
    bl_label = 'FlightGear XML'
    bl_idname = 'FG_PT_object_panel'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        props = context.object.flightgear_xml

        layout.prop(props, 'enabled')
        layout.label(text='AC object name: {0}'.format(context.object.name))
        layout.template_ID(props, 'extra_xml_text', new='text.new')


class FG_PT_ObjectEffects(Panel):
    bl_label = 'Effects'
    bl_idname = 'FG_PT_object_effects'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'
    bl_parent_id = 'FG_PT_object_panel'

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        props = context.object.flightgear_xml

        row = layout.row()
        row.template_list('FG_UL_Items', '', props, 'effects', props, 'effects_index')
        col = row.column(align=True)
        add_op = col.operator('flightgear_xml.list_add', text='', icon='ADD')
        add_op.owner_kind = 'OBJECT'
        add_op.collection_name = 'effects'
        add_op.index_name = 'effects_index'
        remove_op = col.operator('flightgear_xml.list_remove', text='', icon='REMOVE')
        remove_op.owner_kind = 'OBJECT'
        remove_op.collection_name = 'effects'
        remove_op.index_name = 'effects_index'

        if 0 <= props.effects_index < len(props.effects):
            item = props.effects[props.effects_index]
            box = layout.box()
            box.prop(item, 'label')
            box.prop(item, 'enabled')
            box.prop(item, 'effect_path')
            box.prop(item, 'object_name')


class FG_PT_ObjectAnimations(Panel):
    bl_label = 'Animations'
    bl_idname = 'FG_PT_object_animations'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'
    bl_parent_id = 'FG_PT_object_panel'

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        props = context.object.flightgear_xml

        row = layout.row()
        row.template_list(
            'FG_UL_Items', '', props, 'animations', props, 'animations_index')
        col = row.column(align=True)
        add_op = col.operator('flightgear_xml.list_add', text='', icon='ADD')
        add_op.owner_kind = 'OBJECT'
        add_op.collection_name = 'animations'
        add_op.index_name = 'animations_index'
        remove_op = col.operator('flightgear_xml.list_remove', text='', icon='REMOVE')
        remove_op.owner_kind = 'OBJECT'
        remove_op.collection_name = 'animations'
        remove_op.index_name = 'animations_index'

        if 0 <= props.animations_index < len(props.animations):
            item = props.animations[props.animations_index]
            box = layout.box()
            box.prop(item, 'label')
            box.prop(item, 'enabled')
            box.prop(item, 'type')
            box.prop(item, 'object_name')
            box.prop(item, 'property')
            box.prop(item, 'property_base')
            box.prop(item, 'factor')
            if item.type in {'rotate'}:
                box.prop(item, 'offset_deg')
            elif item.type in {'translate'}:
                box.prop(item, 'offset_m')
            else:
                box.prop(item, 'offset')

            if item.type in {'blend', 'flash'}:
                box.prop(item, 'min_value')
                box.prop(item, 'max_value')

            if item.type == 'range':
                box.prop(item, 'min_m')
                box.prop(item, 'max_m')
                box.prop(item, 'min_property')
                box.prop(item, 'max_property')

            if item.type == 'shader':
                box.prop(item, 'shader')
                box.prop(item, 'texture')
            elif item.type == 'interaction':
                box.prop(item, 'interaction_type')
            elif item.type == 'alpha-test':
                box.prop(item, 'alpha_factor')
            elif item.type == 'billboard':
                box.prop(item, 'spherical')
            elif item.type == 'flash':
                box.prop(item, 'power')
                box.prop(item, 'two_sides')
            elif item.type == 'timed':
                box.prop(item, 'use_personality')
                box.prop(item, 'branch_durations')

            if item.type in {'rotate', 'translate', 'spin', 'textranslate',
                             'texrotate', 'flash'}:
                box.prop(item, 'axis_mode')
                if item.axis_mode == 'object':
                    box.prop(item, 'axis_object_name')
                elif item.axis_mode == 'points':
                    box.prop(item, 'axis_point_1')
                    box.prop(item, 'axis_point_2')
                else:
                    box.prop(item, 'axis_vector')
                box.prop(item, 'swap_axis_direction')

            if item.type in {'rotate', 'spin', 'scale', 'dist-scale', 'flash'}:
                box.prop(item, 'center')

            if item.type == 'scale':
                scale_box = box.box()
                scale_box.label(text='Scale Components')
                scale_box.prop(item, 'x_min')
                scale_box.prop(item, 'y_min')
                scale_box.prop(item, 'z_min')
                scale_box.prop(item, 'x_factor')
                scale_box.prop(item, 'y_factor')
                scale_box.prop(item, 'z_factor')
                scale_box.prop(item, 'x_offset')
                scale_box.prop(item, 'y_offset')
                scale_box.prop(item, 'z_offset')

            box.prop(item, 'condition_property')
            if item.condition_property.strip():
                box.prop(item, 'condition_operator')
                box.prop(item, 'condition_value')
            box.prop(item, 'interpolation')


class FG_PT_ObjectParticles(Panel):
    bl_label = 'Particles'
    bl_idname = 'FG_PT_object_particles'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'
    bl_parent_id = 'FG_PT_object_panel'

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        props = context.object.flightgear_xml

        row = layout.row()
        row.template_list('FG_UL_Items', '', props, 'particles', props, 'particles_index')
        col = row.column(align=True)
        add_op = col.operator('flightgear_xml.list_add', text='', icon='ADD')
        add_op.owner_kind = 'OBJECT'
        add_op.collection_name = 'particles'
        add_op.index_name = 'particles_index'
        remove_op = col.operator('flightgear_xml.list_remove', text='', icon='REMOVE')
        remove_op.owner_kind = 'OBJECT'
        remove_op.collection_name = 'particles'
        remove_op.index_name = 'particles_index'

        if 0 <= props.particles_index < len(props.particles):
            item = props.particles[props.particles_index]
            box = layout.box()
            box.prop(item, 'label')
            box.prop(item, 'enabled')
            box.prop(item, 'name')
            box.prop(item, 'type')
            box.prop(item, 'attach')
            box.prop(item, 'align')
            box.prop(item, 'texture')
            box.prop(item, 'emissive')
            box.prop(item, 'lighting')
            box.prop(item, 'offsets_location')
            box.prop(item, 'offsets_rotation')
            box.prop(item, 'condition_property')
            if item.condition_property.strip():
                box.prop(item, 'condition_operator')
                box.prop(item, 'condition_value')


CLASSES = (
    FGEffectItem,
    FGAnimationItem,
    FGParticleItem,
    FGSubmodelItem,
    FGSceneProperties,
    FGObjectProperties,
    FG_UL_Items,
    FG_OT_ListAdd,
    FG_OT_ListRemove,
    FG_OT_Export,
    FG_PT_ScenePanel,
    FG_PT_SceneSubmodels,
    FG_PT_ObjectPanel,
    FG_PT_ObjectEffects,
    FG_PT_ObjectAnimations,
    FG_PT_ObjectParticles,
)


def register_properties():
    bpy.types.Scene.flightgear_xml = PointerProperty(type=FGSceneProperties)
    bpy.types.Object.flightgear_xml = PointerProperty(type=FGObjectProperties)


def unregister_properties():
    if hasattr(bpy.types.Scene, 'flightgear_xml'):
        del bpy.types.Scene.flightgear_xml
    if hasattr(bpy.types.Object, 'flightgear_xml'):
        del bpy.types.Object.flightgear_xml


def menu_func_export(self, context):
    self.layout.operator(FG_OT_Export.bl_idname, text='FlightGear (.xml + .ac)')