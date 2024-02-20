#! /usr/bin/python3

# This was written by Folkert van Heusden in 2024.
# Licensen under the MIT license.

# pip3 install python-chess
# sudo apt install stockfish

import chess
import chess.engine
import paho.mqtt.client as mqtt
import threading
import time
import sys
import random


mqtt_server  = 'mqtt.vm.nurd.space'   # TODO: hostname of MQTT server
mqtt_port    = 1883
topic_prefix = 'GHBot/'  # leave this as is
channels     = ['nurds', 'nurdbottest']  # TODO: channels to respond to
prefix       = '!'
use_lichess  = True

b = chess.Board()

engine = chess.engine.SimpleEngine.popen_uci('/usr/games/stockfish')

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=chess|descr=Play the game of chess.')

def gen_lichess(b):
    fen = b.fen().replace(' ', '_')

    return 'https://lichess.org/editor/' + fen

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

        if command == 'chess' and tokens[0][0] == prefix:
            try:
                if len(tokens) == 2:
                    try:
                        m = tokens[1].replace('-', '')
                        b.push(chess.Move.from_uci(m))

                        if b.is_checkmate():
                            client.publish(response_topic, 'You won! Gratuliere!')
                            b = chess.Board()

                        elif b.is_game_over():
                            client.publish(response_topic, 'Game is over, not sure why :-)')
                            b = chess.Board()

                        else:
                            try:
                                result = engine.play(b, chess.engine.Limit(time=1.))
                                b.push(result.move)
                                client.publish(response_topic, f'I move: {result.move.uci()}')
                                if use_lichess:
                                    client.publish(response_topic, f'New position: {gen_lichess(b)}')
                                else:
                                    client.publish(response_topic, f'New position: {b.fen()}')
                            except Exception as e:
                                client.publish(response_topic, f'* confused *')

                    except Exception as e:
                        moves = [m.uci() for m in b.legal_moves]
                        client.publish(response_topic, f'Try one of: {" ".join(moves)}')

                elif len(tokens) == 1:
                    if use_lichess:
                        client.publish(response_topic, f'New position: {gen_lichess(b)}')
                    else:
                        client.publish(response_topic, f'Current position: {b.fen()}')

                    if b.is_check():
                        client.publish(response_topic, f'Check!')

                else:
                    client.publish(response_topic, f'Hmmm? Either no parameters to see the current position or a move in san or long notation.')

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
