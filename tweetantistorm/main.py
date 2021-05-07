import datetime

import click
import tweepy
import logging
import time
from typing import Optional, List
from requests_html import HTMLSession

from tweepy import API, Status

from tweetantistorm.logs import setup_logging
from tweetantistorm.console import print_colorful_json


logger: Optional[logging.Logger] = None



def scrape(link):
    session = HTMLSession()
    r = session.get(link)
    tweets = r.html.find("[data-controller='mentions'] .content-tweet")
    logger.info("Found %d tweets", len(tweets))
    for t in tweets:
        print(t.text)

@click.command()
@click.option('--thread-reader-app-link', default=None, help='Link to the threaderapp page', required=True)
@click.option('--log-level', default="info", help='Python logging level', required=False)
def main(thread_reader_app_link, log_level):
    """Tweetstorm scraper."""
    global logger
    logger = setup_logging(log_level)

    scrape(thread_reader_app_link)


    # thread = extract_thread(unsorted)
    # logger.info("The thread has %d tweets", len(thread))
    # dump_thread(thread)



