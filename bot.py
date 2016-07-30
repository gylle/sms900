#!/usr/bin/python3
#
""" bot.py - Main file to run the bot """
import argparse
import logging

from sms900 import SMS900

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s:%(funcName)-30s:%(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

PARSER = argparse.ArgumentParser()
PARSER.add_argument('-f', help='Use the given configuration file', default='config.json')
ARGS = PARSER.parse_args()

THEBOT = SMS900(ARGS.f)
THEBOT.run()
