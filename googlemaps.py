# -*- coding: utf-8 -*-
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webelement import WebElement
import pandas as pd
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
import logging
import traceback
import numpy as np
import itertools
from urllib.parse import unquote
from urllib import parse

GM_WEBPAGE = 'https://www.google.com/maps/'
MAX_WAIT = 10
MAX_RETRY = 5
MAX_SCROLLS = 40

class GoogleMapsScraper:

    def __init__(self, debug=False):
        self.debug = debug
        self.driver = self.__get_driver()
        self.logger = self.__get_logger()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_value, tb)

        self.driver.close()
        self.driver.quit()

        return True

    def sort_by(self, url, ind):

        self.driver.get(url)
        self.__click_on_cookie_agreement()

        wait = WebDriverWait(self.driver, MAX_WAIT)

        # open dropdown menu
        clicked = False
        tries = 0
        actions = ActionChains(self.driver)
        while not clicked and tries < MAX_RETRY:
            try:
                menu_bt: WebElement = wait.until(EC.presence_of_element_located((By.XPATH,
                                                                                 "//button[@data-value='Sort']")))
                actions.move_to_element(menu_bt).perform()
                menu_bt.click()
                clicked = True
                time.sleep(3)
            except Exception as e:
                tries += 1
                self.logger.warn('Failed to click sorting button')

            # failed to open the dropdown
            if tries == MAX_RETRY:
                return -1

        #  element of the list specified according to ind
        recent_rating_bt = self.driver.find_elements("xpath", '//div[@role=\'menuitemradio\']')[ind]
        actions.move_to_element(recent_rating_bt).perform()
        recent_rating_bt.click()

        # wait to load review (ajax call)
        time.sleep(5)

        return 0

    def get_places(self, method='urls', keyword_list=None):

        df_places = pd.DataFrame()

        if method == 'urls':
            # search_point_url = row['url']  # TODO:
            pass
        if method == 'squares':
            search_point_url_list = self._gen_search_points_from_square(keyword_list=keyword_list)
        else:
            # search_point_url = f"https://www.google.com/maps/search/{row['keyword']}/@{str(row['longitude'])},{str(row['latitude'])},{str(row['zoom'])}z"
            # TODO:
            pass

        for i, search_point_url in enumerate(search_point_url_list):

            if (i + 1) % 10 == 0:
                print(f"{i}/{len(search_point_url_list)}")
                df_places = df_places[
                    ['search_point_url', 'href', 'name', 'rating', 'num_reviews', 'close_time', 'other',
                     'location_name']]
                df_places.to_csv('output/places_wax.csv', index=False)

            try:
                self.driver.get(search_point_url)
            except NoSuchElementException:
                self.driver.quit()
                self.driver = self.__get_driver()
                self.driver.get(search_point_url)

            # Gambiarra to load all places into the page
            scrollable_div = self.driver.find_element_by_css_selector(
                "div[aria-label*='Results for']")
            for i in range(10):
                self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)

            # Get places names and href
            # time.sleep(2)
            response = BeautifulSoup(self.driver.page_source, 'html.parser')
            div_places = response.select('div[jsaction] > a[href]')
            # print(len(div_places))
            for div_place in div_places:
                location_name = div_place['href']
                location_name = location_name.replace('https://www.google.com/maps/place/', '')
                location_name = unquote(location_name.split('/')[0])
                location_name = re.sub('\+', ' ', location_name)
                place_info = {
                    'search_point_url': search_point_url.replace('https://www.google.com/maps/search/', ''),
                    'href': div_place['href'],
                    'name': div_place['aria-label'],
                    'rating': None,
                    'num_reviews': None,
                    'close_time': None,
                    'other': None,
                    'location_name': location_name,
                }

                df_places = df_places.append(place_info, ignore_index=True)
        df_places = df_places[
            ['search_point_url', 'href', 'name', 'rating', 'num_reviews', 'close_time', 'other', 'location_name']]
        df_places.to_csv('output/places_wax.csv', index=False)
        self.driver.quit()

    def _gen_search_points_from_square(self, keyword_list=None):
        # TODO: Generate search points from corners of square

        keyword_list = [] if keyword_list is None else keyword_list

        square_points = pd.read_csv('input/square_points.csv')

        cities = square_points['city'].unique()

        search_urls = []

        for city in cities:

            df_aux = square_points[square_points['city'] == city]
            latitudes = np.linspace(df_aux['latitude'].min(), df_aux['latitude'].max(), num=20)
            longitudes = np.linspace(df_aux['longitude'].min(), df_aux['longitude'].max(), num=20)
            coordinates_list = list(itertools.product(latitudes, longitudes, keyword_list))

            search_urls += [f"https://www.google.com/maps/search/{coordinates[2]}/@{str(coordinates[1])},{str(coordinates[0])},{str(15)}z"
             for coordinates in coordinates_list]

        return search_urls



    def get_reviews(self, offset, url):

        # scroll to load reviews

        # wait for other reviews to load (ajax)
        time.sleep(4)

        self.__scroll()


        # expand review text
        self.__expand_reviews()

        # parse reviews
        response = BeautifulSoup(self.driver.page_source, 'html.parser')
        # TODO: Subject to changes
        rblock = response.find_all('div', class_=('jftiEf', 'fontBodyMedium'))
        parsed_reviews = []
        for index, review in enumerate(rblock):
            if index >= offset:
                parsed_reviews.append(self.__parse(review, url))

                # logging to std out
                print(self.__parse(review, url))

        return parsed_reviews


    def get_account(self, url):

        self.driver.get(url)

        # ajax call also for this section
        time.sleep(4)

        resp = BeautifulSoup(self.driver.page_source, 'html.parser')

        place_data = self.__parse_place(resp)

        return place_data


    def __parse(self, review, url):

        item = {}


        try:
            # TODO: Subject to changes
            id_review = review['data-review-id']
        except Exception as e:
            id_review = None

        try:
            # TODO: Subject to changes
            username = review['aria-label']
        except Exception as e:
            username = None

        try:
            # TODO: Subject to changes
            review_text = self.__filter_string(review.find('span', class_='wiI7pd').text)
        except Exception as e:
            review_text = None

        try:
            # TODO: Subject to changes
            rating = review.find('span', class_='kvMYJc')
            rat = rating.get('aria-label')
            rat = rat.replace('stars', '')
            rat = rat.replace('star', '')
            rating = rat
        except Exception as e:
            rating = None

        try:
            # TODO: Subject to changes
            relative_date = review.find('span', class_='rsqaWe').text
        except Exception as e:
            relative_date = None

        try:
            n_reviews_photos = review.find('img', class_='NBa7we')
            src = n_reviews_photos.get('src')
            n_photos = src

        except Exception as e:
            n_photos = 0

        try:
            user_url = review.find('a')['href']
        except Exception as e:
            user_url = None

        try:
            all_params = parse.urlparse(url)
            query = all_params.query
            substr = '&place='
            params = query.split(substr)
            place_id = params[1]
        except Exception as e:
            place_id = None

        item['id_review'] = id_review
        item['caption'] = review_text

        # depends on language, which depends on geolocation defined by Google Maps
        # custom mapping to transform into date should be implemented
        item['relative_date'] = relative_date

        # store datetime of scraping and apply further processing to calculate
        # correct date as retrieval_date - time(relative_date)
        item['retrieval_date'] = datetime.now()
        item['rating'] = rating
        item['username'] = username
