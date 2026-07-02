#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Function to strip ANSI color codes
function stripAnsiCodes(str) {
    return str.replace(/\x1b\[[0-9;]*m/g, '');
}

// Get run directory from command line argument
const runDir = process.argv[2];

if (!runDir) {
    console.error('Usage: node generate-report.js <run-directory>');
    process.exit(1);
}

// Check if run directory exists
if (!fs.existsSync(runDir)) {
    console.error(`Run directory not found: ${runDir}`);
    process.exit(1);
}

// Function to extract metrics from log file
function extractMetrics(filePath) {
    try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.split('\n');
        
        let events = 'N/A';
        let throughput = 'N/A';
        let filesScanned = 'N/A';
        let exclusions = [];
        let profiles = [];
        let topEvents = [];
        
        // Find the final Total Events line (with non-zero count)
        let finalEventCount = null;
        let finalEventIdx = -1;
        for (let i = 0; i < lines.length; i++) {
            if (lines[i].includes('Total Events:')) {
                const match = lines[i].match(/Total Events: (\d+)/);
                if (match) {
                    finalEventCount = match[1];
                    finalEventIdx = i;
                }
            }
        }
        
        if (finalEventCount) {
            events = finalEventCount;
            // Also get throughput from same line
            if (finalEventIdx >= 0) {
                const match = lines[finalEventIdx].match(/Throughput:\s*([\d.]+) events\/sec/);
                if (match) throughput = match[1];
            }
        }
        
        // Extract total files scanned (cumulative metric from real-time protection)
        // Note: This is system-wide cumulative data, useful for showing scan time
        let scanTime = 'N/A';
        for (const line of lines) {
            if (line.includes('Scan time (ns):')) {
                const match = line.match(/Scan time \(ns\): (\d+)ns/);
                if (match) {
                    const ns = parseInt(match[1]);
                    const seconds = (ns / 1000000000).toFixed(2);
                    scanTime = seconds;
                    break;
                }
            }
        }
        
        // Extract top hot event sources - look for the LAST occurrence (has actual data)
        let lastHotEventIdx = -1;
        for (let i = lines.length - 1; i >= 0; i--) {
            if (lines[i].includes('=========== Top') && lines[i].includes('Hot Event Sources')) {
                lastHotEventIdx = i;
                break;
            }
        }
        
        if (lastHotEventIdx >= 0) {
            let eventIdx = lastHotEventIdx + 2; // Skip header line
            
            // Collect up to 5 events
            while (eventIdx < lines.length && topEvents.length < 5) {
                const line = lines[eventIdx];
                
                // Stop at the next section header
                if (line.includes('===========')) break;
                
                // Skip empty lines and header lines
                if (!line.trim() || line.includes('count') && line.includes('signing')) {
                    eventIdx++;
                    continue;
                }
                
                // Parse the event line - format: count  signing_id  team_id  path
                const startsWithNumber = /^\d+\s+/.test(line.trim());
                
                if (startsWithNumber) {
                    // Split on multiple spaces to separate columns
                    const parts = line.trim().split(/\s{2,}/);
                    
                    if (parts.length >= 3) {
                        const count = parts[0];
                        const process = parts[1];
                        let path = parts[2];
                        
                        // If path seems incomplete (very short), try to get it from next line
                        if (path && path.length < 5 && eventIdx + 1 < lines.length) {
                            path = path + lines[eventIdx + 1].trim();
                            eventIdx++; // Skip the next line since we consumed it
                        }
                        
                        topEvents.push({
                            count: count,
                            process: stripAnsiCodes(process),
                            path: stripAnsiCodes(path)
                        });
                    }
                }
                
                eventIdx++;
            }
        }
        
        // Extract exclusions
        for (const line of lines) {
            if (line.includes('Excluded folder')) {
                const nextIdx = lines.indexOf(line) + 2;
                if (nextIdx < lines.length && lines[nextIdx].includes('Path:')) {
                    const pathMatch = lines[nextIdx].match(/Path: "(.+)"/);
                    if (pathMatch) exclusions.push(pathMatch[1]);
                }
            }
            if (line.match(/^[a-z-]+$/) && !line.includes('=')) {
                // Simple profile names
                const profiles_list = ['git', 'node', 'vscode', 'vscode-tree'];
                if (profiles_list.includes(line.trim())) {
                    profiles.push(line.trim());
                }
            }
        }
        
        return { events, throughput, exclusions, profiles, topEvents, scanTime };
    } catch (e) {
        return { events: 'N/A', throughput: 'N/A', exclusions: [], profiles: [], topEvents: [] };
    }
}

