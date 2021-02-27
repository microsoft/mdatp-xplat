import json
import sys
import xlsxwriter
from Linuxfilenamelog import Linuxfilenamelog

class Wdavcfg:
    
    def Wdavcfg2Excel():
        
        filename = 'wdavcfg'
        log1 = Linuxfilenamelog(filename)
        log1_content = json.load(Linuxfilenamelog.openlogfile(log1))

        #workbook = xlsxwriter.Workbook(f'{filename}.xlsx')
        #worksheet = workbook.add_worksheet()
        #worksheet.write(0, 0, 'endTime')
        #worksheet.write(0, 1, 'filesScanned')
        #worksheet.write(0, 2, 'startTime')
        #worksheet.write(0, 3, 'threats')
        #worksheet.write(0, 4, 'type')

        allowedThreats = log1_content['antivirusEngine']['allowedThreats']
        disallowedThreatActions = log1_content['antivirusEngine']['disallowedThreatActions']
        enforcementLevel = log1_content['antivirusEngine']['enforcementLevel']
        exclusions = log1_content['antivirusEngine']['exclusions']
        maximumOnDemandScanThreads = log1_content['antivirusEngine']['maximumOnDemandScanThreads']
        maximumRealTimeScanThreads = log1_content['antivirusEngine']['maximumRealTimeScanThreads']
        processExclusionCacheMaximum = log1_content['antivirusEngine']['processExclusionCacheMaximum']
        processIdPathCacheMaximum = log1_content['antivirusEngine']['processIdPathCacheMaximum']
        scanCacheMaximum = log1_content['antivirusEngine']['scanCacheMaximum']
        scanHistoryCleanupIntervalHours = log1_content['antivirusEngine']['scanHistoryCleanupIntervalHours']
        scanHistoryMaximumItems = log1_content['antivirusEngine']['scanHistoryMaximumItems']
        scanResultsRetentionDays = log1_content['antivirusEngine']['scanResultsRetentionDays']
        threatRestorationExclusionTime = log1_content['antivirusEngine']['threatRestorationExclusionTime']
        threatTypeSettings = log1_content['antivirusEngine']['threatTypeSettings']

        automaticDefinitionUpdateEnabled = log1_content['cloudService']['automaticDefinitionUpdateEnabled']
        automaticSampleSubmissionConsent = log1_content['cloudService']['automaticSampleSubmissionConsent']
        definitionUpdateDue = log1_content['cloudService']['definitionUpdateDue']
        defintionUpdatesInterval = log1_content['cloudService']['defintionUpdatesInterval']
        diagnosticLevel = log1_content['cloudService']['diagnosticLevel']
        enabled = log1_content['cloudService']['enabled']
        heartbeatInterval = log1_content['cloudService']['heartbeatInterval']
        proxy = log1_content['cloudService']['proxy']
        retryCount = log1_content['cloudService']['retryCount']
        retryInterval = log1_content['cloudService']['retryInterval']
        serviceUri = log1_content['cloudService']['serviceUri']
        timeout = log1_content['cloudService']['timeout']
        
        connectionRetryTimeout = log1_content['connectionRetryTimeout']
        crashUploadDailyLimit = log1_content['crashUploadDailyLimit']

        navigationTarget = log1_content['deviceControl']['navigationTarget']
        removableMediaPolicy = log1_content['deviceControl']['removableMediaPolicy']

        
        #worksheet.write(index + 1, 0, endTime)
        #worksheet.write(index + 1, 1, filesScanned)
        #worksheet.write(index + 1, 2, startTime)
        #worksheet.write(index + 1, 3, str(threats))
        #worksheet.write(index + 1, 4, str(type))

    #print(f'added all events to {filename}.xlsx')
    #workbook.close()

logparsed = Wdavcfg
logparsed.Wdavcfg2Excel()