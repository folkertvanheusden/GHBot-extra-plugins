#! /usr/bin/python3

from bs4 import BeautifulSoup
import math
import paho.mqtt.client as mqtt
import threading
import time
import sys
import random
import requests


mqtt_server  = 'mqtt.vm.nurd.space'   # TODO: hostname of MQTT server
mqtt_port    = 1883
topic_prefix = 'GHBot/'  # leave this as is
prefix       = '!'
channels     = ['nurds', 'nurdbottest', 'nurdsbofh']

import logging
import os
import sys
from datetime import datetime
from datetime import timedelta

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", logging.INFO))

class OpenDataAPI:
    def __init__(self, api_token: str):
        self.base_url = "https://api.dataplatform.knmi.nl/open-data/v1"
        self.headers = {"Authorization": api_token}

    def __get_data(self, url, params=None):
        return requests.get(url, headers=self.headers, params=params).json()

    def list_files(self, dataset_name: str, dataset_version: str, params: dict):
        return self.__get_data(
            f"{self.base_url}/datasets/{dataset_name}/versions/{dataset_version}/files",
            params=params,
        )

    def get_file_url(self, dataset_name: str, dataset_version: str, file_name: str):
        return self.__get_data(
            f"{self.base_url}/datasets/{dataset_name}/versions/{dataset_version}/files/{file_name}/url"
        )


def download_file_from_temporary_download_url(download_url, filename):
    try:
        print(f'Download: {download_url}')
        with requests.get(download_url) as r:
            print(r.content)
            return r.content.decode('ascii')
    except Exception as e:
        logger.exception("Unable to download file using download URL" + e)

    return '?'

def do_get():
    api_key = "eyJvcmciOiI1ZTU1NGUxOTI3NGE5NjAwMDEyYTNlYjEiLCJpZCI6ImE1OGI5NGZmMDY5NDRhZDNhZjFkMDBmNDBmNTQyNjBkIiwiaCI6Im11cm11cjEyOCJ9"
    dataset_name = "waarschuwingen_nederland_48h"
    dataset_version = "1.0"
    logger.info(f"Fetching latest file of {dataset_name} version {dataset_version}")

    api = OpenDataAPI(api_token=api_key)

    # sort the files in descending order and only retrieve the first file
    params = {"maxKeys": 2, "orderBy": "created", "sorting": "desc"}
    response = api.list_files(dataset_name, dataset_version, params)
    print(response)
    if "error" in response:
        logger.error(f"Unable to retrieve list of files: {response['error']}")
        sys.exit(1)

    for f in response['files']:
        latest_file = f.get("filename")
        if latest_file[-4:] == '.txt':
            break

    logger.info(f"Latest file is: {latest_file}")

    # fetch the download url and download the file
    response = api.get_file_url(dataset_name, dataset_version, latest_file)
    return download_file_from_temporary_download_url(response["temporaryDownloadUrl"], latest_file)

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=weer-alert|descr=Wat is er met \'t weer?!')

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

        if command == 'weer-alert' and tokens[0][0] == prefix:
            try:
                content = do_get().replace('\n', ' ').replace('[IMPACT]', '').replace('[Meer details]', '').replace('  ', ' ')
                client.publish(response_topic, content)

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
client.connect(mqtt_server, port=mqtt_port, keepalive=4, bind_address='')

t = threading.Thread(target=announce_thread, args=(client,))
t.start()

client.loop_forever()
