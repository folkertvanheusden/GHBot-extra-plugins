#! /usr/bin/python3

import math
import paho.mqtt.client as mqtt
import requests
import threading
import time
import sys
import random
import xml.dom.minidom as xmd
import wikipediaapi


mqtt_server  = 'localhost'   # TODO: hostname of MQTT server
mqtt_port    = 18830
topic_prefix = 'kiki-ng/'  # leave this as is
channels     = ['test', 'todo', 'knageroe']  # TODO: channels to respond to
prefix       = '!'

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=wikipedia|descr=Lookup something in wikipedia.')

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

        if command == 'wikipedia' and tokens[0][0] == prefix:
            try:
                space = text.find(' ')
                query = text[space + 1:].strip() if space != -1 else 'multitail'

                wiki_wiki = wikipediaapi.Wikipedia('GHBot (mail@vanheusden.com)', 'en')
                page_py = wiki_wiki.page(query)

                if page_py.exists() == False:
                    client.publish(response_topic, f'There is no page about {query} on wikipedia.')

                else:
                    out = f'{page_py.title}: {page_py.summary[0:300]}'

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

t = threading.Thread(target=announce_thread, args=(client,))
t.start()

client.loop_forever()
