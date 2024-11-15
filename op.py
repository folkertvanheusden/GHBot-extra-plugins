#! /usr/bin/python3

# by FvH, released under Apache License v2.0

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'


import paho.mqtt.client as mqtt
import sqlite3
import threading
import time
import socket
import sys

mqtt_server  = 'mqtt.vm.nurd.space'   # TODO: hostname of MQTT server
mqtt_port    = 1883
topic_prefix = 'GHBot/'  # leave this as is
channels     = ['nurds']  # TODO: channels to respond to
prefix       = '!'  # !command, will be updated by ghbot
db           = 'op.db'

con = sqlite3.connect(db)

cur = con.cursor()
cur.execute('PRAGMA journal_mode=wal')
cur.close()

con.commit()

op_pending = None
op_pending_ch = None

def init_db():
    try:
        cur = con.cursor()
        query = 'CREATE TABLE op(channel TEXT NOT NULL, who TEXT NOT NULL, PRIMARY KEY(channel, who))'
        cur.execute(query)
        cur.close()

        con.commit()

    except sqlite3.OperationalError as oe:
        # table already exists (hopefully)
        pass

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=op|descr=Give a pre-registered user operator-status')

def on_message(client, userdata, message):
    global op_pending
    global op_pending_ch
    global prefix

    text  = message.payload.decode('utf-8')
    topic = message.topic[len(topic_prefix):]

    if topic == 'from/bot/command' and text == 'register':
        announce_commands(client)
        return

    if topic == 'from/bot/parameter/prefix':
        prefix = text
        return

    if len(text) == 0:
        return

    parts   = topic.split('/')
    channel = parts[2] if len(parts) >= 3 else 'knageroe'  # default channel if can't be deduced
    nick    = parts[3] if len(parts) >= 4 else 'jemoeder'  # default nick if it can't be deduced

    command = text[1:].split()[0]

    print(parts, text)

    if len(parts) >= 5 and parts[4].isnumeric():  # irc server status
        command = parts[4]

        if command == '482':
            if op_pending != None:
                response_topic = f'{topic_prefix}to/irc/{op_pending_ch}/privmsg'
                client.publish(response_topic, f"Could not give {op_pending} operator rights: don't have op myself!")
                op_pending = None
                op_pending_ch = None

    elif len(parts) >= 5 and parts[4] == 'MODE':
        response_topic = f'{topic_prefix}to/irc/{op_pending_ch}/privmsg'
        client.publish(response_topic, f"Successfully gave {op_pending} operator rights")

    elif channel in channels or (len(channel) >= 1 and channel[0] == '\\') or command.isnumeric():
        response_topic = f'{topic_prefix}to/irc/{channel}/privmsg'
        command_topic  = f'{topic_prefix}to/irc/{channel}/MODE'

        if command == 'op':
            try:
                if not '!' in nick:
                    client.publish(response_topic, f'Incomplete nick')
                    return

                excl = nick.find('!')
                host = nick[excl + 1:]

                cur = con.cursor()
                cur.execute('SELECT who FROM op WHERE channel=? AND who=?', (channel, host.lower()))
                row = cur.fetchone()
                cur.close()

                if row is None:
                    client.publish(response_topic, f'User ({nick}) is not registered for op-status')

                else:
                    client.publish(response_topic, f'Applying operator status')
                    client.publish(f'{topic_prefix}to/irc/{channel}/mode', f'+o {nick[0:excl]}')

                    op_pending = nick[0:excl]
                    op_pending_ch = channel

            except Exception as e:
                client.publish(response_topic, f'Op failed: {e}, line number: {e.__traceback__.tb_lineno}')

        else:
            op_pending = None
            op_pending_ch = None

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
