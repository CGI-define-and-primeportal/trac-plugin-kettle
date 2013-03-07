from trac.core import *
from trac.web.api import IRequestHandler
from trac.web.chrome import ITemplateProvider, add_script, add_script_data
from trac.web.api import ITemplateStreamFilter, RequestDone, HTTPNotFound
from trac.wiki.macros import WikiMacroBase, parse_args
from trac.config import Option

from genshi.builder import Markup, tag
from genshi.filters.transform import Transformer

from pkg_resources import resource_filename
import os
import uuid
import tempfile
import re
import urllib
import urllib2

from renderer import ReportRenderer

class Charting(Component):
    implements(ITemplateProvider,
               ITemplateStreamFilter)

    ### methods for ITemplateProvider
    def get_htdocs_dirs(self):
        return [('businessintelligenceplugin', resource_filename(__name__, 'htdocs'))]

    def get_templates_dirs(self):
        return []

    # ITemplateStreamFilter methods
    def filter_stream(self, req, method, filename, stream, data):
        if filename == 'query.html':
            if 'groups' in data:
                # <!--[if lte IE 8]> ....
                #add_script(req, "businessintelligenceplugin/js/excanvas.min.js")

                #add_script(req, "businessintelligenceplugin/js/jquery.colorhelpers.js")

                add_script(req, "businessintelligenceplugin/js/jquery.flot.js")
                #add_script(req, "businessintelligenceplugin/js/jquery.flot.crosshair.js")
                #add_script(req, "businessintelligenceplugin/js/jquery.flot.fillbetween.js")
                #add_script(req, "businessintelligenceplugin/js/jquery.flot.image.js")
                #add_script(req, "businessintelligenceplugin/js/jquery.flot.navigate.js")
                add_script(req, "businessintelligenceplugin/js/jquery.flot.pie.js")
                #add_script(req, "businessintelligenceplugin/js/jquery.flot.resize.js")
                #add_script(req, "businessintelligenceplugin/js/jquery.flot.selection.js")
                #add_script(req, "businessintelligenceplugin/js/jquery.flot.stack.js")
                #add_script(req, "businessintelligenceplugin/js/jquery.flot.symbol.js")
                #add_script(req, "businessintelligenceplugin/js/jquery.flot.threshold.js")

                def generate_chart(stream, field, label, function):
                    chartdata = []
                    for groupname, grouptickets in data['groups']:
                        chartdata.append({'label': groupname,
                                          'data': function(grouptickets)})

                    add_script_data(req, {'chartdata_' + field: chartdata})

                    div = tag.div(
                        tag.h4(label,style="background: #F6F6F6" ),
                        tag.div(id_="chartsholder_" + field,style="width: 300px; height: 250px;"),
                        style="float: left;")
                    stream |= Transformer("//div[@id='query_results_replaceable']").before(div)

                    # TODO work out why I can't put HTML into the labels, like the examples can. 

                    script = tag.script("""
    $(function () {
     $.plot($("div#chartsholder_%s"), chartdata_%s,
     {
             series: {
                pie: {
                    radius: 1,
                    innerRadius: 0.3,
                    show: true,
                    label: {
                     show: true,
                     radius: 1,
                     formatter: function(label, series) {
                            return label;
                     },
                     background: { opacity: 0.1 }
                   },
                }
            },
            legend: {
                show: true,
                labelFormatter: function(label, series) {
                        return label + ': ' + Math.round(series.data[0][1]);
                },
            }
     });
    });
    """ % (field, field), type_="text/javascript")
                    stream |= Transformer("//head").append(script)
                    return stream

                stream = generate_chart(stream, 'count', 'Ticket Count', 
                                        lambda tickets: len(tickets))

                # can we work out which by looking for number-presentation fields, rather than hard coding this list?

                if 'remaininghours' in data['col']:
                    stream = generate_chart(stream, 'remaininghours', 'Estimated Remaining Hours', 
                                            lambda tickets: sum(float(ticket['remaininghours']) for ticket in tickets))

                if 'estimatedhours' in data['col']:
                    stream = generate_chart(stream, 'estimatedhours', 'Original Estimated Hours', 
                                            lambda tickets: sum(float(ticket['estimatedhours']) for ticket in tickets))

                if 'totalhours' in data['col']:
                    stream = generate_chart(stream, 'totalhours', 'Total Hours', 
                                            lambda tickets: sum(float(ticket['totalhours']) for ticket in tickets))

        return stream

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

