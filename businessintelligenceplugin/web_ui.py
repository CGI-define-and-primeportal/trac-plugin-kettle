from trac.core import *
from trac.web.api import IRequestHandler
from trac.web.chrome import ITemplateProvider
from trac.web.api import RequestDone, HTTPNotFound

from genshi.builder import Markup

from pkg_resources import resource_filename
import os
import uuid
import tempfile
import re

from renderer import ReportRenderer

class ReportRunner(Component):
    implements(IRequestHandler, 
               ITemplateProvider)

    ### methods for ITemplateProvider
    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [resource_filename(__name__, 'templates')]

    # IRequestHandler methods

    def match_request(self, req):
        if req.path_info.startswith('/reporting'):
            return True

    def process_request(self, req):
        if req.path_info.startswith('/reporting/images/'):
            match = re.match("/reporting/images/(?P<uuid>[^/\.]+)/(?P<image>[^/\.]+)", req.path_info)
            if match:
                filename = os.path.join(req.session["REPORT_IMAGES_DIR"],match.group('uuid'),match.group('image'))
                req.send_file(filename)
            else:
                raise HTTPNotFound

        # TODO take this from arguments
        # TODO be able to get it from subversion
        filename = "chart.jrxml"

        report_filename = os.path.join(resource_filename(__name__, 'sample-reports'), filename)

        if not "REPORT_IMAGES_DIR" in req.session:
            # TODO we need some way to clean these up after a few days?
            req.session["REPORT_IMAGES_DIR"] = tempfile.mkdtemp()

        random = uuid.uuid4().hex
        images_uri = req.abs_href("reporting","images", random) + "/"
        images_dir = os.path.join(req.session["REPORT_IMAGES_DIR"], random)

        if "format" in req.args:
            output = ReportRenderer(self.env).execute_report(report_filename, 
                                                             {}, 
                                                             req.args["format"].upper(),
                                                             images_uri=images_uri,
                                                             images_dir=images_dir)
            req.send_response(200)
            req.send_header('Content-Type', 'text/html; charset=utf-8') # TODO
            req.send_header('Content-Length', len(output))
            req.send_header('Cache-Control', 'no-cache')
            req.end_headers()
            req.write(output.encode('utf-8'))
            raise RequestDone
        else:
            report_body = ReportRenderer(self.env).execute_report(report_filename, 
                                                                  {}, 
                                                                  "HTML", 
                                                                  images_uri=images_uri,
                                                                  images_dir=images_dir,
                                                                  embedded=True,
                                                                  page=0)
            data = {'report_body':  Markup(report_body)}
            return 'report_viewer.html', data, None

