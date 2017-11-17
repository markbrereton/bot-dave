#!/usr/bin/env python

import multiprocessing as mp
import random
import json

from dave.bot import Bot
from dave.slack import Slack
from dave.log import logger

from datetime import datetime
from fuzzywuzzy import process
from os import environ


class Worker(mp.Process):
    def __init__(self, task_queue, result_queue, bot):
        mp.Process.__init__(self)
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.bot = bot
        slack_token = environ["SLACK_API_TOKEN"]
        bot_id = environ.get("BOT_ID")
        bot_channel_id = environ.get("BOT_CHANNEL_ΙD")
        self.chat = Slack(slack_token, bot_id, bot_channel_id)
        with open("dave/resources/phrases.json", "r") as phrases:
            self.phrases = json.loads(phrases.read())

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
        next_meetup = dave.next_meetup
        participants = next_meetup["participants"]
        event_time = next_meetup["time"] / 1000
        date = datetime.fromtimestamp(event_time).strftime('%A %B %d at %H:%M')
        name = next_meetup["name"]
        msg = "Our next event is *{}*, on *{}* and " \
              "there are *{}* people joining:\n{}".format(name, date, len(participants),
                                                          self._natural_join(participants))
        return msg

    def _all_events_info(self):
        msgs = ["Here are our next events.\n"]
        for event in dave.known_events.values():
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
        events = dave.event_names
        logger.debug("Events {}".format(events))
        event_name = process.extractOne(request, events)[0]
        logger.debug("Chosen {}".format(event_name))
        msgs = ["Available tables for "]
        msgs[0] += "*{}*".format(event_name)
        table_info = self.bot.tables(event_name)

        for table, details in table_info.items():
            info = details["info"].replace('\n', '\n>')
            msgs.append("*{}*\n>{}\nJoining: *{}*".format(table.upper(), info, ', '.join(details["members"])))

        return '\n\n'.join(msgs)

    def run(self):
        unknown_responses = self.phrases["responses"]["unknown"]
        while True:
            command, channel_id = self.task_queue.get()
            if command.startswith("help"):
                response = "Hold on tight! I'm coming."
            elif command.lower() == "are you there?":
                response = "I'm here :relaxed:"
            elif "next event" in command.lower() and "events" not in command.lower():
                response = self._next_event_info()
            elif "all events" in command.lower() or "next events" in command.lower():
                response = self._all_events_info()
            elif "table status" in command.lower():
                response = self._tables_info(channel=self.chat.channel_name(channel_id),
                                             request=command.split('table status')[-1])
            elif command.lower().startswith("thanks") or command.lower().startswith("thank you"):
                response = "Anytime :relaxed:"
            else:
                response = self._check_for_greeting(command) if self._check_for_greeting(command) else random.choice(
                    unknown_responses)
            self.bot.respond(response, channel_id)


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
