import sys
import os
import re
import logging

import urllib
import urllib2
import json

from pprint import pprint
from zipfile import ZipFile

from defaultconfig import VERSION

def check_status():
    """
    This function is used to check for updates and disable the script remotely when needed (something broke, important updates, etc.)
    """

    logging.info("Checking script status and if there are any updates...")
    
    latest_version = int(urllib2.urlopen("https://raw.github.com/brucevdkooij/jinni-tools/stable/VERSION").read().strip())
    if VERSION < latest_version: 
        logging.warning("There is a newer version {0} available...".format(latest_version))
        response = raw_input("Do you want to download and extract the new version [Y/n]? ")
        
        if response in ["", "Y", "y"]:
            logging.info("Downloading the new version...")
            download_new_version()
        else:
            logging.info("OK, maybe later...")
    
    status = json.load(
        urllib2.urlopen("http://jinni.parsed.nl/jinni-tools/status?{0}".format(
            urllib.urlencode({
                "version": VERSION
            }))))
    
    if status["status"] == "disabled":
        logging.critical("Script has been remotely disabled: {0}. Exiting...".format(status["message"]))
        sys.exit()
    elif status["status"] == "green":
        logging.info(status["message"])

def download_new_version():
    (tempfile, message) = download_with_progressbar(
        "https://github.com/brucevdkooij/jinni-tools/zipball/stable"
    )
    
    # Extract everything except `config.py`
    zipfile = ZipFile(tempfile, "r")
    
    for member in zipfile.namelist():
        path = os.path.sep.join(member.rstrip(os.path.sep).split(os.path.sep)[1:])
        if path in ["", "jinni-imdb-import/config.py"]: continue
        target_path = os.path.join(
            os.path.sep.join(os.path.abspath(__file__).split(os.path.sep)[:-2]), # i.e. jinni-tools
            path)
        logging.info("Extracting {0}...".format(path))
        zipfile.extract(member, target_path)
    
    logging.info("Finished extracting...")
    
def download_with_progressbar(url, filename=None):
    from progressbar import ProgressBar
    
    def reporthook(count, block_size, total_size):
        progress_bar.maxval = total_size
        
        if count * block_size > total_size:
            progress_bar.update(total_size)
        else:
            progress_bar.update(count * block_size)
    
    progress_bar = ProgressBar()
    
    progress_bar.start()
    response = urllib.urlretrieve(url, filename, reporthook=reporthook)
    progress_bar.finish()
    
    return response

def htmlentitydecode(s):
    """
    Special characters in IMDB titles in the exported CSV are encoded, we have to use this to reverse the process.
    
    TODO: there's probably something better in urlparse.parse_qs
    """
    return re.sub("&#x(.+?);", 
        lambda m: unichr(int("0x{0}".format(m.group(1)), 0)), s)
        
"""
Helper functions for parsing JavaScript
"""

def convert(node, result={}, key="", depth=0):
    """
    This not completely finished function converts a PyNarcissus JavaScript parse tree to a Python dictionary for easier traversal
    """
    #~ print "{0}{1}".format(" " * (depth * 4), node.type)
    
    if node.type == "SCRIPT":
        for sub_node in node: convert(sub_node, depth=depth + 1)
    elif node.type == "VAR": 
        for sub_node in node: convert(sub_node, depth=depth + 1)
    elif node.type == "IDENTIFIER": 
        if hasattr(node, "initializer"):
            result[node.value] = None
            convert(node.initializer, result, node.value, depth=depth + 1)
        else:
            pass
    elif node.type == "OBJECT_INIT": 
        result[key] = {}
        for sub_node in node: convert(sub_node, result, key, depth=depth + 1)
    elif node.type == "PROPERTY_INIT": 
        key_node, value_node = node[0], node[1]
        result[key][key_node.value] = None
        convert(value_node, result[key], key_node.value, depth=depth + 1)
    elif node.type == "ARRAY_INIT": 
        result[key] = []
        for sub_node in node: convert(sub_node, result, key, depth=depth + 1)
    elif node.type == "FALSE" or node.type == "TRUE": pass
    elif node.type == "STRING": 
        if type(result[key]) == list: result[key].append(node.value)
        else: result[key] = node.value
    elif node.type == "NUMBER": 
        if type(result[key]) == list: result[key].append(node.value)
        else: result[key] = node.value
    elif node.type == "NULL": 
        if type(result[key]) == list: result[key].append(None)
        else: result[key] = None

    return result

def evaluate(node, tree):
    if node.type == "SCRIPT":
        for sub_node in node: evaluate(sub_node, tree)
    elif node.type == "SEMICOLON":
        evaluate(node.expression, tree)
    elif node.type == "ASSIGN":
        if node.value == "=":
            identifier_node, value_node = node[0], node[1]
            left_hand_node = identifier_node[0]
            right_hand_node = identifier_node[1]
            
            if identifier_node.type == "DOT":
                if value_node.type == "IDENTIFIER":
                    tree[left_hand_node.value][right_hand_node.value] = tree[value_node.value]
                else:
                    tree[left_hand_node.value][right_hand_node.value] = value_node.value
            
            elif identifier_node.type == "INDEX":
                try:
                    if value_node.type == "IDENTIFIER":
                        tree[left_hand_node.value][right_hand_node.value] = tree[value_node.value]
                    else:
                        tree[left_hand_node.value][right_hand_node.value] = value_node.value
                except IndexError:
                    while len(tree[left_hand_node.value]) < (right_hand_node.value + 1):
                        tree[left_hand_node.value].append("")
                    
                    if value_node.type == "IDENTIFIER":
                        tree[left_hand_node.value][right_hand_node.value] = tree[value_node.value]
                    else:
                        tree[left_hand_node.value][right_hand_node.value] = value_node.value
