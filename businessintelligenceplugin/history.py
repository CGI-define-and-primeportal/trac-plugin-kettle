from trac.admin import IAdminCommandProvider
from trac.core import Component, implements
from trac.db import Table, Column, Index, DatabaseManager, with_transaction
from trac.env import IEnvironmentSetupParticipant
from trac.config import BoolOption
from trac.ticket.api import TicketSystem
import psycopg2
import os
import datetime
import types
import itertools
from cStringIO import StringIO
from trac.util.datefmt import from_utimestamp, to_utimestamp, to_timestamp, utc, utcmax
from logicaordertracker.controller import LogicaOrderController

class HistoryStorageSystem(Component):
    """trac-admin command provider for business intelligence plugin."""

    implements(IEnvironmentSetupParticipant,
               IAdminCommandProvider)

    # IEnvironmentSetupParticipant
    _schema_version = 5
    schema = [
        # Ticket changesets
        Table('ticket_bi_historical')[
            Column('_snapshottime', type='date'), # UTC, END of the day, NOT NULL added later
            Column('_resolutiontime', type='timestamp with time zone'),
            Column('isclosed', type='int'),
            Column('id', type='int64'),
            Column('type'),
            Column('time', type='timestamp with time zone'),
            Column('changetime', type='timestamp with time zone'),
            Column('component'),
            Column('severity'),
            Column('priority'),
            Column('owner'),
            Column('reporter'),
            Column('version'),
            Column('milestone'),
            Column('status'),
            Column('resolution'),
            Column('keywords'),
            Column('effort', type='double precision'),
            Column('estimatedhours', type='double precision'),
            Column('totalhours', type='double precision'),
            Column('remaininghours', type='double precision'),
            Index(['_snapshottime']),
            Index(['isclosed']),
            Index(['id']),
            Index(['milestone']),
            Index(['_snapshottime','milestone','isclosed']),
            ]
        ]
    
    def environment_created(self):
        db_connector, _ = DatabaseManager(self.env).get_connector()
        @self.env.with_transaction()
        def do_create(db):
            cursor = db.cursor()
            for table in self.schema:
                for statement in db_connector.to_sql(table):
                    cursor.execute(statement)
                    if self.env.config.get('trac', 'database').startswith('postgres'):
                        cursor.execute("ALTER TABLE ticket_bi_historical ALTER COLUMN _snapshottime SET NOT NULL")

            # system values are strings
            cursor.execute("INSERT INTO system (name, value) "
                           "VALUES ('bi_history_schema', %s)", 
                           (str(self._schema_version),))

    def _check_schema_version(self, db):
        cursor = db.cursor()
        cursor.execute("select value from system where name = 'bi_history_schema'")
        row = cursor.fetchone()
        if row:
            return int(row[0])
        else:
            return None

    def environment_needs_upgrade(self, db):
        found_version = self._check_schema_version(db)
        if not found_version:
            self.log.debug("Initial schema needed for businessintelligence plugin for history table")
            return True
        else:
            if found_version < self._schema_version:
                self.log.debug("Upgrade schema from %d to %d needed for businessintelligence plugin for history table",
                               found_version,
                               self._schema_version)
                return True
        return False

    def upgrade_environment(self, db):
        self.log.debug("Upgrading schema for bi history plugin")
        
        cursor = db.cursor()
        db_connector, _ = DatabaseManager(self.env).get_connector()
        
        found_version = self._check_schema_version(db)
        if not found_version:
            # Create tables
            self.environment_created()
        elif found_version == 2:
            # We've not released anywhere yet, so this seems more practical 
            # than writing a database-agnostic way to convert the isclosed column
            cursor.execute("DROP table ticket_bi_historical")
            for table in self.schema:
                for statement in db_connector.to_sql(table):
                    cursor.execute(statement)
            cursor.execute("UPDATE system SET value = %s WHERE name = 'bi_history_schema'", 
                           (str(self._schema_version),))
        elif found_version == 3:
            cursor.execute("CREATE INDEX ticket_bi_historical_isclosed "
                           "ON ticket_bi_historical (isclosed)")
            cursor.execute("CREATE INDEX ticket_bi_historical_id "
                           "ON ticket_bi_historical (id)")
            cursor.execute("CREATE INDEX ticket_bi_historical_milestone "
                           "ON ticket_bi_historical (milestone)")
            cursor.execute("UPDATE system SET value = %s "
                           "WHERE name = 'bi_history_schema'", 
                           (str(self._schema_version),))
        elif found_version == 4:
            if self.env.config.get('trac', 'database').startswith('postgres'):
                cursor.execute("ALTER TABLE ticket_bi_historical ALTER COLUMN _snapshottime SET NOT NULL")            
            cursor.execute("UPDATE system SET value = %s "
                           "WHERE name = 'bi_history_schema'", 
                           (str(self._schema_version),))

    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('businessintelligence history capture', '[YYYY-MM-DD] [ticket number]',
               """Catch up history capture tables. 
Run data capture up to end of yesterday, UTC.
Optional argument to collect date until end of YYYY-MM-DD.
Can then also be limited to just one ticket for debugging purposes, but will not function properly if used again with a different ticket number.""",
               None, self.capture)
        yield ('businessintelligence history clear', '[force]',
               """Clear up history capture tables - deletes data""",
               None, self.clear)
        yield ('businessintelligence history clean', '[force]',
               """Check for known data faults, and clear data if necessary - potentially deletes data""",
               None, self.clean)

    # Internal methods

    def capture(self, until_str=None, only_ticket=None):
        # avoid trying to run two captures in parallel for one project
        try: 
            import fcntl
        except ImportError, e:
            self.log.warning("Trying to acquire file lock but fcntl is not available: %s", e)
            fcntl = None
        try:
            if fcntl:
                lock_path = os.path.join(os.path.abspath(self.env.path), 'bi_history_capture.lock')
                lock_file = open(lock_path, 'w')
                try:
                    #acquire non-blocking exclusive lock
                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except IOError, e:
                    self.log.fatal("Failed to acquire lock on %s, is another process still running?", lock_path)
                    fcntl = None
                    return 
            self._capture(until_str, only_ticket)
        finally:
            if fcntl:
                #release lock
                fcntl.flock(lock_file, fcntl.LOCK_UN)
                lock_file.close()
                os.unlink(lock_path)
                

    def _capture(self, until_str=None, only_ticket=None):
        yesterday = datetime.date.today() - datetime.timedelta(days = 1)
        if not until_str:
            until = yesterday
        else:
            until = datetime.datetime.strptime(until_str, "%Y-%m-%d").date()
            if until > yesterday:
                raise ValueError("Can't process any newer than %s" % yesterday)

        if self.env.config.get('trac', 'debug_sql'):
            self.log.warning("Temporarily disabling [trac]debug_sql")
            self.env.config.set('trac', 'debug_sql', False)

        ts = TicketSystem(self.env)
        custom_fields = set(field['name'] for field in ts.fields
                            if 'custom' in field)
        empty_means_zero = set(field['name'] for field in ts.fields
                               if field.get('datatype', 'float')
                                                in set(['float', 'integer']))
        built_in_fields = set(field['name'] for field in ts.fields
                              if 'custom' not in field
                              and 'link' not in field)
        history_table_cols = [col.name for col in self.schema[0].columns]
        proto_values = dict.fromkeys(field
                                     for field in built_in_fields | custom_fields
                                     if field in history_table_cols)
        # history table column names which are not fields from the ticket system
        history_columns = ['isclosed']
        @with_transaction(self.env)
        def _capture(db):
            def calculate_initial_values_for_ticket(ticket_id):
                # first seen changes will be from the very first information we have about this ticket
                initial_values_cursor = db.cursor()
                initial_values_cursor.execute("SELECT time FROM ticket WHERE id = %s", (ticket_id,))
                ticket_created = from_utimestamp(initial_values_cursor.fetchone()[0])
                history_date = ticket_created.date()

                # find original values for the ticket
                for column in ticket_values.keys():
                    initial_values_cursor.execute("SELECT oldvalue FROM ticket_change WHERE ticket = %s AND field = %s ORDER BY time LIMIT 1",  
                                   (ticket_id, column))
                    result = initial_values_cursor.fetchone()
                    if result is None:
                        if column in built_in_fields:
                            initial_values_cursor.execute("SELECT %s FROM ticket WHERE id = %%s" % column, (ticket_id,))
                            result = initial_values_cursor.fetchone()
                            ticket_values[column] = encode_and_escape(result[0])
                        else:
                            initial_values_cursor.execute("SELECT value FROM ticket_custom WHERE ticket = %s AND name = %s", (ticket_id, column))
                            result = initial_values_cursor.fetchone()
                            if result:
                                ticket_values[column] = encode_and_escape(result[0])
                            else:
                                ticket_values[column] = r'\N'
                    else:
                        ticket_values[column] = encode_and_escape(result[0])

                ticket_values['id'] = str(ticket_id)
                ticket_values['time'] = str(ticket_created)
                ticket_values['changetime'] = str(ticket_created)
                ticket_values['_resolutiontime'] = r'\N'
                # assumption that you cannot create a ticket in status closed
                # so we give isclosed a false value from the off
                ticket_values['isclosed'] = "0"

                # PROBLEM: How can we detect when a milestone was renamed (and
                # tickets updated) - this isn't mentioned in the ticket_change
                # table.
                # Maybe we have to search the log file for strings?!  
                # source:trunk/trac/trac/ticket/model.py@8937#L1192

                return ticket_values, ticket_created, history_date

            last_snapshot_cursor = db.cursor()
            last_snapshot_cursor.execute("SELECT _snapshottime FROM ticket_bi_historical ORDER BY _snapshottime DESC LIMIT 1")
            last_snapshot_result = last_snapshot_cursor.fetchone()
            del last_snapshot_cursor
            if last_snapshot_result:
                last_snapshot = last_snapshot_result[0]
                print "Last successful run was at %s" % last_snapshot

                if until <= last_snapshot:
                    print "Already have data for %s, so can't run with until=%s" % (last_snapshot, until)
                    return False
            else:
                last_snapshot = None
                print "No previous runs"

            # Get statuses we consider to be closed for each ticket type
            controller = LogicaOrderController(self.env)
            closed_statuses = controller.type_and_statuses_for_closed_statusgroups()

            if only_ticket:
                ticket_ids = [(int(only_ticket),)]
            else:
                ticket_ids_c = db.cursor()
                ticket_ids_c.execute("SELECT id FROM ticket ORDER BY id")
                ticket_ids = ticket_ids_c.fetchall()

            insert_cursor = db.cursor()
            copy_data_buffer = StringIO()

            eta_prediction__start_time = datetime.datetime.now()
            eta_prediction__done  = 0
            eta_prediction__total = len(ticket_ids)
            for ticket_id, in ticket_ids:
                try:
                    eta_prediction = eta_prediction__start_time + ((datetime.datetime.now() - eta_prediction__start_time) / eta_prediction__done) * eta_prediction__total
                except ZeroDivisionError:
                    eta_prediction = None
                self.log.info("Working on (after) %s to (end of) %s for ticket %d/%d - ETA %s", 
                              last_snapshot,
                              until,
                              ticket_id,
                              eta_prediction__total,
                              eta_prediction)
                eta_prediction__done += 1

                # set up a dictionary to hold the value of the ticket fields, which will change as we step forward in time
                ticket_values = proto_values.copy()
                
                # populate the "initial" values
                if last_snapshot:
                    history_date = last_snapshot + datetime.timedelta(days=1)
                    last_snapshot_cursor = db.cursor()
                    # we add ticket fields and history columns otherwise 
                    # we don't get previous values such as isclosed
                    columns = ticket_values.keys() + history_columns
                    last_snapshot_cursor.execute("SELECT %s FROM ticket_bi_historical "
                                                 "WHERE id = %%s AND _snapshottime = %%s "
                                                 "LIMIT 1 "
                                                 %  ",".join(columns), 
                                                 (ticket_id, last_snapshot))

                    values = last_snapshot_cursor.fetchone()
                    if not values:
                        self.log.warn("No historical data for ticket %s on %s?", ticket_id, last_snapshot)
                        ticket_values, ticket_created, history_date = calculate_initial_values_for_ticket(ticket_id)
                    else:
                        ticket_values.update(dict(zip(columns, values)))

                        # original storage for custom_fields can only store strings, so pretend we had a string
                        for k, v in ticket_values.items():
                            # everything wants to be a string as we use COPY to insert to the database
                            if k in custom_fields and not v:
                                ticket_values[k] = ''
                            else:
                                ticket_values[k] = encode_and_escape(v)

                        ticket_values['id'] = str(ticket_id)

                else:
                    # first time we've run the history capture script
                    ticket_values, ticket_created, history_date = calculate_initial_values_for_ticket(ticket_id)

                # now we're going to get a list of all the changes that this ticket goes through

                ticket_changes_cursor = db.cursor()
                ticket_changes_cursor.execute("SELECT time, field, newvalue "
                               "FROM ticket_change "
                               "WHERE ticket = %%s AND field in (%s) "
                               "AND time >= %%s AND time < %%s "
                               "ORDER BY time "
                               % db.parammarks(len(ticket_values)),
                               [ticket_id]
                               + ticket_values.keys()
                               + [memoized_to_utimestamp(startofday(history_date)),
                                  memoized_to_utimestamp(startofnextday(until)),
                                  ]
                               )
                ticket_changes =[(from_utimestamp(time), field, newvalue)
                                 for time, field, newvalue in ticket_changes_cursor]

                # and then we'll update 'ticket_values' to make a representation of the ticket for the end of each day, and store that into the history database

                def _calculate_totalhours_on_date(date, cursor):
                    cursor.execute("SELECT SUM(seconds_worked)/3600.0 FROM ticket_time WHERE ticket = %s AND time_started < %s",
                              (ticket_values['id'],
                               memoized_to_timestamp(startofnextday(date))))
                    result = cursor.fetchone()
                    return result[0] if result else 0

                def _calculate_remaininghours_on_date(date, cursor):
                    # find the closest absolute value
                    nextdate = startofnextday(date)
                    cursor.execute("SELECT to_timestamp(time / 1000000), oldvalue FROM ticket_change WHERE "
                              "field = 'remaininghours' AND ticket = %s AND time >= %s ORDER BY time ASC LIMIT 1",
                              (ticket_values['id'],
                               memoized_to_utimestamp(nextdate)))
                    next_known = cursor.fetchone()
                    cursor.execute("SELECT to_timestamp(time / 1000000), newvalue FROM ticket_change WHERE "
                              "field = 'remaininghours' AND ticket = %s AND time < %s ORDER BY time DESC LIMIT 1",
                              (ticket_values['id'],
                               memoized_to_utimestamp(nextdate)))
                    previous_known = cursor.fetchone()
                    cursor.execute("SELECT now(), value FROM ticket_custom WHERE ticket = %s AND name = 'remaininghours'",
                              (ticket_values['id'],))
                    currently = cursor.fetchone()
                    self.log.debug("Finding remaininghours for end of %s", date)
                    self.log.debug("Previous known value: %s", previous_known)
                    self.log.debug("Current known value: %s", currently)
                    self.log.debug("Next known value: %s", next_known)
                    candidates = []
                    try:
                        candidates.append((currently[0] - nextdate, currently[0], float(currently[1])))
                    except (TypeError, ValueError), e:
                        self.log.warning("Invalid float in %s for remaininghours on ticket %s", 
                                         currently, ticket_values['id'])
                    if next_known:
                        try:
                            candidates.append((next_known[0] - nextdate, next_known[0], float(next_known[1])))
                        except (TypeError, ValueError), e:
                            self.log.warning("Invalid float for next_known in %s for remaininghours on ticket %s", 
                                             next_known, ticket_values['id'])
                    if previous_known:
                        try:
                            candidates.append((nextdate - previous_known[0], previous_known[0], float(previous_known[1])))
                        except (TypeError, ValueError), e:
                            self.log.warning("Invalid float for previous_known in %s for remaininghours on ticket %s", 
                                             previous_known, ticket_values['id'])
                    if not candidates:
                        self.log.warn("No known information about remaininghours, guessing 0")
                        return 0

                    best_candidate = sorted(candidates)[0]
                    self.log.debug("Closest known data point is %s", best_candidate)

                    #print best_candidate[0], best_candidate

                    # in these comments, "today" and "current" is
                    # 'date' variable passed in above:

                    # extra heuristic - if we know it's going to be 0,
                    # and that's the first value we know at all,
                    # probably it should be 0 right now (as the hours
                    # plugin wouldn't let it go negative
                    if best_candidate[2] == 0 and not previous_known:
                        self.log.debug("The closest known data point is 0, and we don't know any previous data, so assume it must be 0")
                        return 0

                    if nextdate < best_candidate[1]:
                        # we've found evidence of what it was at a
                        # future date, so sum up the time spent
                        # between now and then. As that time would be
                        # subtracting from 'remaininghours', then add
                        # it back to find the current 'remaininghours'
                        
                        cursor.execute("SELECT SUM(seconds_worked) FROM ticket_time WHERE "
                                  "ticket = %s AND time_started >= %s AND time_started < %s",
                                  (ticket_values['id'],
                                   memoized_to_timestamp(nextdate),
                                   memoized_to_timestamp(best_candidate[1])))
                        result = cursor.fetchone()
                        if result and result[0]:
                            r = best_candidate[2] + (result[0]/3600.0)
                            self.log.debug("The closest data point was %s, and there was %s seconds worked between %s and %s, so remaininghours must be %s",
                                           best_candidate[2],
                                           result[0],
                                           nextdate,
                                           best_candidate[1],
                                           r)
                            return r
                        else:
                            self.log.debug("There was no time worked between %s and %s, so remaininghours must be %s",
                                           nextdate,
                                           best_candidate[1],
                                           best_candidate[2])
                            return best_candidate[2]
                    else:
                        # we've found evidence of what it was in the
                        # past, so sum up time spent between then and
                        # now. As that time would be reducing
                        # 'remaininghours', we'll do that same
                        # reduction to find the value for today
                        cursor.execute("SELECT SUM(seconds_worked) FROM ticket_time WHERE "
                                  "ticket = %s AND time_started >= %s AND time_started < %s",
                                  (ticket_values['id'],
                                   memoized_to_timestamp(best_candidate[1]),
                                   memoized_to_timestamp(nextdate)))
                        result = cursor.fetchone()
                        if result and result[0]:
                            r = best_candidate[2] - (result[0]/3600.0)
                            self.log.debug("The closest data point was %s, and there was %s seconds worked between %s and %s, so remaininghours is %s",
                                           best_candidate[2],
                                           result[0],
                                           best_candidate[1],
                                           nextdate,
                                           r)
                            return r
                        else:
                            return best_candidate[2]
                    
                    self.log.warn("Returning default of 0 for remaininghours")
                    return 0

                while history_date <= until:
                    active_changes = {}
                    for time, field, newvalue in ticket_changes:
                        if time < startofnextday(history_date):
                            # finding the newest change for each field, which is older than or equal to history_date
                            self.log.debug("On %s, saw setting %s to %s", time, field, newvalue)
                            active_changes[field] = encode_and_escape(newvalue)
                            active_changes['changetime'] = str(time)
                            if field == "resolution":
                                active_changes['_resolutiontime'] = str(time)
                            # work out if the new status is in a statusgroup with the attr closed='True'
                            if field == 'status':
                                s = closed_statuses[unencode_and_unescape(ticket_values['type'])]
                                if newvalue in s:
                                    self.log.debug("Recognising ticket as closed due to %s in %s", newvalue, s)
                                    active_changes['isclosed'] = "1"
                                else:
                                    self.log.debug("Recognising ticket as open due to %s not in %s", newvalue, s)
                                    active_changes['isclosed'] = "0"

                    ticket_values.update(active_changes)

                    # these are pretty hard to calculate,
                    # remaininghours especially as we don't have all
                    # the values it could have taken recorded. We have
                    # some known data-points, and some known
                    # delta-points, but we don't know for sure (for
                    # example) the value when the ticket was new.
                    # this was improved by https://d4.define.logica.com/ticket/3676
                    # so we only need to do the heuristics for old dates
                    if history_date.year < 2014:
                        ticket_values['totalhours']     = encode_and_escape(_calculate_totalhours_on_date(history_date, ticket_changes_cursor))
                        ticket_values['remaininghours'] = encode_and_escape(_calculate_remaininghours_on_date(history_date, ticket_changes_cursor))

                    for k in ticket_values:
                        if not ticket_values[k] and k in empty_means_zero:
                            ticket_values[k] = "0"

                    ticket_values["_snapshottime"] = str(history_date)
                    #for k, v in ticket_values.items():
                    #    print k, v, type(v)

                    for column in notlast(history_table_cols):
                        #print column
                        #print ticket_values.get(column)
                        try:
                            copy_data_buffer.write(ticket_values[column])
                        except KeyError:
                            copy_data_buffer.write(r'\N')
                        copy_data_buffer.write("\t")
                    copy_data_buffer.write(ticket_values[history_table_cols[-1]])
                    copy_data_buffer.write("\n")

                    history_date = history_date + datetime.timedelta(days=1)

                if copy_data_buffer.tell() > 51916800: # 50 MB, randomly chosen
                    self.log.info("Flushing to table with COPY...")
                    copy_data_buffer.seek(0)
                    insert_cursor.copy_from(copy_data_buffer,
                                            table='ticket_bi_historical',
                                            sep='\t',
                                            null=r'\N',
                                            columns=history_table_cols)
                    copy_data_buffer = StringIO()
            self.log.info("Final flushing to table with COPY...")
            copy_data_buffer.seek(0)
            insert_cursor.copy_from(copy_data_buffer,
                                    table='ticket_bi_historical',
                                    sep='\t',
                                    null=r'\N',
                                    columns=history_table_cols)

    def clear(self, force=False):
        if force != "force":
            print "Will only actually clear if 'force' is passed as additional argument"
            return 

        @with_transaction(self.env)
        def _clear(db):
            cursor = db.cursor()
            cursor.execute("TRUNCATE ticket_bi_historical")

    def clean(self, force=False):
        @with_transaction(self.env)
        def _clean(db):
            cursor = db.cursor()
            cursor.execute("SELECT COUNT(*) FROM ticket_bi_historical WHERE _snapshottime IS NULL");
            null_snapshottimes = cursor.fetchone()[0]
            if null_snapshottimes > 0:
                self.log.warning("There are %d rows which have NULL _snapshottime", null_snapshottimes)
                print "There are %d rows which have NULL _snapshottime, clearing data." % null_snapshottimes

                return self.clear(force)


