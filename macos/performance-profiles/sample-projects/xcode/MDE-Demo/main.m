#import <Foundation/Foundation.h>
#include "helper.h"

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        NSLog(@"=== MDE Performance Profile Demo - Xcode Build ===");
        NSLog(@"Building demo application...");
        
        // Call some C code to add build volume
        performWork();
        performAnalysis();
        
        NSLog(@"Build complete.");
    }
    return 0;
}
