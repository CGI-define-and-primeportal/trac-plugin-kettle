import os
from trac.db.api import _parse_db_str

def write_simple_jndi_properties(connection_uri, tempdir):
    os.mkdir(os.path.join(tempdir,"simple-jndi"))
    scheme, args = _parse_db_str(connection_uri)
    if scheme == 'sqlite':
        if not args['path'].startswith('/'):
            args['path'] = os.path.join(self.env.path, args['path'].lstrip('/'))
        jdbcDriver = "org.sqlite.JDBC"
        jdbcConnection = "jdbc:sqlite:%s" % args['path']
        jdbcUser = ""
        jdbcPassword = ""
    elif scheme == 'postgres':
        jdbcDriver = "org.postgresql.Driver"
        args['path'] = args['path'].strip("/")
        jdbcConnection = "jdbc:postgresql://%(host)s/%(path)s" % args
        jdbcUser = args['user']
        jdbcPassword = args['password']
    else:
        raise KeyError("Unknown database scheme %s" % scheme)

    properties = open(os.path.join(os.path.join(tempdir,"simple-jndi"), "default.properties"), 'w')
    properties.write("projectdata/type=javax.sql.DataSource\n")
    properties.write("projectdata/driver=%s\n" % jdbcDriver)
    properties.write("projectdata/url=%s\n" % jdbcConnection)
    properties.write("projectdata/user=%s\n" % jdbcUser)
    properties.write("projectdata/password=%s\n" % jdbcPassword)
    properties.close()
