import psycopg2
import datetime

from trac.util.datefmt import from_utimestamp, to_utimestamp, utc, utcmax

built_in_fields = ('milestone',
                   'type',
                   'priority',
                   'status',
                   'resolution',
                   'keywords',
                   'severity',
                   'owner',
                   'reporter',
                   'component',
                   'version')

conn = psycopg2.connect("dbname=define_d4_db user=define_d4 password=... host=localhost port=15432")
ticket_ids = conn.cursor()
ticket_ids.execute("SELECT id FROM ticket GROUP BY id ORDER BY id")
for ticket_id, in ticket_ids:
    print "Working on ticket %d" % ticket_id

    c = conn.cursor()
    c.execute("SELECT time FROM ticket WHERE id = %s", (ticket_id,))
    ticket_created = from_utimestamp(c.fetchone()[0])
    
    history_date = ticket_created.date()

    ticket_values = {'milestone': None,
                     'type': None,
                     'priority': None,
                     'status': None,
                     'resolution': None,
                     'keywords': None,
                     'severity': None,
                     'owner': None,
                     'reporter': None,
                     'version': None,
                     'component': None,
                     'resolvedinversion': None,
                     'qualityassurancecontact': None,
                     'totalhours': None,
                     'estimatedhours': None,
                     'remaininghours': None}

    # find original values for the ticket
    for column in ticket_values.keys():
        c.execute("SELECT oldvalue FROM ticket_change WHERE ticket = %s and field = %s ORDER BY time LIMIT 1",  
                  (ticket_id, column))
        result = c.fetchone()
        if result is None:
            # column has never changed
            if column in built_in_fields:
                c.execute("SELECT %s FROM ticket WHERE id = %%s" % column, (ticket_id,))
            else:
                c.execute("SELECT value FROM ticket_custom WHERE ticket = %s AND name = %s", (ticket_id, column))
            result = c.fetchone()
            if result:
                ticket_values[column] = result[0]
            else:
                ticket_values[column] = None
        else:
            ticket_values[column] = result[0]

    ticket_values['id'] =  ticket_id
    ticket_values['time'] = ticket_created
    ticket_values['changetime'] = ticket_created
    ticket_values['resolutiontime'] = None

    # PROBLEM: How can we detect when a milestone was renamed (and
    # tickets updated) - this isn't mentioned in the ticket_change
    # table.
    # Maybe we have to search the log file for strings?!  
    # source:trunk/trac/trac/ticket/model.py@8937#L1192


    ticket_changes = []
    c.execute("SELECT time, field, newvalue FROM ticket_change WHERE ticket = %%s AND field in %s ORDER BY time" % (
            str(tuple(ticket_values.keys())),),
              (ticket_id,))
    for result in c:
        ticket_changes.append((from_utimestamp(result[0]), result[1], result[2]))

    execute_many_buffer = []
    while history_date < datetime.date.today():
        #print history_date
        active_changes = {}
        for time, field, newvalue in ticket_changes:
            history_time = datetime.datetime.combine(history_date, datetime.time(tzinfo=utc))
            if time <= history_time:
                # finding the newest change for each field, which is older than or equal to history_date
                #print "Setting %s to %s" % (field, newvalue)
                active_changes[field] = newvalue
                active_changes['changetime'] = time
                if field == "resolution":
                    active_changes['resolutiontime'] = time
        ticket_values.update(active_changes)

        execute_many_buffer.append(\
                  (history_date,) * 6 + \
                      (ticket_values['id'],
                       ticket_values['type']) + \
                      (ticket_values['time'],) * 6 + \
                      (ticket_values['changetime'],) * 6 + \
                      (ticket_values['resolutiontime'],) * 6 + \
                      (ticket_values['component'],
                       ticket_values['severity'],
                       ticket_values['priority'],
                       ticket_values['owner'],
                       ticket_values['reporter'],
                       ticket_values['qualityassurancecontact']) + \
                      (ticket_values['version'],) * 5 + \
                      (ticket_values['resolvedinversion'],) * 5 + \
                      (ticket_values['milestone'],
                       ticket_values['status'],
                       ticket_values['resolution'],
                       ticket_values['keywords']) + \
                      (ticket_values['estimatedhours'],) * 2 + \
                      (ticket_values['totalhours'],) * 2 + \
                      (ticket_values['remaininghours'],) * 2)

        history_date = history_date + datetime.timedelta(days=1)

    #print "Inserting..."
    # we do as much as possible of the transformations in SQL, so that it matches the ticket_bi_current view
    # and avoids any small differences in Python vs. SQL functions
    c.executemany(r"""
INSERT INTO ticket_bi_historical 
(
 snapshottime,
 snapshottime_year,
 snapshottime_quarter,
 snapshottime_month,
 snapshottime_week,
 snapshottime_day,
 id,
 type,
 "time",
 time_year,
 time_quarter,
 time_month,
 time_week,
 time_day,
 changetime,
 changetime_year,
 changetime_quarter,
 changetime_month,
 changetime_week,
 changetime_day,
 resolutiontime,
 resolutiontime_year,
 resolutiontime_quarter,
 resolutiontime_month,
 resolutiontime_week,
 resolutiontime_day,
 component,
 severity,
 priority,
 owner,
 reporter,
 qualityassurancecontact,
 version,
 version_major,
 version_minor,
 version_point,
 version_patch,
 resolvedinversion,
 resolvedinversion_major,
 resolvedinversion_minor,
 resolvedinversion_point,
 resolvedinversion_patch,
 milestone,
 status,
 resolution,
 keywords,
 estimatedhours,
 totalhours,
 remaininghours
)
VALUES
(
 %s, date_part('year', %s::timestamp), date_part('quarter', %s::timestamp), 
     date_part('month', %s::timestamp), date_part('week', %s::timestamp), date_part('day', %s::timestamp),
 %s,
 %s,
 %s, date_part('year', %s::timestamp), date_part('quarter', %s::timestamp), 
     date_part('month', %s::timestamp), date_part('week', %s::timestamp), date_part('day', %s::timestamp),
 %s, date_part('year', %s::timestamp), date_part('quarter', %s::timestamp), 
     date_part('month', %s::timestamp), date_part('week', %s::timestamp), date_part('day', %s::timestamp),
 %s, date_part('year', %s::timestamp), date_part('quarter', %s::timestamp), 
     date_part('month', %s::timestamp), date_part('week', %s::timestamp), date_part('day', %s::timestamp),
 %s,
 %s,
 %s,
 %s,
 %s,
 %s,
 %s, substring(%s from '([\\d]+)\.[\\d]+\.[\\d]+'),
     substring(%s from '[\\d]+\.([\\d]+)\.[\\d]+'),
     substring(%s from '[\\d]+\.[\\d]+\.([\\d]+)'),
     substring(%s from '[\\d]+\.[\\d]+\.[\\d]+(.+)'),
 %s, substring(%s from '([\\d]+)\.[\\d]+\.[\\d]+'),
     substring(%s from '[\\d]+\.([\\d]+)\.[\\d]+'),
     substring(%s from '[\\d]+\.[\\d]+\.([\\d]+)'),
     substring(%s from '[\\d]+\.[\\d]+\.[\\d]+(.+)'),
 %s,
 %s,
 %s,
 %s,
 CASE WHEN btrim(%s)~E'^[\\d\\.]+$' THEN %s::double precision ELSE 0.0 END,
 CASE WHEN btrim(%s)~E'^[\\d\\.]+$' THEN %s::double precision ELSE 0.0 END,
 CASE WHEN btrim(%s)~E'^[\\d\\.]+$' THEN %s::double precision ELSE 0.0 END
)
""", execute_many_buffer)

    # commit per ticket
    #print "Commit..."
    conn.commit()

