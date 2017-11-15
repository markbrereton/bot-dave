#!/usr/bin/env python

import multiprocessing as mp
import random
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
        self.team_name = environ["TRELLO_TEAM"]
        self.storg = MeetupGroup(meetup_key, group_id)
        self.chat = Slack(slack_token, bot_id)
        self.trello = TrelloBoard(api_key=trello_key, token=trello_token)
        self.ds = Store()
        self.current_events = self.storg.events
        if self.current_events:
            current_event_ids = [e["id"] for e in self.current_events]
            self.known_events = self.ds.retrieve_events(current_event_ids)
        else:
            self.known_events = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save_events()

    def _check_if_new_event(self, event):
        # Check for new event
        event_id = event["id"]
        if event_id not in self.known_events.keys():
            logger.info("New event found: {}".format(event["name"]))
            event_date = int(event["time"]) / 1000

            self.chat.new_event(event["name"],
                                datetime.fromtimestamp(event_date).strftime('%A %B %d %H:%M'),
                                event["venue"]["name"],
                                event["event_url"])
            self.trello.create_board(event["name"], team_name=self.team_name)
            self.known_events[event_id] = event
            self.known_events[event_id]["participants"] = []

    def _check_new_rsvp(self, event):
        event_id = event["id"]
        newcomers = []
        cancels = []

        for rsvp in self.storg.rsvps(event_id):
            member_name = rsvp["member"]["name"]
            member_id = rsvp["member"]["member_id"]
            board_name = event["name"]
            known_participants = self.known_events[event_id]["participants"]

            if member_name not in known_participants and rsvp["response"] == "yes":
                newcomers.append(member_name)
                self.trello.add_rsvp(name=member_name, member_id=member_id, board_name=board_name)
            elif member_name in known_participants and rsvp["response"] == "no":
                self.trello.cancel_rsvp(member_id, board_name=board_name)
                cancels.append(member_name)

        if newcomers or cancels:
            spots_left = int(event["rsvp_limit"]) - int(event["yes_rsvp_count"]) if event["rsvp_limit"] else 'Unknown'
            venue = event["venue"]["name"]

            if venue == "STORG Clubhouse":
                channel = "#storg-south"
            elif venue == "STORG Northern Clubhouse":
                channel = "#storg-north"
            else:
                channel = None

            if newcomers:
                logger.debug("Newcomers found")
                self.chat.new_rsvp(', '.join(newcomers), "yes", event["name"], spots_left, channel)
                self.known_events[event_id]["participants"] += newcomers
                logger.debug("Participant list: {}".format(', '.join(self.known_events[event_id]["participants"])))

            if cancels:
                logger.debug("Cancellations found")
                self.chat.new_rsvp(', '.join(cancels), "no", event["name"], spots_left, channel)
                self.known_events[event_id]["participants"] = [p for p in self.known_events[event_id]["participants"] if
                                                               p not in cancels]
                logger.debug("Participant list: {}".format(', '.join(self.known_events[event_id]["participants"])))
        else:
            logger.info("No changes for {}".format(event["name"]))

    def check_events(self):
        logger.info("Checking for event updates")
        for event in self.current_events:
            self._check_if_new_event(event)
            self._check_new_rsvp(event)
        logger.info("Done checking")
        self.save_events()

    def monitor_events(self, sleep_time=600):
        while True:
            self.check_events()
            sleep(sleep_time)

    def save_events(self):
        logger.debug("Saving events")
        self.ds.store_events(self.known_events)

    def read_chat(self, tasks):
        self.chat.rtm(tasks)

    def respond(self, response, channel):
        self.chat.message(response, channel)

    def next_meetup(self):
        self.current_events.sort(key=lambda d: d["time"])
        next_id = self.current_events[0]["id"]
        return self.known_events[next_id]



class Worker(mp.Process):
    def __init__(self, task_queue, result_queue, bot):
        mp.Process.__init__(self)
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.bot = bot
        self.greeting_keywords = ("hello", "hi", "greetings", "sup", "yo")
        self.greeting_responses = ["Hey!", "*nods*", "Oh hi there!", "*waves*", "greetings"]
        self.none_responses = [
            "Huh?",
            "I have no idea what that means.",
            "I'd like to add you to my professional network on LinkedIn",
            "..."
        ]

    def _check_for_greeting(self, sentence):
        """If any of the words in the user's input was a greeting, return a greeting response"""
        word = sentence.split(' ')[0]
        if word.lower().rstrip('!') in self.greeting_keywords:
            return random.choice(self.greeting_responses)

    def _natural_join(self, lst):
        resp = ',\n'.join(lst)
        resp = ' and'.join(resp.rsplit(',', 1))
        return resp

    def _next_event(self):
        next_meetup = dave.next_meetup()
        participants = next_meetup["participants"]
        event_time = next_meetup["time"] / 1000
        date = datetime.fromtimestamp(event_time).strftime('%A %B %d at %H:%M')
        name = next_meetup["name"]
        return "Our next event is *{}*, on *{}* and there are *{}* people joining:\n{}".format(name, date,
                                                                                               len(participants),
                                                                                               self._natural_join(
                                                                                                   participants))

    def _all_events(self):
        msgs = ["Here are our next events."]
        for event in dave.known_events.values():
            participants = event["participants"]
            event_time = event["time"] / 1000
            date = datetime.fromtimestamp(event_time).strftime('%A %B %d at %H:%M')
            name = event["name"]
            msg = "*{}*, on *{}* with *{}* people joining:\n{}".format(name, date,
                                                                       len(participants),
                                                                       self._natural_join(
                                                                           participants))
            msgs.append(msg)
        return '\n'.join(msgs)

    def run(self):
        proc_name = self.name
        while True:
            next_task = self.task_queue.get()
            logger.debug('{}: {}'.format(proc_name, next_task))
            command, channel = next_task
            if command.startswith("help"):
                response = "Hold on tight! I'm coming."
            elif command.lower() == "are you there?":
                response = "I'm here :relaxed:"
            elif "next meetup" in command.lower() or "next event" in command.lower() and "events" not in command.lower():
                response = self._next_event()
            elif "all meetups" in command.lower() or "all events" in command.lower() or "next events" in command.lower():
                response = self._all_events()
            elif command.lower().startswith("thanks") or command.lower().startswith("thank you"):
                response = "Anytime :relaxed:"
            else:
                response = self._check_for_greeting(command) if self._check_for_greeting(command) else random.choice(self.none_responses)
            self.bot.respond(response, channel)


if __name__ == "__main__":
    dave = Bot()

    tasks = mp.JoinableQueue()
    results = mp.Queue()

    worker = Worker(tasks, results, dave)
    reader = mp.Process(target=dave.read_chat, args=(tasks,))
    monitor = mp.Process(target=dave.monitor_events)

    worker.start()
    reader.start()
    monitor.start()

