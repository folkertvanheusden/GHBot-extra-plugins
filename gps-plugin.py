#! /usr/bin/python3

# apt install python3-ntp

import json
import paho.mqtt.client as mqtt
import requests
import threading
import time
import socket
import sys

from configuration import *

gd_lock      = threading.Lock()
gps_data     = dict()

def gps_processor():
    while True:
        s = None

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(gpsd_server)

            # start stream
            s.send('?WATCH={"enable":true,"json":true}\r\n'.encode('ascii'))

            buffer = ''

            while True:
                buffer += s.recv(65536).decode('ascii').replace('\r','')

                lf = buffer.find('\n')
                if lf == -1:
                    continue

                current = buffer[0:lf]
                buffer = buffer[lf + 1:]

                forget = []

                j = json.loads(current)

                gd_lock.acquire()
                gps_data[j['class']] = j
                gd_lock.release()

        except KeyboardInterrupt as ki:
            print(f'Exception (gps_api.py, ctrl+c): {e}, line number: {e.__traceback__.tb_lineno}')
            break

        except Exception as e:
            print(f'Exception (gps_api.py): {e}, line number: {e.__traceback__.tb_lineno}')
            time.sleep(1)

        if s != None:
            s.close()

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, f'cmd=gps|descr=State of GPS at {gpsd_server}')

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

    if len(text) == 0:
        return

    parts   = topic.split('/')
    channel = parts[2] if len(parts) >= 3 else 'nurds'  # default channel if can't be deduced
    hostmask = parts[3] if len(parts) >= 4 else 'jemoeder'  # default nick if it can't be deduced
    nickname = hostmask.split('!')[0]

    message_response_topic = f'{topic_prefix}to/irc/{channel}/privmsg'
    karma_command_topic = f'{topic_prefix}from/irc/{channel}/{hostmask}/message'

    if channel in channels or (len(channel) >= 1 and channel[0] == '\\'):
        response_topic = f'{topic_prefix}to/irc/{channel}/notice'

        tokens  = text.split(' ')

        command = tokens[0][1:]

        if command == 'gps' and tokens[0][0] == prefix:
            try:
                gd_lock.acquire()
                j = gps_data
                gd_lock.release()

                out = 'GPS:'

                if 'TPV' in j:
                    if j['TPV']['mode'] == 2:
                        out += ' 2D fix'
                    elif j['TPV']['mode'] == 3:
                        out += ' 3D fix'
                    else:
                        out += ' no fix'

                    out += f', lat/lng/alt: {j["TPV"]["lat"]:.5f}/{j["TPV"]["lon"]:.5f}/{j["TPV"]["alt"]:.5f}'

                if 'SKY' in j:
                    out += ', satellites: ' + str(j['SKY']['uSat']) + '/' + str(j['SKY']['nSat'])

                    out += f', h/v/p-dop: {j["SKY"]["hdop"]}/{j["SKY"]["vdop"]}/{j["SKY"]["pdop"]}'

                client.publish(response_topic, out)

            except Exception as e:
                client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')


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

client = mqtt.Client(sys.argv[0], clean_session=False)
client.on_message = on_message
client.on_connect = on_connect
client.connect(mqtt_server, port=mqtt_port, keepalive=4, bind_address="")

t = threading.Thread(target=gps_processor)
t.start()

t = threading.Thread(target=announce_thread, args=(client,))
t.start()

client.loop_forever()
