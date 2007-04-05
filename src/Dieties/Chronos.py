from datetime import datetime, timedelta
import time, pytz, math
from Utils.SingletonMixin import Singleton

class Chronos(Singleton):
    """This class provides a clock to be used in the model timestepping.

    This is a class that is the God of Time, and thus seen from The Model as
    the end-all-be-all of time. Like Helios, there is only one Chronos, telling
    us when we are in time.
    The basic functionality of this class comes from the __iter__() method,
    which will iterate over a certain timespan, given a certain timestep,
    and will return the current timestep value as a datetime object. This
    allows use of the datetime object in calculations, and for dictionary
    or object keys, for instance as an index in a AttrList.TimeList object.
    The class also stores the current time in a TheTime attribute, which can
    be accessed by anyone
    """
    def __init__(self):
        # Some timedelta objects with standard time amounts
        self.day = timedelta(days=1)
        self.hour = timedelta(hours=1)
        self.minute = timedelta(minutes=1)
        self.second = timedelta(seconds=1)
        self.year = timedelta(weeks=52)
        self.tz = "US/Pacific"
        self.__current = None # Current time

    def Start(self, start, dt=None, stop=None, tz="US/Pacific"):
        if (not isinstance(start, datetime)) or (stop and not isinstance(stop, datetime)):
            raise Exception("Start and stop times much be Python datetime.datetime instances.")
        if dt and not isinstance(dt,timedelta):
            raise Exception("dt must be a Python datetime.timedelta instance.")
        self.tz = tz
        self.__start = self.MakeDatetime(start, tz) # Ensures that the timezone is correct
        self.__dt = dt or self.minute
        self.__stop = stop or self.__start + self.year

    def __iter__(self):
        if not self.__start or not self.__dt:
            raise Exception("Must call %s with the Start() method before using." % self.__class__.__name__)
        # We set current to one behind the starttime, because we
        # increment BEFORE we yield the iterator value, that way
        # the current time is current until it's updated in the outer world.
        self.__current = self.__start
        while self.__current <= self.__stop:
            yield self.__current
            self.__current += self.__dt
            self.__jd, self.__jdc = self.GetJD(self.__current)
    def __len__(self):
        return len([i for i in self])
    def GetStart(self): return self.__start
    def SetStart(self, start):
        if isinstance(start, datetime):
            self.__start = start
        else:
            try:
                self.__start = datetime(*time.strptime(start.Format("%m/%d/%y %H:%M:%S"),"%m/%d/%y %H:%M:%S")[:6])
            except AttributeError:
                raise TypeError("Start time must be a PyTime or a datetime object, not %s" % start.__class__.__time__)
    def GetDT(self): return self.__dt
    def SetDT(self, dt):
        """Sets the current timestep in terms of seconds, or sets it to a timedelta object"""
        if isinstance(dt, timedelta):
            self.__dt = dt
        else:
            self.__dt = timedelta(seconds=dt)
    def GetStop(self): return self.__stop
    def SetStop(self, stop):
        if isinstance(stop, datetime):
            self.__stop = stop
        elif isinstance(stop, timedelta):
            self.__stop = self.start + stop
        else:
            try:
                self.__stop = datetime(*time.strptime(stop.Format("%m/%d/%y %H:%M:%S"),"%m/%d/%y %H:%M:%S")[:6])
            except AttributeError:
                raise TypeError("Stop time must be a PyTime, timedelta or a datetime object, not %s" % start.__class__.__time__)
    def GetCurrent(self):
        if self.__current: return self.__current
        else: return 0
    def SetCurrent(self, value): raise AttributeError("You can't tell Chronos the time, he only tells you!")
    def GetJD(self): return self.__jd
    def SetJD(self, value): raise AttributeError("You can't tell Chronos the time, he only tells you!")
    def GetJDC(self): return self.__jdc
    def SetJDC(self, value): raise AttributeError("You can't tell Chronos the time, he only tells you!")
    start = property(GetStart, SetStart)
    dt = property(GetDT, SetDT)
    stop = property(GetStop, SetStop)
    TheTime = property(GetCurrent, SetCurrent)
    JD = property(GetJD, SetJD)
    JDC = property(GetJDC, SetJDC)
    def FracJD(self, t=None):
        """Takes a datetime object in UTC and returns a fractional julian date"""
        t = t or self.__current
        if not t.tzinfo == pytz.utc:
            t = self.GetUTC(t)
        y,m,d,H,M,S,dst = self.makeTuple(t)
        dec_day = d + (H + (M + S/60)/60)/24
        if m < 3:
            m += 12;
            y -= 1;
        julian_day = math.floor(365.25*(y+4716.0)) + math.floor(30.6001*(m+1)) + dec_day - 1524.5;

        if julian_day > 2299160.0:
            a = math.floor(y/100);
            julian_day += (2 - a + math.floor(a/4));

        self.__jd = round(julian_day,5) #Python numerics return to about 10 places, Naval Observatory goes to 5
    def FracJDC(self, t=None):
        """Takes a datetime object in UTC and returns the calculated julian century"""
        t = t or self.__current
        self.FracJD(t) #Set the fractional julian time, even if it's set already (because it might be a leftover from a previous call)
        return round((self.JD-2451545.0)/36525.0,10) # Eqn. 2-5 in HS Manual

    def GetJD(self, t=None):
        """Returns a tuple of julian date and julian century"""
        t = t or self.__current
        jdc = self.FracJDC(t) # Calcs both JD and JDC, but only returns JDC
        return self.__jd,jdc

    def TZOffset(self, t=None):
        """Takes a datetime object and returns the signed integer offset from UTC"""
        t = t or self.__current
        return 24 - (t.utcoffset().seconds/3600)
    def GetUTC(self, t=None):
        """Return UTC version of a datetime object"""
        t = t or self.__current
        s = t.replace(tzinfo=pytz.utc) # Replace our timezone info
        return s - t.tzinfo._utcoffset #then subtract the offset and return the object
    def MakeDatetime(self, t=None, tz=None):
        if not t:
            return self.__current
        tz = tz or self.tz
        y,m,d,H,M,S,dst = self.makeTuple(t)
        return datetime(y,m,d,H,M,S,tzinfo=dst)
    def makeTuple(self, t=None, tz=None):
        t = t or self.__current
        tz = tz or self.tz
        try:
            y,m,d,H,M,S = time.strptime(t.Format("%m/%d/%y %H:%M:%S"),"%m/%d/%y %H:%M:%S")[:6] # Strip out the time info
        except AttributeError, detail:
            if detail.__str__() == "'datetime.datetime' object has no attribute 'Format'":
                y, m, d, H, M, S = t.timetuple()[:6]
            else:
                print t
                raise AttributeError(detail)
        dst = pytz.timezone(tz) # Make a local timezone object
        return y,m,d,H,M,S,dst