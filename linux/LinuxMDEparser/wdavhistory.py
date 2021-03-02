import json
import sys
import xlsxwriter
from Linuxfilenamelog import Linuxfilenamelog

class Wdavhistory:
    
    def Wdavhistory2Excel():
        
        filename = 'wdavhistory'
        log1 = Linuxfilenamelog(filename)
        log1_content = json.load(Linuxfilenamelog.openlogfile(log1))

        workbook = xlsxwriter.Workbook(f'{filename}.xlsx')
        worksheet = workbook.add_worksheet()
        worksheet.write(0, 0, 'endTime')
        worksheet.write(0, 1, 'filesScanned')
        worksheet.write(0, 2, 'startTime')
        worksheet.write(0, 3, 'threats')
        worksheet.write(0, 4, 'type')

        for index, item in enumerate(log1_content['scans']):

            endTime = item['endTime']
            filesScanned = item['filesScanned']
            startTime = item['startTime']
            threats = item['threats']
            type = item['type']

            worksheet.write(index + 1, 0, endTime)
            worksheet.write(index + 1, 1, filesScanned)
            worksheet.write(index + 1, 2, startTime)
            worksheet.write(index + 1, 3, str(threats))
            worksheet.write(index + 1, 4, str(type))

        print(f'added all events to {filename}.xlsx')
        workbook.close()