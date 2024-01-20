#! /usr/bin/python3

# by FvH, released under Apache License v2.0

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'

import paho.mqtt.client as mqtt
import sqlite3
import threading
import time

import socket
import sys

mqtt_server  = 'localhost'
mqtt_port    = 18830
topic_prefix = 'kiki-ng/'
channels     = ['test', 'todo', 'knageroe']
db_file      = 'history.db'
prefix       = '!'

con = sqlite3.connect(db_file)

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

def sparkline(numbers):
    # bar = u'\u9601\u9602\u9603\u9604\u9605\u9606\u9607\u9608'
    bar = chr(9601) + chr(9602) + chr(9603) + chr(9604) + chr(9605) + chr(9606) + chr(9607) + chr(9608)
    barcount = len(bar)

    mn, mx = min(numbers), max(numbers)
    extent = mx - mn
    sparkline = ''.join(bar[min([barcount - 1, int((n - mn) / extent * barcount)])] for n in numbers)

    return mn, mx, sparkline

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

            cur = con.cursor()
            cur.execute(query, (channel, nick.lower(), text))
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
                verbose = '-v' in tokens

                if verbose:
                    for what in ('%H', '%Y', '%m'):
                        cur = con.cursor()
                        cur.execute('SELECT strftime("%s", `when`), COUNT(*) AS n FROM history WHERE channel=? AND nick=? AND (not substr(what, 1, 1)="#") AND (not substr(what, 1, 1)="!") GROUP BY strftime("%s", `when`) ORDER BY strftime("%s", `when`) ASC' % (what, what, what), (channel.lower(), tokens[1].lower()))
                        results = cur.fetchall()
                        cur.close()

                        if results == None:
                            client.publish(response_topic, f'{tokens[1]} was never in {channel}')

                        else:
                            total = sum([result[1] for result in results])

                            percentages = []
                            out = []
                            for result in results:
                                percentage = int(result[1]) * 100 / total
                                percentages.append(percentage)
                                out.append(f'{result[0]}: {percentage:.2f}%')

                            client.publish(response_topic, (', '.join(out)) + ' - ' + sparkline(percentages)[2])

                cur = con.cursor()
                cur.execute('select what, count(*) from history where channel=? AND nick=? AND (not substr(what, 1, 1)="#") AND (not substr(what, 1, 1)="!") group by what order by count(*) desc limit 10', (channel.lower(), tokens[1].lower()))
                results = cur.fetchall()
                cur.close()

                if results != None:
                    client.publish(response_topic, ', '.join([f'{result[0]}: {result[1]}' for result in results]))

                else:
                    client.publish(response_topic, f'{tokens[1]} was never in {channel}')

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

client.loop_forever()
