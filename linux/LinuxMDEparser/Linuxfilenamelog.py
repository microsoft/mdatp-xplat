import json
import sys

class Linuxfilenamelog:
    def __init__(self, filename):
        self.filename = filename

    def openlogfile(self):
         return open(self.filename, 'r')