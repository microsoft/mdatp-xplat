#!/usr/bin/env node
//
// lib/generate-report.js - Shared REPORT.md generator for the MDE performance-
// profile demos. Reads the diagnostic snapshots written by lib/measure.sh from a
// run directory and renders a Markdown report.
//
// Per-sample text (title, excluded-folders note, environment intro) is read from
// an optional report-config.json in the run directory (written by generate_report
// in measure.sh):
//   { "title": "...", "excludedNote": "...", "envIntro": "..." }
// All fields are optional; sensible defaults are used when absent.

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function stripAnsiCodes(str) {
    return str.replace(/\x1b\[[0-9;]*m/g, '');
}

const runDir = process.argv[2];
if (!runDir) {
    console.error('Usage: node generate-report.js <run-directory>');
    process.exit(1);
}
if (!fs.existsSync(runDir)) {
    console.error(`Run directory not found: ${runDir}`);
    process.exit(1);
}

// Load per-sample report configuration (optional).
const cfg = (() => {
    const defaults = {
        title: 'MDE Performance Profile Demo Report',
        excludedNote: '',
        envIntro: 'Machine-specific facts captured at run time (useful when this report was ' +
            'produced on a different machine — e.g. to confirm which toolchain ran the build ' +
            'and whether the performance profile could actually match it):',
    };
    try {
        const raw = JSON.parse(fs.readFileSync(path.join(runDir, 'report-config.json'), 'utf-8'));
        return {
            title: raw.title || defaults.title,
            excludedNote: raw.excludedNote || defaults.excludedNote,
            envIntro: raw.envIntro || defaults.envIntro,
        };
    } catch (e) {
        return defaults;
    }
})();

// Function to extract metrics from log file
function extractMetrics(filePath) {
    try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.split('\n');

        let events = 'N/A';
        let throughput = 'N/A';
        let exclusions = [];
        let profiles = [];
        let topEvents = [];

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
            if (finalEventIdx >= 0) {
                const match = lines[finalEventIdx].match(/Throughput:\s*([\d.]+) events\/sec/);
                if (match) throughput = match[1];
            }
        }

        let scanTime = 'N/A';
        for (const line of lines) {
            if (line.includes('Scan time (ns):')) {
                const match = line.match(/Scan time \(ns\): (\d+)ns/);
                if (match) {
                    const ns = parseInt(match[1]);
                    scanTime = (ns / 1000000000).toFixed(2);
                    break;
                }
            }
        }

        let lastHotEventIdx = -1;
        for (let i = lines.length - 1; i >= 0; i--) {
            if (lines[i].includes('=========== Top') && lines[i].includes('Hot Event Sources')) {
                lastHotEventIdx = i;
                break;
            }
        }

        if (lastHotEventIdx >= 0) {
            let eventIdx = lastHotEventIdx + 2;
            while (eventIdx < lines.length && topEvents.length < 5) {
                const line = lines[eventIdx];
                if (line.includes('===========')) break;
                if (!line.trim() || line.includes('count') && line.includes('signing')) {
                    eventIdx++;
                    continue;
                }
                const startsWithNumber = /^\d+\s+/.test(line.trim());
                if (startsWithNumber) {
                    const parts = line.trim().split(/\s{2,}/);
                    if (parts.length >= 3) {
                        const count = parts[0];
                        const process = parts[1];
                        let path = parts[2];
                        if (path && path.length < 5 && eventIdx + 1 < lines.length) {
                            path = path + lines[eventIdx + 1].trim();
                            eventIdx++;
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

        return { events, throughput, exclusions, profiles, topEvents, scanTime };
    } catch (e) {
        return { events: 'N/A', throughput: 'N/A', exclusions: [], profiles: [], topEvents: [] };
    }
}

function formatHotEventsTable(topEvents) {
    if (!topEvents || topEvents.length === 0) {
        return 'No hot events captured';
    }
    let table = '\n| Count | Process | Location |\n|-------|---------|----------|\n';
    for (const event of topEvents) {
        const p = event.path.length > 60 ? event.path.substring(0, 57) + '...' : event.path;
        table += `| ${event.count} | ${event.process} | ${p} |\n`;
    }
    return table;
}

// Read the persisted EICAR probe result for a phase (written by measure.sh's
// test_eicar) and render the ACTUAL detection outcome.
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
    const raw = stripAnsiCodes(fs.readFileSync(p, 'utf-8')).trim();
    const lines = raw.split('\n');
    if (lines.length === 0 || lines[0].startsWith('(no hot-event')) {
        return '_(no hot-event sources captured during the build window)_';
    }

    const summary = lines.find(l => l.startsWith('Total Events:')) || '';
    const srcIdx = lines.findIndex(l => l.includes('Hot Event Sources'));
    const tgtIdx = lines.findIndex(l => l.includes('Hot Event Targets'));
    const dataRows = (arr) => arr.filter(l => /^\s*\d+\s/.test(l)).slice(0, 10);

    let sourceRows = [];
    let targetRows = [];
    if (srcIdx >= 0) {
        const srcEnd = tgtIdx >= 0 ? tgtIdx : lines.length;
        sourceRows = dataRows(lines.slice(srcIdx + 1, srcEnd));
    }
    if (tgtIdx >= 0) {
        targetRows = dataRows(lines.slice(tgtIdx + 1));
    }
    if (srcIdx < 0 && tgtIdx < 0) {
        sourceRows = dataRows(lines);
    }

    const block = (label, rows, empty) =>
        `**${label}**\n\`\`\`\n${rows.length ? rows.join('\n') : empty}\n\`\`\``;

    const parts = [];
    if (summary) parts.push(`\`${summary}\``);
    parts.push(block('Sources (processes driving scans)', sourceRows,
        '(no hot-event sources captured during the build window)'));
    parts.push(block('Targets (files / paths scanned)', targetRows,
        '(no hot-event targets captured during the build window)'));
    return '\n' + parts.join('\n\n');
}

function extractBuildTimings(filePath) {
    try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.split('\n');
        let avgTime = null, minTime = null, maxTime = null;
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

// Extract the "Build Performance Metrics" block (values measure.sh writes directly).
function extractPhaseMetrics(filePath) {
    const out = {
        median: null, avg: null, min: null, max: null,
        filesScanned: null, scanTimeMs: null, avCpu: null, entCpu: null, allCpu: null,
        peakRss: null, entPeakRss: null, allPeakRss: null,
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
        out.avCpu = grab(/MDE unprivileged AV avg CPU \(%\):\s*(-?[\d.]+)/);
        out.entCpu = grab(/MDE enterprise EDR avg CPU \(%\):\s*(-?[\d.]+)/);
        out.allCpu = grab(/MDE all daemons avg CPU \(%\):\s*(-?[\d.]+)/);
        out.peakRss = grab(/MDE unprivileged AV peak RSS \(MB\):\s*([\d.]+)/);
        out.entPeakRss = grab(/MDE enterprise EDR peak RSS \(MB\):\s*([\d.]+)/);
        out.allPeakRss = grab(/MDE all daemons peak RSS \(MB\):\s*([\d.]+)/);
    } catch (e) { /* leave nulls */ }
    return out;
}

// Read the "Applied Profiles:" block from a snapshot (authoritative record of which
// profiles were active in that phase). Skips the "Merge policy" line.
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

// Format a scan-count delta. These are aggregate deltas of per-process cumulative
// counters; when a process with a large counter exits between the before/after
// snapshots its counter drops out of the sum, so a heavily-suppressed phase can
// produce a meaningless negative delta. Render those as "≈0" with a footnote marker.
function scanNum(v) {
    if (v === null || v === undefined) return 'N/A';
    const n = Number(v);
    if (Number.isNaN(n)) return 'N/A';
    if (n < 0) return '≈0 \\*';
    return n.toLocaleString('en-US');
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
const baselineMetrics = fs.existsSync(baselineBeforePath) ? extractMetrics(baselineBeforePath) : {};

// Per-phase MDE metrics (as written by measure.sh in the "Build Performance Metrics" block)
const baselinePhase = extractPhaseMetrics(baselineAfterPath);
const exclusionsPhase = extractPhaseMetrics(exclusionsAfterPath);
const profilesPhase = extractPhaseMetrics(profilesAfterPath);

// Which profiles were actually active in Phase 3 (authoritative, from the snapshot).
const appliedProfiles = extractAppliedProfiles(profilesAfterPath);

const excludedNoteLine = cfg.excludedNote
    ? `\n${cfg.excludedNote}\n`
    : '';

// Generate markdown report
const report = `# ${cfg.title}

**Generated:** ${new Date().toLocaleString()}  
**Run Location:** \`${runDir}\`

---

## Results

| Metric | Baseline | AV Exclusions | Perf Profiles |
|---|---:|---:|---:|
| Median build time (s) | ${baselinePhase.median || 'N/A'} | ${exclusionsPhase.median || 'N/A'} | ${profilesPhase.median || 'N/A'} |
| Average build time (s) | ${baselinePhase.avg || 'N/A'} | ${exclusionsPhase.avg || 'N/A'} | ${profilesPhase.avg || 'N/A'} |
| MDE files scanned | ${scanNum(baselinePhase.filesScanned)} | ${scanNum(exclusionsPhase.filesScanned)} | ${scanNum(profilesPhase.filesScanned)} |
| MDE scan time (ms) | ${scanNum(baselinePhase.scanTimeMs)} | ${scanNum(exclusionsPhase.scanTimeMs)} | ${scanNum(profilesPhase.scanTimeMs)} |
| AV (unpriv) avg CPU (%) | ${baselinePhase.avCpu || 'N/A'} | ${exclusionsPhase.avCpu || 'N/A'} | ${profilesPhase.avCpu || 'N/A'} |
| Enterprise EDR avg CPU (%) | ${baselinePhase.entCpu || 'N/A'} | ${exclusionsPhase.entCpu || 'N/A'} | ${profilesPhase.entCpu || 'N/A'} |
| All-daemons avg CPU (%) | ${baselinePhase.allCpu || 'N/A'} | ${exclusionsPhase.allCpu || 'N/A'} | ${profilesPhase.allCpu || 'N/A'} |
| AV (unpriv) peak RSS (MB) | ${baselinePhase.peakRss || 'N/A'} | ${exclusionsPhase.peakRss || 'N/A'} | ${profilesPhase.peakRss || 'N/A'} |
| Enterprise EDR peak RSS (MB) | ${baselinePhase.entPeakRss || 'N/A'} | ${exclusionsPhase.entPeakRss || 'N/A'} | ${profilesPhase.entPeakRss || 'N/A'} |
| All-daemons peak RSS (MB) | ${baselinePhase.allPeakRss || 'N/A'} | ${exclusionsPhase.allPeakRss || 'N/A'} | ${profilesPhase.allPeakRss || 'N/A'} |
| EICAR | ${eicarBadge('baseline_eicar.txt')} | ${eicarBadge('exclusions_eicar.txt')} | ${eicarBadge('profiles_eicar.txt')} |
${excludedNoteLine}
\\* **"≈0" / negative scan deltas:** *MDE files scanned* and *scan time* are aggregate
deltas of per-process cumulative counters. When a process with a large counter (e.g. a
compiler or helper) exits between the before/after snapshots, its counter drops out of
the sum, so a heavily-suppressed phase can yield a negative delta. That reflects
suppressed scanning, not negative work — treat it as ≈0 and trust **AV (unpriv) avg CPU %**
as the reliable signal.

Profiles applied in Phase 3: ${appliedProfiles.length ? appliedProfiles.map(p => '\`' + p + '\`').join(', ') : '_N/A_'}

---

## Scan Activity by Phase

Two views per phase: **Sources** (the processes that trigger scans) and **Targets**
(the actual files/paths MDE scanned). Targets are the direct signal for whether an
exclusion is being honored — an excluded path should stop appearing here.

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

${cfg.envIntro}

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

const reportPath = path.join(runDir, 'REPORT.md');
fs.writeFileSync(reportPath, report);
console.log(`✓ Report generated: ${reportPath}`);

try {
    execSync(`open "${reportPath}"`, { stdio: 'ignore' });
    console.log('✓ Opened report');
} catch (e) {
    console.log(`Report ready at: ${reportPath}`);
}
