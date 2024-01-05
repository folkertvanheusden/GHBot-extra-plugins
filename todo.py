#! /usr/bin/python3

# by FvH, released under Apache License v2.0

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'

import os
import paho.mqtt.client as mqtt
import random
import sqlite3
import threading
import time
import socket
import sys

mqtt_server  = 'localhost'
mqtt_port    = 18830
topic_prefix = 'kiki-ng/'
channels     = ['test', 'knageroe', 'todo']
db_file      = 'todo.db'
prefix       = '!'
smtp_server  = '172.29.0.11'
smtp_from    = 'ghbot@vanheusden.com'

con = sqlite3.connect(db_file)

cur = con.cursor()
try:
    cur.execute('CREATE TABLE todo(nr INTEGER PRIMARY KEY, channel TEXT NOT NULL, added_by TEXT NOT NULL, value TEXT NOT NULL)')
    cur.execute('CREATE INDEX learn_key ON learn(key)')
    cur.execute('CREATE TABLE tags(nr INTEGER NOT NULL, tagname VARCHAR(255) NOT NULL)')
    cur.execute('create unique index tags_index on tags(nr, tagname)')
except sqlite3.OperationalError as oe:
    # should be "table already exists"
    pass
cur.close()

cur = con.cursor()
cur.execute('PRAGMA journal_mode=wal')
cur.execute('PRAGMA encoding="UTF-8"')
cur.close()

con.commit()

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=addtodo|descr=add an item (or multiple, seperated by /) to your todo-list')
    client.publish(target_topic, 'cmd=settag|descr=sets a tag on an existing todo-item (settag tag nr nr nr nr...)')
    client.publish(target_topic, 'cmd=untag|descr=removes a tag from an existing todo-item (untag tag nr nr nr...)')
    client.publish(target_topic, 'cmd=deltodo|descr=delete one or more items from your todo-list (seperated by space)')
    client.publish(target_topic, 'cmd=ignoretodo|descr=ignore one or more items from your todo-list (seperated by space)')
    client.publish(target_topic, "cmd=todo|descr=get a list of your todos")
    client.publish(target_topic, "cmd=sendtodo|descr=get a list of your todos via e-mail")
    client.publish(target_topic, "cmd=todotags|descr=get a list of your tags")
    client.publish(target_topic, "cmd=randomtodo|descr=list randomly one of your todos")
    client.publish(target_topic, "cmd=setdefaulttodo|descr=set default list of todos")
    client.publish(target_topic, "cmd=usedefaulttodo|descr=use default list of todos")
    client.publish(target_topic, "cmd=getdefaulttodo|descr=show default list of todos")
    client.publish(target_topic, "cmd=cleardefaulttodo|descr=clear the default list of todos")

def ignore_unlink(file):
    try:
        os.unlink(file)
    except Exception as e:
        print(e)

