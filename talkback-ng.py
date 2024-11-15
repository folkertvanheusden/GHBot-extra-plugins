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

from configuration import *
prompt = 'kiki:'

con = sqlite3.connect('history.db')

def compare(a, b):
    aparts = a.lower().split()
    bparts = b.lower().split()

    match_count = 0
    for apart in aparts:
        if apart in bparts:
            match_count += 1
    return match_count / len(aparts)

def compare_detail(a, b):
    match_count = 0
    for apart in a:
        if apart in b:
            match_count += 1
    return match_count / len(a)

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

    if 'sagtebotje' in nick:
        return

    command = text[1:].split(' ')[0]

    try:
        reply_to = text[text.find(' ') + 1:].strip()

        cur = con.cursor()
        cur.execute('SELECT what, `when` FROM history WHERE length(what) > 1 ORDER BY RANDOM() LIMIT 2500')
        rows = cur.fetchall()
        cur.close()

        best_ts = None
        best_value = -1.
        best_value_detail = -1.
        best_text = None

        for row in rows:
            match_value = compare(row[0], reply_to)
            match_value_detail = compare_detail(row[0], reply_to)
            if match_value > best_value or (match_value == best_value and match_value_detail > best_value_detail):
                best_value = match_value
                best_value_detail = match_value_detail
                best_ts = row[1]
                best_text = row[0]

        if best_ts != None:
            print(f'Selected "{best_text}" ({best_value}/{best_value_detail}, of {best_ts}) to respond to')
            if '!' in nick:
                nick = nick[0:nick.find('!')]

            cur = con.cursor()
            cur.execute('SELECT what FROM history WHERE `when` > ? ORDER BY `when` LIMIT 1', (best_ts,))
            row = cur.fetchone()[0]
            cur.close()

            print(f'Using: \"{row}\"')

            space = row.find(' ')
            colon = row.find(':')
            if colon != -1 and colon < space:
                row = row[colon + 1:].strip()

            response_topic = f'{topic_prefix}to/irc/{channel}/privmsg'
            client.publish(response_topic, f'{nick}: {row}')

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