#         item['n_review_user'] = n_reviews
        item['n_photo_user'] = n_photos

        str = url.replace('https://www.google.com/maps/place/', '')
        idx = str.find('/data')
        ns = str[:idx]
        ns = ns.replace('++', ' ')
        ns = ns.replace('+', ' ')

        item['n_url'] = ns
        item['place_id'] = place_id
        item['url_user'] = user_url

        return item


    def __parse_place(self, response):

        place = {}
        try:
            place['overall_rating'] = float(response.find('div', class_='gm2-display-2').text.replace(',', '.'))
        except:
            place['overall_rating'] = 'NOT FOUND'

        try:
            place['n_reviews'] = int(response.find('div', class_='gm2-caption').text.replace('.', '').replace(',','').split(' ')[0])
        except:
            place['n_reviews'] = 0

        return place

    # expand review description
    # def __expand_reviews(self):
    #     # use XPath to load complete reviews
    #     # TODO: Subject to changes
    #     links = self.driver.find_elements(By.XPATH, '//button[@jsaction="pane.review.expandReview"]')

    #     for l in links:
    #         l.click()
    #         time.sleep(2)

    def __expand_reviews(self):
        # Use explicit wait to wait for the buttons to be clickable
        wait = WebDriverWait(self.driver, 10)
        
        # Find the expand review buttons
        links = wait.until(EC.presence_of_all_elements_located((By.XPATH, '//button[@jsaction="pane.review.expandReview"]')))
        print(len(links))
        for l in links:
            try:
                # Scroll to the element
                self.driver.execute_script("arguments[0].scrollIntoView();", l)
                
                # Wait for the element to be clickable
                wait.until(EC.element_to_be_clickable((By.XPATH, '//button[@jsaction="pane.review.expandReview"]')))
                
                # Click on the element
                l.click()
                
                # Wait briefly to allow content to load
                time.sleep(2)
            except Exception as e:
                # Handle any exceptions that might occur during the process
                print("Error:", e)




    def __scroll(self):
        # TODO: Subject to changes
        scrollable_div = self.driver.find_element("css selector", "div.m6QErb.DxyBCb.kA9KIf.dS8AEf")
        self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
        #self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")


    def __get_logger(self):
        # create logger
        logger = logging.getLogger('googlemaps-scraper')
        logger.setLevel(logging.DEBUG)

        # create console handler and set level to debug
        fh = logging.FileHandler('gm-scraper.log')
        fh.setLevel(logging.DEBUG)

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # add formatter to ch
        fh.setFormatter(formatter)

        # add ch to logger
        logger.addHandler(fh)

        return logger


    def __get_driver(self, debug=False):
        options = Options()

        if not self.debug:
            options.add_argument("--headless")
        else:
            options.add_argument("--window-size=1366,768")

        options.add_argument("--disable-notifications")
        options.add_argument("--lang=en-GB")
        input_driver = webdriver.Chrome(options=options)

         # click on google agree button so we can continue (not needed anymore)
         # EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "I agree")]')))
        input_driver.get(GM_WEBPAGE)

        return input_driver

    # cookies agreement click
    def __click_on_cookie_agreement(self):
        try:
            agree = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "Reject all")]')))
            agree.click()

            # back to the main page
            # self.driver.switch_to_default_content()

            return True
        except:
            return False

    # util function to clean special characters
    def __filter_string(self, str):
        strOut = str.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
        return strOut
