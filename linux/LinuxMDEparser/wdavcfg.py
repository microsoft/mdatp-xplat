import json
import sys
import xlsxwriter
from Linuxfilenamelog import Linuxfilenamelog

class Wdavcfg:
    
    def Wdavcfg2Excel():
        
        filename = 'wdavcfg'
        log1 = Linuxfilenamelog(filename)
        log1_content = json.load(Linuxfilenamelog.openlogfile(log1))

        #Create the excel file
        workbook = xlsxwriter.Workbook(f'{filename}.xlsx')

        #antivirusEngine
    
        worksheet = workbook.add_worksheet('antivirusEngine')
        worksheet.write(0, 0, 'allowedThreats')
        worksheet.write(0, 1, 'disallowedThreatActions')
        worksheet.write(0, 2, 'enforcementLevel')
        worksheet.write(0, 3, 'exclusions')
        worksheet.write(0, 4, 'maximumOnDemandScanThreads')
        worksheet.write(0, 5, 'maximumRealTimeScanThreads')
        worksheet.write(0, 6, 'processExclusionCacheMaximum')
        worksheet.write(0, 7, 'processIdPathCacheMaximum')
        worksheet.write(0, 8, 'scanCacheMaximum')
        worksheet.write(0, 9, 'scanHistoryCleanupIntervalHours')
        worksheet.write(0, 10, 'scanHistoryMaximumItems')
        worksheet.write(0, 11, 'scanResultsRetentionDays')
        worksheet.write(0, 12, 'threatRestorationExclusionTime')
        worksheet.write(0, 13, 'threatTypeSettings')

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

        worksheet.write(1, 0, str(allowedThreats))
        worksheet.write(1, 1, str(disallowedThreatActions))
        worksheet.write(1, 2, str(enforcementLevel))
        worksheet.write(1, 3, str(exclusions))
        worksheet.write(1, 4, maximumOnDemandScanThreads)
        worksheet.write(1, 5, maximumRealTimeScanThreads)
        worksheet.write(1, 6, str(processExclusionCacheMaximum))
        worksheet.write(1, 7, str(processIdPathCacheMaximum))
        worksheet.write(1, 8, scanCacheMaximum)
        worksheet.write(1, 9, scanHistoryCleanupIntervalHours)
        worksheet.write(1, 10, str(scanHistoryMaximumItems))
        worksheet.write(1, 11, str(scanResultsRetentionDays))
        worksheet.write(1, 12, threatRestorationExclusionTime)
        worksheet.write(1, 13, str(threatTypeSettings))

        #cloudService
    
        worksheet = workbook.add_worksheet('cloudService')
        worksheet.write(0, 0, 'automaticDefinitionUpdateEnabled')
        worksheet.write(0, 1, 'automaticSampleSubmissionConsent')
        worksheet.write(0, 2, 'definitionUpdateDue')
        worksheet.write(0, 3, 'defintionUpdatesInterval')
        worksheet.write(0, 4, 'diagnosticLevel')
        worksheet.write(0, 5, 'enabled')
        worksheet.write(0, 6, 'heartbeatInterval')
        worksheet.write(0, 7, 'proxy')
        worksheet.write(0, 8, 'retryCount')
        worksheet.write(0, 9, 'retryInterval')
        worksheet.write(0, 10, 'serviceUri')
        worksheet.write(0, 11, 'timeout')
       
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

        worksheet.write(1, 0, str(automaticDefinitionUpdateEnabled))
        worksheet.write(1, 1, str(automaticSampleSubmissionConsent))
        worksheet.write(1, 2, str(definitionUpdateDue))
        worksheet.write(1, 3, str(defintionUpdatesInterval))
        worksheet.write(1, 4, str(diagnosticLevel))
        worksheet.write(1, 5, str(enabled))
        worksheet.write(1, 6, heartbeatInterval)
        worksheet.write(1, 7, str(proxy))
        worksheet.write(1, 8, str(retryCount))
        worksheet.write(1, 9, str(retryInterval))
        worksheet.write(1, 10, str(serviceUri))
        worksheet.write(1, 11, timeout)

        # Device Control

        worksheet = workbook.add_worksheet('deviceControl')
        worksheet.write(0, 0, 'navigationTarget')
        worksheet.write(0, 1, 'removableMediaPolicy')

        navigationTarget = log1_content['deviceControl']['navigationTarget']
        removableMediaPolicy = log1_content['deviceControl']['removableMediaPolicy']

        worksheet.write(1, 0, str(navigationTarget))
        worksheet.write(1, 1, str(removableMediaPolicy))

        # EDR

        worksheet = workbook.add_worksheet('edr')
        worksheet.write(0, 0, 'earlyPreview')
        worksheet.write(0, 1, 'groupIds')
        worksheet.write(0, 2, 'latencyMode')
        worksheet.write(0, 3, 'proxyAddress')
        worksheet.write(0, 4, 'tags')

        earlyPreview = log1_content['edr']['earlyPreview']
        groupIds = log1_content['edr']['groupIds']
        latencyMode = log1_content['edr']['latencyMode']
        proxyAddress = log1_content['edr']['proxyAddress']
        tags = log1_content['edr']['tags']

        worksheet.write(1, 0, str(earlyPreview))
        worksheet.write(1, 1, str(groupIds))
        worksheet.write(1, 2, str(latencyMode))
        worksheet.write(1, 3, str(proxyAddress))
        worksheet.write(1, 4, str(tags))

        # Features

        worksheet = workbook.add_worksheet('features')
        worksheet.write(0, 0, 'behaviorMonitoring')
        worksheet.write(0, 1, 'behaviorMonitoringStatistics')
        worksheet.write(0, 2, 'crashReporting')
        worksheet.write(0, 3, 'customIndicators')
        worksheet.write(0, 4, 'feedbackReporting')
        worksheet.write(0, 5, 'gibraltar')
        worksheet.write(0, 6, 'kernelExtension')
        worksheet.write(0, 7, 'networkFilter')
        worksheet.write(0, 8, 'networkProtection')
        worksheet.write(0, 9, 'realTimeProtectionStatistics')
        worksheet.write(0, 10, 'scannedFilesPerProcess')
        worksheet.write(0, 11, 'systemExtensions')
        worksheet.write(0, 12, 'tamperProtection')
        worksheet.write(0, 13, 'usbDeviceControl')
        worksheet.write(0, 14, 'v2ContentScanning')
        worksheet.write(0, 15, 'v2DevMode')

        behaviorMonitoring = log1_content['features']['behaviorMonitoring']
        behaviorMonitoringStatistics = log1_content['features']['behaviorMonitoringStatistics']
        crashReporting = log1_content['features']['crashReporting']
        customIndicators = log1_content['features']['customIndicators']
        feedbackReporting = log1_content['features']['feedbackReporting']
        gibraltar = log1_content['features']['gibraltar']
        kernelExtension = log1_content['features']['kernelExtension']
        networkFilter = log1_content['features']['networkFilter']
        networkProtection = log1_content['features']['networkProtection']
        realTimeProtectionStatistics = log1_content['features']['realTimeProtectionStatistics']
        scannedFilesPerProcess = log1_content['features']['scannedFilesPerProcess']
        systemExtensions = log1_content['features']['systemExtensions']
        tamperProtection = log1_content['features']['tamperProtection']
        usbDeviceControl = log1_content['features']['usbDeviceControl']
        v2ContentScanning = log1_content['features']['v2ContentScanning']
        v2DevMode = log1_content['features']['v2DevMode']

        worksheet.write(1, 0, str(behaviorMonitoring))
        worksheet.write(1, 1, str(behaviorMonitoringStatistics))
        worksheet.write(1, 2, str(crashReporting))
        worksheet.write(1, 3, str(customIndicators))
        worksheet.write(1, 4, str(feedbackReporting))
        worksheet.write(1, 5, str(gibraltar))
        worksheet.write(1, 6, str(kernelExtension))
        worksheet.write(1, 7, str(networkFilter))
        worksheet.write(1, 8, str(networkProtection))
        worksheet.write(1, 9, str(realTimeProtectionStatistics))
        worksheet.write(1, 10, str(scannedFilesPerProcess))
        worksheet.write(1, 11, str(systemExtensions))
        worksheet.write(1, 12, str(tamperProtection))
        worksheet.write(1, 13, str(usbDeviceControl))
        worksheet.write(1, 14, str(v2ContentScanning))
        worksheet.write(1, 15, str(v2DevMode))
        
        # filesystemScanner

        worksheet = workbook.add_worksheet('filesystemScanner')
        worksheet.write(0, 0, 'enumerationThreads')
        
        enumerationThreads = log1_content['filesystemScanner']['enumerationThreads']

        worksheet.write(1, 0, str(enumerationThreads))

        # gibraltarSettings

        worksheet = workbook.add_worksheet('gibraltarSettings')
        worksheet.write(0, 0, 'maxRetryAttempts')
        worksheet.write(0, 1, 'portalRefreshInterval')
        worksheet.write(0, 2, 'retryInterval')
        
        maxRetryAttempts = log1_content['gibraltarSettings']['maxRetryAttempts']
        portalRefreshInterval = log1_content['gibraltarSettings']['portalRefreshInterval']
        retryInterval_2 = log1_content['gibraltarSettings']['retryInterval']

        worksheet.write(1, 0, maxRetryAttempts)
        worksheet.write(1, 1, portalRefreshInterval)
        worksheet.write(1, 2, retryInterval_2)

        # networkProtection

        worksheet = workbook.add_worksheet('networkProtection')
        worksheet.write(0, 0, 'enforcementLevel')
        worksheet.write(0, 1, 'exclusions')
        worksheet.write(0, 2, 'sideBySideVpn')

        enforcementLevel_2 = log1_content['networkProtection']['enforcementLevel']
        exclusions_2 = log1_content['networkProtection']['exclusions']
        sideBySideVpn = log1_content['networkProtection']['sideBySideVpn']

        worksheet.write(1, 0, str(enforcementLevel_2))
        worksheet.write(1, 1, str(exclusions_2))
        worksheet.write(1, 2, str(sideBySideVpn))
        
        # tamperProtection
        
        worksheet = workbook.add_worksheet('tamperProtection')
        worksheet.write(0, 0, 'enforcementLevel')

        enforcementLevel_3 = log1_content['tamperProtection']['enforcementLevel']

        worksheet.write(1, 0, str(enforcementLevel_3))
        
        # userInterface
        
        worksheet = workbook.add_worksheet('userInterface')
        worksheet.write(0, 0, 'disableNotifications')
        worksheet.write(0, 1, 'hideStatusMenuIcon')
        worksheet.write(0, 2, 'userInitiatedFeedback')

        disableNotifications = log1_content['userInterface']['disableNotifications']
        hideStatusMenuIcon = log1_content['userInterface']['hideStatusMenuIcon']
        userInitiatedFeedback = log1_content['userInterface']['userInitiatedFeedback']

        worksheet.write(1, 0, str(disableNotifications))
        worksheet.write(1, 1, str(hideStatusMenuIcon))
        worksheet.write(1, 2, str(userInitiatedFeedback))

        
        #All other
        
        worksheet = workbook.add_worksheet('AllOther')
        worksheet.write(0, 0, 'connectionRetryTimeout')
        worksheet.write(0, 1, 'crashUploadDailyLimit')
        worksheet.write(0, 2, 'fileHashCacheMaximum')

        connectionRetryTimeout = log1_content['connectionRetryTimeout']
        crashUploadDailyLimit = log1_content['crashUploadDailyLimit']
        fileHashCacheMaximum = log1_content['fileHashCacheMaximum']

        worksheet.write(1, 0, str(connectionRetryTimeout))
        worksheet.write(1, 1, str(crashUploadDailyLimit))
        worksheet.write(1, 2, str(fileHashCacheMaximum))
                        
        workbook.close()

#logparsed = Wdavcfg
#logparsed.Wdavcfg2Excel()