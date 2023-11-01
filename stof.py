#! /usr/bin/python3

# by FvH, released under Apache License v2.0

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'
# pip3 install geocoder

import datetime
import geocoder
import json
import math
import paho.mqtt.client as mqtt
import pytz
import requests
import threading
import time
import urllib.parse
import urllib.request

import socket
import sys

mqtt_server  = 'localhost'   # TODO: hostname of MQTT server
mqtt_port    = 18830
topic_prefix = 'kiki-ng/'  # leave this as is
channels     = ['test', 'todo', 'knageroe']  # TODO: channels to respond to
prefix       = '!'  # !command, will be updated by ghbot

netherlands_tz = pytz.timezone("Europe/Amsterdam")

prev_j = None

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=stof|descr=Hoeveel stof op een bepaald adres?')

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

    if len(text) == 0:
        return

    parts   = topic.split('/')
    channel = parts[2] if len(parts) >= 3 else 'knageroe'  # default channel if can't be deduced
    nick    = parts[3] if len(parts) >= 4 else 'jemoeder'  # default nick if it can't be deduced

    if text[0] != prefix:
        return

    command = text[1:].split(' ')[0]

    if channel in channels or (len(channel) >= 1 and channel[0] == '\\'):
        response_topic = f'{topic_prefix}to/irc/{channel}/notice'

        if command == 'stof':
            try:
                address = text[text.find(' ') + 1:].strip()
                g = geocoder.osm(address)

                if g == None:
                    client.publish(response_topic, f'Cannot resolve that address')
                    return

                print(g.osm)

                lat = g.osm['y']
                lng = g.osm['x']

                place = ''

                if 'addr:city' in g.osm:
                    place += ' ' + g.osm['addr:city']
                if 'addr:state' in g.osm:
                    place += ' ' + g.osm['addr:state']
                if 'addr:country' in g.osm:
                    place += ' ' + g.osm['addr:country']

                place = place.strip()

                headers = { 'User-Agent': 'Kiki' }
                r = requests.get(f'http://stofradar.nl:9000/air/{lat}/{lng}', timeout=2, headers=headers)

                try:
                    j = json.loads(r.content.decode('ascii'))

                    prev_j = j

                except Exception as e:
                    j = prev_j

                if j != None and 'pm2.5' in j:
                    client.publish(response_topic, f'pm2.5 in {place}: {j["pm2.5"]} µg/m³')

                else:
                    client.publish(response_topic, f'{place} may not be in the data-set of stofradar.nl')

            except Exception as e:
                client.publish(response_topic, f'Exception during "stof": {e}, line number: {e.__traceback__.tb_lineno}')

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
