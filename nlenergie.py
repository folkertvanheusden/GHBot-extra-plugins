#! /usr/bin/python3

# by FvH, released under Apache License v2.0

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'

import datetime
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

bar = chr(9601) + chr(9602) + chr(9603) + chr(9604) + chr(9605) + chr(9606) + chr(9607) + chr(9608)
barcount = len(bar)

prev_j = None
prev_j2 = None

data_gen = []
data_price = []

def collect_thread():
    while True:
        try:
            headers = { 'User-Agent': 'Kiki' }
            r = requests.get('http://stofradar.nl:9001/electricity/generation', timeout=2, headers=headers)
            r2 = requests.get('http://stofradar.nl:9001/electricity/price', timeout=2, headers=headers)

            j = json.loads(r.content.decode('ascii'))
            data_gen.append(j)

            j2 = json.loads(r2.content.decode('ascii'))
            price = j2['current']['price']
            data_price.append(price)

            while len(data_gen) > 288:
                del data_gen[0]
                del data_price[0]

            time.sleep(300)

        except:
            print(f'Exception during "nlenergie": {e}, line number: {e.__traceback__.tb_lineno}')
            # gives skew
            time.sleep(5)

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=nlenergie|descr=Stroomgebruik in Nederland op dit moment')

def name_to_color(name):
    if name == 'solar':
        return 8

    elif name == 'wind':
        return 12

    elif name == 'nuclear':
        return 9

    elif name == 'waste':
        return 15

    elif name == 'other':
        return 6

    elif name == 'fossil':
        return 5

    return (abs(hash(name) * 9) % 13) + 2

def on_message(client, userdata, message):
    global prefix
    global prev_j
    global prev_j2

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

        if command == 'nlenergie':
            try:
                parts = text.split()

                verbose = '-v' in parts
                very_very_verbose = '-vvv' in parts
                very_verbose = ('-vv' in parts) or very_very_verbose

                headers = { 'User-Agent': 'Kiki' }

                r = requests.get('http://stofradar.nl:9001/electricity/generation', timeout=2, headers=headers)

                r2 = requests.get('http://stofradar.nl:9001/electricity/price', timeout=2, headers=headers)

                try:
                    j = json.loads(r.content.decode('ascii'))
                    j2 = json.loads(r2.content.decode('ascii'))

                    t = j['time']

                    prev_j = j
                    prev_j2 = j2

                except Exception as e:
                    j = prev_j
                    j2 = prev_j2

                    t = j['time']

                price = j2['current']['price']

                total = j['total']

                out = ''
                outblocks = ''
                outblocks_l = ''

                for source in j['mix']:
                    if out != '':
                        out += ', '
                        outblocks_l += ', '

                    perc = source['power'] * 100.0 / j['total']
                    not_perc = source['power'] * 40.0 / j['total']

                    color_index = name_to_color(source['id'])

                    out += f"\3{color_index}{source['id']}: {source['power']} MW ({perc:.2f}%"

                    if very_verbose:
                        out += f", {source['power'] * price:.2f}€/h"

                    out += ')'

                    outblocks += f'\3{color_index}'
                    outblocks += '\u2588' * math.ceil(not_perc)

                    outblocks_l += f"\3{color_index}\u2588 {source['id']}"

                ts = netherlands_tz.localize(datetime.datetime.fromtimestamp(t))

                out += f' ({ts})'

                sparkline = ''
                print(data_gen, data_price)
                if very_very_verbose and len(data_gen) >= 2:
                    values = []
                    colors = []

                    n_items = len(data_gen)
                    for i in range(max(0, n_items - 20), n_items):
                        best_value  = -1
                        best_name  = None
                        for source in data_gen[i]['mix']:
                            value = source['power'] * data_price[i]
                            if value > best_value:
                                best_value = value
                                best_name = source['id']

                        values.append(best_value)
                        colors.append(name_to_color(best_name))

                    highest_value = max(values)
                    lowest_value = min(values)
                    print(values, lowest_value, highest_value)

                    extent = highest_value - lowest_value

                    if extent != 0:
                        sparkline = ' '
                        for i in range(len(values)):
                            sparkline += f'\3{colors[i]}'
                            sparkline += bar[min([barcount - 1, int((values[i] - lowest_value) / extent * barcount)])]
                        sparkline += '\3'

                if verbose:
                    client.publish(response_topic, outblocks + f' ({ts} / {outblocks_l})' + sparkline)

                else:
                    client.publish(response_topic, out + sparkline)

            except Exception as e:
                client.publish(response_topic, f'Exception during "nlenergie": {e}, line number: {e.__traceback__.tb_lineno}')

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

t = threading.Thread(target=collect_thread)
t.start()

t2 = threading.Thread(target=announce_thread, args=(client,))
t2.start()

client.loop_forever()
