# Akira Ransomware - Binary Analysis & Initialization

**Research Organization:** MottaSec
**Document:** Technical Analysis - Binary Overview & Execution Initialization
**Date:** 2025-11-08
**Hash:** def3fe8d07d5370ac6e105b1a7872c77e193b4b39a6e1cc9cfc815a36e909904

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Binary Characteristics](#binary-characteristics)
3. [PE Structure Analysis](#pe-structure-analysis)
4. [Import Analysis](#import-analysis)
5. [String Analysis](#string-analysis)
6. [Startup Sequence](#startup-sequence)
7. [Main Function Architecture](#main-function-architecture)
8. [Command-Line Interface](#command-line-interface)
9. [Configuration Management](#configuration-management)
10. [Error Handling](#error-handling)
11. [Function Reference](#function-reference)

---

## Executive Summary

This document provides comprehensive analysis of the Akira ransomware binary structure, initialization sequence, and execution flow. Through static analysis, we have mapped the complete startup process from entry point through main function execution.

### Key Findings

**Binary Properties:**
- PE32+ executable (x64 architecture)
- Compiled with Microsoft Visual C++ (MSVC)
- Size: 1,101,824 bytes (~1.05 MB)
- No packing or obfuscation
- Stack protection enabled (/GS flag)

**Execution Model:**
- Single-threaded initialization
- Multi-threaded execution (CPU-scaled)
- Professional C Runtime (CRT) initialization
- Standard Windows entry point
- Comprehensive error handling

**Attack Configuration:**
- 5 command-line parameters
- Flexible targeting (local/network)
- Adaptive thread allocation
- Silent error correction

---

## Binary Characteristics

### File Information

| Property | Value | Notes |
|----------|-------|-------|
| **File Type** | PE32+ executable | 64-bit Windows binary |
| **Architecture** | x86-64 | Intel/AMD 64-bit |
| **Compiler** | Microsoft Visual C++ | MSVC toolchain |
| **File Size** | 1,101,824 bytes | 1.05 MB |
| **Packing** | None | Unpacked binary |
| **Obfuscation** | Minimal | Function names stripped only |
| **Timestamp** | [To be determined] | PE header timestamp |

### PE Header Analysis

**Entry Point:** `0x14008dd38`
- Standard CRT entry point
- No custom entrypoint tricks
- Normal Windows loader behavior

**Machine Type:** `0x8664` (AMD64)
- 64-bit executable
- Requires 64-bit Windows
- x86-64 instruction set

**Subsystem:** Console Application
- Runs in console mode
- No GUI components
- Command-line driven

**Characteristics:**
- `IMAGE_FILE_EXECUTABLE_IMAGE` - Executable file
- `IMAGE_FILE_LARGE_ADDRESS_AWARE` - Can use >2GB address space
- `IMAGE_FILE_LINE_NUMS_STRIPPED` - Debug info removed
- `IMAGE_FILE_LOCAL_SYMS_STRIPPED` - Symbols removed

---

## PE Structure Analysis

### Section Layout

#### .text Section
**Characteristics:**
- **Size:** ~800 KB
- **Permissions:** Read, Execute
- **Content:** Executable code
- **Alignment:** 4 KB page-aligned

**Purpose:** Contains all executable code including:
- Main ransomware logic
- Cryptographic functions
- File system operations
- Threading implementation
- Statically linked libraries

#### .rdata Section
**Characteristics:**
- **Size:** ~200 KB
- **Permissions:** Read only
- **Content:** Read-only data, constants
- **Alignment:** 4 KB page-aligned

**Purpose:** Stores:
- String constants
- Virtual function tables (vtables)
- Import address table
- ChaCha20 constants
- RSA public key (at 0x1400fa080)
- Error messages

#### .data Section
**Characteristics:**
- **Size:** ~50 KB
- **Permissions:** Read, Write
- **Content:** Initialized data
- **Alignment:** 4 KB page-aligned

**Purpose:** Contains:
- Global variables
- Static variables
- Crypto context structures
- Configuration data

#### .pdata Section
**Characteristics:**
- **Size:** Variable
- **Permissions:** Read only
- **Content:** Exception handling data
- **Alignment:** 4 KB page-aligned

**Purpose:** Stack unwinding information for x64 exception handling

#### .reloc Section
**Characteristics:**
- **Size:** Variable
- **Permissions:** Read only
- **Content:** Relocation data
- **Alignment:** 4 KB page-aligned

**Purpose:** Base relocation information for ASLR (Address Space Layout Randomization)

---

## Import Analysis

### Critical DLL Dependencies

#### kernel32.dll - Core Windows API

**File I/O Operations:**
```
CreateFileW                 - Open files for encryption
ReadFile                    - Read file content
WriteFile                   - Write encrypted content
GetFileSizeEx               - Determine file size
SetFilePointerEx            - Navigate within files
CloseHandle                 - Close file handles
MoveFileExW                 - Rename files (add .akira)
FindFirstFileW              - Begin directory scanning
FindNextFileW               - Continue directory scanning
FindClose                   - End directory scanning
GetLogicalDrives            - Enumerate drives
SetFileInformationByHandle  - Atomic file rename
DeleteFileW                 - Delete original files
```

**Threading & Synchronization:**
```
CreateThread                - Create worker threads
WaitForMultipleObjects      - Thread synchronization
InitializeCriticalSection   - Initialize mutex
EnterCriticalSection        - Acquire lock
LeaveCriticalSection        - Release lock
DeleteCriticalSection       - Cleanup mutex
CreateIoCompletionPort      - ASIO thread pool
GetQueuedCompletionStatus   - ASIO event handling
PostQueuedCompletionStatus  - ASIO task dispatch
```

**Memory Management:**
```
VirtualAlloc                - Allocate memory pages
VirtualFree                 - Free memory pages
HeapAlloc                   - Heap allocation
HeapFree                    - Heap deallocation
GetProcessHeap              - Get process heap handle
```

**Process & System Information:**
```
GetSystemInfo               - CPU count detection
QueryPerformanceCounter     - High-resolution timing (RNG seed!)
GetCommandLineW             - Command-line parsing
GetCurrentProcess           - Process handle
ExitProcess                 - Clean termination
```

#### advapi32.dll - Security & Registry

**Cryptographic Functions:**
```
CryptAcquireContextW        - Initialize crypto provider (UNUSED)
CryptGenRandom              - Random number generation (UNUSED)
CryptReleaseContext         - Release crypto context (UNUSED)
```

**⚠️ Critical Finding:** Despite importing these functions, Akira does NOT use Windows Crypto API for encryption or random number generation. This suggests:
- Statically linked crypto library
- Custom RNG implementation
- Potential security weakness

#### rstrtmgr.dll - Restart Manager

**File Unlocking:**
```
RmStartSession              - Start Restart Manager session
RmRegisterResources         - Register locked files
RmShutdown                  - Force close file handles
RmEndSession                - End session
```

**Purpose:** Force-close files held open by other processes to enable encryption

#### shell32.dll - Shell Operations

**Execution:**
```
ShellExecuteW               - Execute PowerShell commands
CommandLineToArgvW          - Parse command-line arguments
```

**Usage:** PowerShell execution for shadow copy deletion

---

## String Analysis

### Embedded Strings Inventory

**Total Strings:** 1,334 plaintext strings

#### Category 1: Directory Blacklist (11 entries)

```
"Windows"                      - System directory
"Program Files"                - Application directory
"Program Files (x86)"          - 32-bit applications
"ProgramData"                  - Application data
"System Volume Information"    - Volume metadata
"$Recycle.Bin"                 - Recycle bin
"Boot"                         - Boot files
"Recovery"                     - Recovery partition
"AppData"                      - User application data
"Temp"                         - Temporary files
"tmp"                          - Alternative temp
```

**Purpose:** Avoid encrypting critical system files to maintain system stability

#### Category 2: Extension Blacklist (5 entries)

```
".exe"                         - Executables
".dll"                         - Dynamic libraries
".sys"                         - System drivers
".lnk"                         - Shortcuts
".msi"                         - Installers
```

**Purpose:** Prevent double-encryption and maintain system executability

#### Category 3: Target Extensions

```
".akira"                       - Encrypted file extension
```

**Renaming Process:**
```
Original: document.pdf
Encrypted: document.pdf.akira
```

#### Category 4: Ransom Note

**Filename:** `"akira_readme.txt"`

**Content Location:** 0x1400fb0d0 (2,936 bytes)

**Key Phrases:**
- "all your backups - virtual, physical - everything that we managed to reach - are completely removed"
- "identify backup solutions and download your data"
- "databases/source codes - generally speaking, everything that has a value"
- "all of this will be published in our blog"

**Tor URLs:**
```
akiralkzxzq2dsrzsrvbr2xgbbu2wgsmxryd4csgfameg52n7efvr2id.onion
akiral2iz6a7qgd3ayp3l6yub7xx2uep76idk3u2kollpj5z3z636bad.onion
torproject.org
```

#### Category 5: Error Messages

```
"Command line to argvW failed!"
"No cpu available!"
"Init crypto failed!"
"Get file size failed!"
"file rename failed"
"ShellExecute failed: "
```

**Purpose:** Logging and debugging (written to log file)

#### Category 6: Log Filename Template

```
"Log-%d-%m-%Y-%H-%M-%S"
```

**Example Output:**
```
Log-08-11-2025-14-30-45.txt
    DD MM YYYY HH MM SS
```

#### Category 7: PowerShell Command

**Location:** 0x1400ddf10 (75 bytes)

**Command:**
```powershell
powershell.exe -Command "Get-WmiObject Win32_Shadowcopy | Remove-WmiObject"
```

**Purpose:** Delete Volume Shadow Copy Service (VSS) snapshots to prevent recovery

#### Category 8: Cryptographic Constants

**ChaCha20 Sigma Constants:** 0x1400d0760
```
"expand 32-byte k"             - 256-bit key constant
"expand 16-byte k"             - 128-bit key constant
```

**Purpose:** ChaCha20 cipher initialization (standard constants)

#### Category 9: Protected Process Names (13 entries)

```
"spoolsv.exe"                  - Print spooler
"fontdrvhost.exe"              - Font driver
"explorer.exe"                 - Windows Explorer
"sihost.exe"                   - Shell infrastructure
"SearchUI.exe"                 - Windows Search
"lsass.exe"                    - Local Security Authority
"LogonUI.exe"                  - Logon UI
"winlogon.exe"                 - Windows Logon
"services.exe"                 - Service Control Manager
"csrss.exe"                    - Client/Server Runtime
"smss.exe"                     - Session Manager
"conhost.exe"                  - Console Window Host
"wininit.exe"                  - Windows Initialization
```

**Purpose:** Prevent terminating critical Windows processes via Restart Manager

---

## Startup Sequence

### Entry Point Analysis

**Function:** `entry` (0x14008dd38)

```c
void entry(void)
{
  __security_init_cookie();
  startup_main_wrapper();
  return;
}
```

**Operations:**

1. **Security Cookie Initialization** (`__security_init_cookie`)
   - Generates random stack canary value
   - Enables buffer overflow detection
   - Compiler-inserted protection (/GS flag)
   - Places cookie before return addresses
   - Checked on function return

2. **Transfer to CRT Wrapper**
   - Calls startup_main_wrapper
   - Never returns to entry point
   - Continues through CRT initialization chain

**Security Note:** Presence of stack cookies indicates compilation with `/GS` (Buffer Security Check) flag, providing some protection against stack-based buffer overflows.

---

### CRT Initialization Wrapper

**Function:** `startup_main_wrapper` (0x14008dbc4)

**Purpose:** C Runtime (CRT) initialization before main() execution

**Initialization Sequence:**

```
1. CRT Library Initialization
   ├─ __scrt_initialize_crt(1)
   ├─ Check: Success?
   │  ├─ YES → Continue
   │  └─ NO  → terminate_with_error(7)

2. Thread-Safe Startup
   ├─ __scrt_acquire_startup_lock()
   ├─ Check initialization state (DAT_140100ae8)
   │  ├─ State = 0 (Not Initialized)
   │  │  ├─ Set state = 1 (Initializing)
   │  │  ├─ _initterm_e() - C initializers
   │  │  ├─ _initterm() - C++ initializers
   │  │  └─ Set state = 2 (Initialized)
   │  ├─ State = 1 (Initializing)
   │  │  └─ Wait/Error
   │  └─ State = 2 (Already Initialized)
   │     └─ Error: Should not happen
   └─ __scrt_release_startup_lock()

3. Pre-Main Callbacks
   ├─ get_premain_callback_array()
   ├─ validate_callback_array()
   └─ execute_callback_array(0)

4. Thread-Local Cleanup Registration
   ├─ get_thread_atexit_array()
   ├─ validate_callback_array()
   └─ _register_thread_local_exe_atexit_callback()

5. Command-Line Preparation
   ├─ __scrt_get_show_window_mode()
   └─ _get_narrow_winmain_command_line()

6. *** MAIN FUNCTION EXECUTION ***
   └─ main() @ 0x14004d2b0

7. Post-Main Cleanup
   ├─ post_main_cleanup()
   ├─ Check: Success?
   │  ├─ YES:
   │  │  ├─ _cexit() - Call atexit functions
   │  │  ├─ __scrt_uninitialize_crt()
   │  │  └─ Return exit code
   │  └─ NO:
   │     ├─ terminate_with_error()
   │     └─ terminate_abnormally()
```

**Initialization State Machine:**

| State Value | State Name | Meaning |
|-------------|------------|---------|
| 0 | NOT_INITIALIZED | CRT not yet initialized |
| 1 | INITIALIZING | Initialization in progress |
| 2 | INITIALIZED | CRT fully initialized |

**State Storage:** Global variable `DAT_140100ae8`

---

### Error Codes

**CRT Error Codes:**

| Code | Hex | Meaning |
|------|-----|---------|
| 7 | 0x07 | CRT initialization failed |
| -1 | 0xFFFFFFFF | NULL pointer provided |
| -2 | 0xFFFFFFFE | Invalid parameter size |
| -3 | 0xFFFFFFFD | Initialization failed / Already initialized |
| -7 | 0xFFFFFFF9 | Memory allocation failed |
| -9 | 0xFFFFFFF7 | NULL data buffer |

---

## Main Function Architecture

### Main Function Overview

**Function:** `main` (0x14004d2b0)

**Size:** ~1500 lines of decompiled C code

**Complexity:** Very High - orchestrates entire ransomware operation

### Execution Phases

The main function implements a 9-phase execution model:

```
PHASE 1: Initialization & Logging Setup
  ├─ Get current timestamp (_time64)
  ├─ Format log filename (Log-DD-MM-YYYY-HH-MM-SS)
  ├─ Create log file path
  └─ Initialize logging system

PHASE 2: Command-Line Argument Parsing
  ├─ GetCommandLineW()
  ├─ CommandLineToArgvW() → argc, argv
  ├─ Build argv collection
  └─ Parse each argument flag

PHASE 3: Configuration Validation
  ├─ Convert encryption_percent string to int
  ├─ Validate range (1-100)
  ├─ Default to 50 if invalid
  └─ Check at least one target specified

PHASE 4: System Information Gathering
  ├─ GetSystemInfo() → CPU count
  ├─ Validate CPU count > 0
  └─ Check: SUCCESS → continue, FAIL → exit

PHASE 5: Thread Allocation Algorithm
  ├─ Boost CPU count if < 5
  │  ├─ If CPU = 1 → CPU = 2
  │  └─ If CPU < 5 → CPU *= 2
  ├─ Calculate thread allocation:
  │  ├─ Folder parsers = (CPU * 30) / 100
  │  ├─ Root parsers = (CPU * 10) / 100
  │  └─ Encryption = CPU - (folder + root)
  └─ Ensure root_parsers >= 1

PHASE 6: Cryptographic Engine Initialization
  ├─ Allocate crypto_engine (56 bytes)
  ├─ initialize_crypto_structure()
  ├─ Load embedded RSA key (0x1400fa080)
  ├─ init_crypto_engine()
  └─ Check: SUCCESS → continue, FAIL → exit

PHASE 7: Thread Pool Creation
  ├─ Allocate thread_pool (384 bytes)
  ├─ init_thread_pool()
  ├─ Create ASIO I/O contexts
  └─ Spawn worker threads

PHASE 8: Drive Enumeration & Target Selection
  ├─ initialize_drive_list()
  ├─ Check: -localonly flag?
  │  ├─ TRUE: enumerate_local_drives()
  │  └─ FALSE:
  │     ├─ Add --encryption_path if specified
  │     └─ Read --share_file if specified
  └─ Log all targets

PHASE 9: File Discovery & Encryption Dispatch
  ├─ For each target path:
  │  ├─ Check exclusions
  │  ├─ Create encryption task
  │  └─ enqueue_encrypt_task()
  ├─ Wait for folder_parser pool
  ├─ Wait for encryption pool
  └─ All tasks complete

PHASE 10: Post-Encryption Cleanup
  ├─ Check: -dellog flag?
  │  └─ Execute PowerShell (shadow copy deletion)
  ├─ Calculate execution time
  ├─ Log completion statistics
  ├─ cleanup_thread_pool()
  ├─ cleanup_crypto_engine()
  ├─ cleanup_drive_list()
  └─ Return SUCCESS
```

---

### Phase 1: Initialization & Logging

**Purpose:** Establish logging infrastructure for attack tracking

**Code Analysis:**

```c
void main(void) {
  __time64_t current_time;
  struct tm *local_time;
  char log_filename[80];

  // Get current timestamp
  _time64(&current_time);
  local_time = _localtime64(&current_time);

  // Format log filename: "Log-DD-MM-YYYY-HH-MM-SS"
  strftime(log_filename, 0x50, "Log-%d-%m-%Y-%H-%M-%S", local_time);

  // Create log file path string
  create_log_filepath(&log_filepath, log_filename);

  // Setup logging system
  setup_logging(&log_filepath);
}
```

**Log Filename Examples:**
```
Log-08-11-2025-14-30-45.txt
Log-08-11-2025-15-22-19.txt
Log-09-11-2025-09-15-03.txt
```

**Logging Purpose:**
- Track encryption progress
- Record errors
- Document statistics
- Timestamp attack events

---

### Phase 2: Command-Line Parsing

**Purpose:** Configure attack parameters

**Arguments Supported:**

#### 1. --encryption_path <path>
**Type:** Wide string (Unicode)
**Purpose:** Specify target path(s) to encrypt
**Storage:** `encryption_path` variable
**Validation:** Path existence checked later
**Example:** `--encryption_path "C:\Users\Documents"`

#### 2. --share_file <file>
**Type:** Wide string (Unicode)
**Purpose:** File containing list of network shares
**Storage:** `share_file_path` variable
**Format:** One share path per line
**Example:** `--share_file "\\server\shares.txt"`

#### 3. --encryption_percent <n>
**Type:** Integer (0-100)
**Purpose:** Percentage of each file to encrypt
**Storage:** Converted from string to int
**Default:** 50 (if not specified)
**Validation:** Must be 1-100
**Example:** `--encryption_percent 75`

#### 4. -localonly
**Type:** Boolean flag
**Purpose:** Only encrypt local drives (skip network)
**Storage:** `local_only_mode` boolean
**Default:** false (encrypt network shares too)
**Example:** `-localonly`

#### 5. -dellog
**Type:** Boolean flag
**Purpose:** Delete Windows shadow copies after encryption
**Storage:** `delete_logs_flag` boolean
**Default:** false
**Example:** `-dellog`

**Parsing Logic:**

```c
// Get command line
lpCmdLine = GetCommandLineW();

// Parse into argv array
argv = CommandLineToArgvW(lpCmdLine, &argc);

if (argv == NULL) {
    log_error("Command line to argvW failed!");
    return ERROR;
}

// Create configuration structures
create_config_structures(&config);

// Parse arguments into configuration
parse_arguments(&config, argc, argv);
```

---

### Phase 3: Configuration Validation

**Purpose:** Ensure valid configuration with safe defaults

**Validation Rules:**

```c
// Validate encryption_percent argument
if (encryption_percent_str != NULL) {
    errno_ptr = __doserrno();
    *errno_ptr = 0;

    // Convert string to integer
    encryption_percent = wcstol(encryption_percent_str, &endptr, 10);

    // Check if conversion was successful
    if (endptr == encryption_percent_str) {
        // No digits were converted - use default
        encryption_percent = 50;
    }

    // Check for range error
    if (*errno_ptr == ERANGE) {
        encryption_percent = 50;
    }
} else {
    // Default encryption percentage
    encryption_percent = 50;
}

// Validate range (1-100)
if (encryption_percent < 1 || encryption_percent > 100) {
    encryption_percent = 50;  // Reset to default
}
```

**Validation Policy:**
- Invalid values → Revert to default (50%)
- No error messages → Silent correction
- Ensures operation never fails due to bad input

**Default Configuration:**
```c
encryption_percent: 50
local_only_mode: false
delete_logs_flag: false
encryption_path: NULL (optional)
share_file_path: NULL (optional)
```

---

### Phase 5: Thread Allocation Algorithm

**Purpose:** Optimize performance for available CPU resources

**Algorithm:**

```c
// Get CPU count
cpu_count = system_info.dwNumberOfProcessors;

// Boost thread count for systems with few CPUs
if (cpu_count < 5) {
    if (cpu_count == 1) {
        cpu_count = 2;  // Single core becomes 2 threads
    }
    cpu_count = cpu_count * 2;  // Double for small systems
}

// Calculate thread allocation
folder_parser_threads = (cpu_count * 30) / 100;  // 30% for folder parsing
root_folder_threads = (cpu_count * 10) / 100;    // 10% for root parsing

// Ensure at least 1 root folder thread
if (root_folder_threads == 0) {
    root_folder_threads = 1;
}

// Remaining threads for encryption
encryption_threads = cpu_count - folder_parser_threads - root_folder_threads;

// Log thread allocation
log_info("Number of thread to folder parsers = %d", folder_parser_threads);
log_info("Number of thread to root folder parsers = %d", root_folder_threads);
log_info("Number of threads to encrypt = %d", encryption_threads);
```

**Thread Allocation Examples:**

| CPU Count | After Boost | Folder (30%) | Root (10%) | Encrypt (60%) | Total |
|-----------|-------------|--------------|------------|---------------|-------|
| 1         | 4           | 1            | 1          | 2             | 4     |
| 2         | 8           | 2            | 1          | 5             | 8     |
| 4         | 16          | 4            | 1          | 11            | 16    |
| 8         | 8           | 2            | 1          | 5             | 8     |
| 16        | 16          | 4            | 1          | 11            | 16    |
| 32        | 32          | 9            | 3          | 20            | 32    |

**Design Rationale:**
- **30% Folder Parsing:** I/O-bound directory traversal
- **10% Root Handling:** Root directory special processing
- **60% Encryption:** CPU-intensive encryption operations
- **Boost for Low CPU:** Compensate for thread overhead

---

### Phase 6: Cryptographic Initialization

**Purpose:** Initialize encryption engine with embedded key material

**Process:**

```c
// Get number of available CPUs
GetSystemInfo(&system_info);

if (system_info.dwNumberOfProcessors == 0) {
    log_error("No cpu available!");
    return ERROR_NO_CPU;
}

// Allocate crypto engine structure
crypto_engine = operator_new(0x38);  // 56 bytes
initialize_crypto_structure(crypto_engine);

// Initialize crypto engine with key material
crypto_key_id = atoi(crypto_config_string);
result = init_crypto_engine(
    crypto_engine,
    crypto_key_id,
    embedded_key_data,      // RSA public key at 0x1400fa080
    use_asymmetric_crypto
);

if (result != 0) {
    log_error("Init crypto failed!");
    return ERROR_CRYPTO_INIT;
}
```

**Crypto Structure Size:** 56 bytes (0x38)

**Crypto Initialization Steps:**
1. Allocate structure memory
2. Zero-initialize structure
3. Load embedded RSA public key
4. Initialize ChaCha20 context
5. Validate initialization

---

### Phase 7: Thread Pool Creation

**Purpose:** Create worker thread pools for parallel encryption

**Structure Size:** 384 bytes (0x180)

```c
// Create thread pool with calculated thread counts
thread_pool = operator_new(0x180);

init_thread_pool(
    thread_pool,
    folder_parser_threads,
    root_folder_threads
);
```

**Thread Pool Architecture:**
- **Pool 1:** Folder parser threads (2-4 threads typically)
- **Pool 2:** Root folder parser threads (1-3 threads)
- **Pool 3:** Encryption worker threads (6-12 threads typically)

---

### Phase 8: Drive Enumeration

**Decision Tree:**

```
Mode Check: -localonly flag
├─ TRUE: Local Only Mode
│   ├─ Enumerate A: through Z:
│   ├─ Check drive type (Fixed, Removable)
│   ├─ Add accessible drives to target list
│   └─ Log each drive found
│
└─ FALSE: Network Mode
    ├─ If --encryption_path specified
    │   └─ Add specified path(s)
    │
    └─ If --share_file specified
        ├─ Read file line by line
        ├─ Parse each network share path
        └─ Add to target list
```

**Drive Type Classification:**

| Drive Type | Constant | Encrypted? |
|------------|----------|------------|
| Fixed drive | DRIVE_FIXED | ✅ YES |
| Removable drive | DRIVE_REMOVABLE | ✅ YES |
| Network drive | DRIVE_REMOTE | ✅ YES |
| CD-ROM | DRIVE_CDROM | ✅ YES |
| Unknown | DRIVE_UNKNOWN | ❌ NO |
| No root directory | DRIVE_NO_ROOT_DIR | ❌ NO |

---

### Phase 9: Encryption Dispatch

**Purpose:** Create and distribute encryption tasks to worker threads

```c
// For each target path (drive or share)
for (each path in target_list) {

    // Check if -localonly mode and this is network
    if (local_only_mode && is_network_path(path)) {
        continue;  // Skip network paths
    }

    // Check file extension exclusions
    if (is_excluded_extension(path)) {
        continue;  // Skip .akira files
    }

    // Enqueue encryption task
    enqueue_encrypt_task(
        thread_pool,
        share_list_ptr,
        &path,
        crypto_engine,
        encryption_percent,
        is_partial_encrypt
    );
}

// Wait for all encryption tasks to complete
wait_for_task_completion(thread_pool->folder_parser_pool);
wait_for_task_completion(thread_pool->encryption_pool);
```

**Task Queueing Process:**
1. Validate path accessibility
2. Check exclusion filters
3. Create encryption task structure (288 bytes)
4. Add to appropriate thread pool queue
5. Signal worker threads (condition variable)
6. Worker threads pick up tasks FIFO

---

### Phase 10: Post-Encryption Cleanup

**Purpose:** Shadow copy deletion and resource cleanup

```c
// Check if log deletion requested
if (delete_logs_flag) {

    // Build PowerShell command
    build_powershell_command(
        &ps_command,
        PS_CLEAR_SHADOW_COPIES
    );

    // Execute PowerShell
    result = ShellExecuteW(
        NULL,
        NULL,
        L"powershell.exe",
        ps_command,
        NULL,
        SW_HIDE  // Hidden window
    );

    if (result < 33) {
        log_error("ShellExecute failed: %d", result);
    }
}

// Calculate execution time
end_time = get_high_precision_timer();
elapsed_ms = (end_time - start_time) / 1000000;

// Log completion statistics
log_info("Encryption completed in %lld ms", elapsed_ms);

// Cleanup resources
cleanup_thread_pool(thread_pool);
cleanup_crypto_engine(crypto_engine);
cleanup_drive_list(&drive_list);

return SUCCESS;
```

**Shadow Copy Deletion Command:**
```powershell
powershell.exe -Command "Get-WmiObject Win32_Shadowcopy | Remove-WmiObject"
```

**Execution Method:**
- Uses `ShellExecuteW` API
- Hidden window (SW_HIDE)
- Non-blocking execution
- Error logged but not fatal

---

## Command-Line Interface

### Execution Examples

#### Example 1: Encrypt Specific Path (Default Settings)
```cmd
akira.exe --encryption_path "C:\Users\Documents"
```
- Encrypts only C:\Users\Documents
- 50% partial encryption (default)
- No shadow copy deletion
- Includes network shares

#### Example 2: Local Drives Only with Full Encryption
```cmd
akira.exe -localonly --encryption_percent 100
```
- Encrypts all local drives (A-Z)
- 100% full encryption
- Skips network shares
- No shadow copy deletion

#### Example 3: Network Shares from File
```cmd
akira.exe --share_file "\\server\shares.txt" --encryption_percent 30 -dellog
```
- Reads share list from file
- 30% partial encryption
- Deletes shadow copies after encryption
- Targets network shares only

#### Example 4: Maximum Stealth
```cmd
akira.exe --encryption_path "C:\" --encryption_percent 25 -localonly -dellog
```
- Local C: drive only
- Minimal encryption (25%) for speed
- Deletes shadow copies
- No network activity

#### Example 5: Enterprise Attack
```cmd
akira.exe --share_file "shares.txt" --encryption_percent 50
```
- Multiple network shares
- Balanced encryption
- Maximum damage
- Typical deployment scenario

---

## Configuration Management

### Configuration Structure

**Based on analysis, configuration stored in multiple variables:**

```c
struct RansomwareConfig {
    // Command-line arguments
    wchar_t* encryption_path;           // --encryption_path value
    wchar_t* share_file_path;           // --share_file value
    int encryption_percent;             // --encryption_percent value (1-100)
    bool local_only_mode;               // -localonly flag
    bool delete_logs_flag;              // -dellog flag

    // Calculated values
    int folder_parser_threads;          // CPU * 30%
    int root_folder_threads;            // CPU * 10%
    int encryption_threads;             // CPU * 60%

    // Runtime state
    void* crypto_engine;                // Crypto engine instance (56 bytes)
    void* thread_pool;                  // Thread pool instance (384 bytes)
    collection* drive_list;             // List of drives/shares
    collection* share_list;             // Network shares
};
```

### Default Values

```c
encryption_percent: 50
local_only_mode: false
delete_logs_flag: false
encryption_path: NULL (optional)
share_file_path: NULL (optional)
```

### Validation Rules

1. **encryption_percent:** Must be 1-100, defaults to 50 if invalid
2. **At least one target:** Path, share file, or -localonly must be specified
3. **CPU count:** Must be > 0
4. **Crypto engine:** Must initialize successfully
5. **Thread pool:** Must create successfully

---

## Error Handling

### Error Handling Strategy

**Philosophy:** Graceful degradation where possible, fatal errors cause clean exit

**Error Categories:**

#### Fatal Errors (Immediate Exit)
- CRT initialization failure
- No CPU available
- Crypto engine initialization failure
- Memory allocation failure
- Command-line parsing failure

#### Non-Fatal Errors (Logged & Continue)
- Individual file encryption failure
- Shadow copy deletion failure
- Network share accessibility failure
- Invalid configuration values (use defaults)

### Error Logging

**All errors logged to:** `Log-DD-MM-YYYY-HH-MM-SS.txt`

**Format:**
```
[TIMESTAMP] ERROR: <error_message>
[TIMESTAMP] INFO: <info_message>
[TIMESTAMP] SUCCESS: <success_message>
```

### Exit Codes

| Code | Meaning | Severity |
|------|---------|----------|
| 0 | Success | Normal |
| 7 | CRT init failed | Fatal |
| -1 | NULL pointer | Fatal |
| -2 | Invalid parameter | Fatal |
| -3 | Init failed | Fatal |
| -7 | Memory allocation failed | Fatal |

---

## Function Reference

### Complete Function List (Phase 1-2)

#### Startup Sequence (10 functions)
```
0x14008dd38  entry
0x14008dbc4  startup_main_wrapper
0x14008e30c  terminate_with_error
0x14008e650  get_premain_callback_array
0x14008d8a0  validate_callback_array
0x14008e658  get_thread_atexit_array
0x14008e49c  post_main_cleanup
0x1400a0e04  terminate_abnormally
0x1400a0dbc  terminate_with_error_ex
0x14004d2b0  main
```

#### Logging (1 function)
```
0x14004cf60  setup_logging
```

#### Argument Parsing (5 functions)
```
0x14004fe80  parse_command_line_arg
0x140050cd0  extract_arg_value
0x140054870  build_argv_collection
0x140050ef0  convert_wstring_to_string
0x140055e70  add_to_collection
```

#### Cryptography (2 functions)
```
0x140084210  init_crypto_engine
0x140083620  initialize_crypto_structure
```

#### Drive/Share Enumeration (3 functions)
```
0x14007e6a0  initialize_drive_list
0x140042830  read_share_file
0x140054d30  build_share_list
```

#### Threading (2 functions)
```
0x14007b6d0  init_thread_pool
0x14007b850  enqueue_encrypt_task
```

#### File Operations (2 functions)
```
0x1400bf190  folder_processor_worker
0x14007c470  encrypt_file_worker
```

**Total Functions Analyzed:** 25 functions

---

## Appendix: Data Structures

### Global Initialization State

```c
// Address: DAT_140100ae8
enum InitState {
    NOT_INITIALIZED = 0,
    INITIALIZING = 1,
    INITIALIZED = 2
};
```

### Crypto Engine Structure

```c
// Size: 0x38 (56 bytes)
struct CryptoEngine {
    uint8_t unknown_0x00[0x18];    // 24 bytes - initialization data
    void* context_ptr;             // 0x18 - pointer to crypto context
    void* key_data_ptr;            // 0x20 - pointer to key material
    uint8_t flags[2];              // 0x28-0x29 - status flags
    uint8_t unknown_0x2a[14];      // Remaining bytes
};
```

### Thread Pool Structure

```c
// Size: 0x180 (384 bytes)
struct ThreadPool {
    void* asio_context_1;          // 0x00 - ASIO I/O context
    void* asio_context_2;          // 0x08 - ASIO I/O context
    void* folder_parser_pool;      // 0x10 - Folder thread pool
    void* root_folder_pool;        // 0x20 - Root folder thread pool
    void* encryption_pool;         // 0x30 - Encryption thread pool
    int folder_thread_count;       // 0x28 - Folder parsers
    int root_thread_count;         // 0x2C - Root parsers
    int encryption_thread_count;   // 0x30 - Encryption workers
    CRITICAL_SECTION cs_folder;    // 0x40 - Folder mutex (80 bytes)
    CRITICAL_SECTION cs_encryption;// 0x90 - Encryption mutex (80 bytes)
    CONDITION_VARIABLE cv_folder;  // 0xE0 - Folder CV (72 bytes)
    CONDITION_VARIABLE cv_encrypt; // 0x128 - Encryption CV (72 bytes)
    uint8_t remaining[...];        // Additional fields
};
```

---

**Last Updated:** 2025-11-08
**Research Organization:** MottaSec
**Document Version:** 1.0
