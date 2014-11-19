"""
Maintain the database VIEW which simplifies access to the ticket data
"""

# pylint: disable=line-too-long

from trac.core import Component, implements
from trac.env import IEnvironmentSetupParticipant
from trac.admin import IAdminCommandProvider
from trac.ticket.api import TicketSystem

class DatabaseViewSystem(Component):
    """trac-admin command provider for business intelligence plugin."""

    implements(IEnvironmentSetupParticipant,
               IAdminCommandProvider)

    # IEnvironmentSetupParticipant
    _schema_version = 1

    _view_name = "ticket_bi_current"

    # pylint: disable=invalid-name
    _custom_fields_in_basic_view_statement = (u'totalhours',
                                              u'resolvedinversion',
                                              u'qualityassurancecontact',
                                              u'estimatedhours',
                                              u'remaininghours')
    _basic_select_statement = r"""
"ticket"."id",
"ticket"."type",

TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second' AS "time",
date_part('year',    TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second') AS "time_year",
date_part('quarter', TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second') AS "time_quarter",
date_part('month',   TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second') AS "time_month",
date_part('week',    TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second') AS "time_week",
date_part('day',     TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."time"/1000000 * INTERVAL '1 second') AS "time_day",

TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second' AS "changetime",
date_part('year'  ,  TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second') AS "changetime_year",
date_part('quarter', TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second') AS "changetime_quarter",
date_part('month',   TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second') AS "changetime_month",
date_part('week',    TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second') AS "changetime_week",
date_part('day',     TIMESTAMP WITH TIME ZONE 'epoch' + "ticket"."changetime"/1000000 * INTERVAL '1 second') AS "changetime_day",

TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET) /1000000 * INTERVAL '1 second' AS "resolutiontime",
date_part('year',    TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET)/1000000 * INTERVAL '1 second') AS "resolutiontime_year",
date_part('quarter', TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET)/1000000 * INTERVAL '1 second') AS "resolutiontime_quarter",
date_part('month',   TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET)/1000000 * INTERVAL '1 second') AS "resolutiontime_month",
date_part('week',    TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET)/1000000 * INTERVAL '1 second') AS "resolutiontime_week",
date_part('day',     TIMESTAMP WITH TIME ZONE 'epoch' + (SELECT MAX(time) FROM ticket_change WHERE ticket = "ticket"."id" AND field = 'resolution' GROUP BY TICKET)/1000000 * INTERVAL '1 second') AS "resolutiontime_day",

"ticket"."summary",
"ticket"."description",
"ticket"."cc",

"ticket"."component",
"ticket"."severity",
"ticket"."priority",

"ticket"."owner",
"ownername"."value" as "owner_name",

"ticket"."reporter",
"reportername"."value" as "reporter_name",

"qualityassurancecontact"."value" AS "qualityassurancecontact",
"qualityassurancecontactname"."value" as "qualityassurancecontact_name",

"ticket"."version",
substring("ticket"."version" from '([\\d]+)\.[\\d]+\.[\\d]+') as "version_major",
substring("ticket"."version" from '[\\d]+\.([\\d]+)\.[\\d]+') as "version_minor",
substring("ticket"."version" from '[\\d]+\.[\\d]+\.([\\d]+)') as "version_point",
substring("ticket"."version" from '[\\d]+\.[\\d]+\.[\\d]+(.+)') as "version_patch",

"resolvedinversion"."value" AS "resolvedinversion",
substring("resolvedinversion"."value" from '([\\d]+)\.[\\d]+\.[\\d]+') as "resolvedinversion_major",
substring("resolvedinversion"."value" from '[\\d]+\.([\\d]+)\.[\\d]+') as "resolvedinversion_minor",
substring("resolvedinversion"."value" from '[\\d]+\.[\\d]+\.([\\d]+)') as "resolvedinversion_point",
substring("resolvedinversion"."value" from '[\\d]+\.[\\d]+\.[\\d]+(.+)') as "resolvedinversion_patch",

"ticket"."milestone",
"ticket"."status",
"ticket"."resolution",
"ticket"."keywords",

CASE WHEN btrim("estimatedhours"."value")~E'^[\\d\\.]+$' THEN "estimatedhours"."value"::double precision ELSE 0.0 END AS "estimatedhours", 
CASE WHEN btrim("totalhours"."value")~E'^[\\d\\.]+$' THEN "totalhours"."value"::double precision ELSE 0.0 END AS "totalhours", 
CASE WHEN btrim("remaininghours"."value")~E'^[\\d\\.]+$' THEN "remaininghours"."value"::double precision ELSE 0.0 END AS "remaininghours"
"""
    _basic_sql_statement = r"""
FROM "ticket" "ticket"
LEFT OUTER JOIN "ticket_custom" "resolvedinversion"
  ON ("ticket"."id" = "resolvedinversion"."ticket" AND "resolvedinversion"."name" = 'resolvedinversion')
LEFT OUTER JOIN "ticket_custom" "qualityassurancecontact"
  ON ("ticket"."id" = "qualityassurancecontact"."ticket" AND "qualityassurancecontact"."name" = 'qualityassurancecontact')
LEFT OUTER JOIN "ticket_custom" "remaininghours"
  ON ("ticket"."id" = "remaininghours"."ticket" AND "remaininghours"."name" = 'remaininghours')
LEFT OUTER JOIN "ticket_custom" "totalhours"
  ON ("ticket"."id" = "totalhours"."ticket" AND "totalhours"."name" = 'totalhours')
LEFT OUTER JOIN "ticket_custom" "estimatedhours"
  ON ("ticket"."id" = "estimatedhours"."ticket" AND "estimatedhours"."name" = 'estimatedhours')
LEFT OUTER JOIN "session_attribute" "ownername"
  ON ("ticket"."owner" = "ownername"."sid" AND "ownername"."name" = 'name')
LEFT OUTER JOIN "session_attribute" "reportername"
  ON ("ticket"."reporter" = "reportername"."sid" AND "reportername"."name" = 'name')
LEFT OUTER JOIN "session_attribute" "qualityassurancecontactname"
  ON ("qualityassurancecontact"."value" = "qualityassurancecontactname"."sid" AND "qualityassurancecontactname"."name" = 'name')
"""

    def environment_created(self):
        """Create the initial VIEW and put in a revision number
        to the system table. Note the revision number is not the revision of the
        VIEW, as the VIEW will change over time custom fields are added."""

        # pylint: disable=unused-variable,missing-docstring
        @self.env.with_transaction()
        def do_create(db):
            self.update_view(db=db)
            cursor = db.cursor()

            # system values are strings
            cursor.execute("INSERT INTO system (name, value) "
                           "VALUES ('bi_view_schema', %s)",
                           (str(self._schema_version),))

    # pylint: disable=no-self-use
    def _check_schema_version(self, db):
        """Fetch the value of bi_view_schema from the database, as an integer (or None)"""
        cursor = db.cursor()
        cursor.execute("select value from system where name = 'bi_view_schema'")
        row = cursor.fetchone()
        if row:
            return int(row[0])
        else:
            return None

    def environment_needs_upgrade(self, db):
        """Check if we don't have bi_view_schema marked in the db yet"""
        found_version = self._check_schema_version(db)
        if not found_version:
            self.log.debug("Initial schema needed for businessintelligence plugin for views")
            return True
        else:
            if found_version < self._schema_version:
                self.log.debug("Upgrade schema from %d to %d needed for businessintelligence plugin for view table",
                               found_version,
                               self._schema_version)
                return True
        return False

    def upgrade_environment(self, db):
        """Create initial VIEW and insert bi_view_schema marker"""
        self.log.debug("Upgrading schema for bi view plugin")

        found_version = self._check_schema_version(db)
        if not found_version:
            # Create view
            self.environment_created()
        #elif found_version == 2:
        #    pass


    # IAdminCommandProvider methods

    def get_admin_commands(self):
        """Command line utilities"""
        yield ('businessintelligence view update', '[drop]',
               "Check the database VIEW definition is up to date.",
               None, self.update_view)

    # Internal methods

    def update_view(self, drop=None, db=None):
        """Actually generate the VIEW, dropping existing one if caller asked for that."""
        ts = TicketSystem(self.env)

        # pylint: disable=unused-variable,missing-docstring
        @self.env.with_transaction(db)
        def do_update(db):
            print "Updating view"
            cursor = db.cursor()
            select = [self._basic_select_statement]
            sql = [self._basic_sql_statement]

            for cs, field in enumerate(ts.fields):
                if 'custom' in field and field['name'] not in self._custom_fields_in_basic_view_statement:

                    if  field['type'] == "text" and field['datatype'] == "float":
                        select.append('CASE WHEN btrim("cs%d"."value")~E\'^[\\d\\.]+$\' THEN "cs%d"."value"::double precision ELSE 0.0 END AS %s' % (
                            cs, cs, db.quote(field['name'])))
                    elif field['type'] == "text" and field['datatype'] == "integer":
                        select.append('CASE WHEN btrim("cs%d"."value")~E\'^\\d\\+$\' THEN "cs%d"."value"::int ELSE 0 END AS %s' % (
                            cs, cs, db.quote(field['name'])))
                    elif field['type'] == "date":
                        select.append('CASE WHEN btrim("cs%d"."value")~E\'^[0-9]{4}-[0-9]{2}-[0-9]{2}$\' THEN TO_DATE("cs%d"."value",\'YYYY-MM-DD\') ELSE NULL END AS %s' % (cs, cs, db.quote(field['name'])))
                    else:
                        select.append('"cs%d"."value" AS %s' % (cs, db.quote(field['name'])))

                    # using psycopg2 extension mogrify, although Trac doesn't and assumes that
                    # the custom field name is OK to insert directly into the SQL
                    if self.env.config.get('trac', 'database').startswith('postgres'):
                        sql.append(cursor.mogrify('LEFT OUTER JOIN "ticket_custom" "cs%d" ON ("ticket"."id" = "cs%d"."ticket" AND "cs%d"."name" = %%s)' % (
                            cs, cs, cs), (field['name'],)))
                    else:
                        sql.append('LEFT OUTER JOIN "ticket_custom" "cs%d" ON ("ticket"."id" = "cs%d"."ticket" AND "cs%d"."name" = \'%s\')' % (
                            cs, cs, cs, field['name']))

            if drop == 'drop':
                cursor.execute("DROP VIEW %s" % self._view_name)

            create_view_statement = "CREATE OR REPLACE VIEW %s AS SELECT %s %s" % (
                self._view_name,
                ",\n".join(select),
                "\n".join(sql))

            cursor.execute(create_view_statement)
