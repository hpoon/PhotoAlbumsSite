import abc
import argparse
import json
import logging
import os
import re
import sys
import weakref
from collections import OrderedDict
from datetime import datetime, timedelta
from time import sleep

import attr
from selenium import webdriver
from selenium.webdriver import FirefoxProfile
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.remote_connection import LOGGER
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait


class Util:

    @staticmethod
    def execute_with_retry(method, max_attempts):
        start_time = datetime.now()
        e = None
        while datetime.now() < start_time + timedelta(seconds=max_attempts):
            try:
                return method()
            except Exception as exc:
                e = exc
                print(e)
                sleep(1)
        if e is not None:
            raise e


class SeleniumManager:

    __browser = None

    def __init__(self):
        def on_die():
            if self.__browser:
                self.__browser.close()
        self._del_ref = weakref.ref(self, on_die)

    def open_browser(self):
        # Start browser
        # It would have been better to avoid downloading files to disk at all, but trying to a POST
        # request while taking into account a login cookie would have been a giant pain.  That would
        # have returned a response in memory that I could have used if that method had worked.
        profile = FirefoxProfile()
        LOGGER.setLevel(logging.WARNING)
        self.__browser = Util.execute_with_retry(lambda: webdriver.Firefox(profile), 10)

    def close_browser(self):
        if self.__browser:
            self.__browser.close()

    def navigate_to(self, url: str):
        self.__browser.get(url)

    def find_element_by(self, by: By, field: str, timeout_seconds: int=30) -> WebElement:
        element = WebDriverWait(self.__browser, timeout_seconds).until(
            expected_conditions.element_to_be_clickable((by, field)))
        return element

    def find_elements_by_xpath(self, field: str, timeout_seconds: int=30) -> list:
        return Util.execute_with_retry(lambda: self.__browser.find_elements_by_xpath(field), timeout_seconds)

    def execute_script(self, script: str, element: WebElement):
        self.__browser.execute_script(script, element)


class SeleniumAction(abc.ABC):

    def __init__(self, selenium_manager: SeleniumManager, by: By, field: str):
        self._selenium_manager = selenium_manager
        self._by = by
        self._field = field

    @abc.abstractmethod
    def perform_action(self):
        pass


class UrlNavigateSeleniumAction(SeleniumAction):

    def __init__(self, selenium_manager: SeleniumManager, by: By, field: str, url: str):
        SeleniumAction.__init__(self, selenium_manager, by, field)
        self.__url = url

    def perform_action(self):
        self._selenium_manager.navigate_to(self.__url)


class LoginSeleniumAction(SeleniumAction):

    # Use these fields to verify that the login was successful by looking for stuff on a page
    # that shows a login success
    def __init__(self,
                 selenium_manager: SeleniumManager,
                 verify_login_by: By,
                 verify_login_field: str):
        SeleniumAction.__init__(self, selenium_manager, verify_login_by, verify_login_field)

    def perform_action(self):
        timeout_seconds = 300
        self._selenium_manager.find_element_by(self._by, self._field, timeout_seconds)


class ButtonClickSeleniumAction(SeleniumAction):

    def __init__(self, selenium_manager: SeleniumManager, by: By, field: str):
        SeleniumAction.__init__(self, selenium_manager, by, field)

    def perform_action(self):
        self._selenium_manager.find_element_by(self._by, self._field).click()


def jsonDefault(OrderedDict):
    return OrderedDict.__dict__


@attr.s(frozen=True)
class Album:

    title = attr.ib(type=str)
    elements = attr.ib(type=int)
    album_url = attr.ib(type=str)
    cover_image_url = attr.ib(type=str)


ALBUMS_JSON_PATH = "albums.json"


def scrape_html():
    base_url = "https://photos.google.com/albums"
    login_button_id = "js-hero-btn"
    password_field_xpath = "//input[@type='password']"
    album_xpath = ".//a[@class='MTmRkb']"
    album_title_xpath = ".//div[@class='mfQCMe']"
    elements_xpath = ".//div[@class='UV4Xae']"
    album_cover_xpath = ".//div[@class='FLmEnf']"

    # Instantiate class
    selenium_manager = SeleniumManager()

    # Perform actions
    actions = [
        UrlNavigateSeleniumAction(
            selenium_manager,
            By.ID,
            login_button_id,
            base_url),
        LoginSeleniumAction(
            selenium_manager,
            By.XPATH,
            password_field_xpath),
        LoginSeleniumAction(
            selenium_manager,
            By.XPATH,
            album_xpath),
    ]

    # Go to album page
    print("Going to albums page")
    selenium_manager.open_browser()
    for action in actions:
        action.perform_action()

    # Extract the elements for all
    print("Retrieving first set of album elements")
    album_elements = selenium_manager.find_elements_by_xpath(album_xpath)

    # Build album for each one
    albums = OrderedDict()  # Because Python doesn't have OrderedSet by default
    while True:
        cur_album_element = None
        albums_added = 0
        print("Found " + str(len(album_elements)) + " albums")
        for album_element in album_elements:
            cur_album_element = album_element

            # Get album title
            album_title_element = album_element.find_element_by_xpath(album_title_xpath)
            album_title = album_title_element.text

            # Get number of elements in album
            elements_element = album_element.find_element_by_xpath(elements_xpath)
            elements = int(re.sub("[^0-9]", "", elements_element.text))

            # Extract link
            link = album_element.get_attribute("href").replace("photosgooglecom", "photos.google.com")

            # Extract album cover image url
            album_cover_image_element = album_element.find_element_by_xpath(album_cover_xpath)
            image_url = album_cover_image_element.get_attribute("style") \
                .replace("background-image: url(\"", "").replace("\");", "")

            # Add to set
            cur_album = Album(album_title, elements, link, image_url)
            if cur_album not in albums:
                albums[cur_album] = None
                albums_added += 1

        # Stop if nothing new got added
        if albums_added == 0:
            break
        print("Added " + str(albums_added) + " albums")

        # Scroll for more and find new elements
        if cur_album_element is None:
            break
        selenium_manager.execute_script("arguments[0].scrollIntoView(true);", cur_album_element)

        # Wait for page to load after scrolling.  If I knew what element to wait for I would have done that instead.
        sleep_time = 10
        print("Sleeping for " + str(sleep_time) + " seconds")
        sleep(sleep_time)
        album_elements = selenium_manager.find_elements_by_xpath(album_xpath)

    # Clean up browser
    selenium_manager.close_browser()

    # Write outputs
    print("Writing " + str(len(albums)) + " to " + ALBUMS_JSON_PATH)
    out_file = open(ALBUMS_JSON_PATH, "w")
    out_file.write(json.dumps(list(reversed(list(albums.keys()))), default=jsonDefault, indent=4))
    out_file.close()

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
    parser.add_argument("-s", "--scrape", action="store_true", help="Scrapes Google Photos and downloads album info")
    parser.add_argument("-g", "--generate", action="store_true", help="Generates a photo album page")
    parsed_input = parser.parse_args(sys.argv[1:])

    if not parsed_input.scrape and not parsed_input.generate:
        parser.error("At least one option must be selected")

    if parsed_input.scrape:
        scrape_html()
    if parsed_input.generate:
        generate_page()


__main__()
