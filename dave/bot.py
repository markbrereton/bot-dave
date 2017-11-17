#!/usr/bin/env python

from datetime import datetime
from os import environ
from time import sleep

from dave.log import logger
from dave.meetup import MeetupGroup
from dave.slack import Slack
from dave.store import Store
from dave.trello_boards import TrelloBoard

sleep_time = int(environ.get('CHECK_TIME', '600'))


class Bot(object):
    def __init__(self):
        meetup_key = environ.get('MEETUP_API_KEY')
        group_id = environ.get('MEETUP_GROUP_ID')
        slack_token = environ["SLACK_API_TOKEN"]
        trello_key = environ["TRELLO_API_KEY"]
        trello_token = environ["TRELLO_TOKEN"]
        bot_id = environ.get("BOT_ID")
        bot_channel_id = environ.get("BOT_CHANNEL_ID")
        self.team_name = environ["TRELLO_TEAM"]
        self.storg = MeetupGroup(meetup_key, group_id)
        self.chat = Slack(slack_token, bot_id, bot_channel_id)
        self.trello = TrelloBoard(api_key=trello_key, token=trello_token)
        self.ds = Store()
        if self.storg.upcoming_events:
            current_event_ids = [e["id"] for e in self.storg.upcoming_events]
            self.known_events = self.ds.retrieve_events(current_event_ids)
        else:
            self.known_events = {}

    @property
    def event_names(self):
        return [e["name"] for e in self.known_events.values()]

    def _handle_event(self, event):
        # Check for new event
        event_id = event["id"]
        if event_id not in self.known_events.keys():
            logger.info("New event found: {}".format(event["name"]))
            event_date = int(event["time"]) / 1000
            event_date = datetime.fromtimestamp(event_date).strftime('%A %B %d %H:%M')

            self.chat.new_event(event["name"], event_date, event["venue"]["name"], event["event_url"])
            self.trello.create_board(event["name"], team_name=self.team_name)
            self.known_events[event_id] = event
            self.known_events[event_id]["participants"] = []

    def _handle_rsvps(self, event):
        event_id = event["id"]
        event_name = event["name"]
        venue = event["venue"]["name"]
        channel_for_venue = {"STORG Clubhouse": "#storg-south", "STORG Northern Clubhouse": "#storg-north"}
        channel = channel_for_venue.get(venue)
        newcomers = []
        cancels = []

        for rsvp in self.storg.rsvps(event_id):
            member_name = rsvp["member"]["name"]
            member_id = rsvp["member"]["member_id"]
            known_participants = self.known_events[event_id]["participants"]
            self.trello.add_contact(member_name=member_name, member_id=member_id)

            if member_name not in known_participants and rsvp["response"] == "yes":
                newcomers.append(member_name)
                self.trello.add_rsvp(name=member_name, member_id=member_id, board_name=event_name)
            elif member_name in known_participants and rsvp["response"] == "no":
                self.trello.cancel_rsvp(member_id, board_name=event_name)
                cancels.append(member_name)

        if newcomers or cancels:
            spots_left = int(event["rsvp_limit"]) - int(event["yes_rsvp_count"]) if event["rsvp_limit"] else 'Unknown'

            if newcomers:
                logger.info("Newcomers found: {}".format(newcomers))
                self.chat.new_rsvp(', '.join(newcomers), "yes", event_name, spots_left, channel)
                self.known_events[event_id]["participants"] += newcomers
                logger.debug("Participant list: {}".format(self.known_events[event_id]["participants"]))

            if cancels:
                logger.info("Cancellations found: {}".format(cancels))
                self.chat.new_rsvp(', '.join(cancels), "no", event_name, spots_left, channel)
                self.known_events[event_id]["participants"] = [p for p in self.known_events[event_id]["participants"] if
                                                               p not in cancels]
                logger.debug("Participant list: {}".format(self.known_events[event_id]["participants"]))
        else:
            logger.info("No changes for {}".format(event_name))

    def check_events(self):
        logger.info("Checking for event updates")
        for event in self.storg.upcoming_events:
            self._handle_event(event)
            self._handle_rsvps(event)
        logger.info("Done checking")

    def save_events(self):
        logger.debug("Saving events")
        self.ds.store_events(self.known_events)

    def monitor_events(self, sleep_time=600):
        while True:
            self.check_events()
            self.save_events()
            sleep(sleep_time)

    def read_chat(self, tasks):
        self.chat.rtm(tasks)

    def respond(self, response, channel):
        self.chat.message(response, channel)

    @property
    def next_meetup(self):
        self.storg.upcoming_events.sort(key=lambda d: d["time"])
        next_id = self.storg.upcoming_events[0]["id"]
        return self.known_events[next_id]

    def tables(self, event_name):
        return self.trello.tables(event_name)

    def table(self, event_name, table_title):
        return self.trello.table(event_name, table_title)
