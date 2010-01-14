from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import memcache

import datetime
import logging
import time
import haikufinder
import twitter

class TwitterCache(object):
    '''A Twitter cache implementation that uses memcache'''

    def _GetCacheKey(self, key):
        return 'twitter_' + key

    def Get(self, key):
        data = memcache.get(self._GetCacheKey(key))
        if data is not None:
            return data[0]
        return None

    def Set(self, key, data):
        data = (data, time.time())
        memcache.set(self._GetCacheKey(key), data)

    def Remove(self, key):
        memcache.delete(self._GetCacheKey(key))

    def GetCachedTime(self,key):
        data = memcache.get(self._GetCacheKey(key))
        if data is not None:
            return data[1]
        return None

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
        api = twitter.Api(cache=cache)

        # Query for the requested user's public timeline.  If we encounter any
        # problems here, we simply treat them all as a generic "nothing found"
        # case and let the code below sort things out.
        try:
            timeline = api.GetUserTimeline(screen_name, count=300)
        except:
            logging.warning("Failed to get timeline for '%s'", screen_name)
            timeline = []

        # Fill out our user object.  If we didn't get any results from the API
        # query, we make a dummy object based solely on the screen name.
        if timeline:
            user = timeline[0].user
            logging.debug("%d entries for '%s'", len(timeline), screen_name)
        else:
            user = twitter.User(name=screen_name, screen_name=screen_name)
            logging.info("Empty public timeline for '%s'", screen_name)

        # Walk through all of the entries looking for haikus.
        haikus = []
        for entry in timeline:
            matches = haikufinder.find_haikus(entry.text)
            if matches:
                timestamp = entry.created_at_in_seconds
                haiku = {
                    'lines': matches[0],
                    'entry': entry,
                    'date': datetime.date.fromtimestamp(timestamp)
                }
                haikus.append(haiku)

        if not haikus:
            logging.info("No haikus for '%s'", screen_name)

        # Fill out our template variables and render the template.
        vars = {
            'user': user,
            'haikus': haikus,
        }
        self.response.out.write(template.render('templates/user.html', vars))

# Set up our global state variables.
cache = TwitterCache()
application = webapp.WSGIApplication(
        [
            ('/', HomePage),
            ('/about', AboutPage),
            ('/(\w+)', UserPage),
        ],
        debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
