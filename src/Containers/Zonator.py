from EightFoldPath import EightFoldPath
from VegZone import VegZone
from Utils.Exceptions import HSClassError

class Zonator(EightFoldPath):
    """Class to hold information about each of the directional zones of a stream node

    Constructor takes up to 7 arguments which are objects representing each direction.
    Args can be individual objects or a single list of objects. If keyword argument
    north is empty or True, then objects should be ordered starting with NE and
    continuing clockwise. If kw argument north is False, then objects should be ordered
    starting with SW and continuing clockwise"""
    def __init__(self, *args, **kwargs):
        inNorth = True
        if 'north' in kwargs.keys(): inNorth = kwargs['north']
        if 'south' in kwargs.keys(): inNorth = not kwargs['south']
        if len(args) > 7: raise HSClassError("Cannot have more than 7 directions")
        # Now see how many arguments we have and act accordingly
        if len(args) == 1: # Possible list, tuple or dictionary
            if len(args[0]) > 7: raise HSClassError("Cannot have more than 7 directions")
            if isinstance(args[0],list) or isinstance(args[0],tuple):
                paths = args[0]
            elif isinstance(args[0],dict):
                # Make sure we build an argument list ordered properly
                if inNorth: t = ("NE","E","SE","S","SW","W","NW") # Northern hemisphere
                else: t = ("SW","W","NW","N","NE","E","SE")# Southern hem.
                paths = [args[0][k] for k in t] # Build ordered list on the fly
        # Not a single argument, assume they are individual VegZone instances
        else: paths = args
        # No we know we have a valid set of arguments, so we make sure that they
        # are all VegZone instances
        for arg in paths:
            if isinstance(arg, tuple) or isinstance(arg, list):
                for i in xrange(len(arg)):
                    if not isinstance(arg[i],VegZone):
                        raise HSClassError("Only VegZone instances can be added, not %s" % repr(arg))
            else:
                raise HSClassError("Arguments must be sequence of VegZone instances")

        # And then we subclass the EightFoldPath, finalizing our instantiation
        EightFoldPath.__init__(self,paths,inNorth)

    def __iter__(self):
        """Iterator that cycles through the zonator

        This method returns a tuple (i,j,zone) where i is the cardinal direction of the
        Zonator instance (0-6) and j is the zone number (0-3). zone is the actual zone
        instance so that the following syntax can be used:

        >>> SN = StreamNode()
        >>> for i,j,zone in SN:
        >>>     print i, j, zone
        0 0 VZ:(0, 0, 0, 0, 0)
        0 1 VZ:(0, 0, 0, 0, 0)
        0 2 VZ:(0, 0, 0, 0, 0)
        0 3 VZ:(0, 0, 0, 0, 0)
        1 0 VZ:(0, 0, 0, 0, 0)
        1 1 VZ:(0, 0, 0, 0, 0)
        ...
        """
        for i in xrange(7):
            for j in xrange(4):
                yield i,j,self[i][j]
