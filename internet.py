#! /usr/bin/python3

# pip3 install snmp

from snmp import Engine, SNMPv2c
import paho.mqtt.client as mqtt
import threading
import time
import sys
import random
import requests

from configuration import *

Bps = None

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=internet|descr=Internet statistics')

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

        if command == 'internet' and tokens[0][0] == prefix:
            try:
                client.publish(response_topic, f'bits per second (receive) for the last 5 seconds: {Bps * 8}')

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
            time.sleep(0.5)

def snmp_thread():
    global Bps

    previous = None

    while True:
        try:
            with Engine(SNMPv2c, defaultCommunity=b'public') as engine:
                host = engine.Manager('10.208.0.1')
                response = host.get('1.3.6.1.2.1.31.1.1.1.6.2')
                cur_amount = response[0].value.value
                if not previous is None:
                    Bps = (cur_amount - previous) / 5
                previous = cur_amount

        except Exception as e:
            print(f'Failed to announce: {e}')
            previous = None

        time.sleep(5)

client = mqtt.Client(sys.argv[0], clean_session=False)
client.on_message = on_message
client.on_connect = on_connect
client.connect(mqtt_server, port=mqtt_port, keepalive=4, bind_address='')

t1 = threading.Thread(target=snmp_thread)
t1.start()

t2 = threading.Thread(target=announce_thread, args=(client,))
t2.start()

client.loop_forever()
