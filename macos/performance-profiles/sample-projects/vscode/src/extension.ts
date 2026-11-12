// MDE Performance Profile Demo Extension

export function activate(): void {
    console.log("MDE Demo Extension activated");
    
    // Simulate some work during activation
    performAnalysis();
}

export function deactivate(): void {
    console.log("MDE Demo Extension deactivated");
}

function performAnalysis(): void {
    console.log("Performing analysis...");
    
    // Generate some computation to make compilation more realistic
    for (let i = 0; i < 100; i++) {
        for (let j = 0; j < 100; j++) {
            const result = Math.sqrt(i * j);
            void result;
        }
    }
    
    console.log("Analysis complete");
}

// Additional helper modules to generate more compilation volume
export const utilities = {
    formatPath(path: string): string {
        return path.replace(/\\/g, '/');
    },
    
    parseConfig(data: string): Record<string, unknown> {
        try {
            return JSON.parse(data);
        } catch (e) {
            console.error("Failed to parse config", e);
            return {};
        }
    },
    
    async processFiles(files: string[]): Promise<number> {
        return files.length;
    }
};

export interface DemoConfig {
    name: string;
    version: string;
    enabled: boolean;
}

export class DemoProcessor {
    private config: DemoConfig;
    
    constructor(config: DemoConfig) {
        this.config = config;
    }
    
    process(): void {
        console.log(`Processing with config: ${this.config.name}`);
    }
    
    getStatus(): string {
        return this.config.enabled ? "active" : "inactive";
    }
}
