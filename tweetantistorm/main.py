import json
import os.path
import shutil
import textwrap
from urllib.parse import urlparse, urlencode

import click
import logging
import time
from typing import Optional, List
import requests
from lxml import etree
from lxml.html import HtmlElement, fragment_fromstring
from requests_html import HTMLSession, Element


from tweetantistorm.logs import setup_logging


logger: Optional[logging.Logger] = None


TEMPLATE = """
<html>
    <head>
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css" integrity="sha384-Gn5384xqQ1aoWXA+058RXPxPg6fy4IWvTNh0E263XmFcJlSAwiGgFAW/dAiS6JXm" crossorigin="anonymous">
        <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/js/bootstrap.min.js" integrity="sha384-JZR6Spejh4U02d8jOt6vLEHfe/JQGiRRSQQxSfFWpi1MquVdAyjUar5+76PVCmYl" crossorigin="anonymous"></script>
        <link rel="stylesheet" href="sample.css"></link>
    </head>
    <body>
        <div class="container narrow pb-5">
            <div class="row">
                <div class="col-12">
                    <div class="tweetstorm">
                        {body}
                    </div>
                </div>
            </div>
        </div>
    </body>
</html>
"""


MEDIA_OBJECT_TEMPLATE = """
  <a class="link-preview" href="{url}">
    <div class="media">
      <img class="mr-3" src="{image}" alt="">
      <div class="media-body">
        <h5 class="mt-0">{title}</h5>
        {description}
      </div>
    </div>
  </a>
  `;
"""


def set_inner_html(elem: HtmlElement, html: str):
    """Replace innerHTML of a lxml element."""

    # Clear the element contents
    child: HtmlElement
    for child in elem.getchildren():
        elem.remove(child)

    # Create and add new contents
    content = fragment_fromstring(html)
    elem.append(content)


class ImageRewriterJSONifiedState:
        """Store the state of scanned blocks and all events.

        All state is an in-memory dict.
        Simple load/store massive JSON on start up.
        """

        def __init__(self, session: requests.Session, output_path, path_prefix="", linkpreview_api_key=None):
            self.state = None
            self.fname = os.path.join(output_path, "image-rewrites.json")
            # How many second ago we saved the JSON file
            self.last_save = 0
            self.session = session
            self.path_prefix = path_prefix
            self.output_path = output_path
            self.linkpreview_api_key = linkpreview_api_key

        def reset(self):
            """Create initial state of nothing scanned."""
            self.state = {
                "mappings": {},
                "used_filenames": [],
                "link_previews": {},
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

        def fetch_linkpreview_data(self, url) -> dict:
            """Use LinkPreview to get the preview of a link content."""
            if url not in self.state["link_previews"]:
                q = urlencode(url)
                api_url = f"http://api.linkpreview.net/?key={self.linkpreview_api_key}&q={q}"
                data = requests.get(api_url)
                image_url = data.get("image")
                if image_url:
                    rewrite = self.rewrite_image_url(image_url)
                    data["rewritten_image_url"] = rewrite

                self.state["link_previews"][url] = data

            self.save()
            return self.state["link_previews"][url]


def scrape(link, output_path, image_src_prefix, linkpreview_api_key):
    """Read Threader app HTML output and modify it for a local blog post."""

    session = requests.Session()
    image_rewriter = ImageRewriterJSONifiedState(session=session, output_path=output_path, path_prefix=image_src_prefix, linkpreview_api_key=linkpreview_api_key)

    image_rewriter.restore()

    scrape_session = HTMLSession()
    r = scrape_session.get(link)
    tweets = r.html.find("[data-controller='mentions'] .content-tweet")
    logger.info("Found %d tweets", len(tweets))

    body = ""

    with open(os.path.join(output_path, "out.html"), "wt") as md:

        for idx, request_element in enumerate(tweets):

            # Manipulate the individual tweet HTML from Threader App in place
            # to make it more suiatble for the blog
            t: HtmlElement = request_element.element

            # Scrape images and rewrite srcs using local URLs
            for img in t.cssselect("img"):
                # Threader app specific
                # <Element 'img' alt='' src='/images/1px.png' data-src='https://pbs.twimg.com/media/E0i_12IWQAMJL15.jpg'>
                src = img.attrib.get("data-src") or img.attrib.get("src")
                if src:
                    new_url = image_rewriter.rewrite_image_url(src)
                    if "data-src" in img.attrib:
                        del img.attrib["data-src"]
                    img.set("src", new_url)

            # Move Tweet main pic to the top (if any)
            pic = t.cssselect(".entity-image")
            if pic:
                assert len(pic) == 1
                t.insert(0, pic[0])

            # Fix hashtag links
            for hashtag in t.cssselect(".entity-hashtag"):
                orig_href = hashtag.attrib["href"]
                hashtag.set("href", "https://twitter.com" + orig_href)

            # Convert Twitter links to link previews
            if image_rewriter.linkpreview_api_key:
                entity: HtmlElement
                for entity in t.cssselect(".entity-url"):
                    orig_href = hashtag.attrib["href"]
                    data = image_rewriter.fetch_linkpreview_data(orig_href)
                    # prev = entity.getprevious()
                    html = MEDIA_OBJECT_TEMPLATE.format(data)
                    new_element = fragment_fromstring(html)
                    parent: HtmlElement = entity.getparent()
                    t.addnext(new_element)
                    parent.remove(t)
                    print("Added", new_element)

            # Fix permalinks
            tweet_id = t.attrib["data-tweet"]
            tweet_url = f"https://twitter.com/web/status/{tweet_id}"

            entity: HtmlElement
            for entity in t.cssselect(".entity-url"):
                # Filter our junk new lines at the end of the tweet
                previous: HtmlElement = entity.getprevious()
                while previous is not None and previous.tag == "br":
                    to_delete: HtmlElement = previous
                    previous = previous.getprevious()
                    to_delete.getparent().remove(to_delete)

            perma: HtmlElement
            for perma in t.cssselect(".tw-permalink"):
                content = f"""
                    <a href="{tweet_url}">
                        <i class="fas fa-link" aria-hidden="true"></i>
                    </a>
                """
                set_inner_html(perma, content)

            # Move URL previews past perlinks
            for link_preview in t.cssselect(".entity-url"):
                t.append(link_preview)

            if idx != 0:
                src = "\n"
            else:
                src = ""
            src += f"<!-- Tweet {idx + 1}-->\n"
            src += etree.tostring(t, encoding="unicode", method="html").strip()
            src = textwrap.indent(src, prefix="                        ")

            body += src

        md.write(TEMPLATE.format(body=body))

    # Have some basic styles for the example
    shutil.copy("sample.css", output_path)


@click.command()
@click.option('--thread-reader-app-link', default=None, help='Link to the threaderapp page', required=True)
@click.option('--log-level', default="info", help='Python logging level', required=False)
@click.option('--output-folder', default="out", help='Output folder', required=False)
@click.option('--image-src-prefix', default="", help='Prefix for image sources for blog hosting', required=False)
@click.option('--linkpreview-api-key', default="", help='API key to render link previews using linkpreview.net', required=False)
def main(thread_reader_app_link, log_level, output_folder, image_src_prefix, linkpreview_api_key=None):
    """Tweetstorm scraper."""
    global logger
    logger = setup_logging(log_level)

    if not os.path.exists(output_folder):
        output_folder = os.path.abspath(output_folder)
        logger.info("Storing output in %s", output_folder)
        os.makedirs(output_folder)

    scrape(thread_reader_app_link, output_folder, image_src_prefix, linkpreview_api_key)