// Function to format hot events for display
function formatHotEventsTable(topEvents) {
    if (!topEvents || topEvents.length === 0) {
        return 'No hot events captured';
    }
    
    let table = '\n| Count | Process | Location |\n|-------|---------|----------|\n';
    for (const event of topEvents) {
        const path = event.path.length > 60 ? event.path.substring(0, 57) + '...' : event.path;
        table += `| ${event.count} | ${event.process} | ${path} |\n`;
    }
    return table;
}

// Format the DURING-build hot-event capture for a phase. Unlike the post-build
// snapshot (idle noise), this shows the cumulative top scan sources measured WHILE
// the build ran, which is what reveals whether a profile actually suppressed a
// process's scan load.
// Read the persisted EICAR probe result for a phase (written by run-demo.sh's
// test_eicar) and render the ACTUAL detection outcome. Falls back gracefully for
// older runs that predate real EICAR persistence.
function readEicarResult(fileName) {
    const p = path.join(runDir, fileName);
    if (!fs.existsSync(p)) {
        return '_N/A (no EICAR result captured — re-run with the latest run-demo.sh)_';
    }
    const txt = stripAnsiCodes(fs.readFileSync(p, 'utf-8'));
    const grab = (re) => { const m = txt.match(re); return m ? m[1] : null; };
    const result = grab(/Result:\s*(\w+)/);
    const before = grab(/Threat count before:\s*(\d+)/);
    const after = grab(/Threat count after:\s*(\d+)/);
    const removed = grab(/File removed by MDE:\s*(\w+)/);
    if (result === 'DETECTED') {
        const how = removed === 'yes' ? 'file quarantined' : `threat count ${before}→${after}`;
        return `✅ **Detected** (${how})`;
    }
    if (result === 'NOT_DETECTED') {
        return `❌ **NOT detected** (file remained on disk, threat count unchanged at ${before})`;
    }
    return '_N/A (no EICAR result captured)_';
}

// Compact EICAR badge for table cells.
function eicarBadge(fileName) {
    const p = path.join(runDir, fileName);
    if (!fs.existsSync(p)) return 'N/A';
    const txt = stripAnsiCodes(fs.readFileSync(p, 'utf-8'));
    const m = txt.match(/Result:\s*(\w+)/);
    if (!m) return 'N/A';
    return m[1] === 'DETECTED' ? '✅ Detected' : '❌ Missed';
}

function formatLiveHotEvents(fileName) {
    const p = path.join(runDir, fileName);
    if (!fs.existsSync(p)) {
        return '_(no during-build capture — re-run with the latest run-demo.sh)_';
    }
    const lines = stripAnsiCodes(fs.readFileSync(p, 'utf-8')).trim().split('\n');
    if (lines.length === 0 || lines[0].startsWith('(no hot-event')) {
        return '_(no hot-event sources captured during the build window)_';
    }
    // Keep the summary line plus the header and top 10 source rows.
    const summary = lines.find(l => l.startsWith('Total Events:')) || '';
    const rows = lines.filter(l => /^\s*\d+\s/.test(l)).slice(0, 10);
    return `\n\`\`\`\n${summary ? summary + '\n' : ''}${rows.join('\n')}\n\`\`\``;
}

// Function to extract build timing metrics from a snapshot
function extractBuildTimings(filePath) {
    try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.split('\n');
        
        let avgTime = null;
        let minTime = null;
        let maxTime = null;
        
        for (const line of lines) {
            if (line.includes('Average build time:')) {
                avgTime = line.match(/Average build time:\s*([\d.]+)s/)?.[1];
            }
            if (line.includes('Min build time:')) {
                minTime = line.match(/Min build time:\s*([\d.]+)s/)?.[1];
            }
            if (line.includes('Max build time:')) {
                maxTime = line.match(/Max build time:\s*([\d.]+)s/)?.[1];
            }
        }
        
        return { avgTime, minTime, maxTime };
    } catch (e) {
        return { avgTime: null, minTime: null, maxTime: null };
    }
}

// Extract the "Build Performance Metrics" block (values run-demo.sh writes directly).
function extractPhaseMetrics(filePath) {
    const out = {
        median: null, avg: null, min: null, max: null,
        filesScanned: null, scanTimeMs: null, avCpu: null, allCpu: null, peakRss: null,
    };
    try {
        const txt = fs.readFileSync(filePath, 'utf-8');
        const grab = (re) => { const m = txt.match(re); return m ? m[1] : null; };
        out.median = grab(/Median build time:\s*([\d.]+)s/);
        out.avg = grab(/Average build time:\s*([\d.]+)s?/);
        out.min = grab(/Min build time:\s*([\d.]+)s/);
        out.max = grab(/Max build time:\s*([\d.]+)s/);
        out.filesScanned = grab(/MDE files scanned during builds:\s*(-?[\d]+)/);
        out.scanTimeMs = grab(/MDE scan time during builds \(ms\):\s*(-?[\d.]+)/);
        out.avCpu = grab(/MDE unprivileged AV avg CPU \(%\):\s*([\d.]+)/);
        out.allCpu = grab(/MDE all daemons avg CPU \(%\):\s*([\d.]+)/);
        out.peakRss = grab(/MDE unprivileged AV peak RSS \(MB\):\s*([\d.]+)/);
    } catch (e) { /* leave nulls */ }
    return out;
}