class ReportRunner(Component):
    implements(IRequestHandler)

    pentaho_username = Option('pentaho','username',"joe")
    pentaho_password = Option('pentaho','password',"password")

    def match_request(self, req):
        if req.path_info.startswith('/reportrender'):
            return True

    def process_request(self, req):
        url = "https://brasstest01.define.logica.com/pentaho/content/reporting/execute/steel-wheels/sample-report-1.html?solution=steel-wheels&path=&name=sample-report-1.prpt&locale=en_GB&paginate=false&output-target=table%%2Fhtml%%3Bpage-mode%%3Dstream&dashboard-mode=true&accepted-page=-1&showParameters=true&renderMode=REPORT&htmlProportionalWidth=true&userid=%s&password=%s" % (self.pentaho_username, self.pentaho_password)
        report_table = urllib2.urlopen(url).read()
        report_table = report_table.replace("/pentaho/getImage","https://brasstest01.define.logica.com/pentaho/getImage")
        data = {'report_table': Markup(report_table)}
        return 'embedreport.html', data, None

class OLAPAnalyzer(Component):
    implements(IRequestHandler)
    def match_request(self, req):
        if req.path_info.startswith('/olap'):
            return True

    def process_request(self, req):
        #add_script(req, "businessintelligenceplugin/js/analyzer.js")
        data = {}
        return 'analyzer.html', data, None

class ReportDesigner(Component):
    implements(IRequestHandler)
    def match_request(self, req):
        if req.path_info.startswith('/reporter'):
            return True

    def process_request(self, req):
        #add_script(req, "businessintelligenceplugin/js/reporter.js")
        data = {}
        return 'reporter.html', data, None

class PentahoDashboard(Component):
    implements(IRequestHandler)
    def match_request(self, req):
        if req.path_info.startswith('/bidashboard'):
            return True

    def process_request(self, req):
        #add_script(req, "businessintelligenceplugin/js/reporter.js")
        data = {}
        return 'bidashboard.html', data, None


class PentahoTagCloudMacro(WikiMacroBase):

    pentaho_username = Option('pentaho','username',"joe")
    pentaho_password = Option('pentaho','password',"password")

    def expand_macro(self, formatter, name, args):
        largs, kwargs = parse_args(args)
        width = kwargs.get("width","100%")
        height = kwargs.get("height","500")
        milestone = kwargs.get("milestone")
        if milestone:
            action = "chart - tag cloud.xanalyzer"
        else:
            action = "chart - tag cloud nofilter.xanalyzer"            
        urlargs = urllib.urlencode({"command": "open",
                                    "solution":"steel-wheels",
                                    "path": "/Project d4",
                                    "action": action,
                                    "userid": self.pentaho_username,
                                    "password": self.pentaho_password,
                                    "milestone": milestone})
        doc = """
<iframe width="%s" height="%s" src="/pentaho/content/analyzer/viewer?%s">
</iframe>""" % (width, height, urlargs)
        return doc

