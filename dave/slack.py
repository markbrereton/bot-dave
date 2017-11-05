#!/usr/bin/env python

from slackclient import SlackClient
import json


class Slack(object):
    def __init__(self, slack_token):
        self.sc = SlackClient(slack_token)

    def _announcement(self, attachment, channel="#small_council"):
        self.sc.api_call(
            "chat.postMessage",
            as_user=True,
            channel=channel,
            attachments=attachment
        )

    def new_event(self, name, date, venue, url, channel="#announcements"):
        attachment = [{
            "pretext": "Woohoo! We've got a new event coming up!",
            "color": "#36a64f",
            "title": name,
            "title_link": url,
            "text": "{}\n{}".format(date, venue)
        }]
        self._announcement(attachment, channel=channel)

    def new_rsvp(self, names, response, event, spots, channel="#dungeon_lab"):
        attachment = [{
            "pretext": "New RSVP",
            "color": "#36a64f",
            "text": "{} replied {} for the {}\n{} spots left".format(names, response, event, spots)
        }]
        self._announcement(attachment, channel=channel)

    def members_of_channel(self, channel_id):
        info = self.sc.api_call(
            "conversations.members",
            channel=channel_id
        )
        info = json.loads(info)
        if info['ok']:
            return info['members']
