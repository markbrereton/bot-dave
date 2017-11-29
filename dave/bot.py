#!/usr/bin/env python

import json
import random

from datetime import datetime
from os import environ
from time import sleep
from fuzzywuzzy import process

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
        lab_channel_id = environ.get("LAB_CHANNEL_ΙD")
        self.team_name = environ["TRELLO_TEAM"]
        self.storg = MeetupGroup(meetup_key, group_id)
        self.chat = Slack(slack_token, bot_id)
        self.trello = TrelloBoard(api_key=trello_key, token=trello_token)
        self.ds = Store()
        if self.storg.upcoming_events:
            current_event_ids = [e["id"] for e in self.storg.upcoming_events]
            self.known_events = self.ds.retrieve_events(current_event_ids)
        else:
            self.known_events = {}
        logger.debug("Known events: {}".format(self.known_events))
        with open("dave/resources/phrases.json", "r") as phrases:
            self.phrases = json.loads(phrases.read())
        self.chat.message("Bot starting up!", lab_channel_id)

    @property
    def event_names(self):
        return [e["name"] for e in self.known_events.values()]

    # @property
    # def known_events(self):
    #     if self.storg.upcoming_events:
    #         current_event_ids = [e["id"] for e in self.storg.upcoming_events]
    #         known_events = self.ds.retrieve_events(current_event_ids)
    #     else:
    #         known_events = {}
    #     return known_events

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

    def _check_for_greeting(self, sentence):
        """If any of the words in the user's input was a greeting, return a greeting response"""
        greeting_keywords = self.phrases["requests"]["greetings"]
        greeting_responses = self.phrases["responses"]["greetings"]
        word = sentence.split(' ')[0]
        if word.lower().rstrip('!') in greeting_keywords:
            return random.choice(greeting_responses)

    @staticmethod
    def _natural_join(lst, separator=None):
        if not separator:
            separator = '\n'
        resp = ',{}'.format(separator).join(lst)
        resp = ' and'.join(resp.rsplit(',', 1))
        return resp

    def _next_event_info(self):
        next_event = self.next_event
        if next_event:
            participants = next_event["participants"]
            event_time = next_event["time"] / 1000
            date = datetime.fromtimestamp(event_time).strftime('%A %B %d at %H:%M')
            name = next_event["name"]
            msg = "Our next event is *{}*, on *{}* and " \
                  "there are *{}* people joining:\n{}".format(name, date, len(participants),
                                                              self._natural_join(participants))
        else:
            msg = "I can't find any event :disappointed:"
        return msg

    def _all_events_info(self):
        msgs = ["Here are our next events.\n"]
        for event in self.known_events.values():
            participants = event["participants"]
            event_time = event["time"] / 1000
            date = datetime.fromtimestamp(event_time).strftime('%A %B %d at %H:%M')
            name = event["name"]
            msg = "*{}*,\non *{}* with *{}* " \
                  "people joining:\n{}".format(name, date, len(participants), self._natural_join(participants))
            msgs.append(msg)
        return '\n\n'.join(msgs)

    def _tables_info(self, channel, request=None):
        logger.debug("Got {} and {}".format(channel, request))
        if not request and channel:
            request = ' '.join(channel.split("_"))

        logger.debug("Request {}".format(request))
        logger.debug("Channel {}".format(channel))
        logger.debug("Requested {}".format(request))
        events = self.event_names
        logger.debug("Events {}".format(events))
        event_name = process.extractOne(request, events)[0]
        logger.debug("Chosen {}".format(event_name))
        msgs = ["Available tables for "]
        msgs[0] += "*{}*".format(event_name)
        table_info = self.tables(event_name)

        for table, details in table_info.items():
            info = details["info"].replace('\n', '\n>')
            msgs.append("*{}*\n>{}\nJoining: *{}*".format(table.upper(), info, ', '.join(details["members"])))

        return '\n\n'.join(msgs)

    def _user_info(self, user_id):
        info = self.user_info(user_id)
        if info:
            msg = "You are {} with id {} and slack username <@{}>".format(info["name"], info["id"], user_id)
        else:
            msg = "I don't know :disappointed:"
        return msg

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
    def next_event(self):
        if not self.storg.upcoming_events:
            return None
        self.storg.upcoming_events.sort(key=lambda d: d["time"])
        next_id = self.storg.upcoming_events[0]["id"]
        return self.known_events[next_id]

    def tables(self, event_name):
        return self.trello.tables(event_name)

    def table(self, event_name, table_title):
        return self.trello.table(event_name, table_title)

    def user_info(self, slack_user_id):
        slack_name = self.chat.user_info(slack_user_id)["name"]
        return self.trello.contact_by_slack_name(slack_name)

    def conversation(self, task_queue):
        unknown_responses = self.phrases["responses"]["unknown"]
        while True:
            command, channel_id, user_id = task_queue.get()
            if command.startswith("help"):
                response = "Hold on tight! I'm coming."
            elif "table status" in command.lower():
                response = self._tables_info(channel=self.chat.channel_name(channel_id),
                                             request=command.split('table status')[-1])
            elif "next event" in command.lower() and "events" not in command.lower():
                response = self._next_event_info()
            elif "events" in command.lower():
                response = self._all_events_info()
            elif "thanks" in command.lower() or "thank you" in command.lower():
                response = "Anytime :relaxed:"
            elif command.lower().startswith("who am i"):
                response = self._user_info(user_id)
            elif command.lower().startswith("what can you do?"):
                response = self.phrases["responses"]["help"]
            elif "admin info" in command.lower():
                response = self.phrases["responses"]["admin_info"]
            else:
                response = self._check_for_greeting(command) if self._check_for_greeting(command) else random.choice(
                    unknown_responses)
            self.respond(response, channel_id)
