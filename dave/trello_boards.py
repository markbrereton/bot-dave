#!/usr/bin/env python

import yaml
from trello import TrelloClient
from dave.log import logger


class TrelloBoard(object):
    def __init__(self, api_key, token):
        self.tc = TrelloClient(api_key=api_key, token=token)

    def _org_id(self, team_name):
        orgs = self.tc.list_organizations()
        for org in orgs:
            if org.name == team_name:
                return org.id

    def _locate_board(self, board_name):
        board = [b for b in self.boards if b.name == board_name]
        if board:
            return board[0]

    def _locate_member(self, member_id, board_name):
        member_id = str(member_id)
        board = self._locate_board(board_name)

        for l in board.list_lists():
            for card in l.list_cards():
                if card.desc == member_id:
                    return card

    def _locate_label(self, label_name, board_name):
        board = self._locate_board(board_name)
        label = [l for l in board.get_labels() if l.name == label_name]

        if label:
            return label[0]

    def create_board(self, board_name, team_name=None):
        template = [b for b in self.boards if b.name == "Meetup Template"][0]
        board = self._locate_board(board_name)
        org_id= self._org_id(team_name=team_name)

        if not board:
            self.tc.add_board(board_name=board_name, source_board=template, organization_id=org_id)

    @property
    def boards(self):
        return self.tc.list_boards()

    @property
    def addressbook(self):
        board = self._locate_board("Address Book")
        book = {}
        for l in board.list_lists():
            for card in l.list_cards():
                info = yaml.load(card.desc)
                if info:
                    book[info["id"]] = {"name": card.name, "slack": info["slack"]}
        return book

    def add_rsvp(self, name, member_id, board_name):
        member_id = str(member_id)
        board = [b for b in self.boards if b.name == board_name][0]
        rsvp_list = board.list_lists()[0]

        if not self._locate_member(member_id, board_name):
            rsvp_list.add_card(name=name, desc=member_id)

    def cancel_rsvp(self, member_id, board_name):
        logger.debug("Cancelling RSVP for members id {} at {}".format(member_id, board_name))
        card = self._locate_member(member_id, board_name)
        logger.debug("Card for member id {} is {}".format(member_id, card))
        canceled = self._locate_label("Canceled", board_name)
        logger.debug("Canceled tag is {}".format(canceled))
        if card:
            card.add_label(canceled)

    def add_address(self, member_name, member_id):
        pass
