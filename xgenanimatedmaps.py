import maya.cmds as cmds
import maya.OpenMaya as om
import maya.utils as mu
import pymel.core as pm
import xgenm as xg
import os
import shutil
import unicodedata
import re


class Utils:

    @staticmethod
    def safe_string(value):
        if type(value) is unicode:
            value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')

        return value

    @staticmethod
    def use_global_vars(value, project):
        collection = project.settings.get('xgenCollection')
        description = project.settings.get('xgenDescription')
        path = xg.descriptionPath(collection, description)

        return value.replace('${DESC}', path)


class XgenAttributeWrapper(object):

    def __init__(self, id, collection, description, obj):
        self.id = id
        self.collection = collection
        self.description = description
        self.object = obj
        self.value = self.get()

    def get(self):
        return xg.getAttr(self.id, self.collection, self.description, self.object)

    def get_lines(self, cached=True):
        return (self.value if cached else self.get()).split('\\n')

    def commit(self):
        xg.setAttr(self.id, xg.prepForAttribute(self.value), self.collection, self.description, self.object)

        # Refresh the ui.
        xg.xgGlobal.DescriptionEditor.refresh('Full')

    def clear(self):
        self.value = ''

        return self

    def append_line(self, value=''):
        self.value += '%s\n' % value

        return self


# Look, autodesk, this is how it must've actually worked from the box.
# Amen.
class UiElementWrapper(object):
    """
    Implements basic ui element wrapper.
    """

    def __init__(self, id, default_value='', change_callback=None, project=None):
        self.id_pure = id
        self.on_change = change_callback
        self.value = ''
        self.settings = None

        if project:
            self.settings = project.settings

        if default_value:
            self.set_value(default_value)

    def set_value(self, value):
        self.value = value

        if self.settings:
            self.settings.set(self.id_pure, value)

        if callable(self.on_change):
            self.on_change()


class UiButtonToggle(UiElementWrapper):
    """
    Implements toggling button.
    """
    background = [0.3, 0.3, 0.3]

    def __init__(self, id, on_label='', off_label='', callback=None):
        super(UiButtonToggle, self).__init__(id)

        self.id = pm.button(id, label=off_label, c=self.on_click, bgc=self.background)
        self.on_label = on_label
        self.off_label = off_label or on_label
        self.callback = callback
        self.toggled = False

    def on_click(self, flag=False):
        self.toggled = not self.toggled

        background = self.background
        label = self.off_label
        if self.toggled:
            background = [0.2, 0.2, 0.2]
            label = self.on_label

        # Toggle button visuals.
        pm.button(self.id, e=True, bgc=background, label=label)

        # Execute the callback.
        if self.callback:
            self.callback(self.toggled)

class UiProgressBar(UiElementWrapper):
    """
    Implements encapsulated progress bar ui element.
    """

    def __init__(self, id, max_value=100):
        super(UiProgressBar, self).__init__(id)

        self.id = pm.progressBar(id, maxValue=max_value)

        self.max_value = max_value
        self.progress = 0

    def is_cancelled(self):
        return pm.progressBar(self.id, q=True, isCancelled=True) or False

    def cancel(self):
        pm.progressBar(self.id, e=True, isCancelled=True)

        return self

    def set_status(self, value):
        pm.progressBar(self.id, e=True, status=value)

        return self

    def set_max_value(self, value):
        pm.progressBar(self.id, e=True, maxValue=value)
        self.max_value = value

        return self

    def set_step(self, value=1):
        pm.progressBar(self.id, e=True, step=value)
        self.progress += value

        return self

    def set_progress(self, value):
        pm.progressBar(self.id, e=True, progress=value)
        self.progress = value

        return self


class UiOptionMenu(UiElementWrapper):
    """
    Implements encapsulated option menu ui element.
    """

    def __init__(self, id, value='', label='', change_callback=None, project=None):
        super(UiOptionMenu, self).__init__(id, value, change_callback, project)

        # Create the element itself.
        self.id = pm.optionMenu(id, label=label, cc=self.set_value)

    def get_items(self):
        return pm.optionMenu(self.id, q=True, ill=True) or []

    def set_items(self, items):
        for item in self.get_items():
            pm.deleteUI(item)

        if not len(items):
            return

        for item in items:
            pm.menuItem(item, label=item, parent=self.id)

        # Update the element.
        self.set_value(items[0])


