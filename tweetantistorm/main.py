import datetime

import json
import os.path
from urllib.parse import urlparse

import click
import tweepy
import logging
import time
from typing import Optional, List
import requests
from requests_html import HTMLSession

from tweepy import API, Status

from tweetantistorm.logs import setup_logging
from tweetantistorm.console import print_colorful_json


logger: Optional[logging.Logger] = None


class ImageRewriterJSONifiedState:
        """Store the state of scanned blocks and all events.

        All state is an in-memory dict.
        Simple load/store massive JSON on start up.
        """

        def __init__(self, session: requests.Session, output_path, path_prefix=""):
            self.state = None
            self.fname = os.path.join(output_path, "image-rewrites.json")
            # How many second ago we saved the JSON file
            self.last_save = 0
            self.session = session
            self.path_prefix = path_prefix
            self.output_path = output_path

        def reset(self):
            """Create initial state of nothing scanned."""
            self.state = {
                "mappings": {},
                "used_filenames": [],
            }

        def restore(self):
            """Restore the last scan state from a file."""
            try:
                self.state = json.load(open(self.fname, "rt"))
                logger.info(f"Restored the image rewriter state, previously {len(self.state['mappings'])} saved images")
            except (IOError, json.decoder.JSONDecodeError):
                logger.info("State starting from scratch")
                self.reset()

        def save(self):
            """Save everything we have scanned so far in a file."""
            with open(self.fname, "wt") as f:
                json.dump(self.state, f)
            self.last_save = time.time()

        def remap(self, image_url) -> str:
            """Get a localised URL for a remote image."""
            path = urlparse(image_url).path
            fname = os.path.basename(path)
            idx = 0
            cur_fname = fname
            while cur_fname in self.state["used_filenames"] and idx < 1000:
                idx += 1
                cur_fname = "{idx}_{fname}"
            self.state["used_filenames"].append(cur_fname)
            return cur_fname

        def rewrite_image_url(self, image_url):
            if image_url not in self.state["mappings"]:
                fname = self.remap(image_url)
                self.state["mappings"][image_url] = fname
                out_fname = os.path.join(self.output_path, fname)
                logger.info("Downloading new image %s as %s", image_url, fname)
                resp = self.session.get(image_url)
                image_data = resp.content

                if not image_data:
                    raise RuntimeError(f"Failed to read image data from {image_url}, status code {resp.status_code}")

                with open(out_fname, "wb") as out:
                    out.write(image_data)

                self.state["mappings"][image_url] = fname
            else:
                fname = self.state["mappings"][image_url]
                logger.info("Already downloaded image %s as %s", image_url, fname)

            self.save()

            return os.path.join(self.path_prefix, self.state["mappings"][image_url])


def scrape(link, output_path):

    session = requests.Session()
    image_rewriter = ImageRewriterJSONifiedState(session=session, output_path=output_path)

    image_rewriter.restore()

    scrape_session = HTMLSession()
    r = scrape_session.get(link)
    tweets = r.html.find("[data-controller='mentions'] .content-tweet")
    logger.info("Found %d tweets", len(tweets))

    with open(os.path.join(output_path, "out.md"), "wt") as md:

        for idx, t in enumerate(tweets):
            # Replace images
            for img in t.find("img"):
                # Threader app specific
                # <Element 'img' alt='' src='/images/1px.png' data-src='https://pbs.twimg.com/media/E0i_12IWQAMJL15.jpg'>
                src = img.attrs.get("data-src") or img.attrs.get("src")
                if src:
                    img.attrs["src"] = image_rewriter.rewrite_image_url(src)
                    if "data-src" in img.attrs:
                        del img.attrs["data-src"]

            md.write(f"\n\n <!-- Tweet {idx}-->\n")
            md.write(t.html)


@click.command()
@click.option('--thread-reader-app-link', default=None, help='Link to the threaderapp page', required=True)
@click.option('--log-level', default="info", help='Python logging level', required=False)
@click.option('--output-folder', default="out", help='Output folder', required=False)
def main(thread_reader_app_link, log_level, output_folder):
    """Tweetstorm scraper."""
    global logger
    logger = setup_logging(log_level)

    if not os.path.exists(output_folder):
        output_folder = os.path.abspath(output_folder)
        logger.info("Storing output in %s", output_folder)
        os.makedirs(output_folder)

    scrape(thread_reader_app_link, output_folder)

    # thread = extract_thread(unsorted)
    # logger.info("The thread has %d tweets", len(thread))
    # dump_thread(thread)



