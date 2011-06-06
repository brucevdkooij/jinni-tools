# -*- coding: utf-8 -*-

import os
import sys
import time
import math

import logging

import csv
import unicode_csv

import urllib
import urllib2
import cookielib

import lxml.html
import lxml.html.soupparser

import config

from collections import namedtuple

# Special characters in IMDB titles in the exported CSV are encoded, we have to use this to reverse the process.
# TODO: there's probably something better in urlparse.parse_qs
import re
def htmlentitydecode(s):
    return re.sub("&#x([0-9]+);", 
        lambda m: chr(int("0x{0}".format(m.group(1)), 0)), s)

data_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s: %(asctime)s %(message)s"
)

# We need a cookiejar to login and store the session tokens
cj = cookielib.LWPCookieJar()
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
opener.addheaders = [("User-agent", config.USER_AGENT)]

# Just a helper function to throttle requests
last_request_time = 0
def open_url(request):
    global last_request_time
    
    current_time = time.time()
    difference = current_time - last_request_time

    if difference < config.THROTTLE_AMOUNT:
        time.sleep(config.THROTTLE_AMOUNT - difference)
    
    last_request_time = time.time()
    
    return opener.open(request)

# This maps Jinni's textual ratings to IMDB numerical ratings (1-10)
jinni_imdb_rating_map = {
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

Rating = namedtuple("Rating", ["jinni_id", "title", "digitRate", "textualRate", "ratingDate"])

def jinni_login():
    logging.info("Logging in...")
    
    url = "https://www.jinni.com/jinniLogin"
    values = {
        "user": config.JINNI_USERNAME,
        "pass": config.JINNI_PASSWORD,
        "rememberme": "true",
        "loginOverlayURL": "",
        "loginSource": "loginOverlay"
    }
    
    # TODO: it seems that if authentication fails a HTTP 500 error is returned
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

def jinni_export_ratings():
    """
    Getting a user their ratings requires authentication.
    
    While getting the first page of ratings after authenticating is easy (simply request `http://www.jinni.com/user/{username}/ratings/`), getting consecutive pages is not so much. 
    
    The Jinni website uses the Direct Web Remoting (DWR) Java library that enables Java on the server and JavaScript in a browser to interact and call each other.
    
    To get consecutive ratings you have to send a POST request with a valid `javax.faces.ViewState` value.
    
    """
    
    logging.info("Exporting ratings...")
    
    url = "http://www.jinni.com/user/{0}/ratings/".format(config.JINNI_USERNAME)
    
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
            document = lxml.html.soupparser.fromstring(content)
            
            ratings.extend(jinni_parse_ratings_page(document))
            
    # Export the ratings to CSV
    with open(os.path.join(data_directory, "jinni_ratings.csv"), "wb") as jinni_ratings_file:
        writer = unicode_csv.UnicodeDictWriter(jinni_ratings_file, fieldnames=Rating._fields)
        writer.writeheader()
        writer.writerows([rating._asdict() for rating in ratings])
    
def jinni_parse_ratings_page(document):
    """
    IMDB CSV: position,id,created,modified,description,your_rating,title,imdb_rating,runtime,year,genres,num_votes
    Jinni CSV: jinni_id, title, digitRate, textualRate, ratingDate
    
    Notes:
    
     - Jinni tends to use ids with the character `:` in them, such as `userRatingForm:ratingsTable`. lxml's cssselect, unlike jQuery, doesn't seem to be able to handle it properly and tries to parse it as a pseudo-class.
    """
    
    ratings = []
    for rating_row in document.cssselect("#userRatingForm li"):
        # Can't use the content in the element with the .title class because in it the title is elipsed (shortened)
        title = rating_row.cssselect(".title")[0].getparent().get("title")
        digitRate = rating_row.cssselect(".digitRate")[0].text.strip()
        digitRate = int(digitRate[:digitRate.find("/")])
        textualRate = imdb_jinni_ratings_map[digitRate]
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
    
def jinni_findSuggestionsWithFilters(search):
    logging.info("Doing a suggestion search for `{0}`...".format(search))
    
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
        "c0-param0": "string:{0}".format(search),
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
    document = response.read()
    
    # Parse the response (JavaScript)
    from spidermonkey import Runtime, JSError
    
    rt = Runtime()
    cx = rt.new_context()
    
    # Make sure the variable dwr is defined or we'll get an exception
    cx.execute("""
    var dwr = {
        engine: {
            _remoteHandleCallback: function(x, y, z) { }
        }
    }
    """)
    
    cx.execute(document)
    results = cx.execute("s1")
    
    """
    Example result:
    
    result.categoryType=null;
    result.contentType='FeatureFilm';
    result.entityType='Title';
    result.id=21951;
    result.name="One Day Like Rain";
    result.popularity=null;
    result.year=2007;
    """

    return results

def import_imdb_ratings():
    # The IMDB CSV export starts with an empty line which isn't good for using with 
    # csv.DictReader, so fix it up first by stripping all empty lines.
    # TODO: this certainly could be done more elegantly...
    imdb_ratings_file = os.path.join(data_directory, "ratings.csv")
    jinni_ratings_file = os.path.join(data_directory, "jinni_ratings.csv")
    
    ratings = [line for line in open(imdb_ratings_file, "rb").readlines() if line.strip() != ""]
    open(imdb_ratings_file, "wb").writelines(ratings)

    imdb_ratings = csv.DictReader(open(imdb_ratings_file, "rb"))
    jinni_ratings = csv.DictReader(open(jinni_ratings_file, "rb"))
    
    jinni_ratings = [jinni_rating for jinni_rating in jinni_ratings]
    jinni_titles = set([jinni_rating["title"].lower() for jinni_rating in jinni_ratings])
    jinni_ids = set([int(jinni_rating["jinni_id"]) for jinni_rating in jinni_ratings])

    for rating in imdb_ratings:
        title = htmlentitydecode(rating["title"])
        imdb_id = rating["id"]
        your_rating = rating["your_rating"]
        
        # FIXME: sometimes titles differ in IMDB and Jinni
        if title.lower() in jinni_titles:
            logging.info("Skipping title `{0}` because rating already exists in Jinni...".format(title))
            continue
        
        # Use the Jinni suggestion search to find our title
        # TODO: would be nice if we could just search using IMDB id
        suggestion = jinni_findSuggestionsWithFilters(title)[0]
        
        # Because titles sometimes differ between IMDB and Jinni, we'll also check the id from the suggestion
        
        if suggestion.id in jinni_ids:
            logging.info("Skipping title `{0}` because rating already exists in Jinni...".format(title))
            continue
        
        # Verify if the IMDB ID listed matches up
        document = jinni_fetch_title_by_id(suggestion.id)
        imdb_url = [a.get("href") for a in document.cssselect(".relatedLinks a") if a.text == "IMDb"][0]
        jinni_imdb_id = imdb_url[len("http://www.imdb.com/title/"):]
        
        if imdb_id == jinni_imdb_id:
            logging.info("Submitting rating for {0} (Jinni id: {1})...".format(title, suggestion.id))
            jinni_submit_rating(your_rating, suggestion.id)
        else:
            logging.error("IMDB id does not match up for {0} (IMDB) / {1} (Jinni) ({2} versus {3})...".format(title, suggestion.name, imdb_id, jinni_imdb_id))

def main():
    jinni_login()
    jinni_export_ratings()
    import_imdb_ratings()

if __name__ == "__main__":
    main()