class UiObjectSelection(UiElementWrapper):
    """
    Implements encapsulated object selection ui element.
    """

    def __init__(self, id, object_types=None, label='', button_label='Selection', change_callback=None, project=None):
        object_types = object_types or []

        super(UiObjectSelection, self).__init__(id, change_callback=change_callback, project=project)
        self.object_types = object_types

        # Create the element itself.
        self.id = pm.textFieldButtonGrp(id, label=label, bl=button_label, bc=self.object_selection, tcc=self.set_value)

    def object_selection(self):
        obj = cmds.ls(sl=True)

        # Do nothing in case no objects are present in the selection.
        if not len(obj):
            return cmds.warning('The selection is empty.')

        # Otherwise use the first reference.
        obj = obj[0]

        # Check the object type compliance, if any is given.
        if len(self.object_types) and not cmds.objectType(obj) in self.object_types:
            return cmds.warning('Selected object is of a wrong type. Anticipated any of the following types: %s.' % ', '.join(self.object_types))

        self.set_value(obj)

    def set_value(self, value):
        super(UiObjectSelection, self).set_value(value)

        # Update textfield value.
        pm.textFieldButtonGrp(self.id, e=True, tx=value)


class UiTextField(UiElementWrapper):
    """
    Implements encapsulated text field ui element.
    """

    def __init__(self, id, label='', default_value='', project=None):
        super(UiTextField, self).__init__(id, default_value=default_value, project=project)

        # Create the element itself.
        pm.textFieldGrp(id, label=label, tx=default_value, tcc=self.set_value)


class ProjectSettings:
    """
    Implements project settings data structure.
    """

    def __init__(self):
        pass

    _storage = {}

    def get(self, id, default_value=None):
        result = default_value

        if self.has(id) and len(self._storage):
            result = self._storage[id]

        return result

    def set(self, id, value):
        # Ensure value usage safety.
        value = Utils.safe_string(value)

        # Set the storage value.
        self._storage[id] = value

        return self

    def has(self, id):
        return id in self._storage and self._storage[id]


class XgenAnimSettingsDependant(object):

    def __init__(self, project, required_settings=None):
        required_settings = required_settings or []

        self.project = project
        self.required_settings = required_settings

    def get_settings(self, id, default_value=None):
        return self.project.settings.get(id, default_value)

    def validate(self):
        result = True

        for item in self.required_settings:
            if not self.project.settings.has(item):
                result = False

                break

        return result


