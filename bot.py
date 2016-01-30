#!/usr/bin/python3
import argparse
import logging

from sms900 import SMS900

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s:%(funcName)-30s:%(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')


parser = argparse.ArgumentParser()
parser.add_argument('-f', help = 'Use the given configuration file', default = 'config.json')
args = parser.parse_args()

sms900 = SMS900(args.f)
sms900.run()
