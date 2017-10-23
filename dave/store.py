#!/usr/bin/env python

import json
from os import environ
from urllib import parse

import psycopg2


class Store(object):
    def __init__(self):
        parse.uses_netloc.append("postgres")
        url = parse.urlparse(environ["DATABASE_URL"])
        self.conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
        self.cur = self.conn.cursor()

    def store_event(self, event_id, data):
        data = json.dumps(data)
        sql = "INSERT INTO events (event_id, data) VALUES ('{0}', $${1}$$) ON CONFLICT (event_id) DO UPDATE SET " \
              "data=$${1}$$;".format(event_id, data)
        self.cur.execute(sql)
        self.conn.commit()

    def retrieve_event(self, event_id):
        sql = "SELECT data FROM events WHERE event_id='{}';".format(event_id)
        self.cur.execute(sql)
        resp = self.cur.fetchone()
        return json.dumps(resp)

    def retrieve_many_events(self, event_ids):
        resp = {}
        event_ids = ["$${}$$".format(e) for e in event_ids]
        sql = "SELECT event_id, data FROM events WHERE event_id IN ({});".format(','.join(event_ids))
        self.cur.execute(sql)
        all = self.cur.fetchall()
        for event_id, data in all:
            resp[event_id] = json.loads(data)
        return resp

    def store_many_events(self, events):
        for event_id, data in events.items():
            self.store_event(event_id, data)

    def retrieve_all_events(self):
        resp = {}
        sql = "SELECT event_id, data FROM events;"
        self.cur.execute(sql)
        all = self.cur.fetchall()
        self.conn.commit()
        for event_id, data in all:
            resp[event_id] = json.loads(data)
        return resp