# http://code.activestate.com/recipes/578231-probably-the-fastest-memoization-decorator-in-the-/
def memodict(f):
    """ Memoization decorator for a function taking a single argument """
    class memodict(dict):
        def __missing__(self, key):
            ret = self[key] = f(key)
            return ret 
    return memodict().__getitem__

@memodict
def memoized_to_timestamp(o):
    return to_timestamp(o)

@memodict
def memoized_to_utimestamp(o):
    return to_utimestamp(o)

@memodict
def startofday(date):
    if date:
        return datetime.datetime.combine(date, datetime.time(tzinfo=utc))
    else:
        return None

@memodict
def startofnextday(date):
    if date:
        return datetime.datetime.combine(date + datetime.timedelta(days=1),
                                         datetime.time(tzinfo=utc))
    else:
        return None

# can't use memodict, as it doesn't distinguish between
# encode_and_escape(1) vs. encode_and_escape(1.0) Taking a gamble (as
# did memodict) on overall memory consumption. If needed, we could use
# https://pypi.python.org/pypi/backports.functools_lru_cache
# (with typed=True)
encode_and_escape_dict = {}
def encode_and_escape(o):
    """
>>> encode_and_escape(1)
'1'
>>> encode_and_escape(1.0)
'1.0'
>>> encode_and_escape(1)
'1'
    """
    if o is None:
        return r'\N'
    else:
        try:
            return encode_and_escape_dict[(type(o), o)]
        except KeyError:
            # http://www.postgresql.org/docs/8.1/static/sql-copy.html
            # http://docs.python.org/2/reference/lexical_analysis.html#string-literals
            # http://initd.org/psycopg/docs/cursor.html#cursor.copy_expert
            r = unicode(o).encode('utf-8').encode('string_escape')
            encode_and_escape_dict[(type(o), o)] = r
            return r

@memodict
def unencode_and_unescape(o):
    if o == r'\N':
        return None
    else:
        # not entirely symmetric - this gives strings, but
        # encode_and_escape() would take non-strings too. This is OK.
        return o.decode('string_escape').decode('utf8')

# http://stackoverflow.com/questions/2429098/how-to-treat-the-last-element-in-list-differently-in-python
notlast = lambda lst:itertools.islice(lst, 0, len(lst)-1)
