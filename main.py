from functools import partial
import maya.cmds as cmds
import pymel.core as pm
import xgenm as xg
import os
import shutil


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


# TODO: Implement ui elements factory.
class UiFactory:

    @staticmethod
    def field_change_callback(project, id, value):
        project.settings.set(id, value)

    @staticmethod
    def text_field(project, id, label='', default_value=''):
        return pm.textFieldGrp(id, label=label, tx=default_value, tcc=partial(UiFactory.field_change_callback, project, id))

    @staticmethod
    def range_field(project, id, label='', default_value=0):
        return pm.rangeControl(id, ann=label, min=0, max=1000, cc=partial(UiFactory.field_change_callback, project, id))

    @staticmethod
    def object_selection_callback(group_id, object_type=None):
        obj = cmds.ls(sl=True)

        # Do nothing in case no objects are present in the selection.
        if not len(obj):
            return cmds.warning('Selection is empty.')

        # Otherwise use the first reference.
        obj = obj[0]

        # Check the object type compliance, if any is given.
        if object_type and not cmds.objectType(obj) == object_type:
            return cmds.warning('Selected object is of a wrong type. Anticipated %s.' % object_type)

        pm.textFieldButtonGrp(group_id, e=True, tx=obj)

    @staticmethod
    def object_selection(project, id, label='', object_type=None, default_value=''):
        return pm.textFieldButtonGrp(id, label=label, tx=default_value, bl='Selection',
                              bc=partial(UiFactory.object_selection_callback, id, object_type),
                              tcc=partial(UiFactory.field_change_callback, project, id))

    @staticmethod
    def option_selection(self, id, label='', items_callback=None, change_callback=None, edit=False):
        items = []
        label = label or pm.optionMenu(id, q=True, l=True)
        change_callback = change_callback or ''

        if items_callback:
            items = items_callback()

        result = pm.optionMenu(id, label=label, cc=change_callback, edit=edit)

        for item in pm.optionMenu(result, q=True, ill=True) or []:
            pm.deleteUI(item)

        for item in items:
            pm.menuItem(item, label=item, parent=result)

        if change_callback and len(items):
            change_callback()

        return result

    @staticmethod
    def directory_selection_callback(group_id):
        directory = cmds.fileDialog2(fm=3)

        if len(directory):
            pm.textFieldButtonGrp(group_id, e=True, tx=directory[0])

    def directory_selection(self, id, label='', default_value=''):
        return pm.textFieldButtonGrp(id, label=label, tx=default_value, bl='Browse',
                              bc=partial(self.directory_selection_callback, id),
                              tcc=partial(self.field_change_callback, self, id))


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
                UiFactory.option_selection(self, 'xgenCollection', label='Collection',
                                           items_callback=xg.palettes,
                                           change_callback=self.update_collections)
                UiFactory.option_selection(self, 'xgenDescription', label='Description')
                # Make sure descriptions records are up to date.
                self.update_descriptions()

                UiFactory.object_selection(self, 'xgenSequence', label='Animated Sequence Node', object_type='file')
                UiFactory.object_selection(self, 'xgenEmitter', label='xGen Emitter Object', object_type='transform')
                UiFactory.text_field(self, 'xgenMap', label='Result map path', default_value='default/map')
                UiFactory.range_field(self, 'xgenResolution', label='Result map resolution', default_value=100)
                pm.button('assign', label='Assign', c=self.assign)
                pm.button('update', label='Update', c=self.update_ui)

        self.window.show()

    def update_ui(self, flag):
        self.update_collections()
        self.update_descriptions()

    def update_descriptions(self):
        UiFactory.option_selection(self, 'xgenDescription', edit=True,
                                   items_callback=lambda: xg.descriptions(self.settings.get('xgenCollection', '')))

    def update_collections(self):
        UiFactory.option_selection(self, 'xgenCollection', edit=True,
                                   items_callback=lambda: xg.palettes())

    def assign(self, flag):
        PtxBaker.perform_conversion(self)


if __name__ == '__main__':
    XgenAnim()
