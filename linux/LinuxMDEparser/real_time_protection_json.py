import json
import sys
import xlsxwriter
from Linuxfilenamelog import Linuxfilenamelog

class RealTimeStatiscsJson:
    
    def RealTimeStatiscsJson2Excel():
        
        filename = 'real_time_protection.json'
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

        for index, item in enumerate(log1_content['counters']):

            id = item['id']
            name = item['name']
            path = item['path']
            total_files_scanned = item['total_files_scanned']
            total_scan_time = item['total_scan_time']
            max_file_scan_time = item['max_file_scan_time']
            scanned_file_paths = item['scanned_file_paths']
            is_active = item['is_active']

            worksheet.write(index + 1, 0, str(id))
            worksheet.write(index + 1, 1, str(name))
            worksheet.write(index + 1, 2, str(path))
            worksheet.write(index + 1, 3, str(total_files_scanned))
            worksheet.write(index + 1, 4, str(total_scan_time))
            worksheet.write(index + 1, 5, str(max_file_scan_time))
            worksheet.write(index + 1, 6, str(scanned_file_paths))
            worksheet.write(index + 1, 7, str(is_active))
            print(f'added event {id} to {filename}.xlsx')
        
        workbook.close()