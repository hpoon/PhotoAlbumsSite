import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

import attr
from bs4 import BeautifulSoup


def jsonDefault(OrderedDict):
    return OrderedDict.__dict__


@attr.s(frozen=True)
class Album:

    title = attr.ib(type=str)
    elements = attr.ib(type=int)
    album_url = attr.ib(type=str)
    cover_image_url = attr.ib(type=str)


ALBUMS_JSON_PATH = "albums.json"


def scrape_html(file: str):
    album_class = "MTmRkb"
    elements_class = "UV4Xae"
    album_title_class = "mfQCMe"
    album_cover_class = "FLmEnf"

    with open(ALBUMS_JSON_PATH, "r+") as albums_file, open(file) as html_file:
        album_file_data = json.load(albums_file)
        existing_albums = len(album_file_data)

        html = html_file.read()
        soup = BeautifulSoup(html, "html.parser")

        # Extract the elements for all
        print("Retrieving first set of album elements")
        album_elements = soup.findAll("a", {"class": album_class})

        # Build album for each one
        total_albums = len(album_elements)
        print("Found " + str(total_albums) + " albums")
        albums_added = 0
        elements_to_add = total_albums - existing_albums
        for i in reversed(range(0, elements_to_add)):
            album_element = album_elements[i]

            # Get album title
            album_title_element = album_element.find("div", {"class": album_title_class})
            album_title = album_title_element.text

            # Get number of elements in album
            elements_element = album_element.find("div", {"class": elements_class})
            elements = int(re.sub("[^0-9]", "", elements_element.text))

            # Extract link
            link = album_element.get("href").replace("photosgooglecom", "photos.google.com")

            # Extract album cover image url
            album_cover_image_element = album_element.find("div", {"class": album_cover_class})
            image_url = album_cover_image_element.get("style") \
                .replace("background-image: url(\"", "").replace("\");", "")

            # Add to set
            album_file_data.append(Album(album_title, elements, link, image_url))
            albums_added += 1

        print("Added " + str(albums_added) + " albums")

        # Write outputs
        print("Writing " + str(len(album_file_data)) + " to " + ALBUMS_JSON_PATH)
        albums_file.seek(0)
        albums_file.write(json.dumps(album_file_data, default=jsonDefault, indent=4, sort_keys=True))

        print("Success!")


def generate_page():
    with open(ALBUMS_JSON_PATH) as f:
        albums = json.load(f)

    jekyll_output = "./docs/_posts/"
    id = 0
    for album in albums:
        # Create output file
        fake_date = datetime(year=1970, month=1, day=1)
        fake_date = fake_date + timedelta(days=id)
        fake_date = fake_date.strftime("%Y-%m-%d")
        post_path = fake_date + "-" + album["title"] + ".md"
        post_path = post_path.replace(" ", "-")
        post_path = jekyll_output + post_path

        # Skip files that are already existing
        if os.path.isfile(post_path):
            id += 1
            continue

        out_file = open(post_path, "w")
        out_file.write("---\n")
        out_file.write("title: " + album["title"] + "\n")
        out_file.write("elements: " + str(album["elements"]) + "\n")
        out_file.write("album_url: " + album["album_url"] + "\n")
        out_file.write("cover_image_url: " + album["cover_image_url"] + "\n")
        out_file.write("categories: [ Uncategorized ]\n")
        out_file.write("---\n")
        out_file.close()

        if id % 25 == 0:
            print(str(id + 1) + " files written")

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
