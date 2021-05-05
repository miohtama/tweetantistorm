import click
import tweepy

from tweetantistorm.logs import setup_logging


@click.command()
@click.option('--consumer-key', default=None, help='API key', required=False)
@click.option('--consumer-secret', default=None, help='API secret', required=False)
@click.option('--log-level', default="info", help='Python logging level', required=False)
def main(consumer_key, consumer_secret, log_level):
    """Tweetstorm scraper."""
    logger = setup_logging(log_level)

    logger.info("Connecting to Twitter using API key: %s", consumer_key)
    auth = tweepy.AppAuthHandler(consumer_key, consumer_secret)
    client = tweepy.Client(auth)