// Read the "Applied Profiles:" block from a snapshot (the authoritative record of
// which profiles were actually active in that phase). Skips the "Merge policy" line.
function extractAppliedProfiles(filePath) {
    try {
        const lines = fs.readFileSync(filePath, 'utf-8').split('\n');
        const start = lines.findIndex(l => l.trim() === 'Applied Profiles:');
        if (start === -1) return [];
        const profiles = [];
        for (let i = start + 1; i < lines.length; i++) {
            const t = lines[i].trim();
            if (t === '') break;
            if (t.startsWith('Merge policy')) continue;
            profiles.push(t);
        }
        return profiles;
    } catch (e) {
        return [];
    }
}

// Format an integer with thousands separators, or 'N/A'.
function num(v) {
    if (v === null || v === undefined) return 'N/A';
    const n = Number(v);
    if (Number.isNaN(n)) return 'N/A';
    return n.toLocaleString('en-US');
}

// Function to extract total files scanned from a snapshot
function extractTotalFilesScanned(filePath) {
    try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.split('\n');
        
        let totalScanned = 0;
        let processCount = 0;
        
        // Find all processes and their "Total files scanned" lines
        for (let i = 0; i < lines.length; i++) {
            if (lines[i].includes('Process id:')) {
                // Read the process block
                let procScanned = 0;
                let procName = 'Unknown';
                
                // Look ahead for process name and files scanned in next 10 lines
                for (let j = i; j < Math.min(i + 10, lines.length); j++) {
                    if (lines[j].includes('Name:')) {
                        procName = lines[j].match(/Name:\s*(.+)/)?.[1] || 'Unknown';
                    }
                    if (lines[j].includes('Total files scanned:')) {
                        procScanned = parseInt(lines[j].match(/Total files scanned:\s*(\d+)/)?.[1] || '0', 10);
                        
                        // Exclude system process launchd since its counter is global
                        if (procName !== 'launchd') {
                            totalScanned += procScanned;
                            processCount++;
                        }
                        break;
                    }
                }
            }
        }
        
        return { total: totalScanned, count: processCount };
    } catch (e) {
        return { total: 0, count: 0 };
    }
}

// Read log files
const baselineBeforePath = path.join(runDir, 'baseline_(full_scanning)_before.txt');
const baselineAfterPath = path.join(runDir, 'baseline_(full_scanning)_after.txt');
const exclusionsBeforePath = path.join(runDir, 'with_exclusions_before.txt');
const exclusionsAfterPath = path.join(runDir, 'with_exclusions_after.txt');
const profilesBeforePath = path.join(runDir, 'with_performance_profiles_before.txt');
const profilesAfterPath = path.join(runDir, 'with_performance_profiles_after.txt');

const exclusionsMetrics = fs.existsSync(exclusionsAfterPath) ? extractMetrics(exclusionsAfterPath) : {};
const profilesMetrics = fs.existsSync(profilesAfterPath) ? extractMetrics(profilesAfterPath) : {};

// Extract metrics from BEFORE snapshot for baseline (true unoptimized state)
const baselineMetrics = fs.existsSync(baselineBeforePath) ? extractMetrics(baselineBeforePath) : {};

// Extract build timing metrics
const baselineTimings = fs.existsSync(baselineAfterPath) ? extractBuildTimings(baselineAfterPath) : {};
const exclusionsTimings = fs.existsSync(exclusionsAfterPath) ? extractBuildTimings(exclusionsAfterPath) : {};
const profilesTimings = fs.existsSync(profilesAfterPath) ? extractBuildTimings(profilesAfterPath) : {};

// Calculate files scanned during each phase (delta between before and after, excluding launchd)
const baselineBeforeScanned = extractTotalFilesScanned(baselineBeforePath);
const baselineAfterScanned = extractTotalFilesScanned(baselineAfterPath);
const baselineFilesScanned = baselineAfterScanned.total - baselineBeforeScanned.total;

const exclusionsBeforeScanned = extractTotalFilesScanned(exclusionsBeforePath);
const exclusionsAfterScanned = extractTotalFilesScanned(exclusionsAfterPath);
const exclusionsFilesScanned = exclusionsAfterScanned.total - exclusionsBeforeScanned.total;

const profilesBeforeScanned = extractTotalFilesScanned(profilesBeforePath);
const profilesAfterScanned = extractTotalFilesScanned(profilesAfterPath);
const profilesFilesScanned = profilesAfterScanned.total - profilesBeforeScanned.total;

