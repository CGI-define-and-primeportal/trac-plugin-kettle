from trac.core import *
from trac.config import Option
from trac.db.api import DatabaseManager, _parse_db_str

import sys
import os
import glob
from pkg_resources import resource_filename

try:
    from jpype import *
except ImportError:
    # Workaround that it doesn't put the python files onto the path when using "develop" mode for the egg
    import _jpype
    sys.path.append(os.path.join(os.path.split(_jpype.__file__)[0],'src/python'))
    from jpype import *
    del _jpype

jvm_running = False

class ReportRenderer(Component):
    jvm_library = Option("BusinessIntelligence","JVM",
                         "/usr/lib/jvm/java-7-openjdk-amd64/jre/lib/amd64/server/libjvm.so",
                         doc="Path to libjvm.so")

    _jdbc_connections = {}

    def _get_jdbc_connection(self):
        connection_uri = DatabaseManager(self.env).connection_uri
        try:
            # maintain the connection per-environment, but keyed by
            # the connection_uri in case it changes while we're
            # running
            return self._jdbc_connections[connection_uri]
        except KeyError:
            for k in self._jdbc_connections:
                del self._jdbc_connections[k]
        scheme, args = _parse_db_str(connection_uri)
        if scheme == 'sqlite':
            if not args['path'].startswith('/'):
                args['path'] = os.path.join(self.env.path, args['path'].lstrip('/'))
            jdbcDriver = JClass("org.sqlite.JDBC")
            jdbcConnection = java.sql.DriverManager.getConnection("jdbc:sqlite:%s" % args['path'])
        elif scheme == 'postgres':
            jdbcDriver = JClass("org.postgresql.Driver")
            jdbcConnection = java.sql.DriverManager.getConnection("jdbc:postgresql://%(host)s:%(port)s/%(path)s" % args,
                                                                  args['user'], args['password'])
        else:
            raise KeyError("Unknown database scheme %s" % scheme)
        self._jdbc_connections[connection_uri] = jdbcConnection
        return jdbcConnection

    def _startJVM(self):
        global jvm_running
        if not jvm_running:
            classpath = ":".join(glob.glob(os.path.join(resource_filename(__name__, 'libs'),"*")))
            startJVM(self.jvm_library, "-ea", "-Djava.class.path=%s" % classpath)
            jvm_running = True
        else:
            if not isThreadAttachedToJVM():
                attachThreadToJVM()

    def __del__(self):
        global jvm_running
        if jvm_running:
            shutdownJVM()

    def execute_report(self, report_filename, parameters, output_format="HTML",
                       images_uri=None, images_dir=None, embedded=False, page=0):
        ext = os.path.splitext(report_filename)[1]
        if ext == ".jrxml":
            return self.execute_jasper_report(report_filename, parameters, output_format,
                                              images_uri, images_dir, embedded, page)
        elif ext == ".prpt":
            return self.execute_pentaho_report(report_filename, parameters, output_format,
                                               images_uri, images_dir, embedded, page)
        else:
            raise NotImplementedError("Unknown format for %s" % report_filename)

    def execute_jasper_report(self, report_filename, parameters, output_format, 
                              images_uri, images_dir, embedded, page):
        self._startJVM()

        CompileManager = JClass("net.sf.jasperreports.engine.JasperCompileManager")
        JasperFillManager = JClass("net.sf.jasperreports.engine.JasperFillManager")
        JREmptyDataSource = JClass("net.sf.jasperreports.engine.JREmptyDataSource")

        JRParameter         = JClass("net.sf.jasperreports.engine.JRParameter")
        JRExporterParameter = JClass("net.sf.jasperreports.engine.JRExporterParameter")

        jasperParameters = java.util.HashMap()

        jdbcConnection = self._get_jdbc_connection()

        jasperReport = CompileManager.compileReport(report_filename)
        jasperPrint = JasperFillManager.fillReport(jasperReport,
                                                   jasperParameters,
                                                   jdbcConnection)
        if output_format == "HTML":
            exporter = JClass("net.sf.jasperreports.engine.export.JRHtmlExporter")()
            JRHtmlExporterParameter = JClass("net.sf.jasperreports.engine.export.JRHtmlExporterParameter")
            if embedded:
                exporter.setParameter(JRHtmlExporterParameter.HTML_HEADER, "")
                exporter.setParameter(JRHtmlExporterParameter.BETWEEN_PAGES_HTML, "")
                exporter.setParameter(JRHtmlExporterParameter.HTML_FOOTER, "")
                exporter.setParameter(JRHtmlExporterParameter.IS_USING_IMAGES_TO_ALIGN, False);

            if images_uri:
                exporter.setParameter(JRHtmlExporterParameter.IMAGES_URI, images_uri)

            if images_dir:
                exporter.setParameter(JRHtmlExporterParameter.IS_OUTPUT_IMAGES_TO_DIR, True);
                exporter.setParameter(JRHtmlExporterParameter.IMAGES_DIR_NAME, images_dir)
        else:
            raise KeyError("Unknown output format %s" % output_format)

        exporter.setParameter(JRExporterParameter.JASPER_PRINT, jasperPrint)
        exporter.setParameter(JRExporterParameter.CHARACTER_ENCODING, "UTF-8");
        exporter.setParameter(JRExporterParameter.PAGE_INDEX, page)

        stringBuffer = java.lang.StringBuffer()
        exporter.setParameter(JRExporterParameter.OUTPUT_STRING_BUFFER, stringBuffer)

        exporter.exportReport()

        result = stringBuffer.toString()

        return result

    def execute_pentaho_report(self, report_filename, parameters, output_format,
                               images_uri, images_dir, embedded, page):
        raise NotImplementedError
        self._startJVM()

        ClassicEngineBoot = JClass("org.pentaho.reporting.engine.classic.core.ClassicEngineBoot")
        ResourceManager   = JClass("org.pentaho.reporting.libraries.resourceloader.ResourceManager")
        # MRO problems :-(
        #MasterReport      = JClass("org.pentaho.reporting.engine.classic.core.MasterReport")

        ClassicEngineBoot.getInstance().start()

        resourceManager   = ResourceManager()
        resourceManager.registerDefaults()
        reportDefinitionURL = "file://%s" % report_filename
        resourceManager.createDirectly(reportDefinitionURL, MasterReport)



