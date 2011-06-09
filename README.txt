This script isn't perfect, I'm making no guarantees it will work for you. 

Note that before doing anything the script will check with a remote server if it should run and will exit if it is told to do so. I implemented this functionality to be able to remotely disable any versions of the script out in the wild if there's an important update available or if the script broke due to a change by the folks at Jinni.

Feel free to report any issues on https://github.com/brucevdkooij/jinni-tools/issues

However, make sure you are using the very latest version before asking any questions.

How the script works:

  1. It reads in a CSV export of your IMDB ratings
  2. It reads in your ratings on Jinni to skip any titles from IMDB that you've already rated
  3. The script uses Jinni's search to find a match based on the title
  4. If it finds a match it submits the rating
  
Note that your ratings won't appear until after you've logged out and back in of Jinni (this is likely because Jinni maintains viewstate on the server per session).

Also note that your Jinni ratings will be exported into the data subdirectory as `jinni_ratings.csv` and any mismatches as `mismatches.csv`.

Module requirements:

 - lxml: a Pythonic binding for the C libraries libxml2 and libxslt for parsing XML
 - BeautifulSoup: a Python HTML/XML parser designed for quick turnaround projects like screen-scraping
 - progressbar: a library that provides a text mode progressbar used to display the progress of a long running operation

Installing requirements and running the script:

The verbose instructions below are oriented towards novice Windows users. However the script was both written and tested on Ubuntu (Linux).

  1. Download and install Python 2.7.x (not Python 3.x) from http://python.org/
  
     Direct link to the 2.7.1 Windows Installer: http://python.org/ftp/python/2.7.1/python-2.7.1.msi
  
  2. Download setuptools from http://pypi.python.org/pypi/setuptools
  
     Direct link to 0.6c11 Windows Installer: http://pypi.python.org/packages/2.7/s/setuptools/setuptools-0.6c11.win32-py2.7.exe
  
  3. Use easy_install to install the module requirements
  
     Open up a command prompt (cmd.exe) using the Windows Run dialog `Windows Key + R` or by starting it from the `Accessoires` menu.
  
     Navigate to the scripts directory in the Python installation path using `cd C:\Python27\Scripts`
  
     Then execute: `easy_install lxml`, `easy_install BeautifulSoup` and `easy_install progressbar`
  
  4. Export your IMDB ratings to CSV manually
  
     Go to http://www.imdb.com/list/export?list_id=ratings and save the file as `imdb_ratings.csv` in the `data` subdirectory in the `imdb-jinni-import` directory.
  
  5. Open up `config.py` and enter your username and password
  
     Simply open `config.py` inside the directory `imdb-jinni-import` with a text editor and change `username` and `password` to your own.
  
  6. Run the script using `main.py`
  
     After installing Python you should be able to run `main.py` inside the `imdb-jinni-import` directory by double clicking it.
  
     However, you may have to use the command prompt (cmd.exe) to navigate to the imdb-jinni-import directory and then run it using `C:\Python27\python.exe main.py`

