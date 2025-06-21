import argparse
import json
import os
import shutil
import sys
import urllib.request
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta

import attr
from PIL import Image
from bs4 import BeautifulSoup


def jsonDefault(OrderedDict):
    return OrderedDict.__dict__


@attr.s(frozen=True)
class Album:
    title = attr.ib(type=str)
    elements = attr.ib(type=int)
    album_url = attr.ib(type=str)
    cover_image_url = attr.ib(type=str)

    def id(self):
        # Don't use the cover image in the hash because the URL is not unique
        # Don't use the number of elements in the hash because I always add/delete things
        return hash((self.title, self.album_url))


ALBUMS_JSON_PATH = "albums.json"
IMAGE_PATH = "docs/assets/img"
MARKUP_PATH = "/assets/img/"


def scrape_html(file: str):
    album_class = "w-full"
    album_title_class = "text-immich-primary"
    album_cover_class = "size-full"

    with open(ALBUMS_JSON_PATH, "r+") as albums_file, open(file) as html_file:
        album_file_data = json.load(albums_file)

        # Read what is already existing, so we know how to dedupe
        albums = OrderedDict()
        for obj in album_file_data:
            album = Album(obj["title"], obj["elements"], obj["album_url"], obj["cover_image_url"])
            albums[album.id()] = album

        html = html_file.read()
        soup = BeautifulSoup(html, "html.parser")

        # Extract the elements for all
        print("Retrieving first set of album elements")
        album_elements = soup.findAll("a", {"class": album_class})

        # Build album for each one
        print("Found " + str(len(album_elements)) + " albums")
        albums_added = 0
        for album_element in reversed(album_elements):
            # Get album title
            album_title_element = album_element.find("p", {"class": album_title_class})
            if album_title_element is None:
                continue

            album_title = album_title_element.text

            # Extract link
            link = album_element.get("href").replace("photosgooglecom", "photos.google.com")

            # Extract album cover image url
            album_cover_image_element = album_element.find("img", {"class": album_cover_class})
            image_url = f"{os.path.dirname(file)}/{album_cover_image_element.get('src')}" \
                .replace("%20", " ").replace("%25", "%")

            # Generate the filename
            filename = (album_title + "_" + str(uuid.uuid4()) + ".jpg") \
                .replace(" ", "").replace("'", "").replace(":", "_")

            # Check if dictionary already has it
            album = Album(album_title, -1, link, os.path.join(MARKUP_PATH, filename))
            if album.id() in albums:
                continue

            # Add to dictionary for deduping
            albums[album.id()] = album

            # Download image since we don't have it already
            print(f"Image URL: {image_url}")
            image_local_path = os.path.join(
                IMAGE_PATH,
                filename.replace(":", "_"))

            # Open image with PIL
            with Image.open(image_url) as img:
                width, height = img.size
                min_dim = min(width, height)

                # Calculate cropping box (centered square)
                left = (width - min_dim) // 2
                top = (height - min_dim) // 2
                right = left + min_dim
                bottom = top + min_dim

                # Crop the image
                img_cropped = img.crop((left, top, right, bottom))

                # Resize to 202x202
                img_resized = img_cropped.resize((202, 202), Image.LANCZOS)

                # Save the final image
                img_resized.save(image_local_path, "JPEG", quality=95)

            albums_added += 1

        print("Added " + str(albums_added) + " albums")

        # Write outputs
        print("Writing " + str(len(albums)) + " to " + ALBUMS_JSON_PATH)
        albums_file.seek(0)
        albums_file.write(json.dumps(list(albums.values()), default=jsonDefault, indent=4, sort_keys=True))

        print("Success!")


def generate_page():
    ignored_albums = {
        "Blog Photos",
        "Half-Life 2 Leaked Beta"
    }

    with open(ALBUMS_JSON_PATH) as f:
        albums = json.load(f)

    jekyll_output = "./docs/_posts/"
    id = 0
    for album in albums:
        # Create output file
        fake_date = datetime(year=1970, month=1, day=1)
        fake_date = fake_date + timedelta(days=id)
        fake_date = fake_date.strftime("%Y-%m-%d")

        title = album["title"]
        post_path = fake_date + "-" + album["title"] + ".md"
        post_path = post_path.replace(" ", "-").replace(":", "")
        post_path = jekyll_output + post_path

        # Skip files that are already existing
        if os.path.isfile(post_path) or title in ignored_albums:
            id += 1
            continue

        out_file = open(post_path, "w")
        out_file.write("---\n")
        out_file.write("title: \"" + album["title"] + "\"\n")
        out_file.write("elements: " + str(album["elements"]) + "\n")
        out_file.write("album_url: " + album["album_url"] + "\n")
        out_file.write("cover_image_url: " + album["cover_image_url"] + "\n")
        out_file.write("categories: [ Uncategorized ]\n")
        out_file.write("---\n")
        out_file.close()
        id += 1

    print(str(id + 1) + " files written")
    print("Success!")


def __main__():
    parser = argparse.ArgumentParser(description="Downloads album information from Google Photos via Selenium and "
                                                 "generates a photo album page")
    parser.add_argument("-s", "--scrape", type=str, help="Scrapes Google Photos html file and downloads album info")
    parser.add_argument("-g", "--generate", action="store_true", help="Generates a photo album page")
    parsed_input = parser.parse_args(sys.argv[1:])

    if not parsed_input.scrape and not parsed_input.generate:
        parser.error("At least one option must be selected")

    if parsed_input.scrape:
        scrape_html(parsed_input.scrape)
    if parsed_input.generate:
        generate_page()


__main__()
