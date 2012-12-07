from trac.core import *
from trac.admin import IAdminCommandProvider
from trac.web.api import IRequestHandler
from trac.web.chrome import ITemplateProvider

from renderer import ReportRenderer

class ReportAdmin(Component):
    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('report execute', '', "Execute a report", None, self.execute)

    def execute(self, report_filename):
        self.log.debug("Running report: %s" % report_filename)
        print ReportRenderer(self.env).execute_report(report_filename, {}, "HTML")
