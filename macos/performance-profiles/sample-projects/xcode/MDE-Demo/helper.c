#include <stdio.h>
#include "helper.h"

void performWork(void) {
    printf("Performing work iteration...\n");
    for (int i = 0; i < 500; i++) {
        for (int j = 0; j < 100; j++) {
            // Simulated work to increase build volume
            volatile int result = i * j;
            (void)result;
        }
    }
    printf("Work iteration complete.\n");
}

void performAnalysis(void) {
    printf("Running analysis...\n");
    for (int i = 0; i < 1000; i++) {
        volatile double val = (double)i * 3.14159;
        (void)val;
    }
    printf("Analysis complete.\n");
}
