import click
import tweepy
import logging
import time
from typing import Optional, List

from tweepy import API, Status

from tweetantistorm.logs import setup_logging
from tweetantistorm.console import print_colorful_json


logger: Optional[logging.Logger] = None


def fetch_replies(api: API, username, tweet_id) -> List[Status]:
    """Get all replies to a tweet.

    https://stackoverflow.com/a/55804977/315168
    """

    out = []
    replies = tweepy.Cursor(api.search, q='to:{}'.format(username),
                            since_id=tweet_id, tweet_mode='extended').items()
    while True:
        try:
            reply = replies.next()

            if not hasattr(reply, 'in_reply_to_status_id_str'):
                continue

            if reply.in_reply_to_status_id == tweet_id:
                logger.info("reply of tweet:{}".format(reply.full_text))

            out.append(reply)

        except tweepy.RateLimitError as e:
            logger.warning("Twitter api rate limit reached".format(e))
            time.sleep(60)
            continue

        except tweepy.TweepError as e:
            logger.error("Tweepy error occured:{}".format(e))
            break

        except StopIteration:
            break

        except Exception as e:
            logger.error("Failed while fetching replies {}".format(e))
            break

    return out


def extract_thread(replies: List[Status]) -> List[Status]:
    """Get only the original author replies to the thread.

    Assume the first reply is the start of the thread.
    """

    original_user = replies[0].user.screen_name
    current_head = replies[0].id
    extracted = [replies[0]]

    # Sort thread from the start to the end
    replies = sorted(replies, key=lambda r: r.created_at)
    for r in replies[1:]:

        if r.in_reply_to_status_id != current_head:
            continue

        if r.user.screen_name != original_user:
            continue

        extracted.append(r)
        current_head = r.id

    return extracted


def dump_thread(thread: List[Status]):
    for r in thread:
        if hasattr(r, "text"):
            print(r.created_at, r.text)
        elif hasattr(r, "full_text"):
            print(r.created_at, r.full_text)


@click.command()
@click.option('--consumer-key', default=None, help='Consumer key', required=True)
@click.option('--consumer-secret', default=None, help='Consumer secret', required=True)
@click.option('--tweet-id', default=None, help='The id of the first tweet', required=True)
@click.option('--log-level', default="info", help='Python logging level', required=False)
def main(consumer_key, consumer_secret, log_level, tweet_id):
    """Tweetstorm scraper."""
    global logger

    logger = setup_logging(log_level)

    logger.info("Connecting to Twitter using API key: %s", consumer_key)
    auth = tweepy.AppAuthHandler(consumer_key, consumer_secret)
    api = tweepy.API(auth)

    status = api.get_status(tweet_id)
    username = status.user.screen_name
    replies = fetch_replies(api, username, tweet_id)
    unsorted = [status] + replies
    logger.info("Unsorted replies blob is %d tweets long", len(unsorted))

    thread = extract_thread(unsorted)
    logger.info("The thread has %d tweets", len(thread))
    # dump_thread(thread)



