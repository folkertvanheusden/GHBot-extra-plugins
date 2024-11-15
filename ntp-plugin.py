#! /usr/bin/python3

# apt install python3-ntp

import datetime
import math
import paho.mqtt.client as mqtt
import requests
import threading
import time
import sys

import ntp.control
import ntp.magic
import ntp.ntpc
import ntp.packet
import ntp.util

from configuration import *


def NTP_time_string_to_ctime(s):
    if s == None:
        return '?'

    dot = s.find('.')
    v1 = int(s[2:dot], 16)
    v2 = int(s[dot + 1:], 16)
    ts = v1 + v2 / 1000000000.

    UNIX_EPOCH = 2208988800
    ts -= UNIX_EPOCH

    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S.%f')

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, f'cmd=ntp|descr=State of {ntp_server}')

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

        if command == 'ntp' and tokens[0][0] == prefix:
            try:
                info = dict()
                info['poll_ts'] = time.time()

                session = ntp.packet.ControlSession()
                session.openhost(ntp_server)

                sysvars = session.readvar()
                info['sysvars'] = sysvars

                info['peers'] = dict()
                peers = session.readstat()
                for peer in peers:
                    peer_variables = session.readvar(peer.associd)
                    peer_variables['reftime'] = NTP_time_string_to_ctime(peer_variables['reftime'])
                    peer_variables['rec'] = NTP_time_string_to_ctime(peer_variables['rec'])
                    peer_variables['xmt'] = NTP_time_string_to_ctime(peer_variables['xmt'])
                    peer_variables['reach'] = f"{int(peer_variables['reach']):o} (octal)"
                    info['peers'][peer.associd] = peer_variables

                # replace peer id by host or address
                if 'peer' in info['sysvars']:
                    peer_assoc = info['sysvars']['peer']
                    if peer_assoc in info['peers']:
                        info['sysvars']['assoc'] = peer_assoc
                        info['sysvars']['peer'] = info['peers'][peer_assoc]['srchost'] if 'srchost' in info['peers'][peer_assoc] else None
                        if info['sysvars']['peer'] == None:
                            info['sysvars']['peer'] = info['peers'][peer_assoc]['srcadr']
                else:
                    info['sysvars']['assoc'] = None

                # replace clocks by human readable
                info['sysvars']['reftime'] = NTP_time_string_to_ctime(info['sysvars']['reftime'])
                info['sysvars']['clock'] = NTP_time_string_to_ctime(info['sysvars']['clock'])

                out = f'Offset: {sysvars["offset"]}, clock jitter: {sysvars["clk_jitter"]}, syncing to: {info["sysvars"]["peer"]}, precision: {info["sysvars"]["precision"]}, clock: {info["sysvars"]["clock"]}, clock wander: {sysvars["clk_wander"]}, stratum: {info["sysvars"]["stratum"]}'

                print(info['sysvars'])

                client.publish(response_topic, out)

                del session

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
