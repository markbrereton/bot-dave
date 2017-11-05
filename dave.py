#!/usr/bin/env python

# TODO:
# RTM Documentation https://api.slack.com/rtm
# asyncio documentation http://chriskiehl.com/article/parallelism-in-one-line/
# http://cheat.readthedocs.io/en/latest/python/asyncio.html
# https://stackoverflow.com/questions/42279675/syncronous-sleep-into-asyncio-coroutine
# https://snarky.ca/how-the-heck-does-async-await-work-in-python-3-5/

from datetime import datetime
from os import environ
from time import sleep

from dave.log import logger
from dave.meetup import MeetupGroup
from dave.slack import Slack
from dave.store import Store
from dave.trello_boards import TrelloBoard

meetup_key = environ.get('MEETUP_API_KEY')
group_id = environ.get('MEETUP_GROUP_ID')
slack_token = environ["SLACK_API_TOKEN"]
trello_key = environ["TRELLO_API_KEY"]
trello_token = environ["TRELLO_TOKEN"]
team_name = environ["TRELLO_TEAM"]


def announcements():
    storg = MeetupGroup(meetup_key, group_id)
    chat = Slack(slack_token)
    trello = TrelloBoard(api_key=trello_key, token=trello_token)
    ds = Store()

    while True:
        logger.info("Checking for event updates")
        current_events = [e["id"] for e in storg.events]
        events = ds.retrieve_many_events(current_events)

        for event in storg.events:
            event_id = event["id"]
            newcomers = []
            cancels = []

            # Check for new event
            if event_id not in events.keys():
                event_date = int(event["time"]) / 1000

                chat.new_event(event["name"],
                               datetime.fromtimestamp(event_date).strftime('%A %B %d %H:%M'),
                               event["venue"]["name"],
                               event["event_url"])
                trello.create_board(event["name"], team_name=team_name)
                events[event_id] = event
                events[event_id]["participants"] = []

            # Check for new RSVP
            for rsvp in storg.rsvps(event_id):
                member_name = rsvp["member"]["name"]
                member_id = rsvp["member"]["member_id"]
                board_name = event["name"]
                if member_name not in events[event_id]["participants"] and rsvp["response"] == "yes":
                    newcomers.append(member_name)
                    trello.add_rsvp(name=member_name, member_id=member_id, board_name=board_name)
                elif member_name in events[event_id]["participants"] and rsvp["response"] == "no":
                    trello.cancel_rsvp(member_id, board_name=board_name)
                    cancels.append(member_name)

            if newcomers or cancels:
                spots_left = int(event["rsvp_limit"]) - int(event["yes_rsvp_count"])
                venue = rsvp["venue"]["name"]
                if venue == "STORG Clubhouse":
                    channel = "#storg-south"
                elif venue == "STORG Northern Clubhouse":
                    channel = "#storg-north"
                else:
                    channel = None
                if newcomers:
                    chat.new_rsvp(', '.join(newcomers), rsvp["response"], rsvp["event"]["name"], spots_left, channel)
                    events[event_id]["participants"] += newcomers
                if cancels:
                    chat.new_rsvp(', '.join(cancels), rsvp["response"], rsvp["event"]["name"], spots_left, channel)
                    events[event_id]["participants"] = [p for p in events[event_id]["participants"] if p not in cancels]
            else:
                logger.info("No changes for {}".format(event["name"]))
        logger.debug("Saving events")
        ds.store_many_events(events)
        logger.info("Done checking")
        sleep(600)


if __name__ == "__main__":
    announcements()
