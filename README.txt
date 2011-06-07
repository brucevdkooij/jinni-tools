*** This script doesn't work on Windows (yet) -- see: https://github.com/brucevdkooij/jinni-tools/issues/2***

This script isn't perfect, I'm making no guarantees it will work for you. 

Feel free to report any issues on https://github.com/brucevdkooij/jinni-tools/issues

How the script works:

  1. It reads in a CSV export of your IMDB ratings
  2. It reads in your ratings on Jinni to skip movies from IMDB you've already rated
  3. The script uses Jinni's suggestion search to find a potential match
  3. It verifies the match by comparing the IMDB link on the Jinni result page
  4. It submits the rating

Module requirements:

 - lxml: for parsing HTML
 - python-spidermonkey: for parsing the JavaScript returned by the Jinni suggestion search
 - BeautifulSoup: required for parsing Jinni's ratings page

Installing and running the program:

  1. Download and install Python 2.7.x (not Python 3.x).
  2. Download setuptools (http://pypi.python.org/pypi/setuptools)
  3. Use easy_install to install lxml, python-spidermonkey and BeautifulSoup
  
  4. Export your IMDB ratings to CSV manually at http://www.imdb.com/list/export?list_id=ratings (save it as `ratings.csv` in the data subdirectory)
  5. Open up config.py and enter your username and password
  6. Run the script using main.py

Note that your ratings won't appear until after you've logged out and back in of Jinni (this is likely because Jinni maintains viewstate on the server per session).

Also note that your Jinni ratings will be exported into the data subdirectory as jinni_ratings.csv
