import os
from trac.db.api import DatabaseManager, _parse_db_str

def write_simple_jndi_properties(env, targetdir, connection_uri=None, ip=None):
    if not connection_uri:
        connection_uri = DatabaseManager(env).connection_uri
    if not os.path.exists(os.path.join(targetdir,"simple-jndi")):
        os.mkdir(os.path.join(targetdir,"simple-jndi"))
    scheme, args = _parse_db_str(connection_uri)
    if scheme == 'sqlite':
        if not args['path'].startswith('/'):
            args['path'] = os.path.join(env.path, args['path'].lstrip('/'))
        jdbcDriver = "org.sqlite.JDBC"
        jdbcConnection = "jdbc:sqlite:%s" % args['path']
        jdbcUser = ""
        jdbcPassword = ""
    elif scheme == 'postgres':
        jdbcDriver = "org.postgresql.Driver"
        args['path'] = args['path'].strip("/")
        if ip:
            args['host'] = ip
        jdbcConnection = "jdbc:postgresql://%(host)s/%(path)s" % args
        jdbcUser = args['user']
        jdbcPassword = args['password']
    else:
        raise KeyError("Unknown database scheme %s" % scheme)

    jndi_filename = os.path.join(os.path.join(targetdir,"simple-jndi"), "default.properties")
    properties = open(jndi_filename, 'w')
    properties.write("projectdata/type=javax.sql.DataSource\n")
    properties.write("projectdata/driver=%s\n" % jdbcDriver)
    properties.write("projectdata/url=%s\n" % jdbcConnection)
    properties.write("projectdata/user=%s\n" % jdbcUser)
    properties.write("projectdata/password=%s\n" % jdbcPassword)
    properties.close()

    env.log.info("Written JNDI details to %s" % jndi_filename)
