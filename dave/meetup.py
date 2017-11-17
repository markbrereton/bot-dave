#!/usr/bin/env python

import requests

from dave.log import logger


class MeetupGroup(object):
    def __init__(self, api_key, group_id):
        """ Creates a Meetup Group object
        :param api_key: (str) The API key for your Meetup account
        :param group_id: (int) The group_id of the Meetup Group. Get it at GET /2/groups
        """
        self.api_url = "http://api.meetup.com"
        self.api_key = api_key
        self.group_id = group_id

    @property
    def upcoming_events(self):
        """Gets all upcoming events for the MeetupGroup
        https://secure.meetup.com/meetup_api/console/?path=/2/events

        :return: (list) A list of dicts, one dict per event
        """
        params = {"key": self.api_key, "group_id": self.group_id, "status": "upcoming"}
        return self._get("/2/events", params)

    def rsvps(self, event_id):
        """Get's all RSVPs for a specific event
        https://secure.meetup.com/meetup_api/console/?path=/2/rsvps

        :param event_id: (str) The id of the event you're querying
        :return: (list) A list of dicts, one dict per RSVP
        """
        params = {"event_id": event_id, "key": self.api_key}
        return self._get("/2/rsvps", params)

    def _get(self, path, params):
        """ Do a GET towards the Meetup API
        :param path: (str) The path to GET
        :param params: (dict) Extra parameters to pass to the request
        :return: (list) The "response" list contained in the Meetup API response
        """
        url = self.api_url + path
        req = requests.get(url, params)
        try:
            return req.json()["results"]
        except Exception:
            logger.debug("GET {} failed".format(self.api_url + path))
            return []