class PtxBaker(XgenAnimSettingsDependant):

    @staticmethod
    def perform_conversion(project):
        # Perform the baking procedure.
        (PtxBaker(project)).convert()

    @staticmethod
    def perform_preview(project):
        (PtxBaker(project).preview())

    def __init__(self, project):
        super(PtxBaker, self).__init__(project, ['xgenCollection', 'xgenDescription', 'xgenSequence',
                                                 'xgenEmitter', 'xgenAttribute'])

        self.collection = self.get_settings('xgenCollection')
        self.description = self.get_settings('xgenDescription')
        self.emitter = self.get_settings('xgenEmitter')
        self.sequence = self.get_settings('xgenSequence')
        self.is_bakeable = cmds.objectType(self.sequence) == 'file'
        self.obj = self.get_settings('xgenObject')
        self.attr = XgenAttributeWrapper(self.get_settings('xgenAttribute'), self.collection, self.description, self.obj)
        self.expression = self.get_settings('xgenExpression', self.get_expression() or '$a')
        self.tpu = self.get_settings('xgenResolution', 512)

        # Resolve paths.
        self.path_map = '/paintmaps/%s' % self.attr.id
        self.path = '%s/%s/' % (xg.descriptionPath(self.collection, self.description), self.path_map)
        self.path_bake = '%s%s.ptx' % (self.path, self.emitter)

        self.cached_frames = []

    def get_assigned_map(self):
        attr_map = re.search("^[^#]+=map\(\\'(.*?)\\'", self.attr.value)
        if attr_map:
            attr_map = attr_map.group(1).replace('${DESC}', '')

        # Perform regex test.
        return attr_map

    def get_expression(self):
        lines = self.attr.get_lines()
        result = ''

        for index in reversed(range(len(lines))):
            if '$a' in lines[index]:
                result = lines[index]

                break

        return result

    def get_start_frame(self):
        return int(cmds.playbackOptions(q=True, minTime=True))

    def get_end_frame(self):
        return int(cmds.playbackOptions(q=True, maxTime=True))

    def get_current_frame(self):
        return int(cmds.currentTime(q=True))

    def cache_complete(self):
        return range(self.get_start_frame(), self.get_end_frame()) == self.cached_frames

    def cache_get_missing_frame(self):
        frames = range(self.get_start_frame(), self.get_end_frame())
        current_frame = self.get_current_frame()
        bake_frame = None

        if current_frame in frames:
            index = frames.index(current_frame)
            frames = frames[index:] + frames[:index]

        for item in frames:
            if item not in self.cached_frames:
                bake_frame = item

                break

        return bake_frame

    def preview(self):
        if not self.validate():
            return cmds.warning('Missing required settings.')

        def test(*args, **kwargs):
            print('test')

        # Initialize preview callbacks.
        om.MNodeMessage.addAttributeChangedCallback(self.emitter, test)

        # Initialize background conversion loop.
        mu.executeDeferred(self.convert_preview)

    def convert_preview(self):
        if not self.validate():
            return cmds.warning('Missing required settings.')

        # Render closest frame to the left side from current frame.
        if self.cache_complete():
            return

        bake_frame = self.cache_get_missing_frame()
        if not bake_frame:
            return cmds.warning('No frames to bake left.')

        # Bake preview frame.
        self.bake(bake_frame)

        # Store cached frame.
        self.cached_frames.append(bake_frame)

        mu.executeDeferred(self.convert_preview)

    def convert(self, start_frame=None, end_frame=None):
        # Validate settings fields.
        if not self.validate():
            return cmds.warning('Missing required settings.')

        start_frame = start_frame or self.get_start_frame()
        end_frame = end_frame or self.get_end_frame()

        # Check whether the alleged attribute has a map assigned.
        if not self.get_assigned_map():
            return cmds.warning('No map is currently assigned to the channel selected.')

        # Prepare the ui.
        self.project.ui_progress.set_max_value(end_frame).set_progress(start_frame)

        # And the attribute wrapper.
        self.attr.clear().append_line(
            '# This script has been generated by xgen animated maps script.'
        ).append_line(
            "# You're free to modify it as you please, just remember to do that with care."
        ).append_line(
            '# You may be surprised by the enormous size of the script, considering the alleged ability to'
        ).append_line(
            '# assign multiple expression variables within strings, yet this is the safest way of'
        ).append_line(
            '# providing animated maps to xgen channels.'
        ).append_line()

        is_file = cmds.objectType(self.sequence) == 'file'

        for frame in range(start_frame, end_frame):
            # Bake it.
            self.bake(frame)

            # Append a new frame reference to the attribute.
            if not frame == end_frame:
                self.attr.append_line(
                    '%s ($frame <= %s) {' % ('if' if frame == start_frame else 'else if', frame)
                )
            else:
                self.attr.append_line(
                    'else {'
                )

            self.attr.append_line(
                '\t$a=map(\'${DESC}%s/%s.%s.ptx\');' % (self.path_map, self.emitter, frame)
            ).append_line(
                '}'
            )

            # Increase progress bar position.
            self.project.ui_progress.set_step()

        # Set the attribute script.
        self.attr.append_line(self.expression).commit()

    def bake(self, frame):
        result = None

        # Set required frame.
        cmds.currentTime(frame)

        # Make sure source sequence can be baked.
        bake_node = self.sequence
        if not self.is_bakeable:
            bake_node = cmds.convertSolidTx(bake_node, self.emitter, alpha=False, antiAlias=False, bm=2, fts=True,
                                            sp=False, sh=False, ds=False, cr=False, rx=self.tpu, ry=self.tpu, fil='iff',
                                            fileImageName='_xgenBakeTemp')
            if len(bake_node):
                bake_node = bake_node[0]

        cmds.ptexBake(inMesh=self.emitter, o=self.path, bt=bake_node, tpu=self.tpu)

        if not self.is_bakeable:
            cmds.delete(bake_node)

        if os.path.isfile(self.path_bake):
            result = '%s%s.%s.ptx' % (self.path, self.emitter, frame)
            shutil.copy2(self.path_bake, result)

        return result


