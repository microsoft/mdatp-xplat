#!/usr/bin/env node
// generate-workload.js - Generate a realistic TypeScript workload for the MDE demo.
//
// The single hand-written extension.ts compiles in well under a second, which is
// far too small for MDE scanning overhead to be measurable above noise. This
// script generates many interdependent .ts modules under src/generated/ so that
// `npm run compile` does real work (typically 20-40s) and produces enough file
// I/O for Microsoft Defender to scan. That is what makes the per-phase numbers
// (both wall-clock and MDE scan counts) meaningful.
//
// Usage:
//   node generate-workload.js [moduleCount]
//   MDE_DEMO_MODULES=600 node generate-workload.js
//
// Output files live in src/generated/ (gitignored) and are picked up by tsconfig
// automatically because it already includes "src".

const fs = require('fs');
const path = require('path');

const PROJECT_DIR = __dirname;
const OUT_DIR = path.join(PROJECT_DIR, 'src', 'generated');

const moduleCount = parseInt(
    process.argv[2] || process.env.MDE_DEMO_MODULES || '4000',
    10
);

if (!Number.isFinite(moduleCount) || moduleCount < 1) {
    console.error(`Invalid module count: ${process.argv[2]}`);
    process.exit(1);
}

function moduleName(i) {
    return `module_${String(i).padStart(4, '0')}`;
}

// Each module imports two earlier siblings (a dependency graph) and does enough
// typed work that tsc must actually type-check, not just transpile.
function renderModule(i) {
    const depA = i > 0 ? moduleName(i - 1) : null;
    const depB = i > 1 ? moduleName(i - 2) : null;

    const imports = [];
    if (depA) imports.push(`import { compute as computeA, Widget as WidgetA } from './${depA}';`);
    if (depB) imports.push(`import { compute as computeB } from './${depB}';`);

    return `${imports.join('\n')}

export interface Widget${i} {
    id: number;
    label: string;
    tags: readonly string[];
    metadata: Record<string, number>;
}

export type WidgetInput = Partial<Omit<Widget${i}, 'id'>> & { id: number };

export class Widget {
    private readonly widgets: Map<number, Widget${i}> = new Map();

    add(input: WidgetInput): Widget${i} {
        const widget: Widget${i} = {
            id: input.id,
            label: input.label ?? \`widget-${i}-\${input.id}\`,
            tags: input.tags ?? [],
            metadata: input.metadata ?? {},
        };
        this.widgets.set(widget.id, widget);
        return widget;
    }

    get(id: number): Widget${i} | undefined {
        return this.widgets.get(id);
    }

    all(): Widget${i}[] {
        return Array.from(this.widgets.values());
    }
}

export function compute(seed: number): number {
    let acc = seed;
    for (let j = 0; j < 32; j++) {
        acc = (acc * 31 + ${i}) % 1_000_003;
        acc ^= (acc >> 3);
    }
    ${depA ? 'acc += computeA(acc % 97);' : ''}
    ${depB ? 'acc += computeB(acc % 89);' : ''}
    return acc >>> 0;
}

export function makeWidgets(count: number): Widget${i}[] {
    const store = new Widget();
    ${depA ? 'const upstream = new WidgetA();' : ''}
    for (let k = 0; k < count; k++) {
        store.add({ id: k, label: \`w\${k}\`, tags: ['generated', 'demo'], metadata: { seed: compute(k) } });
        ${depA ? "upstream.add({ id: k, label: `u${k}` });" : ''}
    }
    return store.all();
}
`;
}

function renderIndex(count) {
    const lines = [
        '// Auto-generated aggregator - imports every generated module so tsc',
        '// must type-check and emit the entire graph.',
    ];
    const names = [];
    for (let i = 0; i < count; i++) {
        const m = moduleName(i);
        lines.push(`import { compute as compute_${i} } from './${m}';`);
        names.push(`compute_${i}`);
    }
    lines.push('');
    lines.push('export function runAll(seed: number): number {');
    lines.push('    let total = seed;');
    for (let i = 0; i < count; i++) {
        lines.push(`    total += compute_${i}(total % 100);`);
    }
    lines.push('    return total >>> 0;');
    lines.push('}');
    lines.push('');
    return lines.join('\n');
}

function main() {
    // Clean prior generation so counts are deterministic.
    fs.rmSync(OUT_DIR, { recursive: true, force: true });
    fs.mkdirSync(OUT_DIR, { recursive: true });

    // Tell Spotlight not to index the generated tree. Without this, mdworker_shared
    // and mds_stores index the thousands of output files and MDE scans those
    // Spotlight-initiated accesses. That scan load is NOT muted by developer
    // performance profiles (node/vscode), so it masks the profile benefit and makes
    // Phase 3 look identical to the baseline. The marker keeps the demo measuring the
    // build's own process tree, which the profiles actually mute.
    fs.writeFileSync(path.join(OUT_DIR, '.metadata_never_index'), '');
    fs.writeFileSync(path.join(PROJECT_DIR, '.metadata_never_index'), '');

    for (let i = 0; i < moduleCount; i++) {
        fs.writeFileSync(path.join(OUT_DIR, `${moduleName(i)}.ts`), renderModule(i));
    }
    fs.writeFileSync(path.join(OUT_DIR, 'index.ts'), renderIndex(moduleCount));

    console.log(`Generated ${moduleCount} TypeScript modules in ${path.relative(PROJECT_DIR, OUT_DIR)}/`);
    console.log('These will be compiled by `npm run compile` along with src/extension.ts.');
    console.log('Spotlight indexing suppressed via .metadata_never_index markers.');
}

main();
