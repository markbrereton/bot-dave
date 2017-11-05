#!/usr/bin/env python

import requests

from dave.log import logger


class MeetupGroup(object):
    def __init__(self, api_key, group_id):
        self.api_url = "http://api.meetup.com"
        self.api_key = api_key
        self.group_id = group_id

    @property
    def events(self):
        params = {"key": self.api_key, "group_id": self.group_id, "status": "upcoming"}
        return self._get("/2/events", params)

    def rsvps(self, event_id):
        params = {"event_id": event_id, "key": self.api_key}
        return self._get("/2/rsvps", params)

    def _get(self, path, params):
        url = self.api_url + path
        req = requests.get(url, params)
        try:
            return req.json()["results"]
        except Exception:
            logger.debug("GET {} failed".format(self.api_url + path))
            return []
