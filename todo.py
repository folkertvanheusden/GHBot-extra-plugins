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
channels     = ['test', 'knageroe', 'todo']
db_file      = 'todo.db'
prefix       = '!'

con = sqlite3.connect(db_file)

cur = con.cursor()
try:
    cur.execute('CREATE TABLE todo(nr INTEGER PRIMARY KEY, channel TEXT NOT NULL, added_by TEXT NOT NULL, value TEXT NOT NULL)')
    cur.execute('CREATE INDEX learn_key ON learn(key)')
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

    client.publish(target_topic, 'cmd=addtodo|descr=add an item (or multiple, seperated by /) to your todo-list')
    client.publish(target_topic, 'cmd=deltodo|descr=delete one or more items from your todo-list (seperated by space)')
    client.publish(target_topic, "cmd=todo|descr=get a list of your todos")
    client.publish(target_topic, "cmd=randomtodo|descr=list randomly one of your todos")
    client.publish(target_topic, "cmd=setdefaulttodo|descr=set default list of todos")
    client.publish(target_topic, "cmd=usedefaulttodo|descr=use default list of todos")

def on_message(client, userdata, message):
    global prefix

    text = message.payload.decode('utf-8')

    topic = message.topic[len(topic_prefix):]

    if topic == 'from/bot/command' and text == 'register':
        announce_commands(client)
        return

    if topic == 'from/bot/parameter/prefix':
        prefix = text
        return

    parts   = topic.split('/')
    channel = parts[2] if len(parts) >= 3 else 'knageroe'
    nick    = parts[3] if len(parts) >= 4 else 'jemoeder'

    if channel in channels or (len(channel) >= 1 and channel[0] == '\\'):
        response_topic = f'{topic_prefix}to/irc/{channel}/notice'

        if '!' in nick:
            nick = nick.split('!')[0]

        tokens  = text.split(' ')

        command = tokens[0][1:]

        if command == 'addtodo' and tokens[0][0] == prefix:
            if len(tokens) >= 2:
                todo_item = text[text.find(' ') + 1:]

                cur = con.cursor()

                for item in todo_item.split('/'):
                    try:
                        cur.execute("INSERT INTO todo(channel, added_by, value, added_when) VALUES(?, ?, ?, strftime('%Y-%m-%d %H:%M:%S', 'now'))", (channel, nick, item))
                        nr = cur.lastrowid
                        client.publish(response_topic, f'Todo item "{item}" stored under number {nr}')

                        con.commit()

                    except Exception as e:
                        client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

                cur.close()

            else:
                client.publish(response_topic, 'Todo item missing')

        elif command == 'setdefaulttodo' and tokens[0][0] == prefix:
            # sqlite> create table dflt(channel TEXT NOT NULL, added_by TEXT NOT NULL, value TEXT NOT NULL);
            if len(tokens) >= 2:
                todo_item = text[text.find(' ') + 1:]

                cur = con.cursor()

                try:
                    cur.execute('DELETE FROM dflt WHERE channel=? AND added_by=?', (channel, nick))
                    cur.execute('INSERT INTO dflt(channel, added_by, value) VALUES(?, ?, ?)', (channel, nick, todo_item))
                    client.publish(response_topic, f'Default todo items set')

                    con.commit()

                except Exception as e:
                    client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

                cur.close()

            else:
                client.publish(response_topic, 'Todo item(s) missing')

        elif command == 'usedefaulttodo' and tokens[0][0] == prefix:
            cur = con.cursor()

            try:
                cur.execute('SELECT value FROM dflt WHERE channel=? AND added_by=?', (channel, nick))
                row = cur.fetchone()

                if row == None:
                    client.publish(response_topic, f'No default todo items set')

                else:
                    n = 0
                    for item in row[0].split('/'):
                        try:
                            cur.execute("INSERT INTO todo(channel, added_by, value, added_when) VALUES(?, ?, ?, strftime('%Y-%m-%d %H:%M:%S', 'now'))", (channel, nick, item))
                            n += 1

                        except Exception as e:
                            client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

                    client.publish(response_topic, f'Added {n} item(s)')

                con.commit()

            except Exception as e:
                client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

            cur.close()

        elif command == 'deltodo' and tokens[0][0] == prefix:
            if len(tokens) >= 2:
                cur = con.cursor()

                try:
                    for nr in tokens[1:]:
                        cur.execute("SELECT value, added_when, JULIANDAY(strftime('%Y-%m-%d %H:%M:%S', 'now')) - JULIANDAY(added_when) as took FROM todo WHERE nr=?", (nr,))
                        row = cur.fetchone()

                        took = row[2]
                        if took < 86400:
                            took = f' Took: {took * 86400:.2f} seconds' if took != None else ''
                        else:
                            took = f' Took: {took:.2f} days' if took != None else ''

                        cur.execute('DELETE FROM todo WHERE nr=? AND added_by=?', (nr, nick))

                        if cur.rowcount == 1:
                            if row != None:
                                client.publish(response_topic, f'Todo item {nr} deleted ({row[0]}){took}')

                            else:
                                client.publish(response_topic, f'Todo item {nr} deleted{took}')

                        else:
                            client.publish(response_topic, f'Todo item {nr} is either not yours or does not exist')

                except Exception as e:
                    client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

                cur.close()
                con.commit()

            else:
                client.publish(response_topic, 'Invalid number of parameters: parameter should be the todo-number')

        elif command == 'todo' and tokens[0][0] == prefix:
            cur = con.cursor()

            try:
                verbose = True #if len(tokens) == 2 and tokens[1] == '-v' else False
                word = tokens[0][0:-1]
                who = (tokens[1] if len(tokens) >= 2 else nick).lower()

                cur.execute('SELECT value, nr FROM todo WHERE added_by=? ORDER BY nr DESC', (who,))

                todo = None

                for row in cur.fetchall():
                    item = f'{row[0]} ({row[1]})' if verbose else row[0]

                    if todo == None:
                        todo = item

                    else:
                        todo += ' / ' + item

                if todo != None:
                    client.publish(response_topic, f'{nick}: {todo}')

                else:
                    client.publish(response_topic, f'{nick}: -nothing-')

            except Exception as e:
                client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

            cur.close()

        elif command == 'randomtodo' and tokens[0][0] == prefix:
            cur = con.cursor()

            try:
                cur.execute('SELECT value, nr FROM todo WHERE added_by=? ORDER BY RANDOM() LIMIT 1', (nick.lower(),))
                row = cur.fetchone()

                item = f'{row[0]} ({row[1]})' if row else '-nothing-'

                client.publish(response_topic, f'{nick}: {item}')

            except Exception as e:
                client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

            cur.close()

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

client = mqtt.Client(f'{socket.gethostname()}_{sys.argv[0]}', clean_session=False)
client.on_message = on_message
client.on_connect = on_connect
client.connect(mqtt_server, port=mqtt_port, keepalive=4, bind_address="")

t = threading.Thread(target=announce_thread, args=(client,))
t.start()

client.loop_forever()
