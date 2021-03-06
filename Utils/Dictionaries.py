from __future__ import division
from time import ctime, gmtime
from collections import defaultdict
from bisect import bisect_right, bisect_left

from ..Dieties.IniParamsDiety import IniParams
from .. import opt

class Interpolator(defaultdict):
    def __init__(self, *args, **kwargs):
        """Linearly interpolated dictionary class

        This class assumes a numeric key/value pair and will
        allow a linear interpolation between the
        all values, filling the dictionary with the results."""
        defaultdict.__init__(self)
        self.sortedkeys = None

    def __missing__(self,key):
        """Interpolate between dictionary values and stock dictionary with results"""
        # First time the dictionary is in actual use, so we do some setup
        if not self.sortedkeys:
            # If there are no keys, then we have an empty dictionary
            # which will raise an exception when searching for keys.
            # Since we are assuming no change once created, we will
            # set a lambda function to replace this one because we're
            # not using the method anyway.
            if not len(self.keys()):
                self.__missing__ = lambda x: (0.0,)
                return (0.0,)
            else:
                # ASSUMPTION: This dictionary is not changed once created.
                # TODO: We need to make this immutable by modifying __getattr__
                self.sortedkeys = sorted(self.keys())

        # Find the previous and next available keys
        ind = bisect_right(self.sortedkeys, key)-1
        x0 = int(self.sortedkeys[ind])
        x1 = int(self.sortedkeys[ind+1])

        # Find the previous and next available values
        y0 = self[x0]
        y1 = self[x1]
        val = None
        if isinstance(y0, tuple):
            if not len(y0): return () # We have nothing in the tuple, so return a blank tuple (not 'val', which is None)
            for i in xrange(len(y0)):
                # Try to add value to the tuple of values
                try: val += y0[i] + ((y1[i]-y0[i])*(key-x0))/(x1-x0),
                # Unless we have a value of None, then we make a tuple
                except TypeError: val = y0[i] + ((y1[i]-y0[i])*(key-x0))/(x1-x0),
        else: val = y0 + ((y1-y0)*(key-x0))/(x1-x0)
        # This can store the value in the dictionary to prevent us from
        # interpolating later, however, it is too much data for big models
        # and will fill the memory like a leak. It's commented here, but
        # kept in case people want to play.
        #self[key] = val
        return val

    def View(self, minkey, maxkey, fore=None, aft=None):
        """Return dictionary subset

        Return a subset of the current dictionary containing items
        with keys between minkey and maxkey. If either or both of
        fore and/or aft are anything but None, then the returned
        dictionary will also contain the next element before or
        after minkey and maxkey, respectively."""
        keys = sorted(self.keys())
        # If our subset includes all values (i.e. we're not really
        # subsetting), just return ourself.
        start_new = gmtime(minkey)[0:3]
        start_old = gmtime(min(keys))[0:3]
        stop_new = gmtime(maxkey)[0:3]
        stop_old = gmtime(max(keys))[0:3]
        if (start_new == start_old) and (stop_new == stop_old):
            return self
        # Get the minimum and maximum indices, including the one
        # before and one after if fore or aft are anything but None
        newmin = bisect_left(keys, minkey) - (fore is not None)
        newmax = bisect_right(keys, maxkey) + (aft is not None)

        d = Interpolator()
        for k in keys[newmin:newmax]:
            d[k] = self[k]
        return d

try:
    if opt(__name__):
        import psyco
        psyco.bind(Interpolator.__missing__)
except ImportError: pass
