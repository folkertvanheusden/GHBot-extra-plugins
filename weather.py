#! /usr/bin/python3

import math
import paho.mqtt.client as mqtt
import requests
import threading
import time
import sys
import random
import xml.dom.minidom as xmd
from weathercfg import *

# weathercfg should contain:
#appid = '...'


mqtt_server  = 'localhost'   # TODO: hostname of MQTT server
mqtt_port    = 18830
topic_prefix = 'kiki-ng/'  # leave this as is
channels     = ['test', 'todo', 'knageroe']  # TODO: channels to respond to
prefix       = '!'

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=weather|descr=What is the weather at the given location?')

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

        if command == 'weather' and tokens[0][0] == prefix:
            try:
                query = text[text.find(' ') + 1:].strip()
                if query == '':
                    query = 'Groningen'

                r     = requests.get(f'https://api.openweathermap.org/data/2.5/weather?q={query}&mode=xml&lang=en&units=metric&appid={appid}')
                data  = r.content.decode('utf8')

                if data == '':
                    client.publish(response_topic, 'openweathermap returned nothing')
                    return

                dom = xmd.parseString(data)

                result           = dom.getElementsByTagName('current').item(0)

                temperature      = result.getElementsByTagName('temperature').item(0)
                temperatureValue = temperature.getAttribute('value')
                temperatureMin   = temperature.getAttribute('min')
                temperatureMax   = temperature.getAttribute('max')

                feels_like       = result.getElementsByTagName('feels_like').item(0)
                feels_likeValue  = temperature.getAttribute('value')

                wind             = result.getElementsByTagName("wind").item(0);
                windSpeed        = wind.getElementsByTagName("speed").item(0);
                windDirection    = wind.getElementsByTagName("direction").item(0);
                speed            = float(windSpeed.getAttribute("value"));
                beaufort         = math.pow(speed / .836, 2.0 / 3);

                windDescription = f"{beaufort:.1f} Beaufort, ({windSpeed.getAttribute('name')}), {windDirection.getAttribute('name')}"

                humidity         = result.getElementsByTagName("humidity").item(0);
                humidityValue    = humidity.getAttribute("value");
                humidityUnit     = humidity.getAttribute("unit");

                pressure         = result.getElementsByTagName("pressure").item(0);
                pressureValue    = pressure.getAttribute("value");
                pressureUnit     = pressure.getAttribute("unit");

                condition        = result.getElementsByTagName("weather").item(0);
                conditionValue   = condition.getAttribute("value");

                client.publish(response_topic, f'{query}: temperature={temperatureMin}/{temperatureValue}/{temperatureMax}℃  (feels like {feels_likeValue}℃), {windDescription}, humidity={humidityValue} {humidityUnit}, pressure={pressureValue} {pressureUnit}, condition={conditionValue}')

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