class PentahoSunburstMacro(WikiMacroBase):

    pentaho_username = Option('pentaho','username',"joe")
    pentaho_password = Option('pentaho','password',"password")

    action = "chart - sunburst.xanalyzer"

    def expand_macro(self, formatter, name, args):
        largs, kwargs = parse_args(args)
        width = kwargs.get("width","100%")
        height = kwargs.get("height","500")
        urlargs = urllib.urlencode({"command": "open",
                                    "solution":"steel-wheels",
                                    "path": "/Project d4",
                                    "userid": self.pentaho_username,
                                    "password": self.pentaho_password,
                                    "action": self.action})
        doc = """
<iframe width="%s" height="%s" src="https://brasstest01.define.logica.com/pentaho/content/analyzer/viewer?%s">
</iframe>""" % (width, height, urlargs)
        return doc
    
class PentahoReportMacro(WikiMacroBase):

    pentaho_username = Option('pentaho','username',"joe")
    pentaho_password = Option('pentaho','password',"password")

    def expand_macro(self, formatter, name, args):
        largs, kwargs = parse_args(args)
        report = largs[0] + ".prpt"
        width = kwargs.get("width","100%")
        height = kwargs.get("height","500")
        urlargs = urllib.urlencode({"command": "open",
                                    "solution":"steel-wheels",
                                    "path": "",
                                    "userid": self.pentaho_username,
                                    "password": self.pentaho_password,
                                    "locale":"en_GB",
                                    "paginate":"false",
                                    "output-target":"table/html;page-mode=stream",
                                    "dashboard-mode":"true",
                                    "accepted-page":"-1",
                                    "showParameters":"true",
                                    "renderMode":"REPORT",
                                    "htmlProportionalWidth":"true",
                                    "name": report})

        url = "https://brasstest01.define.logica.com/pentaho/content/reporting/execute/report.html?%s" % urlargs
        report_table = urllib2.urlopen(url).read()
        report_table = report_table.replace("/pentaho/getImage","https://brasstest01.define.logica.com/pentaho/getImage")
        return report_table

class PentahoChartMacro(WikiMacroBase):

    pentaho_username = Option('pentaho','username',"joe")
    pentaho_password = Option('pentaho','password',"password")

    def expand_macro(self, formatter, name, args):
        largs, kwargs = parse_args(args)
        chart = largs[0] + ".xanalyzer"
        width = kwargs.get("width","100%")
        height = kwargs.get("height","500")
        urlargs = urllib.urlencode({"command": "open",
                                    "solution":"steel-wheels",
                                    "path": "",
                                    "userid": self.pentaho_username,
                                    "password": self.pentaho_password,
                                    "action": chart})
        doc = """
<iframe width="%s" height="%s" src="https://brasstest01.define.logica.com/pentaho/content/analyzer/viewer?%s">
</iframe>""" % (width, height, urlargs)
        return doc
    
class PentahoCalendarMacro(PentahoSunburstMacro):
    action = "chart - calendar.xanalyzer"

class PentahoScatterMacro(WikiMacroBase):
    action = "Time estimates scatter.xanalyzer"

class PentahoOLAPMacro(WikiMacroBase):
    pentaho_username = Option('pentaho','username',"joe")
    pentaho_password = Option('pentaho','password',"password")

    def expand_macro(self, formatter, name, args):
        largs, kwargs = parse_args(args)

        # bad idea, what if password contains non URL-safe chars...
        doc = """
<iframe width="100%%" height="700" src="https://brasstest01.define.logica.com/pentaho/content/analyzer/editor?command=new&userid=%s&password=%s&showFieldList=true&showFieldLayout=true&catalog=d4%%20current&cube=d4%%20current&autoRefresh=true">
</iframe>""" % (self.pentaho_username, self.pentaho_password)
        return doc

class SaikuOLAPMacro(WikiMacroBase):
    def expand_macro(self, formatter, name, args):
        largs, kwargs = parse_args(args)

        doc = """
<iframe width="100%" height="700" src="https://brasstest01.define.logica.com/pentaho/content/saiku-ui/index.html?biplugin=true&userid=%s&password=%s">
</iframe>""" % (self.pentaho_username, self.pentaho_password)
        return doc

