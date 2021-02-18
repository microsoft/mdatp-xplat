import json
import sys
import xlsxwriter
from Linuxfilenamelog import Linuxfilenamelog

class RealTimeStatiscs:
    
    def RealTimeStatiscs2Excel():
        
        filename = 'real_time_protection'
        log1 = Linuxfilenamelog(filename)
        log1_content = json.load(Linuxfilenamelog.openlogfile(log1))

        workbook = xlsxwriter.Workbook(f'{filename}.xlsx')
        worksheet = workbook.add_worksheet()
        worksheet.write(0, 0, 'id')
        worksheet.write(0, 1, 'isActive')
        worksheet.write(0, 2, 'maxFileScanTime')
        worksheet.write(0, 3, 'name')
        worksheet.write(0, 4, 'path')
        worksheet.write(0, 5, 'scannedFilePaths')
        worksheet.write(0, 6, 'totalFilesScanned')
        worksheet.write(0, 7, 'totalScanTime')

        for index, item in enumerate(log1_content['value']):

            id = item['id']
            isActive = item['isActive']
            maxFileScanTime = item['maxFileScanTime']
            name = item['name']
            path = item['path']
            scannedFilePaths = item['scannedFilePaths']
            totalFilesScanned = item['totalFilesScanned']
            totalScanTime = item['totalScanTime']

            worksheet.write(index + 1, 0, str(id))
            worksheet.write(index + 1, 1, str(isActive))
            worksheet.write(index + 1, 2, str(maxFileScanTime))
            worksheet.write(index + 1, 3, str(name))
            worksheet.write(index + 1, 4, str(path))
            worksheet.write(index + 1, 5, str(scannedFilePaths))
            worksheet.write(index + 1, 6, str(totalFilesScanned))
            worksheet.write(index + 1, 7, str(totalScanTime))
            print(f'added event {id} to {filename}.xlsx')
        
        workbook.close()