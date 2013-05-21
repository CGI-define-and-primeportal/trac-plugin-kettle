from trac.admin import IAdminCommandProvider
from trac.core import Component, implements

import os
import tempfile
import subprocess

from pkg_resources import resource_filename

from businessintelligenceplugin.util import write_simple_jndi_properties

class SpoonExecutor(Component):
    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods
    def get_admin_commands(self):
        yield ('businessintelligence spoon', '',
               """Start spoon
               """,
               self._complete_transformation_list, self._do_spoon)
        yield ('businessintelligence simple-jndi', '',
               """Write a JDNI properties file to "$HOME/.pentaho/simple-jndi". This is useful before starting report-designer/report-designer.sh
               """,
               self._complete_transformation_list, self._do_jndi)

    def _complete_transformation_list(self, args):
        pass

    def _do_spoon(self):
        tempdir = tempfile.mkdtemp()
        write_simple_jndi_properties(self.env, tempdir)

        # execute transform 

        spoon = subprocess.Popen(["/bin/sh", "./spoon.sh"], 
                                 executable="/bin/sh",
                                 cwd=resource_filename(__name__, 'pentaho-data-integration'),
                                 env={'PENTAHO_DI_JAVA_OPTIONS': "-Dorg.osjava.sj.root=%s" % os.path.join(tempdir,"simple-jndi"),
                                      'KETTLE_HOME': os.path.join(tempdir,"kettle"),
                                      'DISPLAY': os.environ['DISPLAY']})

        spoon.wait()

        shutil.rmtree(tempdir)

    def _do_jndi(self):
        write_simple_jndi_properties(self.env, os.path.expanduser("~/.pentaho"))

