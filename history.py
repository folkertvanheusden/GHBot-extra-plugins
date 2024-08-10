#! /usr/bin/python3

# by FvH, released under Apache License v2.0

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'

import math
import paho.mqtt.client as mqtt
import sqlite3
import threading
import time
import pandas as pd
from prophet import Prophet

import socket
import sys

mqtt_server  = 'mqtt.vm.nurd.space'
mqtt_port    = 1883
topic_prefix = 'GHBot/'
channels     = ['nurds', 'nurdbottest', 'nurdsbofh']
db_file      = 'history.db'
prefix       = '!'

con = sqlite3.connect(db_file)
con.set_trace_callback(print)

def init_db():
    global con

    print('Init DB...')

    cur = con.cursor()
    try:
        cur.execute('CREATE TABLE history(channel TEXT NOT NULL, `when` DATETIME NOT NULL, nick TEXT NOT NULL, what TEXT NOT NULL)')
        cur.execute('CREATE INDEX history_channel ON history(`channel`)')
        cur.execute('CREATE INDEX history_when ON history(`when`)')
        cur.execute('CREATE INDEX history_nick ON history(`nick`)')

    except sqlite3.OperationalError as oe:
        # should be "table already exists"
        pass

    cur.close()

    cur = con.cursor()
    cur.execute('PRAGMA journal_mode=wal')
    cur.execute('PRAGMA encoding="UTF-8"')
    cur.close()

    con.commit()

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'hgrp=history|cmd=firstseen|descr=when was a person first seen')
    client.publish(target_topic, 'hgrp=history|cmd=searchhistory|descr=when was a text-string seen')
    client.publish(target_topic, 'hgrp=history|cmd=searchhistorybynick|descr=when was a text-string seen, by nick')
    client.publish(target_topic, 'hgrp=history|cmd=personstats|descr=statistics of a person')
    client.publish(target_topic, 'hgrp=history|cmd=predictactivity|descr=predict your own activity')

def sparkline(numbers):
    if len(numbers) == 0:
        return 0, 0, ''

    # bar = u'\u9601\u9602\u9603\u9604\u9605\u9606\u9607\u9608'
    bar = chr(9601) + chr(9602) + chr(9603) + chr(9604) + chr(9605) + chr(9606) + chr(9607) + chr(9608)
    barcount = len(bar)

    mn, mx = min(numbers), max(numbers)
    extent = mx - mn
    if extent != 0:
        sparkline = ''.join(bar[min([barcount - 1, int((n - mn) / extent * barcount)])] for n in numbers)
    else:
        sparkline = '-'

    return mn, mx, sparkline

def prophet(client, response_topic, who, channel):
    print('prophet start')

    try:
        con = sqlite3.connect(db_file)

        cur = con.cursor()
        cur.execute("select strftime('%s', strftime('%Y-%m-%d 00:00:00', `when`)), count(*) as n from history where channel=? and nick=? group by date(`when`) order by `when`", (channel, who))

        tsa = []
        va  = []

        for row in cur:
            tsa.append(row[0])
            va .append(row[1])

        cur.close()

        con.close()

        # average
        ds_a = pd.to_datetime(tsa, unit='s')

        df_a = pd.DataFrame({'ds': ds_a, 'y': va}, columns=['ds', 'y'])

        m = Prophet()
        m.fit(df_a)

        future = m.make_future_dataframe(periods=31)
        future.tail()

        forecast = m.predict(future)

        latest_ts = None
        latest_hr = None

        now = time.time()
        print(forecast)

        next_ = None
        for i in range(0, forecast['ds'].count()):
            if forecast['ds'][i].to_pydatetime().timestamp() > now:
                next_ = i
                break

        if next_ == None:
            client.publish(response_topic, f'No idea!')

        else:
            dates = []
            for i in range(0, 3):
                latest_ts = forecast['ds'][i + next_].to_pydatetime()
                latest_cnt = forecast['yhat'][i + next_]
                date = str(latest_ts)
                date = date.split()[0]
                dates.append(f'on {date} you will say {math.floor(latest_cnt)} lines of text in {channel}')

            if len(dates) > 0:
                client.publish(response_topic, f'{", ".join(dates)}')
            else:
                client.publish(response_topic, f'Not sure')

    except Exception as e:
        client.publish(response_topic, f'Exception while predicting activiy of {who} in {channel}: {e}, line number: {e.__traceback__.tb_lineno}')

    print('prophet end')

