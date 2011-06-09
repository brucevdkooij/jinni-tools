# -*- coding: utf-8 -*-

import sys
sys.exit("NOTE: Script disabled, see: https://github.com/brucevdkooij/jinni-tools")

import os
import sys
import re
import time
import math
import argparse
import json

import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s: %(asctime)s %(message)s"
)

import csv
import unicode_csv

import urllib
import urllib2
import cookielib

import lxml.html
import lxml.html.soupparser

from defaultconfig import *
from config import *

from collections import namedtuple
from pprint import pprint

from helpers import check_status, convert, evaluate, htmlentitydecode
from libs.jsparser import parse as parse_js

data_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# We need a cookiejar to login and store the session tokens
cj = cookielib.LWPCookieJar()
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
opener.addheaders = [("User-agent", USER_AGENT)]

# Just a helper function to throttle requests
last_request_time = 0
def open_url(request):
    global last_request_time
    
    current_time = time.time()
    difference = current_time - last_request_time

    if difference < THROTTLE_AMOUNT:
        time.sleep(THROTTLE_AMOUNT - difference)
    
    response =  opener.open(request)
    last_request_time = time.time()
    
    return response

# This maps Jinni's textual ratings to IMDB numerical ratings (1-10)
jinni_imdb_rating_map = {
    "terrible": 0, # FIXME: not sure what to do with this, wasn't expecting there to be a 0 rating...
    "awful": 1,
    "bad": 2,
    "poor": 3,
    "disappointing": 4,
    "so-so": 5,
    "okay": 6,
    "good": 7,
    "great": 8,
    "amazing": 9,
    "must see": 10
}

# And the reverse (IMDB numerical ratings to Jinni's textual ratings)
imdb_jinni_ratings_map = dict((v,k) for k, v in jinni_imdb_rating_map.iteritems())

# Class for storing ratings parsed from the ratings page
Rating = namedtuple("Rating", ["jinni_id", "title", "digitRate", "textualRate", "ratingDate"])

def jinni_login():
    logging.info("Logging in...")
    
    url = "https://www.jinni.com/jinniLogin"
    values = {
        "user": JINNI_USERNAME,
        "pass": JINNI_PASSWORD,
        "rememberme": "true",
        "loginOverlayURL": "",
        "loginSource": "loginOverlay"
    }
    
    # TODO: display a message if authentication credentials are incorrect, note that if authentication fails a HTTP 500 error is returned
    data = urllib.urlencode(values)
    request = urllib2.Request(url, data)
    response = open_url(request)
    content = response.read()

def jinni_submit_rating(rating, title_id):
    logging.info("Submitting rating...")
    
    url = "http://www.jinni.com/dwr/call/plaincall/AjaxUserRatingBean.submiteContentUserRating.dwr"
    
    values = {
        "callCount": "1",
        "page": "",
        # TODO: not exactly the most elegant way to get a specific cookie
        "httpSessionId": [cookie.value for cookie in cj if cookie.name == "JSESSIONID"][0],
        "scriptSessionId": "",
        "c0-scriptName": "AjaxUserRatingBean",
        "c0-methodName": "submiteContentUserRating",
        "c0-id": "0",
        "c0-param0": "number:{0}".format(title_id), # this the title id
        "c0-param1": "number:{0}".format(rating), # this is the rating
        "batchId": "0" # can differ per request (0, 1, 2 etc.)
    }
    
    data = urllib.urlencode(values)
    request = urllib2.Request(url, data)
    response = open_url(request)
    content = response.read()

    # response:

    #~ //#DWR-INSERT
    #~ //#DWR-REPLY
    #~ dwr.engine._remoteHandleCallback('0','0',"Thank you for rating");

def jinni_fetch_title_by_id(id):
    url = "http://www.jinni.com/discovery.html"
    values = {
        "content": "All",
        "search": "[{0}]T".format(id),
        "auditTextSearch": "",
        "auditSuggestions": "",
        "auditSelected": "",
        "filterWatched": "False"
    }
    
    data = urllib.urlencode(values)
    request = urllib2.Request(url, data)
    response = open_url(request)
    content = response.read()
    document = lxml.html.soupparser.fromstring(content)
    
    return document

