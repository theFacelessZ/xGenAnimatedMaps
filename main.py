from functools import partial
import maya.cmds as cmds
import pymel.core as pm
import xgenm as xg
import os
import shutil


class XgenAnimSettingsDependant(object):

    def __init__(self, project, required_settings=[]):
        self.settings = project.settings
        self.required_settings = required_settings

    def validate(self):
        result = True

        for item in self.required_settings:
            if item not in self.settings or not self.settings[item]:
                result = False

                break

        return result

    def get_setting(self, id, default_value=''):
        result = default_value

        if id in self.settings:
            result = self.settings[id]

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

        path = '%s/xgen/animated_bakes/%s/' % (cmds.workspace(q=True, rd=True), self.get_setting('xgenMap'))
        emitter = self.get_setting('xgenEmitter')
        bake_file = '%s%s.ptx' %()

        # Bake it.
        for frame in range(int(cmds.playbackOptions(q=True, minTime=True)), int(cmds.playbackOptions(q=True, maxTime=True))):
            # Set current time.
            cmds.currentTime(frame)

            cmds.ptexBake(inMesh=emitter, o=path, bt=self.get_setting('xgenSequence'), tpu=self.get_setting('xgenResolution', 100))

            bake_file = '%s%s.0%s.ptx' % (path, emitter, frame)
            if os.path.isfile(bake_file):
                shutil.copy2()


#TODO: Implement ui elements factory.
class UiFactory:
    pass


class XgenAnim:

    ui_id = 'xgenanim'
    title = 'xGen Animation Maps'
    version = '0.1'
    settings = {}

    def __init__(self):

        if pm.window(self.ui_id, exists=True):
            pm.deleteUI(self.ui_id)

        self.window = pm.window(self.ui_id, title='%s | %s' %(self.title, self.version), mnb=False, mxb=False, sizeable=False)

        # Form the UI.
        with pm.columnLayout():
            with pm.frameLayout(l='Map Properties', cll=False, cl=False):
                self.object_selection('xgenSequence', label='Animated Sequence Node', object_type='file')
                self.object_selection('xgenEmitter', label='xGen Emitter Object', object_type='transform')
                self.text_field('xgenMap', label='Result map path', default_value='default/map')
                self.range_field('xgenResolution', label='Result map resolution', default_value=100)
                pm.button('assign', label='Assign', c=self.assign)

        self.window.show()

    def assign(self, flag):
        PtxBaker.perform_conversion(self)

    @staticmethod
    def field_change_callback(self, id, value):
        self.settings[id] = value

    def text_field(self, id, label='', default_value=''):
        return pm.textFieldGrp(id, label=label, tx=default_value, tcc=partial(self.field_change_callback, self, id))

    def range_field(self, id, label='', default_value=0):
        return pm.rangeControl(id, ann=label, min=0, max=1000, cc=partial(self.field_change_callback, self, id))

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

    def object_selection(self, id, label='', object_type=None, default_value=''):
        return pm.textFieldButtonGrp(id, label=label, tx=default_value, bl='Selection',
                              bc=partial(self.object_selection_callback, id, object_type),
                              tcc=partial(self.field_change_callback, self, id))

    def option_selection(self, id, label='', items_callback=None):
        return pm.optionMenu(id, label=label)

    @staticmethod
    def directory_selection_callback(group_id):
        directory = cmds.fileDialog2(fm=3)

        if len(directory):
            pm.textFieldButtonGrp(group_id, e=True, tx=directory[0])

    def directory_selection(self, id, label='', default_value=''):
        return pm.textFieldButtonGrp(id, label=label, tx=default_value, bl='Browse',
                              bc=partial(self.directory_selection_callback, id),
                              tcc=partial(self.field_change_callback, self, id))


if __name__ == '__main__':
    XgenAnim()
