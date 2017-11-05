#!/usr/bin/env python

from trello import TrelloClient
import json


class TrelloBoard(object):
    def __init__(self, api_key, token):
        self.tc = TrelloClient(api_key=api_key, token=token)

    @property
    def boards(self):
        return self.tc.list_boards()

    @property
    def addressbook(self):
        book = {}
        board = [b for b in self.boards if b.name == "Address Book"][0]
        lists = board.list_lists()
        for list in lists:
            for card in list.list_cards():
                try:
                    info = json.loads(card.desc)
                    book[info["id"]] = {"name": card.name, "slack": info["slack"]}
                except json.decoder.JSONDecodeError:
                    pass
        return book

    def _org_id(self, team_name):
        orgs = self.tc.list_organizations()
        for org in orgs:
            if org.name == team_name:
                return org.id

    def _locate_member(self, member_id, board_name):
        board = [b for b in self.boards if b.name == board_name][0]
        lists = board.list_lists()

        for list in lists:
            for card in list.list_cards():
                if card.desc == member_id:
                    return card

    def _locate_label(self, label_name, board_name):
        board = [b for b in self.boards if b.name == board_name][0]
        label = [l for l in board.get_labels() if l.name == label_name]

        if label:
            return label[0]

    def _add_label(self, member_id, board_name, label_name):
        card = self._locate_member(member_id, board_name)
        label = self._locate_label(label_name, board_name)
        if card and label:
            card.add_label(label)

    def create_board(self, board_name, team_name=None):
        template = [b for b in self.boards if b.name == "Meetup Template"][0]
        boards = [b for b in self.boards if b.name == board_name]
        org_id= self._org_id(team_name=team_name)

        if not boards:
            self.tc.add_board(board_name=board_name, source_board=template, organization_id=org_id)

    def add_rsvp(self, name, member_id, board_name):
        member_id = str(member_id)
        board = [b for b in self.boards if b.name == board_name][0]
        rsvp_list = board.list_lists()[0]

        if not self._locate_member(member_id, board_name):
            rsvp_list.add_card(name=name, desc=member_id)

    def cancel_rsvp(self, member_id, board_name):
        self._add_label(member_id, board_name, "Canceled")

    def mark_inchannel(self, member_id, board_name):
        self._add_label(member_id, board_name, "InSlackChannel")


if __name__ == "__main__":
    tb = TrelloBoard("***REMOVED***", "***REMOVED***")
    print(tb.addressbook)
