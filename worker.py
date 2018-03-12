#!/usr/bin/env python

import multiprocessing as mp

from dave.bot import Bot


class Worker(mp.Process):
    def __init__(self, task_queue, result_queue, bot):
        mp.Process.__init__(self)
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.bot = bot

    def run(self):
        self.bot.conversation(self.task_queue)

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
