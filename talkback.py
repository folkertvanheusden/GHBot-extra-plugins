#! /usr/bin/python3

# by FvH, released under Apache License v2.0

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'

import datetime
import math
import paho.mqtt.client as mqtt
import sqlite3
import threading
import time

import socket
import sys

mqtt_server  = 'localhost'   # TODO: hostname of MQTT server
mqtt_port    = 18830
topic_prefix = 'kiki-ng/'  # leave this as is
channels     = ['test', 'todo', 'knageroe']  # TODO: channels to respond to
prefix       = '!'  # !command, will be updated by ghbot
prompt       = 'kiki:'

con = sqlite3.connect('history.db')

def counter(s):
    m = dict()

    for c in s:
        if c in m:
            m[c] += 1
        else:
            m[c] = 1

    return m

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

def on_message(client, userdata, message):
    global prefix
    global prev_j

    text = message.payload.decode('utf-8')

    topic = message.topic[len(topic_prefix):]

    if topic == 'from/bot/command' and text == 'register':
        announce_commands(client)

        return

    if topic == 'from/bot/parameter/prefix':
        prefix = text

        return

    if text[0:len(prompt)] != prompt:
        return

    parts   = topic.split('/')
    channel = parts[2] if len(parts) >= 3 else 'knageroe'  # default channel if can't be deduced
    nick    = parts[3] if len(parts) >= 4 else 'jemoeder'  # default nick if it can't be deduced

    command = text[1:].split(' ')[0]

    try:
        reply_to = text[text.find(' ') + 1:].strip()
        reply_to_counts = counter(reply_to)

        cur = con.cursor()
        cur.execute('SELECT what FROM history WHERE length(what) > 5 ORDER BY RANDOM() LIMIT 1000')
        rows = cur.fetchall()
        cur.close()

        best = None
        best_val = 1000000000000000

        for row in rows:
            row_counts = counter(row[0])
            cur_val = math.sqrt(sum((reply_to_counts.get(d,0) - row_counts.get(d,0))**2 for d in set(reply_to_counts) | set(row_counts)))

            if cur_val < best_val and cur_val != 0:
                best_val = cur_val
                best = row[0]

        if best != None:
            if '!' in nick:
                nick = nick[0:nick.find('!')]

            colon = best.find(':')
            space = best.find(' ')
            if colon != -1 and space != -1 and space > colon:
                best = best[best.find(':') + 1].strip()

            response_topic = f'{topic_prefix}to/irc/{channel}/privmsg'
            client.publish(response_topic, f'{nick}: {best}')

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

client = mqtt.Client(f'{socket.gethostname()}_{sys.argv[0]}', clean_session=False)
client.on_message = on_message
client.on_connect = on_connect
client.connect(mqtt_server, port=mqtt_port, keepalive=4, bind_address="")

t = threading.Thread(target=announce_thread, args=(client,))
t.start()

client.loop_forever()
