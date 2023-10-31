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
channels     = ['test', 'knageroe']
db_file      = 'history.db'

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
    cur.close()

    con.commit()

def on_message(client, userdata, message):
    global history

    try:
        text = message.payload.decode('utf-8')

        topic = message.topic[len(topic_prefix):]

        parts   = topic.split('/')
        channel = parts[2] if len(parts) >= 3 else 'nurds'
        nick    = parts[3] if len(parts) >= 4 else 'jemoeder'

        if parts[-1] == 'topic':
            return

        if channel in channels or (len(channel) >= 1 and channel[0] == '\\'):
            print(channel, nick, text)

            query = "INSERT INTO history(`when`, channel, nick, what) VALUES(strftime('%Y-%m-%d %H:%M:%S', 'now'), ?, ?, ?)"

            cur = con.cursor()
            cur.execute(query, (channel, nick, text))
            cur.close()

            con.commit()

    except Exception as e:
        print(f'{e}, line number: {e.__traceback__.tb_lineno}')

def on_connect(client, userdata, flags, rc):
    client.subscribe(f'{topic_prefix}from/irc/#')

init_db()

client = mqtt.Client(f'{socket.gethostname()}_{sys.argv[0]}', clean_session=False)
client.on_message = on_message
client.on_connect = on_connect
client.connect(mqtt_server, port=mqtt_port, keepalive=4, bind_address="")

client.loop_forever()