def send_pdf(con, nick, email):
    pdf_file = f'/tmp/test{random.random()}.pdf'  # TODO generate random

    print(f'using temporary file {pdf_file}')

    try:
        cur = con.cursor()
        cur.execute('SELECT value, nr FROM todo WHERE added_by=? AND finished_when is NULL AND deleted_when is NULL ORDER BY nr ASC', (nick,))
        rows_items = cur.fetchall()

        dict_tags = dict()
        for row in rows_items:
            cur.execute('SELECT tagname FROM tags WHERE nr=?', (row[1],))
            row_tag = cur.fetchone()
            if row_tag != None:
                dict_tags[row[1]] = row_tag[0]

        cur.close()

        import cairo

        paper_width = 210
        paper_height = 297
        margin = 20

        heading_height1 = 25

        text_x = margin * 1.7
        max_x = paper_width - margin * 1.7 * 2
        initial_text_y = margin + heading_height1

        item_height = 4
        pdf = cairo.PDFSurface(pdf_file, paper_width, paper_height)
        max_n_items = int((paper_height - margin * 2 - initial_text_y - item_height) / item_height)
        cur_n_items = 0

        new_page_required = True

        # items
        for row in rows_items:
            if new_page_required == True:
                new_page_required = False

                text_y = initial_text_y

                # background rectangle
                ctx = cairo.Context(pdf)
                pat = cairo.LinearGradient(0.0, 0.0, 0.0, 1.0)
                pat.add_color_stop_rgba(0, 0.4, 0.4, 0.6, 0.5)  # First stop, 50% opacity
                pat.add_color_stop_rgba(1, 0.6, 0.6, 1.0, 1)  # Last stop, 100% opacity
                ctx.rectangle(margin, margin, paper_width - margin * 2, paper_height - margin * 2)
                ctx.set_source(pat)
                ctx.fill()
                ctx.stroke()

                # heading
                ctx = cairo.Context(pdf)
                ctx.set_source_rgb(0.1, 0.1, 0.1)
                use_heading_height1 = heading_height1
                ctx.select_font_face('Arial', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL) 
                while True:
                    ctx.set_font_size(use_heading_height1)
                    text = 'Todo for: ' + nick
                    xbearing, ybearing, width, height, dx, dy = ctx.text_extents(text)
                    if width < max_x:
                        break
                    use_heading_height1 *= 0.75
                ctx.move_to(margin + item_height, margin + heading_height1)
                ctx.show_text(text)
                ctx.stroke()

                # rectangle around text
                ctx = cairo.Context(pdf)
                ctx.set_source_rgb(0.1, 0.1, 0.1)
                ctx.rectangle(margin * 1.5, text_y + margin / 2, paper_width - margin * 3, paper_height - margin * 2 - text_y)
                ctx.stroke()

                text_y += margin

            item = row[0].strip()
            tag = dict_tags[row[1]].strip() if row[1] in dict_tags else None

            ctx = cairo.Context(pdf)
            ctx.set_source_rgb(0.1, 0.1, 0.1)
            ctx.set_font_size(item_height)
            ctx.select_font_face('Courier', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL) 
            ctx.move_to(text_x, text_y)
            text = str(row[1]) + ') ' + item
            if tag:
                text += ' (' + tag + ')'
            xbearing, ybearing, width, height, dx, dy = ctx.text_extents(text)
            if width > max_x:
                l = len(text)
                per_char = width / l
                h_fits = int(max_x / per_char) // 2
                text = text[0:h_fits - 2] + '...' + text[l - h_fits + 1:]
            ctx.show_text(text)
            ctx.stroke()

            text_y += item_height

            cur_n_items += 1
            if cur_n_items >= max_n_items:
                new_page_required = True
                cur_n_items = 0

                ctx.copy_page()

                #Q clear page
                ctx = cairo.Context(pdf)
                pat = cairo.LinearGradient(0.0, 0.0, 0.0, 1.0)
                pat.add_color_stop_rgba(0, 1.0, 1.0, 1.0, 1.0)
                ctx.rectangle(0, 0, paper_width, paper_height)
                ctx.set_source(pat)
                ctx.fill()
                ctx.stroke()

        pdf.show_page()

        pdf.finish()

        import smtplib
        server = smtplib.SMTP(smtp_server, 25)

        from email.mime.application import MIMEApplication
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        #import email.utils

        message = f'Here is your TODO from GHBot!'

        msg = MIMEMultipart()
        msg['Subject'] = 'Todo PDF'
        msg['From'] = smtp_from
        msg['To'] = email
        #msg['Date'] = email.utils.formatdate()
        #at = smtp_from.find('@')
        #d = smtp_from[at+1:]
        #msg['Message-ID'] = email.utils.make_msgid(domain=d)
        msg.attach(MIMEText(message, 'plain'))
        with open(pdf_file, 'rb') as f:
            attach = MIMEApplication(f.read(), _subtype='pdf')
            attach.add_header('Content-Disposition', 'attachment', filename='ToDo.pdf')
            msg.attach(attach)
        server.send_message(msg)

        server.close()

    except Exception as e:
        ignore_unlink(pdf_file)
        return f'Exception: {e}, line number: {e.__traceback__.tb_lineno}'

    ignore_unlink(pdf_file)

    return 'PDF sent!'