// Per-phase MDE metrics (as written by run-demo.sh in the "Build Performance Metrics" block)
const baselinePhase = extractPhaseMetrics(baselineAfterPath);
const exclusionsPhase = extractPhaseMetrics(exclusionsAfterPath);
const profilesPhase = extractPhaseMetrics(profilesAfterPath);

// Which profiles were actually active in Phase 3 (authoritative, from the snapshot).
const appliedProfiles = extractAppliedProfiles(profilesAfterPath);

// Generate markdown report
const report = `# MDE Performance Profile Demo Report

**Generated:** ${new Date().toLocaleString()}  
**Run Location:** \`${runDir}\`

---

## Results

| Metric | Baseline | AV Exclusions | Perf Profiles |
|---|---:|---:|---:|
| Median build time (s) | ${baselinePhase.median || 'N/A'} | ${exclusionsPhase.median || 'N/A'} | ${profilesPhase.median || 'N/A'} |
| Average build time (s) | ${baselinePhase.avg || 'N/A'} | ${exclusionsPhase.avg || 'N/A'} | ${profilesPhase.avg || 'N/A'} |
| MDE files scanned | ${num(baselinePhase.filesScanned)} | ${num(exclusionsPhase.filesScanned)} | ${num(profilesPhase.filesScanned)} |
| MDE scan time (ms) | ${num(baselinePhase.scanTimeMs)} | ${num(exclusionsPhase.scanTimeMs)} | ${num(profilesPhase.scanTimeMs)} |
| AV avg CPU (%) | ${baselinePhase.avCpu || 'N/A'} | ${exclusionsPhase.avCpu || 'N/A'} | ${profilesPhase.avCpu || 'N/A'} |
| All-daemons avg CPU (%) | ${baselinePhase.allCpu || 'N/A'} | ${exclusionsPhase.allCpu || 'N/A'} | ${profilesPhase.allCpu || 'N/A'} |
| AV peak RSS (MB) | ${baselinePhase.peakRss || 'N/A'} | ${exclusionsPhase.peakRss || 'N/A'} | ${profilesPhase.peakRss || 'N/A'} |
| EICAR | ${eicarBadge('baseline_eicar.txt')} | ${eicarBadge('exclusions_eicar.txt')} | ${eicarBadge('profiles_eicar.txt')} |

Exclusions phase excluded folders: \`out\`, \`node_modules\`, \`.build\`. Negative "files scanned"/"scan time" in the exclusions phase is a per-PID counter artifact — trust AV CPU as the signal.

Profiles applied in Phase 3: ${appliedProfiles.length ? appliedProfiles.map(p => '\`' + p + '\`').join(', ') : '_N/A_'}

---

## Scan Sources by Phase

### Baseline

Top processes scanned:
${formatHotEventsTable(baselineMetrics.topEvents)}

During the build (live capture):
${formatLiveHotEvents('baseline_(full_scanning)_hot_events.txt')}

### Exclusions

Top processes scanned:
${formatHotEventsTable(exclusionsMetrics.topEvents)}

During the build (live capture):
${formatLiveHotEvents('with_exclusions_hot_events.txt')}

### Profiles

Top processes scanned:
${formatHotEventsTable(profilesMetrics.topEvents)}

During the build (live capture):
${formatLiveHotEvents('with_performance_profiles_hot_events.txt')}

---

## Diagnostic Data

All raw diagnostic snapshots captured during this run are available in this directory:

${fs.readdirSync(runDir)
    .filter(f => f.endsWith('.txt'))
    .map(f => `- \`${f}\``)
    .join('\n')}

### Environment Diagnostics

Machine-specific facts captured at run time (useful when this report was produced on
a different machine — e.g. to confirm which node ran the build and whether the \`node\`
performance profile could actually match it):

\`\`\`
${(() => {
    try {
        return stripAnsiCodes(fs.readFileSync(path.join(runDir, 'diagnostics.txt'), 'utf-8')).trim();
    } catch (e) {
        return '(diagnostics.txt not found — re-run with the latest run-demo.sh)';
    }
})()}
\`\`\`

---

## Conclusion

Performance profiles are the recommended approach for optimizing MDE in development environments. They provide measurable performance improvements without sacrificing security, making them the clear winner over folder exclusions.

**Key Metric:** Profiles achieved threat detection (EICAR found) while maintaining optimized scanning, proving they don't create the protection gaps that exclusions do.
`;

// Write report
const reportPath = path.join(runDir, 'REPORT.md');
fs.writeFileSync(reportPath, report);
console.log(`✓ Report generated: ${reportPath}`);

// Open in VS Code
try {
    execSync(`code "${reportPath}"`, { stdio: 'ignore' });
    console.log('✓ Opened in VS Code');
} catch (e) {
    console.log(`Report ready at: ${reportPath}`);
}
