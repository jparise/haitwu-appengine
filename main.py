from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import memcache, urlfetch
from django.utils import simplejson

import calendar
import datetime
import haikufinder
import logging
import rfc822
import urllib

class TwitterCache(object):

    def __init__(self, expiration):
        self.expiration = expiration

    def get(self, key):
        return memcache.get(key, 'twitter')

    def set(self, key, data):
        memcache.set(key, data, self.expiration, 'twitter')

    def discard(self, key):
        memcache.delete(key, 0, 'twitter')

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

def get_timeline(screen_name, cache):
    # Start by looking up this user's content in the cache.
    content = cache.get(screen_name)

    # If we didn't find any cached content, we need to fetch.
    if not content:
        url = 'http://twitter.com/statuses/user_timeline.json'
        url += '?screen_name=' + urllib.quote(screen_name) + '&count=200'

        result = urlfetch.fetch(url, deadline=10)
        if result.status_code == 200:
            content = result.content

    # If we still don't have any content, just return an empty list.
    if not content:
        return []

    # Store the content in the cache.
    cache.set(screen_name, content)
    
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

        # Query for the requested user's public timeline.  If we encounter any
        # problems here, we simply treat them all as a generic "nothing found"
        # case and let the code below sort things out.
        #timeline = api.GetUserTimeline(screen_name, count=200)
        try:
            timeline = get_timeline(screen_name, cache)
        except Exception, e:
            logging.warning("Failed to get timeline for '%s': %s",
                            screen_name, str(e))
            timeline = []

        # Fill out our user object.  If we didn't get any results from the API
        # query, we make a dummy object based solely on the screen name.
        if timeline:
            user = timeline[0].user
        else:
            user = User(name=screen_name, screen_name=screen_name)

        # Walk through all of the entries looking for haikus.
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

        # Fill out our template variables and render the template.
        vars = {
            'user': user,
            'haikus': haikus,
        }
        self.response.out.write(template.render('templates/user.html', vars))

# Set up our global state variables.
cache = TwitterCache(3600)
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
