#!/bin/bash
# setup-project.sh - Generate the Xcode project structure for MDE-Demo

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_NAME="MDE-Demo"
PROJ_PATH="$PROJECT_DIR/$PROJ_NAME.xcodeproj"
BUILD_PHASE_ID="PHASE_BUILD"
FILE_REF_MAIN="MAIN_M"
FILE_REF_HELPER_C="HELPER_C"
FILE_REF_HELPER_H="HELPER_H"

echo "Setting up Xcode project at $PROJ_PATH..."

# Create project structure
mkdir -p "$PROJ_PATH"

# Create minimal pbxproj (this is a simplified version for a CLI app)
cat > "$PROJ_PATH/project.pbxproj" << 'EOF'
// !$*UTF8*$!
{
	archiveVersion = 1;
	classes = {
	};
	objectVersion = 52;
	objects = {
		/* Begin PBXBuildFile section */
		MAIN_FILE_ID /* main.m in Sources */ = {isa = PBXBuildFile; fileRef = MAIN_M /* main.m */; };
		HELPER_C_FILE_ID /* helper.c in Sources */ = {isa = PBXBuildFile; fileRef = HELPER_C /* helper.c */; };
		/* End PBXBuildFile section */
		
		/* Begin PBXFileReference section */
		EXEC_FILE_ID /* MDE-Demo */ = {isa = PBXFileReference; explicitFileType = "compiled.mach-o.executable"; includeInIndex = 0; path = "MDE-Demo"; sourceTree = BUILT_PRODUCTS_DIR; };
		MAIN_M /* main.m */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.c.objc; path = "MDE-Demo/main.m"; sourceTree = "<group>"; };
		HELPER_C /* helper.c */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.c.c; path = "MDE-Demo/helper.c"; sourceTree = "<group>"; };
		HELPER_H /* helper.h */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.c.h; path = "MDE-Demo/helper.h"; sourceTree = "<group>"; };
		/* End PBXFileReference section */
		
		/* Begin PBXFrameworksBuildPhase section */
		FRAMEWORKS_PHASE_ID /* Frameworks */ = {
			isa = PBXFrameworksBuildPhase;
			buildActionMask = 2147483647;
			files = (
			);
			runOnlyForDeploymentPostprocessing = 0;
		};
		/* End PBXFrameworksBuildPhase section */
		
		/* Begin PBXGroup section */
		PRODUCT_GROUP_ID = {
			isa = PBXGroup;
			children = (
				EXEC_FILE_ID /* MDE-Demo */,
			);
			name = Products;
			sourceTree = "<group>";
		};
		SOURCE_GROUP_ID = {
			isa = PBXGroup;
			children = (
				MAIN_M /* main.m */,
				HELPER_C /* helper.c */,
				HELPER_H /* helper.h */,
			);
			path = "MDE-Demo";
			sourceTree = "<group>";
		};
		ROOT_GROUP_ID = {
			isa = PBXGroup;
			children = (
				SOURCE_GROUP_ID /* MDE-Demo */,
				PRODUCT_GROUP_ID /* Products */,
			);
			sourceTree = "<group>";
		};
		/* End PBXGroup section */
		
		/* Begin PBXNativeTarget section */
		TARGET_ID /* MDE-Demo */ = {
			isa = PBXNativeTarget;
			buildConfigurationList = CONFIG_LIST_ID /* Build configuration list for PBXNativeTarget "MDE-Demo" */;
			buildPhases = (
				SOURCES_PHASE_ID /* Sources */,
				FRAMEWORKS_PHASE_ID /* Frameworks */,
			);
			buildRules = (
			);
			dependencies = (
			);
			name = "MDE-Demo";
			productName = "MDE-Demo";
			productReference = EXEC_FILE_ID /* MDE-Demo */;
			productType = "com.apple.product-type.tool";
		};
		/* End PBXNativeTarget section */
		
		/* Begin PBXProject section */
		PROJECT_ID /* Project object */ = {
			isa = PBXProject;
			attributes = {
				BuildIndependentTargetsInParallel = 1;
				LastUpgradeCheck = 1320;
				ORGANIZATIONNAME = "Microsoft";
				TargetAttributes = {
					TARGET_ID = {
						CreatedOnToolsVersion = 13.2;
					};
				};
			};
			buildConfigurationList = PROJ_CONFIG_LIST_ID /* Build configuration list for PBXProject "MDE-Demo" */;
			compatibilityVersion = "Xcode 9.3";
			developmentRegion = en;
			hasScannedForEncodings = 0;
			knownRegions = (
				en,
				Base,
			);
			mainGroup = ROOT_GROUP_ID;
			productRefGroup = PRODUCT_GROUP_ID /* Products */;
			projectDirPath = "";
			projectRoot = "";
			targets = (
				TARGET_ID /* MDE-Demo */,
			);
		};
		/* End PBXProject section */
		
		/* Begin PBXSourcesBuildPhase section */
		SOURCES_PHASE_ID /* Sources */ = {
			isa = PBXSourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
				MAIN_FILE_ID /* main.m in Sources */,
				HELPER_C_FILE_ID /* helper.c in Sources */,
			);
			runOnlyForDeploymentPostprocessing = 0;
		};
		/* End PBXSourcesBuildPhase section */
		
		/* Begin XCBuildConfiguration section */
		DEBUG_CONFIG_ID /* Debug */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				ALWAYS_SEARCH_USER_PATHS = NO;
				CLANG_ANALYZER_NONNULL = YES;
				CLANG_ANALYZER_NUMBER_OBJECT_CONVERSION = YES_AGGRESSIVE;
				CLANG_CXX_LANGUAGE_DIALECT = "c++17";
				CLANG_CXX_LIBRARY = "libc++";
				CLANG_ENABLE_MODULES = YES;
				CLANG_ENABLE_OBJC_ARC = YES;
				CLANG_WARN_BLOCK_CAPTURE_AUTORELEASING = YES;
				CLANG_WARN_BOOL_CONVERSION = YES;
				CLANG_WARN_COMMA = YES;
				CLANG_WARN_CONSTANT_CONVERSION = YES;
				CLANG_WARN_DEPRECATED_OBJC_IMPLEMENTATIONS = YES;
				CLANG_WARN_DIRECT_OBJC_ISA_USAGE = YES_ERROR;
				CLANG_WARN_DOCUMENTATION_COMMENTS = YES;
				CLANG_WARN_EMPTY_BODY = YES;
				CLANG_WARN_ENUM_CONVERSION = YES;
				CLANG_WARN_INFINITE_RECURSION = YES;
				CLANG_WARN_INT_CONVERSION = YES;
				CLANG_WARN_NON_LITERAL_NULL_CONVERSION = YES;
				CLANG_WARN_OBJC_IMPLICIT_RETAIN_SELF = YES;
				CLANG_WARN_OBJC_LITERAL_CONVERSION = YES;
				CLANG_WARN_OBJC_ROOT_CLASS = YES_ERROR;
				CLANG_WARN_QUOTED_INCLUDE_IN_FRAMEWORK_HEADER = YES;
				CLANG_WARN_RANGE_LOOP_ANALYSIS = YES;
				CLANG_WARN_STRICT_PROTOTYPES = YES;
				CLANG_WARN_SUSPICIOUS_MOVE = YES;
				CLANG_WARN_UNGUARDED_AVAILABILITY = YES_AGGRESSIVE;
				CLANG_WARN_UNREACHABLE_CODE = YES;
				CLANG_WARN__DUPLICATE_METHOD_MATCH = YES;
				CODE_SIGN_STYLE = Automatic;
				COPY_PHASE_STRIP = NO;
				DEBUG_INFORMATION_FORMAT = dwarf;
				ENABLE_STRICT_OBJC_MSGSEND = YES;
				ENABLE_TESTABILITY = YES;
				GCC_C_LANGUAGE_DIALECT = gnu11;
				GCC_DYNAMIC_NO_PIC = NO;
				GCC_NO_COMMON_BLOCKS = YES;
				GCC_OPTIMIZATION_LEVEL = 0;
				GCC_PREPROCESSOR_DEFINITIONS = (
					"DEBUG=1",
					"$(inherited)",
				);
				GCC_WARN_64_TO_32_BIT_CONVERSION = YES;
				GCC_WARN_ABOUT_RETURN_TYPE = YES_ERROR;
				GCC_WARN_UNDECLARED_SELECTOR = YES;
				GCC_WARN_UNINITIALIZED_AUTOS = YES_AGGRESSIVE;
				GCC_WARN_UNUSED_FUNCTION = YES;
				GCC_WARN_UNUSED_VARIABLE = YES;
				MACOSX_DEPLOYMENT_TARGET = 11.0;
				MTL_ENABLE_DEBUG_INFO = INCLUDE_SOURCE;
				MTL_FAST_MATH = YES;
				ONLY_ACTIVE_ARCH = YES;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SDKROOT = macosx;
			};
			name = Debug;
		};
		RELEASE_CONFIG_ID /* Release */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				ALWAYS_SEARCH_USER_PATHS = NO;
				CLANG_ANALYZER_NONNULL = YES;
				CLANG_ANALYZER_NUMBER_OBJECT_CONVERSION = YES_AGGRESSIVE;
				CLANG_CXX_LANGUAGE_DIALECT = "c++17";
				CLANG_CXX_LIBRARY = "libc++";
				CLANG_ENABLE_MODULES = YES;
				CLANG_ENABLE_OBJC_ARC = YES;
				CLANG_WARN_BLOCK_CAPTURE_AUTORELEASING = YES;
				CLANG_WARN_BOOL_CONVERSION = YES;
				CLANG_WARN_COMMA = YES;
				CLANG_WARN_CONSTANT_CONVERSION = YES;
				CLANG_WARN_DEPRECATED_OBJC_IMPLEMENTATIONS = YES;
				CLANG_WARN_DIRECT_OBJC_ISA_USAGE = YES_ERROR;
				CLANG_WARN_DOCUMENTATION_COMMENTS = YES;
				CLANG_WARN_EMPTY_BODY = YES;
				CLANG_WARN_ENUM_CONVERSION = YES;
				CLANG_WARN_INFINITE_RECURSION = YES;
				CLANG_WARN_INT_CONVERSION = YES;
				CLANG_WARN_NON_LITERAL_NULL_OBJECT_CONVERSION = YES;
				CLANG_WARN_OBJC_IMPLICIT_RETAIN_SELF = YES;
				CLANG_WARN_OBJC_LITERAL_CONVERSION = YES;
				CLANG_WARN_OBJC_ROOT_CLASS = YES_ERROR;
				CLANG_WARN_QUOTED_INCLUDE_IN_FRAMEWORK_HEADER = YES;
				CLANG_WARN_RANGE_LOOP_ANALYSIS = YES;
				CLANG_WARN_STRICT_PROTOTYPES = YES;
				CLANG_WARN_SUSPICIOUS_MOVE = YES;
				CLANG_WARN_UNGUARDED_AVAILABILITY = YES_AGGRESSIVE;
				CLANG_WARN_UNREACHABLE_CODE = YES;
				CLANG_WARN__DUPLICATE_METHOD_MATCH = YES;
				CODE_SIGN_STYLE = Automatic;
				COPY_PHASE_STRIP = NO;
				DEBUG_INFORMATION_FORMAT = "dwarf-with-dsym";
				ENABLE_NS_ASSERTIONS = NO;
				ENABLE_STRICT_OBJC_MSGSEND = YES;
				GCC_C_LANGUAGE_DIALECT = gnu11;
				GCC_NO_COMMON_BLOCKS = YES;
				GCC_OPTIMIZATION_LEVEL = s;
				GCC_WARN_64_TO_32_BIT_CONVERSION = YES;
				GCC_WARN_ABOUT_RETURN_TYPE = YES_ERROR;
				GCC_WARN_UNDECLARED_SELECTOR = YES;
				GCC_WARN_UNINITIALIZED_AUTOS = YES_AGGRESSIVE;
				GCC_WARN_UNUSED_FUNCTION = YES;
				GCC_WARN_UNUSED_VARIABLE = YES;
				MACOSX_DEPLOYMENT_TARGET = 11.0;
				MTL_ENABLE_DEBUG_INFO = NO;
				MTL_FAST_MATH = YES;
				PRODUCT_NAME = "$(TARGET_NAME)";
				SDKROOT = macosx;
				STRIP_INSTALLED_PRODUCT = YES;
			};
			name = Release;
		};
		/* End XCBuildConfiguration section */
		
		/* Begin XCConfigurationList section */
		PROJ_CONFIG_LIST_ID /* Build configuration list for PBXProject "MDE-Demo" */ = {
			isa = XCConfigurationList;
			buildConfigurations = (
				DEBUG_CONFIG_ID /* Debug */,
				RELEASE_CONFIG_ID /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		};
		CONFIG_LIST_ID /* Build configuration list for PBXNativeTarget "MDE-Demo" */ = {
			isa = XCConfigurationList;
			buildConfigurations = (
				DEBUG_CONFIG_ID /* Debug */,
				RELEASE_CONFIG_ID /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		};
		/* End XCConfigurationList section */
	};
	rootObject = PROJECT_ID /* Project object */;
}
EOF

echo "Xcode project created at $PROJ_PATH"
echo "You can now run: ./run-demo.sh"
