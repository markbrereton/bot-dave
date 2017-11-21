#!/usr/bin/env python

import yaml
from functools import lru_cache
from trello import TrelloClient
from collections import OrderedDict
from dave.log import logger


class TrelloBoard(object):
    def __init__(self, api_key, token):
        """Creates a TrelloBoard object

        :param api_key: (str) Your Trello api key https://trello.com/1/appKey/generate
        :param token:  (str) Your Trello token
        """
        self.tc = TrelloClient(api_key=api_key, token=token)
        self._ab_id_cache = {}
        self._ab_name_cache = {}
        self._ab_slack_cache = {}
        self._warmup_caches()

    @property
    def boards(self):
        """All the boards that can be accessed

        :return: (Board) list of Board
        """
        return self.tc.list_boards()

    @property
    def addressbook(self):
        board = self._board("Address Book")
        ab = {}
        for l in board.list_lists(list_filter="open"):
            for card in l.list_cards():
                info = yaml.load(card.desc)
                if info:
                    ab[info["id"]] = {"name": card.name, "slack": info["slack"]}
        self._ab_id_cache = ab
        return ab

    @lru_cache(maxsize=128)
    def _org_id(self, team_name):
        """Get the id of a Trello team

        :param team_name:
        :return:
        """
        orgs = self.tc.list_organizations()
        for org in orgs:
            if org.name == team_name:
                return org.id

    @lru_cache(maxsize=128)
    def _board(self, board_name):
        board = [b for b in self.boards if b.name == board_name]
        if board:
            return board[0]

    @lru_cache(maxsize=128)
    def _member(self, member_id, board_name):
        member_id = str(member_id)
        board = self._board(board_name)

        for l in board.list_lists(list_filter="open"):
            for card in l.list_cards():
                if card.desc == member_id:
                    return card

    @lru_cache(maxsize=128)
    def _label(self, label_name, board_name):
        board = self._board(board_name)
        label = [l for l in board.get_labels() if l.name == label_name]
        if label:
            return label[0]

    def _warmup_caches(self):
        logger.debug("Warming up the caches")
        ids = self.addressbook
        # for meetup_name, slack_name in [(n["name"], n["slack"]) for n in ids.values()]:
        #     _ = self.contact_by_name(meetup_name)
        #     if slack_name:
        #         _ = self.contact_by_slack_name(slack_name)

    def create_board(self, board_name, team_name=None):
        template = self._board("Meetup Template")
        board = self._board(board_name)
        org_id = self._org_id(team_name=team_name)

        if not board:
            self.tc.add_board(board_name=board_name, source_board=template, organization_id=org_id)

    def add_rsvp(self, name, member_id, board_name):
        member_id = str(member_id)
        board = self._board(board_name)
        rsvp_list = board.list_lists(list_filter="open")[0]

        if not self._member(member_id, board_name):
            rsvp_list.add_card(name=name, desc=member_id)
        logger.debug("add_rsvp: ", self._member.cache_info())

    def cancel_rsvp(self, member_id, board_name):
        logger.debug("Cancelling RSVP for members id {} at {}".format(member_id, board_name))
        card = self._member(member_id, board_name)
        logger.debug("Card for member id {} is {}".format(member_id, card))
        canceled = self._label("Canceled", board_name)
        logger.debug("Canceled tag is {}".format(canceled))
        if card:
            card.add_label(canceled)
        logger.debug("cancel_rsvp", self._member.cache_info())
        logger.debug("cancel_rsvp", self._label.cache_info())

    def tables(self, board_name):
        tables = {}
        board = self._board(board_name)
        info_card = None
        if not board:
            return None
        for table in board.list_lists(list_filter="open"):
            names = []
            title = table.name if not table.name.startswith("RSVP") else "~ without a table ~"
            for card in table.list_cards():
                if card.name != "Info" and not card.labels:
                    names.append(card.name)
                elif card.name == "Info":
                    info_card = card
                elif card.labels:
                    for label in card.labels:
                        if label.name == "GM":
                            names.append(card.name + " (GM)")
                        else:
                            names.append(card.name)
            if info_card:
                info = info_card.desc
            else:
                info = ""
            tables[title] = {}
            tables[title]["members"] = names
            tables[title]["info"] = info
        resp = OrderedDict(sorted(tables.items()))
        return resp

    def table(self, board_name, list_name):
        return self.tables(board_name)[list_name]

    def contact_by_name(self, member_name):
        if self._ab_name_cache.get(member_name):
            return self._ab_name_cache[member_name]
        else:
            board = self._board("Address Book")
            for l in board.list_lists(list_filter="open"):
                for card in l.list_cards():
                    desc = yaml.load(card.desc)
                    if card.name == member_name and desc["slack"]:
                        self._ab_name_cache[member_name] = yaml.load(card.desc)
                        return self._ab_name_cache[member_name]

    def contact_by_slack_name(self, slack_name):
        if self._ab_slack_cache.get(slack_name):
            return self._ab_slack_cache[slack_name]
        else:
            board = self._board("Address Book")
            for l in board.list_lists(list_filter="open"):
                for card in l.list_cards():
                    desc = yaml.load(card.desc)
                    if desc["slack"] == slack_name:
                        self._ab_slack_cache[slack_name] = {"name": card.name, "id": desc["id"]}
                        return self._ab_slack_cache[slack_name]

    def contact_by_id(self, member_id):
        if self._ab_id_cache.get(member_id):
            return self._ab_id_cache[member_id]
        else:
            board = self._board("Address Book")
            for l in board.list_lists(list_filter="open"):
                for card in l.list_cards():
                    info = yaml.load(card.desc)
                    if info:
                        if info['id'] == member_id and info["slack"]:
                            self._ab_id_cache[member_id] = {"name": card.name, "slack": info["slack"]}
                            return self._ab_id_cache[member_id]

    def add_contact(self, member_name, member_id):
        member_id = str(member_id)
        if self._ab_id_cache.get(member_id):
            return True

        board = self._board("Address Book")
        ab_list = board.list_lists(list_filter="open")[0]
        info = yaml.dump({"id": member_id, "slack": None}, default_flow_style=False)
        no_slack = self._label("NoSlack", "Address Book")

        for card in ab_list.list_cards():
            desc = yaml.load(card.desc)
            if desc["id"] == member_id:
                return True

        ab_list.add_card(name=member_name, desc=info, labels=[no_slack])


if __name__ == "__main__":
    from os import environ
    trello_key = environ["TRELLO_API_KEY"]
    trello_token = environ["TRELLO_TOKEN"]
    t = TrelloBoard(api_key=trello_key, token=trello_token)
    print(t._ab_id_cache)
    print(t.addressbook)
    print(t._ab_id_cache)
    print(t.contact_by_id(62568802))

    print(t._ab_name_cache)
    # print(t.contact_by_name("Alex T"))
    # print(t._ab_name_cache)
    # print(t.contact_by_name("Alex T"))
    print(t._ab_slack_cache)
