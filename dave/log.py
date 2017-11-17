#!/usr/bin/env python
"""
A simple module setting up the Python logger for logging to stdout
"""

import logging
from os import environ

logger = logging.getLogger("dave")
level = environ.get("LOG_LEVEL")
if level.lower() == "debug":
    logger.setLevel(logging.DEBUG)
elif level.lower() == "info":
    logger.setLevel(logging.INFO)
else:
    logger.setLevel(logging.WARN)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
