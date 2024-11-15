#! /usr/bin/python3

# sudo apt install python3-easysnmp

from easysnmp import Session
from ping3 import ping
import math
import paho.mqtt.client as mqtt
import requests
import threading
import time
import sys
import random


from configuration import *
snmp_com     = 'NURDs'
snmp_host    = 'gateway.lan.nurd.space'
snmp_version = 1


def WAN_stat(session):
    in_count = int(session.get('IF-MIB::ifInOctets.10').value)
    out_count = int(session.get('IF-MIB::ifOutOctets.10').value)

    return in_count, out_count


def get_n_DHCP():
    try:
        r = requests.get('https://dns.lan.nurd.space/hosts.txt', verify=False)
        dhcp = 0
        total = 0
        for line in r.content.decode('ascii').split('\n'):
            total += 1
            if line[0:9] == '10.208.2.' or line[0:9] == '10.208.3.':
                dhcp += 1
        return total, dhcp

    except Exception as e:
        print(f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

    return -1, 0


def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'
    client.publish(target_topic, 'cmd=netstat|descr=Network statistics')


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

        if command == 'netstat' and tokens[0][0] == prefix:
            try:
                session = Session(hostname=snmp_host, community=snmp_com, version=snmp_version)

                t_before = time.time()
                before = WAN_stat(session)

                latency = ping('178.238.96.89')

                while True:
                    after = WAN_stat(session)

                    t_after = time.time()
                    dt = t_after - t_before

                    kB_in = ((after[0] - before[0]) / dt + 1023) // 1024
                    kB_out = ((after[1] - before[1]) / dt + 1023) // 1024

                    if kB_in > 0 or kB_out > 0:
                        break

                    time.sleep(0.125)

                client.publish(response_topic, f'WAN in: {kB_in} kB/s, out: {kB_out} kB/s, DHCP entries: {get_n_DHCP()[1]}, glas latency: {latency * 1000:.2f} ms')

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
