import json
import csv

class Json2excel:
    def __init__(self, logfile, dictionaykey, filename):
        self.logfile = logfile
        self.dictionaykey = dictionaykey
        self.filename = filename
    
    def json2excel(self):
        try:
            with open (self.logfile) as json_file:
                log_dict = json.load(json_file)
                keys = log_dict[self.dictionaykey][0].keys()
                with open(self.filename, 'w', newline='', encoding = 'utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames = keys)
                    writer.writeheader()
                    writer.writerows(log_dict['scans'])
                    print(f'{self.filename} created')
        except Exception as e:
            print(f'Someting went wrong:{e}')