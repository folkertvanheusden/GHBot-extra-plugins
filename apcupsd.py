#! /usr/bin/python3

# This was written by Folkert van Heusden in 2025.
# Licensen under the MIT license.

from struct import pack
import paho.mqtt.client as mqtt
import random
import socket
import sys
import threading
import time

from configuration import *

def get_data():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((apcupsd, 3551))
    # Packet is pad byte, size byte, and command
    s.send(pack('xb6s', 6, 'status'.encode('ascii')))
    s.settimeout(1.)
    data = s.recv(2)
    while True:
        try:
            temp = s.recv(4096)
        except TimeoutError as te:
            break
        data += temp
    s.close()

    out = dict()
    remove = True
    line = ''
    offset = 0
    while offset < len(data):
        if remove:
            offset += 2
            remove = False
            continue
        if data[offset] == ord('\n'):
            parts = line.split(':')
            if len(parts) == 2:
                out[parts[0].strip()] = parts[1].strip()
            remove = True
            line = ''
        else:
            line += chr(data[offset])
        offset += 1
    return out

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=ups|descr=Show status of APCUPSD')


def on_message(client, userdata, message):
    global b
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

        if command == 'ups' and tokens[0][0] == prefix:
            try:
                data = get_data()

                # 'APC': '001,027,0662', 'HOSTNAME': 'nutpi', 'VERSION': '3.14.14 (31 May 2016) debian', 'UPSNAME': 'rackserver', 'CABLE': 'USB Cable', 'DRIVER': 'USB UPS Driver', 'UPSMODE': 'Stand Alone', 'MODEL': 'Smart-UPS_2200', 'STATUS': 'ONLINE', 'BCHARGE': '100.0 Percent', 'TIMELEFT': '64.8 Minutes', 'MBATTCHG': '5 Percent', 'MINTIMEL': '3 Minutes', 'MAXTIME': '0 Seconds', 'ALARMDEL': '30 Seconds', 'BATTV': '52.4 Volts', 'NUMXFERS': '0', 'TONBATT': '0 Seconds', 'CUMONBATT': '0 Seconds', 'XOFFBATT': 'N/A', 'STATFLAG': '0x05000008', 'MANDATE': '2019-06-03', 'SERIALNO': 'AS1923160161', 'NOMBATTV': '48.0 Volts', 'FIRMWARE': 'UPS 03.7 / ID=1015'}

                response = data['STATUS'] + ' / charge:' + data['BCHARGE'] + ' / time left: ' + data['TIMELEFT']

                client.publish(response_topic, response)

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

def poll_thread(client):
    pstate = None
    while True:
        try:
            data = get_data()

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(influx_server)
            now = int(time.time())
            s.send(('ups-BCHARGE ' + data['BCHARGE'].split()[0] + f' {now}\n').encode('ascii'))
            s.send(('ups-TIMELEFT ' + data['TIMELEFT'].split()[0] + f' {now}\n').encode('ascii'))
            s.close()

            if data['STATUS'] != pstate:
                pstate = data['STATUS']

                response = data['STATUS'] + ' / charge:' + data['BCHARGE'] + ' / time left: ' + data['TIMELEFT']

                for channel in channels:
                    topic = f'{topic_prefix}to/irc/{channel}/notice'
                    client.publish(topic, response)

        except Exception as e:
            print(e)

        time.sleep(5)

client = mqtt.Client(sys.argv[0], clean_session=False)
client.on_message = on_message
client.on_connect = on_connect
client.connect(mqtt_server, port=mqtt_port, keepalive=4, bind_address="")

t1 = threading.Thread(target=poll_thread, args=(client,))
t1.start()

t2 = threading.Thread(target=announce_thread, args=(client,))
t2.start()

client.loop_forever()
