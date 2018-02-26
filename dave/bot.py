#!/usr/bin/env python

import json
import random

from datetime import datetime, timezone, timedelta
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
        self.lab_channel_id = environ.get("LAB_CHANNEL_ID")
        self.team_name = environ["TRELLO_TEAM"]
        self.storg = MeetupGroup(meetup_key, group_id)
        self.chat = Slack(slack_token, bot_id)
        self.trello = TrelloBoard(api_key=trello_key, token=trello_token)
        self.ds = Store()
        with open("dave/resources/phrases.json", "r") as phrases:
            self._phrases = json.loads(phrases.read())
        if self.storg.upcoming_events:
            current_event_ids = [e["id"] for e in self.storg.upcoming_events]
            self.known_events = self.ds.retrieve_events(current_event_ids)
        else:
            self.known_events = {}

        logger.debug("Known events: {}".format(self.known_events))
        logger.debug("Env: {}".format(environ.items()))
        self.chat.message("Bot Dave reporting for duty!", environ.get("LAB_CHANNEL_ID"))

    @property
    def event_names(self):
        return [e["name"] for e in self.known_events.values()]

    def _handle_event(self, event):
        cet = timezone(timedelta(0, 3600), "CET")
        # Check for new event
        event_id = event["id"]
        if event_id not in self.known_events.keys():
            logger.info("New event found: {}".format(event["name"]))
            event_date = int(event["time"]) / 1000
            event_date = datetime.fromtimestamp(event_date, tz=cet).strftime('%A %B %d %H:%M')

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
            try:
                known_participants = self.known_events[event_id]["participants"]
            except KeyError:
                logger.error("No key {}".format(event_id))
                logger.error("Known events: {}".format(self.known_events))

            if member_name not in known_participants and rsvp["response"] == "yes":
                self.trello.add_rsvp(name=member_name, member_id=member_id, board_name=event_name)
                # self.trello.add_contact(member_name=member_name, member_id=member_id)
                newcomers.append(member_name)
                sleep(0.2)
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
        greeting_keywords = self._phrases["requests"]["greetings"]
        greeting_responses = self._phrases["responses"]["greetings"]
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

    def _tables_info(self, channel, request=None, detail=False, table_number=None):
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
        if table_number:
            msgs = ["Table {} for {}".format(table_number, event_name)]
        else:
            msgs = ["Available tables for "]
            msgs[0] += "*{}*".format(event_name)

        table_info = self.tables_detail(event_name)

        for table, details in table_info.items():
            if not table_number:
                blurb = details["blurb"].replace('\n', '\n>')
                players = details["players"].replace('\n', '\n>')
                if detail:
                    msgs.append("*{}*\n>{}{}\nJoining: *{}*".format(table.upper(), blurb, players, ', '.join(details["members"])))
                else:
                    msgs.append(
                        "*{}*\n{}\nJoining: *{}*".format(table.upper(), players, ', '.join(details["members"])))
            elif table_number and table.startswith(str(table_number)):
                blurb = details["blurb"].replace('\n', '\n>')
                players = details["players"].replace('\n', '\n>')
                msgs.append("*{}*\n>{}{}\nJoining: *{}*".format(table.upper(), blurb, players,
                                                                   ', '.join(details["members"])))

        return '\n\n'.join(msgs)

    def check_events(self):
        logger.info("Checking for event updates")
        self.storg.update_upcoming_events()
        for event in self.storg.upcoming_events:
            self._handle_event(event)
            self._handle_rsvps(event)
        logger.info("Done checking")

    def save_events(self):
        logger.debug("Saving events")
        self.ds.store_events(self.known_events)

    def monitor_events(self, sleep_time=900):
        while True:
            try:
                self.check_events()
            except Exception as e:
                self.chat.message("Swallowed exception at check_events: {}".format(e), self.lab_channel_id)
                logger.error("Swallowed exception at check_events: {}".format(e))
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

    def tables_detail(self, event_name):
        return self.trello.tables_detail(event_name)

    def table(self, event_name, table_title):
        return self.trello.table(event_name, table_title)

    def _user_info(self, slack_name):
        info = self.trello.contact_by_slack_name(slack_name)
        if not info:
            return "I don't know :disappointed:"
        meetup_username = info["name"]
        meetup_id = info["id"]
        profile_url = "https://www.meetup.com/Stockholm-Roleplaying-Guild/members/{}/".format(meetup_id)
        return "{} is known on Meetup as *{}*: {}".format(slack_name, meetup_username, profile_url )

    def conversation(self, task_queue):
        unknown_responses = self._phrases["responses"]["unknown"]
        while True:
            command, channel_id, user_id = task_queue.get()
            if command.startswith("help"):
                response = "Hold on tight, I'm coming!"
            elif command.lower().startswith("table status"):
                response = self._tables_info(channel=self.chat.channel_name(channel_id),
                                             request=command.split('table status')[-1])
            elif command.lower().startswith("detailed table status"):
                response = self._tables_info(channel=self.chat.channel_name(channel_id),
                                             request=command.split('table status')[-1], detail=True)
            elif command.lower().startswith("table"):
                full_req = command.split('table')[-1].strip()
                split_req = full_req.split(" ", 1)
                table_number = split_req[0]
                if len(split_req) == 2:
                    request = split_req[1]
                else:
                    request = None
                logger.debug("Table {}".format(table_number))
                response = self._tables_info(channel=self.chat.channel_name(channel_id),
                                            request=request, detail=True, table_number=table_number)
            elif "next event" in command.lower() and "events" not in command.lower():
                response = self._next_event_info()
            elif "events" in command.lower():
                response = self._all_events_info()
            elif "thanks" in command.lower() or "thank you" in command.lower():
                response = random.choice(self._phrases["responses"]["thanks"])
            elif "who is" in command.lower():
                slack_name = command.split("who is")[-1].strip("?").strip()
                response = self._user_info(slack_name)
            elif command.lower().startswith("what can you do") or command.lower() == "man":
                response = self._phrases["responses"]["help"]
            elif "admin info" in command.lower():
                response = self._phrases["responses"]["admin_info"]
            else:
                response = self._check_for_greeting(command) if self._check_for_greeting(command) else random.choice(
                    unknown_responses)
            self.respond(response, channel_id)