class XgenAnim:

    ui_id = 'xgenanim'
    title = 'xGen Animated Maps'
    version = '0.2'

    def __init__(self):
        self.settings = ProjectSettings()

        if pm.window(self.ui_id, exists=True):
            pm.deleteUI(self.ui_id)

        self.window = pm.window(self.ui_id, title='%s | %s' % (self.title, self.version), mnb=False, mxb=False, sizeable=True)

        # Form the UI.
        with pm.columnLayout():
            with pm.frameLayout(l='Map Properties', cll=False, cl=False):
                self.ui_collection = UiOptionMenu('xgenCollection', label='Collection',
                                                  change_callback=self.update_descriptions, project=self)
                self.ui_description = UiOptionMenu('xgenDescription', label='Description',
                                                   change_callback=self.update_objects, project=self)
                self.ui_objects = UiOptionMenu('xgenObject', label='Object',
                                               change_callback=self.update_attributes, project=self)
                self.ui_attributes = UiOptionMenu('xgenAttribute', label='Attribute', project=self)

                # Set the collection items to trigger the rest.
                self.update_collections()

                pm.button('update', label='Update', c=self.update_collections)

                self.ui_expression = UiTextField('xgenExpression', label='Final Expression', project=self)
                self.ui_progress = UiProgressBar('xgenProgress', 1000)

                pm.button('assign', label='Assign', c=self.assign)
                self.ui_preview = UiButtonToggle('preview', off_label='Preview', on_label='Stop Preview', callback=self.preview)

        self.window.show()

    def get_collection(self):
        return self.settings.get('xgenCollection', '')

    def get_description(self):
        return self.settings.get('xgenDescription', '')

    def get_object(self):
        return self.settings.get('xgenObject', '')

    def get_attribute(self):
        return self.settings.get('xgenAttribute', '')

    def update_collections(self, flag=False):
        if not self.ui_collection:
            return

        self.ui_collection.set_items(xg.palettes())

    def update_descriptions(self):
        if not self.ui_description:
            return

        collection = self.get_collection()
        descriptions = xg.descriptions(collection)

        self.ui_description.set_items(descriptions)

    def update_objects(self):
        if not self.ui_objects:
            return

        objects = xg.objects(self.get_collection(), self.get_description(), True)
        self.ui_objects.set_items(objects)

    def update_attributes(self):
        if not self.ui_attributes:
            return

        attributes = xg.allAttrs(self.get_collection(), self.get_description(), self.get_object())
        self.ui_attributes.set_items(attributes)

    def get_selection_typed(self, type, inverse=False):
        selection = cmds.ls(sl=True)
        result = None

        for item in selection:
            if cmds.objectType(item) == type:
                if not inverse:
                    result = item
            elif inverse:
                result = item

        return result

    def preview(self, flag=False):
        pass

    def assign(self, preview=False, flag=False):
        # Get selected object.
        object = self.get_selection_typed('transform')
        node = self.get_selection_typed('transform', True)

        if not object or not node:
            return cmds.warning('Selection must contain a target object and texture source node.')

        # Set alleged nodes.
        self.settings.set('xgenEmitter', object).set('xgenSequence', node)

        if not preview:
            # Perform the baking conversion.
            PtxBaker.perform_conversion(self)
        else:
            PtxBaker.preview(self)


if __name__ == '__main__':
    XgenAnim()
