#!/usr/bin/env python

from slackclient import SlackClient
from dave.log import logger
from time import sleep


class Slack(object):
    def __init__(self, slack_token, bot_id):
        """Creates a Slack connection object

        :param slack_token: (str) Your Slack API key
        :param bot_id: (str) The bot's user id
        """
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
        """Parse the :slack_rtm_output: received from Slack and return everything after the bot's @-name
        or None if it wasn't directed at the bot.

        :param slack_rtm_output: (str) Slack message to parse
        :return: (tuple) A tuple of the stripes message and channel id
        """
        output_list = slack_rtm_output
        if output_list and len(output_list) > 0:
            for output in output_list:
                if output and 'text' in output and self.at_bot in output['text']:
                    # return text after the @ mention, whitespace removed
                    return output['text'].split(self.at_bot)[1].strip().lower(), \
                           output['channel']
        return None, None

    def new_event(self, event_name, date, venue, url, channel="#announcements"):
        """
        Announces a new event on :channel: using an attachment
        :param event_name: (str) The event's title
        :param date: (str) The event's date formatted the way we want to be presented
        :param venue: (str) The venue of the event
        :param url: (str) The event's URL. Used to create a hyperlink.
        :param channel: (str) The channel where to make the announcement. Needs a leading #
        :return: None
        """
        attachment = [{
            "pretext": "Woohoo! We've got a new event coming up!",
            "color": "#36a64f",
            "title": event_name,
            "title_link": url,
            "text": "{}\n{}".format(date, venue)
        }]
        self._announcement(attachment, channel=channel)

    def new_rsvp(self, names, response, event_name, spots, channel="#dungeon_lab"):
        """Announces a new RSVP on :channel:

        :param names: (str) The names of the ones that RSVPed
        :param response: (str) "yes" or "no"
        :param event_name: (str) The event's title
        :param spots: (str) The number of spots left
        :param channel: (str) The channel where to make the announcement. Needs a leading #
        :return: None
        """
        attachment = [{
            "pretext": "New RSVP",
            "color": "#36a64f",
            "text": "{} replied {} for the {}\n{} spots left".format(names, response, event_name, spots)
        }]
        self._announcement(attachment, channel=channel)

    def rtm(self, queue, read_delay=1):
        """Creates a Real Time Messaging connection to Slack and listens for events
        https://api.slack.com/rtm

        :param queue: (queue) A Multiprocess Queue where it'll put the incoming events
        :param read_delay: (int) How often to check for events. Default: 1s
        :return: None
        """
        if self.sc.rtm_connect():
            logger.info("Slack RTM connected")
            while True:
                command, channel = self._parse_slack_output(self.sc.rtm_read())
                if command and channel:
                    logger.debug("command and channel found {} {}".format(command, channel))
                    queue.put((command, channel))
                sleep(read_delay)

    def message(self, content, channel):
        """Sends a simple message containing :content: to :channel:

        :param content: (str) The, well, content of the message
        :param channel: (str) The channel where to make the announcement. Needs a leading #
        :return: None
        """
        self.sc.api_call(
            "chat.postMessage",
            as_user=True,
            channel=channel,
            text=content)
