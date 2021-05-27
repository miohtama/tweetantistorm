This is my Twitter thread to blog post exporter. It uses Thread Reader App scraping as the source and the modifies the output HTML.

* Download and link any images locally

* Build link previews using [linkpreview.net](https://linkpreview.net)

# Demo

* [The original Twitter thread](https://twitter.com/moo9000/status/1389571466002325510)

* [The exported blog post: History and Future of cryptocurrencies](https://capitalgram.com/posts/history-of-cryptocurrencies/)

# Install

Using poetry

# Set up

[Get API key from Twitter]().

Run. Example:

```shell
poetry run tweetantistorm --thread-reader-app-link=https://threadreaderapp.com/thread/1389571466002325510.html --output-folder=out --image-src-prefix=/static/img/content/fixed-size/history-of-cryptocurrencies/
```