#! /usr/bin/python3

import json
import paho.mqtt.client as mqtt
import random
import requests
import sys
import threading
import time

mqtt_server  = 'localhost'   # TODO: hostname of MQTT server
mqtt_port    = 18830
topic_prefix = 'kiki-ng/'  # leave this as is
channels     = ['test', 'todo', 'knageroe']  # TODO: channels to respond to
prefix       = '!'

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=urban|descr=lookup a word in the urban dictionary')

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

        if command == 'urban' and tokens[0][0] == prefix:
            try:
                query = text[text.find(' ') + 1:].strip()

                r    = requests.get(f'https://api.urbandictionary.com/v0/define?term={query}')
                data = json.loads(r.content.decode('utf8'))

                out_len = 0
                out = []

                for item in data['list']:
                    current_out = f'\3{5}' + item['definition'] + f'\3{8} (' + item['example'] + f')\3{2}'
                    l = len(current_out)

                    if out_len + l < 300:
                        out.append(current_out)
                        out_len += l

                if len(out) == 0:
                    client.publish(response_topic, 'No definition found')

                else:
                    client.publish(response_topic, ', '.join(out))

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

t = threading.Thread(target=announce_thread, args=(client,))
t.start()

client.loop_forever()
