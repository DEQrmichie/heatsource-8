from SingletonMixin import Singleton
import time

class Logger(Singleton):
    def __init__(self):
        self._last = None
        self._file = None
    def SetFile(self, filename):
        self._file = filename

    def write(self, message):
        if message != self._last:
            t = time.strftime("%H:%M:%S",time.localtime(time.time()))
            self._file.write("%s-> %s\n"% (t,message))
            self._last = message