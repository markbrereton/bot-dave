#!/usr/bin/env python

import json
from os import environ
from urllib import parse
from dave.log import logger

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

    def _run_sql(self, sql):
        with self.conn.cursor() as cursor:
            cursor.execute(sql)

    def store_event(self, event_id, data):
        logger.debug("Storing event {}".format(event_id))
        data = json.dumps(data)
        sql = "INSERT INTO events (event_id, data) VALUES ('{0}', $${1}$$) ON CONFLICT (event_id) DO UPDATE SET " \
              "data=$${1}$$;".format(event_id, data)
        self._run_sql(sql)

    def retrieve_event(self, event_id):
        logger.debug("Retrieving event {}".format(event_id))
        if not event_id:
            return {}
        sql = "SELECT data FROM events WHERE event_id='{}';".format(event_id)
        with self.conn.cursor() as cursor:
            cursor.execute(sql)
            resp = cursor.fetchone()
        return json.dumps(resp)

    def retrieve_events(self, event_ids):
        logger.debug("Retrieving events {}".format(event_ids))
        resp = {}
        if not event_ids:
            return resp
        event_ids = ["$${}$$".format(e) for e in event_ids]
        sql = "SELECT event_id, data FROM events WHERE event_id IN ({});".format(','.join(event_ids))
        with self.conn.cursor() as cursor:
            cursor.execute(sql)
            all_events = cursor.fetchall()
        for event_id, data in all_events:
            resp[event_id] = json.loads(data)
        return resp

    def store_events(self, events):
        logger.debug("Storing events {}".format(events))
        for event_id, data in events.items():
            self.store_event(event_id, data)

    def retrieve_all_events(self):
        logger.debug("Retrieving all events {}")
        resp = {}
        sql = "SELECT event_id, data FROM events;"

        with self.conn.cursor() as cursor:
            cursor.execute(sql)
            all_events = cursor.fetchall()

        for event_id, data in all_events:
            resp[event_id] = json.loads(data)
        return resp
