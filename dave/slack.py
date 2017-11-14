#!/usr/bin/env python

from slackclient import SlackClient
from dave.log import logger
from time import sleep


class Slack(object):
    def __init__(self, slack_token, bot_id):
        self.sc = SlackClient(slack_token)
        self.at_bot = "<@" + bot_id + ">"

    def _announcement(self, attachment, channel="#small_council"):
        self.sc.api_call(
            "chat.postMessage",
            as_user=True,
            channel=channel,
            attachments=attachment
        )

    def _parse_slack_output(self, slack_rtm_output):
        """
            The Slack Real Time Messaging API is an events firehose.
            this parsing function returns None unless a message is
            directed at the Bot, based on its ID.
        """
        output_list = slack_rtm_output
        if output_list and len(output_list) > 0:
            for output in output_list:
                if output and 'text' in output and self.at_bot in output['text']:
                    # return text after the @ mention, whitespace removed
                    return output['text'].split(self.at_bot)[1].strip().lower(), \
                           output['channel']
        return None, None

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

    def rtm(self, queue, read_delay=1):
        if self.sc.rtm_connect():
            logger.info("Slack RTM connected")
            while True:
                command, channel = self._parse_slack_output(self.sc.rtm_read())
                if command and channel:
                    logger.debug("command and channel found {} {}".format(command, channel))
                    queue.put((command, channel))
                sleep(read_delay)

    def message(self, response, channel):
            self.sc.api_call(
                "chat.postMessage",
                as_user=True,
                channel=channel,
                text=response)