def jinni_export_ratings(jinni_ratings_file_path):
    """
    Getting a user their ratings requires authentication.
    
    While getting the first page of ratings after authenticating is easy (simply request `http://www.jinni.com/user/{username}/ratings/`), getting consecutive pages is not so much. 
    
    The Jinni website uses the Direct Web Remoting (DWR) Java library that enables Java on the server and JavaScript in a browser to interact and call each other.
    
    To get consecutive ratings you have to send a POST request with a valid `javax.faces.ViewState` value.
    
    """
    
    logging.info("Exporting ratings...")
    
    url = "http://www.jinni.com/user/{0}/ratings/".format(JINNI_USERNAME)
    
    request = urllib2.Request(url)
    response = open_url(request)
    content = response.read()
    # NOTE: For some reason neither lxml nor BeautifulSoup manage to handle decoding the ratings page properly (when special characters are present, e.g. `é`).
    # Using lxml.html.parser: UnicodeDecodeError: 'ascii' codec can't decode byte 0xc3 in position 65766: ordinal not in range(128)
    #~ document = lxml.html.parse(content)
    document = lxml.html.soupparser.fromstring(content.decode("utf-8")) # ... so decode it before passing it to the parser
    ratings = jinni_parse_ratings_page(document)
    
    # Calculate the number of pages (by default Jinni displays 50 results per page)
    scroller_text = document.cssselect("#userRatingForm .scrollerText")[0].text_content()
    total_number_of_results = int(re.findall("[0-9]+", scroller_text)[-1])
    number_of_pages = math.ceil(total_number_of_results / 50.0)
    
    if number_of_pages > 1:
        for i in range(1, int(number_of_pages)):
            index = i + 1
            
            logging.info("Fetching another ratings page...")
            
            # Fetching consecutive pages requires passing along the viewstate
            viewstate = document.xpath('//input[@name="javax.faces.ViewState"]')[0].value
            values = {
                "userRatingForm": "userRatingForm",
                "javax.faces.ViewState": viewstate,
                # idx stands for index and represent the page number
                "userRatingForm:j_id268idx{0}".format(index): "userRatingForm:j_id268idx{0}".format(index),
                "userRatingForm:j_id268": "idx{0}".format(index)
            }
            
            data = urllib.urlencode(values)
            request = urllib2.Request(url, data)
            response = open_url(request)
            content = response.read()
            document = lxml.html.soupparser.fromstring(content.decode("utf-8"))
            
            ratings.extend(jinni_parse_ratings_page(document))
            
    # Export the ratings to CSV
    jinni_ratings_file = open(jinni_ratings_file_path, "wb")
    writer = unicode_csv.UnicodeDictWriter(jinni_ratings_file, fieldnames=Rating._fields)
    writer.writeheader()
    writer.writerows([rating._asdict() for rating in ratings])
    
def jinni_parse_ratings_page(document):
    ratings = []
    for rating_row in document.cssselect("#userRatingForm li"):
        # Can't use the content in the element with the .title class because in it the title is elipsed (shortened)
        title = rating_row.cssselect(".title")[0].getparent().get("title")

        try:
            digitRate = rating_row.cssselect(".digitRate")[0].text.strip()
            digitRate = int(digitRate[:digitRate.find("/")])
            textualRate = imdb_jinni_ratings_map[digitRate]
        except ValueError, ex:
            # There are two non-numerical ratings that appear in a users ratings: "Likely to see" and "Not for me"
            digitRate = ""
            if len(rating_row.cssselect(".likekyToSee")) > 0: 
                textualRate = "likely to see" 
            elif len(rating_row.cssselect(".notForMe")) > 0:
                textualRate = "not for me" 
            
        ratingDate = rating_row.cssselect(".ratingDate")[0].text.strip()
        
        # Easiest way to get the id for the title is to parse it out of the onclick attribute for the rate "button". However, (robustly) selecting it isn't exactly easy.
        jinni_id = None
        for span in rating_row.cssselect("span"):
            id = span.get("id")
            if id is not None and id.startswith("rateButton"):
                jinni_id = re.findall("[0-9]+", span.get("onclick"))[1]
                break
        
        ratings.append(Rating(jinni_id, title, digitRate, textualRate, ratingDate))
        
    return ratings
    
def jinni_findSuggestionsWithFilters(query):
    logging.info(u'Doing a suggestion search for "{0}"...'.format(query))
    
    url = "http://www.jinni.com/dwr/call/plaincall/AjaxController.findSuggestionsWithFilters.dwr"
    values = {
        # Both the httpSessionId and scriptSessionId need to be submitted
        # or the server will respond with a "HTTP Error 501: Not Implemented".
        # However, they are not validated.
        # FIXME: when logged in for some reason you do need to send along a valid httpSessionId
        "httpSessionId": [cookie.value for cookie in cj if cookie.name == "JSESSIONID"][0],
        "scriptSessionId": "", # i.e. 3C675DDBB02222BE8CB51E2415259E99878
        "callCount": "1",
        "page": "/discovery.html",
        "c0-scriptName": "AjaxController",
        "c0-methodName": "findSuggestionsWithFilters",
        "c0-id": "0",
        "c0-param0": "string:{0}".format(query.encode("utf-8")),
        "c0-e1": "null:null",
        "c0-e2": "boolean:false",
        "c0-e3": "boolean:false",
        "c0-e4": "boolean:false",
        "c0-e5": "Array:[]",
        "c0-param1": "Object_Object:{contentTypeFilter:reference:c0-e1, onlineContentFilter:reference:c0-e2, dvdContentFilter:reference:c0-e3, theaterContentFilter:reference:c0-e4, contentAffiliates:reference:c0-e5}",
        "batchId": "2"
    }
    
    data = urllib.urlencode(values)
    request = urllib2.Request(url, data)
    response = open_url(request)
    content = response.read()
    
    js_tree = parse_js(content)
    tree = convert(js_tree)
    evaluate(js_tree, tree)
    
    results = tree["s1"]
    
    return results
    