def on_message(client, userdata, message):
    global history
    global prefix

    try:
        text = message.payload.decode('utf-8')

        topic = message.topic[len(topic_prefix):]

        if topic == 'from/bot/command' and text == 'register':
            announce_commands(client)
            return

        if topic == 'from/bot/parameter/prefix':
            prefix = text
            return

        parts   = topic.split('/')
        channel = parts[2] if len(parts) >= 3 else 'nurds'
        nick    = parts[3] if len(parts) >= 4 else 'jemoeder'

        if parts[-1] == 'topic':
            return

        if channel in channels or (len(channel) >= 1 and channel[0] == '\\'):
            print(channel, nick, text)

            query = "INSERT INTO history(`when`, channel, nick, what) VALUES(strftime('%Y-%m-%d %H:%M:%S', 'now'), ?, ?, ?)"

            work_nick = nick.lower()
            excl = work_nick.find('!')
            if excl != -1:
                work_nick = work_nick[0:excl]

            cur = con.cursor()
            cur.execute(query, (channel, work_nick, text))
            cur.close()

            con.commit()

            tokens  = text.split(' ')

            command = tokens[0][1:]

            response_topic = f'{topic_prefix}to/irc/{channel}/notice'

            if command == 'firstseen' and tokens[0][0] == prefix and len(tokens) >= 2:
                cur = con.cursor()
                cur.execute('SELECT what, `when` FROM history WHERE channel=? AND nick=? ORDER BY `when` ASC LIMIT 3', (channel.lower(), tokens[1].lower()))
                results = cur.fetchall()
                cur.close()

                if results == None:
                    client.publish(response_topic, f'{tokens[1]} was never in {channel}')

                else:
                    out = ''
                    for result in results:
                        out += f'It was {result[1]} when {tokens[1]} said "{result[0]}" '

                    client.publish(response_topic, out)

            elif command == 'personstats' and tokens[0][0] == prefix and len(tokens) >= 2:
                try:
                    verbose = '-v' in tokens

                    never_there = False

                    if verbose:
                        for what in ('%H', '%Y', '%m'):
                            cur = con.cursor()
                            cur.execute('SELECT strftime("%s", `when`), COUNT(*) AS n FROM history WHERE channel=? AND nick=? AND (not substr(what, 1, 1)="#") AND (not substr(what, 1, 1)="!") GROUP BY strftime("%s", `when`) ORDER BY strftime("%s", `when`) ASC' % (what, what, what), (channel.lower(), tokens[1].lower()))
                            results = cur.fetchall()
                            cur.close()

                            if results == None or len(results) == 0:
                                client.publish(response_topic, f'{tokens[1]} was never in {channel}')
                                never_there = True
                                break

                            total = sum([result[1] for result in results])

                            percentages = []
                            out = []
                            for result in results:
                                percentage = int(result[1]) * 100 / total
                                percentages.append(percentage)
                                out.append(f'{result[0]}: {percentage:.2f}%')

                            client.publish(response_topic, (', '.join(out)) + ' - ' + sparkline(percentages)[2])

                    if never_there == False:
                        cur = con.cursor()
                        cur.execute('select what, count(*) from history where channel=? AND nick=? AND (not substr(what, 1, 1)="#") AND (not substr(what, 1, 1)="!") group by what order by count(*) desc limit 10', (channel.lower(), tokens[1].lower()))
                        results = cur.fetchall()
                        cur.close()

                        if results != None and len(results) > 0:
                            client.publish(response_topic, ', '.join([f'{result[0]}: {result[1]}' for result in results]))

                        else:
                            client.publish(response_topic, f'{tokens[1]} was never in {channel}')

                except Exception as e:
                    client.publish(response_topic, f'Error: {e}, line number: {e.__traceback__.tb_lineno}')
                    print(f'{e}, line number: {e.__traceback__.tb_lineno}')

            elif (command == 'searchhistory' or command == 'searchhistorybynick') and tokens[0][0] == prefix and len(tokens) >= (3 if command == 'searchhistorybynick' else 2):
                cur = con.cursor()

                if command == 'searchhistorybynick':
                    what = '%' + text[text.find(' ', text.find(' ') + 1) + 1:].strip() + '%'
                    cur.execute('SELECT what, `when`, nick FROM history WHERE channel=? AND nick=? AND what like ? AND DATE(`when`) != DATE() ORDER BY RANDOM() LIMIT 25', (channel.lower(), tokens[1].lower(), what))
                else:
                    what = '%' + text[text.find(' ') + 1:].strip() + '%'
                    cur.execute('SELECT what, `when`, nick FROM history WHERE channel=? AND what like ? AND DATE(`when`) != DATE() ORDER BY RANDOM() LIMIT 25', (channel.lower(), what))

                out = None
                color = False

                while True:
                    result = cur.fetchone()
                    if result == None:
                        break

                    new = '\3'
                    new += '15' if color else '5'
                    color = not color

                    if command == 'searchhistorybynick':
                        new += f'It was {result[1]} when {tokens[1]} said "{result[0]}"'
                    else:
                        new += f'It was {result[1]} when {result[2]} said "{result[0]}"'

                    if out == None:
                        out = new
                    else:
                        if len(out) + len(new) > 8192:
                            break
                        out += ' ' + new

                cur.close()

                if out == None:
                    client.publish(response_topic, f'no-one ever said "{what[1:-1]}" in {channel}')

                else:
                    client.publish(response_topic, out)

            elif command == 'predictactivity' and tokens[0][0] == prefix:
                prophet(client, response_topic, work_nick, channel)

    except Exception as e:
        print(f'{e}, line number: {e.__traceback__.tb_lineno}')

def on_connect(client, userdata, flags, rc):
    client.subscribe(f'{topic_prefix}from/irc/#')

    client.subscribe(f'{topic_prefix}from/bot/command')

def announce_thread(client):
    while True:
        try:
            announce_commands(client)

            time.sleep(4.1)

        except Exception as e:
            print(f'Failed to announce: {e}')

init_db()

client = mqtt.Client(f'{socket.gethostname()}_{sys.argv[0]}', clean_session=False)
client.on_message = on_message
client.on_connect = on_connect
client.connect(mqtt_server, port=mqtt_port, keepalive=4, bind_address="")

t = threading.Thread(target=announce_thread, args=(client,))
t.start()

print('Go!')
client.loop_forever()
