from functools import partial
import maya.cmds as cmds
import pymel.core as pm
import xgenm as xg
import os
import unicodedata


class Utils:

    @staticmethod
    def safe_string(value):
        return unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')


# Look, autodesk, this is how it must've actually worked from the box.
# Amen.
class UiElementWrapper(object):

    def __init__(self, id, default_value='', change_callback=None, project=None):
        self.id_pure = id
        self.on_change = change_callback
        self.value = ''
        self.settings = None

        if default_value:
            self.set_value(default_value)

        if project:
            self.settings = project.settings

    def set_value(self, value):
        if type(value) is unicode:
            value = Utils.safe_string(value)

        self.value = value

        if self.settings:
            self.settings.set(self.id_pure, value)

        if callable(self.on_change):
            self.on_change()


class UiOptionMenu(UiElementWrapper):

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

    def __init__(self, id, object_type='', label='', button_label='Selection', change_callback=None, project=None):
        super(UiObjectSelection, self).__init__(id, change_callback=change_callback, project=project)
        self.object_type = object_type

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
        if self.object_type and not cmds.objectType(obj) == self.object_type:
            return cmds.warning('Selected object is of a wrong type. Anticipated %s.' % self.object_type)

        self.set_value(obj)

    def set_value(self, value):
        super(UiObjectSelection, self).set_value(value)

        # Update textfield value.
        pm.textFieldButtonGrp(self.id, e=True, tx=value)


class UiTextField(UiElementWrapper):

    def __init__(self, id, label='', default_value='', project=None):
        super(UiTextField, self).__init__(id, default_value=default_value, project=project)

        # Create the element itself.
        pm.textFieldGrp(id, label=label, tx=default_value, tcc=self.set_value)


class ProjectSettings:

    def __init__(self):
        pass

    _storage = {}

    def get(self, id, default_value=None):
        result = default_value

        if self.has(id):
            result = self._storage[id]

        return result

    def set(self, id, value):
        self._storage[id] = value

    def has(self, id):
        return id in self._storage and self._storage[id]


class XgenAnimSettingsDependant(object):

    def __init__(self, project, required_settings=[]):
        self.settings = project.settings
        self.required_settings = required_settings

    def validate(self):
        result = True

        for item in self.required_settings:
            if not self.settings.has(item):
                result = False

                break

        return result


class PtxBaker(XgenAnimSettingsDependant):

    @staticmethod
    def perform_conversion(project):
        # Perform the baking procedure.
        (PtxBaker(project)).convert()

    def __init__(self, project):
        super(PtxBaker, self).__init__(project, ['xgenSequence', 'xgenEmitter', 'xgenMap'])

    def convert(self):
        # Validate settings fields.
        if not self.validate():
            return cmds.warning('Missing required settings.')

        path = '%s/xgen/animated_bakes/%s/' % (cmds.workspace(q=True, rd=True), self.settings.get('xgenMap'))
        emitter = self.settings.get('xgenEmitter')
        # bake_file = '%s%s.ptx' %()

        # Bake it.
        for frame in range(int(cmds.playbackOptions(q=True, minTime=True)), int(cmds.playbackOptions(q=True, maxTime=True))):
            # Set current time.
            cmds.currentTime(frame)

            cmds.ptexBake(inMesh=emitter, o=path, bt=self.settings.get('xgenSequence'),
                          tpu=self.settings.get('xgenResolution', 100))

            bake_file = '%s%s.0%s.ptx' % (path, emitter, frame)
            if os.path.isfile(bake_file):
                # shutil.copy2()
                pass


class XgenAnim:

    ui_id = 'xgenanim'
    title = 'xGen Animation Maps'
    version = '0.1'

    def __init__(self):
        self.settings = ProjectSettings()

        if pm.window(self.ui_id, exists=True):
            pm.deleteUI(self.ui_id)

        self.window = pm.window(self.ui_id, title='%s | %s' % (self.title, self.version), mnb=False, mxb=False, sizeable=False)

        # Form the UI.
        with pm.columnLayout():
            with pm.frameLayout(l='Map Properties', cll=False, cl=False):
                self.ui_collection = UiOptionMenu('xgenCollection', label='Collection',
                                                  change_callback=self.update_descriptions, project=self)
                self.ui_description = UiOptionMenu('xgenDescription', label='Description',
                                                   change_callback=self.update_objects, project=self)
                self.ui_objects = UiOptionMenu('xgenObject', label='Object',
                                               change_callback=self.update_attributes, project=self)
                self.ui_attributes = UiOptionMenu('xgenAttribute', label='Attribute',
                                                  project=self)

                # Set the collection items to trigger the rest.
                self.update_collections()

                pm.button('update', label='Update', c=self.update_collections)

                self.ui_sequence = UiObjectSelection('xgenSequence', label='Animated Sequence Node', object_type='file', project=self)
                self.ui_emitter = UiObjectSelection('xgenEmitter', label='xGen Emitter Object', object_type='transform', project=self)
                self.ui_map = UiTextField('xgenMap', label='Result map path', default_value='default/map', project=self)

                pm.button('assign', label='Assign', c=self.assign)

        self.window.show()

    def get_collection(self):
        return self.settings.get('xgenCollection', '')

    def get_description(self):
        return self.settings.get('xgenDescription', '')

    def get_object(self):
        return self.settings.get('xgenObject', '')

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

    def assign(self, flag):
        PtxBaker.perform_conversion(self)


if __name__ == '__main__':
    XgenAnim()