def get_preferences(nick):
    if '!' in nick:
        nick = nick[0:nick.find('!')]

    prefs = dict()

    cur = con.cursor()
    cur.execute('SELECT key, value FROM preferences WHERE nick=?', (nick.lower(),))
    for row in cur.fetchall():
        prefs[row[0]] = row[1]
    cur.close()

    print(nick, prefs)

    return prefs

def check_preferences_bool(prefs, key, default):
    if key in prefs:
        return prefs[key] == '1'

    return default

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

    parts   = topic.split('/')
    channel = parts[2] if len(parts) >= 3 else 'knageroe'
    nick    = parts[3] if len(parts) >= 4 else 'jemoeder'

    prefs = get_preferences(nick)

    if channel in channels or (len(channel) >= 1 and channel[0] == '\\'):
        response_topic = f'{topic_prefix}to/irc/{channel}/notice'

        if '!' in nick:
            nick = nick.split('!')[0]

        tokens  = text.split(' ')

        command = tokens[0][1:]

        if command == 'addtodo' and tokens[0][0] == prefix:
            if len(tokens) >= 2:
                todo_item = text[text.find(' ') + 1:]

                tag = None
                pipe_char = todo_item.find('|')
                if pipe_char != -1:
                    tag = todo_item[0:pipe_char].lower()
                    todo_item = todo_item[pipe_char+1:]

                cur = con.cursor()

                for item in todo_item.split('/'):
                    try:
                        cur.execute("INSERT INTO todo(channel, added_by, value, added_when) VALUES(?, ?, ?, strftime('%Y-%m-%d %H:%M:%S', 'now'))", (channel, nick, item.strip()))
                        nr = cur.lastrowid
                        client.publish(response_topic, f'Todo item "{item}" stored under number {nr}')

                        if tag != None:
                            cur.execute('INSERT INTO tags(nr, tagname) VALUES(?, ?)', (nr, tag.strip()))

                        con.commit()

                    except Exception as e:
                        client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

                cur.close()

            else:
                client.publish(response_topic, 'Todo item missing')
 
        elif command == 'settag' and tokens[0][0] == prefix:
            cur = con.cursor()

            tag = tokens[1].lower()

            n = 0

            for item in tokens[2:]:
                try:
                    cur.execute('INSERT INTO tags(nr, tagname) VALUES(?, ?)', (item, tag.strip()))

                    n += cur.rowcount

                except Exception as e:
                    pass

            con.commit()
            cur.close()

            client.publish(response_topic, f'Tag {tag} set on {n} item(s)')

        elif command == 'untag' and tokens[0][0] == prefix:
            cur = con.cursor()

            tag = tokens[1].lower()

            n = 0

            for item in tokens[2:]:
                try:
                    cur.execute('DELETE FROM tags WHERE nr=? and tagname=?', (item, tag))
                    n += cur.rowcount

                except Exception as e:
                    pass

            con.commit()
            cur.close()

            client.publish(response_topic, f'Tag {tag} removed from {n} item(s)')

        elif command == 'cleardefaulttodo' and tokens[0][0] == prefix:
            cur = con.cursor()

            try:
                cur.execute('SELECT value FROM dflt WHERE channel=? AND added_by=?', (channel, nick))
                row = cur.fetchone()

                cur.execute('DELETE FROM dflt WHERE channel=? AND added_by=?', (channel, nick))
                con.commit()

                if row == None:
                    client.publish(response_topic, f'Default todo cleared')
                else:
                    client.publish(response_topic, f'Default todo ({row[0]}) cleared')

            except Exception as e:
                client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

            cur.close()

        elif command == 'setdefaulttodo' and tokens[0][0] == prefix:
            # sqlite> create table dflt(channel TEXT NOT NULL, added_by TEXT NOT NULL, value TEXT NOT NULL);
            if len(tokens) >= 2:
                todo_item = text[text.find(' ') + 1:]

                cur = con.cursor()

                try:
                    cur.execute('DELETE FROM dflt WHERE channel=? AND added_by=?', (channel, nick))
                    cur.execute('INSERT INTO dflt(channel, added_by, value) VALUES(?, ?, ?)', (channel, nick, todo_item))
                    client.publish(response_topic, f'Default todo items set')

                    con.commit()

                except Exception as e:
                    client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

                cur.close()

            else:
                client.publish(response_topic, 'Todo item(s) missing')

        elif command == 'getdefaulttodo' and tokens[0][0] == prefix:
            cur = con.cursor()

            try:
                cur.execute('SELECT value FROM dflt WHERE channel=? AND added_by=?', (channel, nick))
                row = cur.fetchone()

                if row == None:
                    client.publish(response_topic, f'No default todo items set')

                else:
                    client.publish(response_topic, f'Default todo for {nick}: {row[0]}')

            except Exception as e:
                client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

            cur.close()

        elif command == 'usedefaulttodo' and tokens[0][0] == prefix:
            cur = con.cursor()

            try:
                cur.execute('SELECT value FROM dflt WHERE channel=? AND added_by=?', (channel, nick))
                row = cur.fetchone()

                if row == None:
                    client.publish(response_topic, f'No default todo items set')

                else:
                    n = 0
                    for todo_item in row[0].split('/'):
                        try:
                            tag = None
                            pipe_char = todo_item.find('|')
                            if pipe_char != -1:
                                tag = todo_item[0:pipe_char].lower()
                                item = todo_item[pipe_char+1:]
                            else:
                                item = todo_item

                            cur.execute("INSERT INTO todo(channel, added_by, value, added_when) VALUES(?, ?, ?, strftime('%Y-%m-%d %H:%M:%S', 'now'))", (channel, nick, item))

                            if tag != None:
                                nr = cur.lastrowid
                                cur.execute('INSERT INTO tags(nr, tagname) VALUES(?, ?)', (nr, tag.strip()))

                            n += 1

                        except Exception as e:
                            client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

                    client.publish(response_topic, f'Added {n} item(s)')

                con.commit()

            except Exception as e:
                client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

            cur.close()

        elif (command == 'deltodo' or command == 'ignoretodo') and tokens[0][0] == prefix:
            if len(tokens) >= 2:
                cur = con.cursor()

                action = 'ignored' if command == 'ignoretodo' else 'deleted'

                try:
                    for nr in tokens[1:]:
                        cur.execute("SELECT value, added_when, JULIANDAY(strftime('%Y-%m-%d %H:%M:%S', 'now')) - JULIANDAY(added_when) as took FROM todo WHERE nr=?", (nr,))
                        row = cur.fetchone()

                        took = row[2]
                        if took == None:
                            took = ''
                        elif took < 86400:
                            took = f' Took: {took * 86400:.2f} seconds'
                        else:
                            took = f' Took: {took:.2f} days'

                        if command == 'ignoretodo':
                            cur.execute("UPDATE todo SET deleted_when=strftime('%Y-%m-%d %H:%M:%S', 'now') WHERE nr=? AND added_by=?", (nr, nick))
                        else:
                            cur.execute("UPDATE todo SET finished_when=strftime('%Y-%m-%d %H:%M:%S', 'now') WHERE nr=? AND added_by=?", (nr, nick))

                        if cur.rowcount == 1:
                            if row != None:
                                client.publish(response_topic, f'Todo item {nr} {action} ({row[0]}){took}')

                            else:
                                client.publish(response_topic, f'Todo item {nr} {action}{took}')

                        else:
                            client.publish(response_topic, f'Todo item {nr} is either not yours or does not exist')

                except Exception as e:
                    client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

                cur.close()
                con.commit()

            else:
                client.publish(response_topic, 'Invalid number of parameters: parameter should be the todo-number')

        elif command == 'todotags' and tokens[0][0] == prefix:
            cur = con.cursor()

            try:
                cur.execute('SELECT DISTINCT tagname FROM todo, tags WHERE added_by=? AND todo.nr=tags.nr', (nick,))

                tags = []

                for row in cur.fetchall():
                    tags.append(row[0])

                tag_list = ', '.join(tags)

                if tag_list != None:
                    client.publish(response_topic, f'{nick}: {tag_list}')

                else:
                    client.publish(response_topic, f'{nick}: -nothing-')

            except Exception as e:
                client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

            cur.close()

        elif command == 'sendtodo' and tokens[0][0] == prefix:
            if len(tokens) != 2:
                client.publish(response_topic, 'Parameter should be your e-mail address')
            else:
                client.publish(response_topic, send_pdf(con, nick, tokens[1]))

        elif command == 'todo' and tokens[0][0] == prefix:
            cur = con.cursor()

            try:
                verbose = check_preferences_bool(prefs, 'todo-verbose', True)
                colors  = check_preferences_bool(prefs, 'todo-colors', False)
                word = tokens[0][0:-1]

                tag = None
                i = 1
                while i < len(tokens):
                    if tokens[i] != '-v':
                        tag = tokens[i].lower()
                        break
                    i += 1

                if tag == None:
                    cur.execute('SELECT value, nr FROM todo WHERE added_by=? AND finished_when is NULL AND deleted_when is NULL ORDER BY nr DESC', (nick,))
                else:
                    cur.execute('SELECT value, todo.nr FROM todo, tags WHERE added_by=? AND tags.tagname=? AND tags.nr=todo.nr AND finished_when is NULL AND deleted_when is NULL ORDER BY todo.nr DESC', (nick, tag))

                todo = None

                for row in cur.fetchall():
                    if verbose:
                        cur.execute('SELECT tagname FROM tags WHERE nr=?', (row[1],))
                        row2 = cur.fetchone()
                        if colors:
                            if row2 == None:
                                item = f'\3{0}{row[0]} \3{3}({row[1]})\3{0}'
                            else:
                                item = f'\3{0}{row[0]} \3{3}({row[1]} / {row2[0]})\3{0}'
                        else:
                            if row2 == None:
                                item = f'{row[0]} ({row[1]})'
                            else:
                                item = f'{row[0]} ({row[1]} / {row2[0]})'
                    else:
                        item = row[0]

                    if todo == None:
                        todo = item

                    else:
                        todo += ' / ' + item

                if todo != None:
                    client.publish(response_topic, f'{nick}: {todo}')

                else:
                    client.publish(response_topic, f'{nick}: -nothing-')

            except Exception as e:
                client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

            cur.close()

        elif command == 'randomtodo' and tokens[0][0] == prefix:
            cur = con.cursor()

            try:
                tag = None if len(tokens) == 1 else tokens[1]

                if tag == None:
                    cur.execute('SELECT value, nr FROM todo WHERE added_by=? AND finished_when is NULL AND deleted_when is NULL ORDER BY RANDOM() LIMIT 1', (nick.lower(),))
                else:
                    cur.execute('SELECT value, todo.nr FROM todo, tags WHERE added_by=? AND tags.tagname=? AND tags.nr=todo.nr AND finished_when is NULL AND deleted_when is NULL ORDER BY RANDOM() LIMIT 1', (nick.lower(), tag))
                row = cur.fetchone()

                item = f'{row[0]} ({row[1]})' if row else '-nothing-'

                client.publish(response_topic, f'{nick}: {item}')

            except Exception as e:
                client.publish(response_topic, f'Exception: {e}, line number: {e.__traceback__.tb_lineno}')

            cur.close()

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
