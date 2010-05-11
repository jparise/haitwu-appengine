from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import memcache, urlfetch
from django.utils import simplejson

import calendar
import datetime
import logging
import pickle
import rfc822
import urllib

import haikufinder

# How long should users' data be stored in memcache (in seconds)?
CACHE_EXPIRATION = 3600

class User(object):

    def __init__(self, data=None, name=None, screen_name=None):
        if data is not None:
            self.id = data.get('id', None)
            self.name = data.get('name', None)
            self.screen_name = data.get('screen_name', None)
        if name is not None:
            self.name = name
        if screen_name is not None:
            self.screen_name = screen_name

class Entry(object):

    def __init__(self, data):
        self.id = data.get('id', None)
        self.text = data.get('text', None)
        self.user = User(data.get('user', None))

        created_at = data.get('created_at', None)
        if created_at is not None:
            self.timestamp = calendar.timegm(rfc822.parsedate(created_at))
        else:
            self.timestamp = None

def get_rate_limit():
    url = 'http://api.twitter.com/1/account/rate_limit_status.json'

    result = urlfetch.fetch(url, deadline=10)
    if result.status_code != 200:
        return 0

    data = simplejson.loads(result.content)
    return data.get('remaining_hits', 0)

def get_timeline(screen_name):
    if get_rate_limit() == 0:
        raise Exception("Rate Limit Exceeded")

    url = 'http://api.twitter.com/1/statuses/user_timeline.json'
    url += '?screen_name=' + urllib.quote(screen_name) + '&count=200'

    result = urlfetch.fetch(url, deadline=10)
    if result.status_code != 200:
        raise Exception("Bad HTTP result: %d" % result.status_code)

    # If we still don't have any content, just return an empty list.
    if not result.content:
        return []

    # Parse the JSON content and convert it into a list of entries.
    data = simplejson.loads(result.content)
    return [Entry(e) for e in data]

class HomePage(webapp.RequestHandler):
    def get(self):
        user = self.request.get('u')
        if not user:
            self.response.out.write(template.render('templates/home.html', {}))
            return

        self.redirect('/' + user)

class AboutPage(webapp.RequestHandler):
    def get(self):
        self.response.out.write(template.render('templates/about.html', {}))

class UserPage(webapp.RequestHandler):
    def get(self, screen_name):
        logging.info("Handling '%s'" % screen_name)

        # The error flag is used to indicate that some sort of error occurred.
        # It is treated as a generic failure by the output template.
        error = False

        # The cached flag indicates whether or not the requested user's data
        # could be loaded from memcache.
        cached = False

        # Attempt to load this user's data from the cache.
        data = memcache.get(screen_name)
        if data:
            try:
                user, haikus = pickle.loads(data)
                cached = True
                logging.debug("Loaded '%s' from cache", screen_name)
            except Exception, e:
                # We allow all failures, leaving 'cached' set to False.
                logging.error("Cache error for '%s': %s", screen_name, str(e))

        # If we have weren't able to load cached data, we need to fetch this
        # user's timeline and parse the text for haikus.
        if not cached:
            # Query for the requested user's public timeline.  If we encounter
            # any problems here, we simply treat them all as a generic
            # "nothing found" case and let the code below sort things out.
            try:
                timeline = get_timeline(screen_name)
                logging.debug("Fetched timeline for '%s'", screen_name)
            except Exception, e:
                logging.warn("Fetch error for '%s': %s", screen_name, str(e))
                error = True
                timeline = []

            # Fill out our user object.  If we didn't get any results from the
            # API query, we make a dummy object based on the screen name.
            if timeline:
                user = timeline[0].user
            else:
                user = User(name=screen_name, screen_name=screen_name)

            # Walk through all of the timeline entries looking for haikus.
            haikus = []
            for entry in timeline:
                matches = haikufinder.find_haikus(entry.text)
                if matches:
                    haiku = {
                        'lines': matches[0],
                        'entry': entry,
                        'date': datetime.date.fromtimestamp(entry.timestamp)
                    }
                    haikus.append(haiku)

            if not error:
                # Pickle the user's data and insert it into the cache.
                data = pickle.dumps((user, haikus))
                memcache.set(screen_name, data, CACHE_EXPIRATION)

        # Fill out our template variables and render the template.
        vars = {
            'user': user,
            'error': error,
            'haikus': haikus,
        }
        self.response.out.write(template.render('templates/user.html', vars))

# Set up our global state variables.
application = webapp.WSGIApplication(
        [
            ('/', HomePage),
            ('/about', AboutPage),
            ('/(\w+)', UserPage),
        ],
        debug=False)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