def jinni_search(query):
    logging.info(u'Doing a normal search for "{0}"'.format(query))
    
    # File "/usr/lib/python2.6/urllib.py", line 1269, in urlencode
    #  v = quote_plus(str(v))
    # UnicodeEncodeError: 'ascii' codec can't encode character u'\xe9' in position 1: ordinal not in range(128)
    #
    # See: http://mail.python.org/pipermail/baypiggies/2007-April/002102.html
    url = "http://www.jinni.com/discovery.html?{0}".format(urllib.urlencode({
        "query": query.encode("utf-8")
    }))
    
    request = urllib2.Request(url)
    response = open_url(request)
    content = response.read()
    document = lxml.html.soupparser.fromstring(content)
    
    # Find the script tag that contains the search results and parse it
    try:
        script_text = [script.text for script in document.xpath('//script[not(@src)]') 
            if "obj_collageEntry" in script.text][0]
        # PyNarcissus doesn't handle unicode properly:
        # 
        # File "jsparser.py", line 197, in __init__
        #   self.source = str(s)
        # UnicodeEncodeError: 'ascii' codec can't encode characters in position 31704-31706: ordinal not in range(128)
        # 
        # So encoding to UTF-8 first
        js_tree = parse_js(script_text.encode("utf-8"))
        results = convert(js_tree).values()
    except IndexError, ex:
        # No search results available
        results = []
    
    return results

def import_imdb_ratings(imdb_ratings_file_path, jinni_ratings_file_path):
    # The IMDB CSV export starts with an empty line which isn't good for using with 
    # csv.DictReader, so fix it up first by stripping all empty lines.
    # TODO: this certainly could be done more elegantly...
    ratings = [line for line in open(imdb_ratings_file_path, "rb").readlines() if line.strip() != ""]
    open(imdb_ratings_file_path, "wb").writelines(ratings)
    imdb_ratings = unicode_csv.UnicodeDictReader(open(imdb_ratings_file_path, "rb"))
    
    # Read in the exported Jinni ratingss
    jinni_ratings_file = os.path.join(data_directory, jinni_ratings_file_path)
    jinni_ratings = unicode_csv.UnicodeDictReader(open(jinni_ratings_file, "rb"))
    jinni_ratings = [jinni_rating for jinni_rating in jinni_ratings]
    jinni_titles = set([jinni_rating["title"].lower() for jinni_rating in jinni_ratings])
    jinni_ids = set([jinni_rating["jinni_id"] for jinni_rating in jinni_ratings])
    
    # A CSV for saving any mismatches
    mismatches_file = open(os.path.join(data_directory, "mismatches.csv"), "wb")
    mismatches_csv = unicode_csv.UnicodeDictWriter(mismatches_file, fieldnames=["position", "id", "created", "modified", "description", "your_rating", "title", "imdb_rating", "runtime", "year", "genres", "num_votes"])
    mismatches = []

    for imdb_rating in imdb_ratings:
        imdb_title = htmlentitydecode(imdb_rating["title"])
        
        # TODO: check Jinni export for match before searching?
        
        search_results = jinni_search(u"{0} {1}".format(imdb_title, imdb_rating["year"]))
        
        if len(search_results) == 0:
            logging.error(u'No search results for "{0}"...'.format(imdb_title))
            mismatches.append(imdb_rating)
        else:
            match = None
            for search_result in search_results:
                try:
                    if imdb_rating["id"] == search_result["affiliates"]["IMDB"]["affiliateContentIds"]["key"]:
                        match = search_result
                        break
                except KeyError, ex:
                    continue
                    
            if match:
                logging.info(u'Submitting rating for "{0}" (Jinni id: {1})...'.format(imdb_title, search_result["DBID"]))
                jinni_submit_rating(imdb_rating["your_rating"], search_result["DBID"])
            else:
                # TODO: try a suggestion search before giving up?
                logging.error(u'Could not find a match for "{0}"...'.format(imdb_title))
                mismatches.append(imdb_rating)
    
    mismatches_csv.writeheader()
    mismatches_csv.writerows(mismatches)

def main():
    parser = argparse.ArgumentParser(description="Import your exported IMDB ratings into Jinni.")
    
    parser.add_argument(
        "--imdb-ratings-file",
        dest = "imdb_ratings_file_path",
        default=os.path.join(data_directory, "imdb_ratings.csv"),
        help="Path to the CSV export of your IMDB ratings (i.e. imdb_ratings.csv)")
        
    parser.add_argument(
        "--jinni-ratings-file",
        dest = "jinni_ratings_file_path",
        default=os.path.join(data_directory, "jinni_ratings.csv"),
        help="Path to the CSV export of your Jinni ratings (i.e. jinni_ratings.csv)")
        
    args = parser.parse_args()
    
    check_status()
    jinni_login()
    #~ jinni_export_ratings(args.jinni_ratings_file_path)
    import_imdb_ratings(args.imdb_ratings_file_path, args.jinni_ratings_file_path)

if __name__ == "__main__":
    main()
