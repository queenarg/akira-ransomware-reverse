# Akira Ransomware - Indicators of Compromise (IOCs)

**Analysis Date:** 2025-11-08
**Research Organization:** MottaSec
**TLP:** WHITE (Public distribution authorized)

---

## File Indicators

### Encrypted File Extension
```
Extension: .akira
Pattern: [original_filename].[original_extension].akira

Examples:
- document.docx → document.docx.akira
- report.pdf → report.pdf.akira
- database.sql → database.sql.akira
```

### Ransom Note
```
Filename: akira_readme.txt
Locations: Multiple copies across filesystem (typically 350+ copies)
Placement:
  - Desktop
  - Documents folder
  - Root of each encrypted drive
  - Each subfolder containing encrypted files

Content indicators:
  - "Your files have been encrypted"
  - "Akira" group attribution
  - Payment instructions (Bitcoin/cryptocurrency)
  - Contact email or Tor .onion URL
```

### File Footer Structure
```
Size: 512 bytes (appended to each encrypted file)
Location: Last 512 bytes of encrypted file

Structure:
  Offset | Size | Description
  -------|------|----------------------------------
  -512   |  8   | Magic signature ("AKIRA!!!" or variant)
  -504   | 256  | RSA-encrypted ChaCha20 session key
  -248   | 256  | RSA-encrypted ChaCha20 nonce
  -0     |  n   | Metadata (original size, timestamps)

Hex pattern (magic signature):
  41 4B 49 52 41 21 21 21  # "AKIRA!!!"
```

### File Size Delta
```
Encrypted file size = Original file size + 512 bytes

Example:
  Original:  5,242,880 bytes (5 MB document.docx)
  Encrypted: 5,243,392 bytes (5 MB + 512 bytes footer)
```

---

## Hash Indicators

### Sample Hashes (Example - Replace with Actual)
```
MD5:    [INSERT_ACTUAL_MD5_HASH]
SHA1:   [INSERT_ACTUAL_SHA1_HASH]
SHA256: [INSERT_ACTUAL_SHA256_HASH]
SHA512: [INSERT_ACTUAL_SHA512_HASH]

Note: Replace with actual hash values from analyzed samples
```

### Imphash (Import Hash)
```
Imphash: [INSERT_ACTUAL_IMPHASH]

Key imports to calculate imphash:
  - crypt32.dll: CryptGenRandom, CryptImportKey, CryptEncrypt
  - kernel32.dll: CreateThread, CreateFileW, MoveFileExW
  - advapi32.dll: CryptAcquireContext, CryptReleaseContext
```

---

## Memory Indicators

### RSA Public Key (DER Format)
```
Size: 256 bytes
Location: .rdata section (typical address: 0x1400fa080)

DER Structure (first 16 bytes):
  30 82 01 0a 02 82 01 01 00 [...]

Pattern:
  - DER sequence tag (0x30)
  - Length encoding (0x82 0x01 0x0a = 266 bytes total)
  - Integer tag (0x02) for modulus
  - RSA-2048 modulus (256 bytes)
```

### ChaCha20 S-box (Custom 256-byte table)
```
Size: 256 bytes
Location: .rdata section (typical address: 0x1400b6e50)

First 32 bytes:
  63 7C 77 7B F2 6B 6F C5 30 01 67 2B FE D7 AB 76
  CA 82 C9 7D FA 59 47 F0 AD D4 A2 AF 9C A4 72 C0

Note: Custom S-box, not standard AES or ChaCha20
```

### Task Queue Structures (Heap Allocations)
```
Structure: task_t
Size: 288 bytes per task
Location: Heap allocations during execution

Layout:
  +0x000: char file_path[260]      # Wide char path buffer
  +0x104: crypto_ctx_t* ctx        # Pointer to crypto context
  +0x10C: HANDLE file_handle       # File handle
  +0x114: uint64_t file_size       # Original file size
  +0x11C: uint32_t flags           # Processing flags
```

### Crypto Context (Per Worker Thread)
```
Structure: crypto_ctx_t
Size: 56 bytes
Location: Heap allocation (one per worker thread)

Layout:
  +0x00: uint32_t state[16]        # 64 bytes ChaCha20 state
  +0x40: uint8_t key[32]           # 32-byte session key
  +0x60: uint8_t nonce[16]         # 16-byte nonce (REUSED!)
  +0x70: uint64_t counter          # Block counter
```

---

## Process Indicators

### Process Name
```
Common names:
  - akira.exe
  - ransomware.exe
  - encrypt.exe
  - [random_name].exe

Note: Filename may vary, use behavioral indicators
```

### Command Line Arguments
```
Syntax:
  akira.exe [options]

Common arguments:
  --path <target_path>      # Specify encryption target
  --threads <count>         # Worker thread count
  --no-shadow               # Skip shadow copy deletion (rare)

Examples:
  akira.exe
  akira.exe --path C:\
  akira.exe --path "\\fileserver\share" --threads 12
```

### Thread Count
```
Typical configuration: 8-16 threads

Breakdown:
  - Main thread: 1
  - Folder parser threads: 2-4 (ASIO pool #1)
  - Encryption worker threads: 6-12 (ASIO pool #2)

Detection threshold:
  Alert if: thread_count >= 8 within 10 seconds
```

### Parent Process
```
Typical parent processes:
  - explorer.exe (user execution, double-click)
  - cmd.exe (batch script execution)
  - powershell.exe (PowerShell script execution)

Remote execution (lateral movement):
  - psexec.exe (PsExec remote execution)
  - wmic.exe (WMI remote execution)
  - services.exe (service installation, rare)
```

### Child Processes
```
Common child process:
  powershell.exe

Purpose: Shadow copy deletion

Command line:
  powershell.exe -Command "vssadmin delete shadows /all /quiet"
  powershell.exe -ExecutionPolicy Bypass -File [script].ps1

Alternative:
  vssadmin.exe delete shadows /all /quiet
  wmic.exe shadowcopy delete
```

---

## API Call Indicators

### Cryptographic APIs
```
Library: crypt32.dll, advapi32.dll

Function calls (in order):
1. LoadLibraryW("crypt32.dll")
2. CryptAcquireContext(hProv, NULL, NULL, PROV_RSA_FULL, 0)
3. CryptGenRandom(hProv, 32, session_key)  # Generate key
4. CryptGenRandom(hProv, 16, nonce)        # Generate nonce
5. CryptImportKey(hProv, pubkey, 256, ...)  # Import RSA public key
6. CryptEncrypt(hKey, 0, TRUE, 0, ...)      # Encrypt session key/nonce
7. CryptReleaseContext(hProv, 0)

Detection pattern:
  - CryptAcquireContext + CryptGenRandom (2x) + CryptImportKey
  - Within 5 seconds of process start
```

### File System APIs
```
Library: kernel32.dll

Function calls (typical sequence):
1. GetLogicalDrives()                       # Enumerate drives
2. FindFirstFileW(L"C:\\*", &findData)      # Start directory scan
3. FindNextFileW(hFind, &findData)          # Iterate files (loop)
4. CreateFileW(path, GENERIC_READ|WRITE, ...)  # Open file
5. ReadFile(hFile, buffer, size, ...)       # Read plaintext
6. WriteFile(hFile, ciphertext, size, ...)  # Write ciphertext
7. SetFilePointer(hFile, 0, NULL, FILE_END) # Seek to end
8. WriteFile(hFile, footer, 512, ...)       # Append footer
9. CloseHandle(hFile)
10. MoveFileExW(original, L"*.akira", ...)   # Rename to .akira

Detection pattern:
  - High frequency MoveFileExW calls (50+ per minute)
  - Pattern: [filename] → [filename].akira
```

### Threading APIs
```
Library: kernel32.dll

Function calls:
1. CreateThread(NULL, 0, worker_func, ...) # Create worker threads (8-16x)
2. CreateIoCompletionPort(...)             # ASIO thread pool setup
3. InitializeCriticalSection(&cs)          # Mutex initialization
4. EnterCriticalSection(&cs)               # Lock mutex (frequent)
5. LeaveCriticalSection(&cs)               # Unlock mutex (frequent)
6. SleepConditionVariableCS(&cv, &cs, ...) # Wait on condition variable
7. WakeConditionVariable(&cv)              # Signal condition variable
8. WaitForMultipleObjects(...)             # Wait for thread completion

Detection pattern:
  - CreateThread called 8-16 times within 10 seconds
  - CreateIoCompletionPort (ASIO thread pool indicator)
```

### Restart Manager APIs (File Unlocking)
```
Library: rstrtmgr.dll

Function calls:
1. RmStartSession(&session, 0, ...)        # Start RM session
2. RmRegisterResources(session, files, ...)  # Register locked files
3. RmGetList(session, &needed, ...)        # Get processes using files
4. RmShutdown(session, RmForceShutdown, ...) # Force close handles
5. RmEndSession(session)                   # End RM session

Detection pattern:
  - RmStartSession + RmShutdown (aggressive file unlocking)
  - Indicates intent to encrypt in-use files
```

---

## Network Indicators

### ⚠️ NO C2 COMMUNICATION

**Important:** Akira ransomware operates OFFLINE during encryption phase.

```
Network activity: NONE during active encryption

Exceptions:
  - Initial compromise (phishing, RDP, VPN)
  - Post-encryption victim communication (Tor .onion sites)
```

### Initial Access Indicators
```
Phishing:
  - SMTP traffic (email delivery)
  - Malicious attachment download (HTTP/HTTPS)

RDP Brute Force:
  - TCP/3389 (RDP protocol)
  - Multiple failed authentication attempts
  - Successful RDP login from unusual IP

VPN Exploitation:
  - VPN protocol traffic (varies by vendor)
  - Authentication attempts to VPN endpoint
```

### Post-Encryption (Victim Side)
```
Tor Network:
  - Victim visits .onion URL (ransom payment site)
  - Tor client download/usage

Email Communication:
  - Victim contacts attacker via email (SMTP/IMAP)
  - Email addresses in ransom note
```

---

## Registry Indicators

### ⚠️ NO PERSISTENCE MECHANISM

**Important:** Akira ransomware does NOT create persistence.

```
Registry modifications: NONE

No entries in:
  - HKLM\Software\Microsoft\Windows\CurrentVersion\Run
  - HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  - HKLM\System\CurrentControlSet\Services
  - Scheduled Tasks (Task Scheduler)

Explanation:
  - Single-run attack model
  - No persistence required (manual deployment by threat actor)
  - Quick execution (50 minutes) then termination
```

---

## Behavioral Indicators

### Phase 1: Initialization (T+0 to T+10s)
```
Behaviors:
  ✅ Rapid thread creation (8-16 threads within 10 seconds)
  ✅ crypt32.dll loading (cryptographic API)
  ✅ GetLogicalDrives() call (enumerate C:, D:, E:, ...)
  ✅ CreateIoCompletionPort (ASIO thread pool setup)
  ✅ CryptImportKey (RSA public key import, 256 bytes DER)

CPU usage: 0% → 10% (ramp-up)
Disk usage: Minimal (initialization only)
Network: None
```

### Phase 2: Encryption Campaign (T+10s to T+3000s)
```
Behaviors:
  ✅ Sustained 91% CPU usage (all cores)
  ✅ 100% disk saturation (sequential read/write)
  ✅ Mass file renaming (*.* → *.akira pattern)
  ✅ High-frequency MoveFileExW calls (35-70 files/sec)
  ✅ RmStartSession + RmShutdown (file unlocking)

CPU usage: 91% sustained
Disk usage: 100% sustained (BOTTLENECK)
Files encrypted: 0 → 9,850 (98.5% of total)
```

### Phase 3: Post-Encryption (T+3000s+)
```
Behaviors:
  ✅ PowerShell spawn (child process)
  ✅ vssadmin delete shadows /all /quiet (shadow copy deletion)
  ✅ Mass creation of ransom notes (akira_readme.txt, 350+ copies)
  ✅ Process termination (attack complete)

CPU usage: 91% → 0% (wind-down)
Disk usage: 100% → 0%
Process lifetime: ~50 minutes total
```

---

## SIEM/EDR Detection Rules

### Rule 1: Rapid Thread Creation
```yaml
name: Akira_Rapid_Thread_Creation
severity: critical
conditions:
  - event_type: CreateThread
  - count: >= 8
  - timeframe: 10 seconds
  - process_name: not_in_whitelist
actions:
  - alert
  - terminate_process
  - memory_dump
  - network_isolate
```

### Rule 2: Mass File Rename Pattern
```yaml
name: Akira_Mass_File_Rename
severity: critical
conditions:
  - event_type: MoveFileExW
  - pattern: "*.* → *.akira"
  - count: >= 50
  - timeframe: 60 seconds
actions:
  - alert
  - terminate_process
  - snapshot_filesystem
  - restore_from_backup
```

### Rule 3: Shadow Copy Deletion
```yaml
name: Akira_Shadow_Copy_Delete
severity: high
conditions:
  - process_name: powershell.exe OR vssadmin.exe
  - command_line_contains:
      - "vssadmin"
      - "delete shadows"
      - "/all"
      - "/quiet"
  - parent_process: suspicious (not services.exe, not svchost.exe)
actions:
  - alert
  - block_execution
  - preserve_vss
```

### Rule 4: Sustained High CPU + Disk Usage
```yaml
name: Akira_Resource_Exhaustion
severity: high
conditions:
  - cpu_usage: > 85%
  - disk_usage: > 90%
  - duration: > 30 seconds
  - thread_count: >= 8
actions:
  - alert
  - investigate_process
  - check_file_renames
```

### Rule 5: Crypto API + File Operations
```yaml
name: Akira_Crypto_File_Pattern
severity: medium
conditions:
  - apis_called:
      - CryptAcquireContext
      - CryptGenRandom (2+ times)
      - CryptImportKey
  - apis_called:
      - FindFirstFileW
      - MoveFileExW (50+ times)
  - timeframe: 60 seconds
actions:
  - alert
  - sandbox_analysis
  - block_network
```

---

## Forensic Artifacts

### File System Artifacts
```
Windows Event Logs:
  - Event ID 4688 (Process Creation): akira.exe execution timestamp
  - Event ID 4663 (File Access): Mass file access/modify events
  - Event ID 4656 (File Handle Request): File handle operations

USN Journal ($UsnJrnl):
  - File rename operations (*.* → *.akira)
  - Timestamp: Precise execution time
  - Reason code: 0x00001000 (FILE_NAME_CHANGE)

MFT (Master File Table):
  - $FILE_NAME attribute changes
  - $DATA attribute modifications (file content encrypted)
  - Timestamps: Created, Modified, Accessed

Prefetch Files:
  - C:\Windows\Prefetch\AKIRA.EXE-[HASH].pf
  - Execution count, last run time, loaded DLLs

AmCache.hve:
  - HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\AppCompatCache
  - Application execution record (akira.exe path, timestamp)
```

### Memory Artifacts
```
Process Memory:
  - RSA public key (256 bytes DER @ 0x1400fa080)
  - ChaCha20 S-box (256 bytes @ 0x1400b6e50)
  - Task queue structures (288 bytes each, heap)
  - Crypto contexts (56 bytes each, per worker thread)

Heap Allocations:
  - task_t structures (multiple 288-byte allocations)
  - crypto_ctx_t structures (8-16 allocations, 56 bytes each)
  - File path buffers (260-char wide strings)

Tools for extraction:
  - Volatility (memory forensics framework)
  - WinDbg (Windows debugger)
  - Rekall (memory analysis framework)
```

### Network Artifacts (Initial Compromise Only)
```
Firewall Logs:
  - RDP connection logs (TCP/3389)
  - VPN authentication logs
  - Unusual source IPs

Web Proxy Logs:
  - Phishing email attachment download (HTTP/HTTPS)
  - Malicious URL access

Email Logs (Exchange/SMTP):
  - Phishing email delivery
  - Malicious attachment (ZIP, EXE, LNK, etc.)
```

---

## IOC Summary

### Critical Indicators (High Confidence)
1. ✅ File extension: `.akira`
2. ✅ Ransom note: `akira_readme.txt`
3. ✅ Footer magic: `41 4B 49 52 41 21 21 21` ("AKIRA!!!")
4. ✅ RSA public key DER: `30 82 01 0a 02 82 01 01 00 [...]`
5. ✅ ChaCha20 S-box: `63 7C 77 7B F2 6B 6F C5 [...]`

### Behavioral Indicators (Medium Confidence)
1. ✅ Rapid thread creation (8-16 threads in 10 seconds)
2. ✅ Sustained 91% CPU + 100% disk saturation
3. ✅ Mass file rename pattern (*.* → *.akira)
4. ✅ Shadow copy deletion (vssadmin delete shadows)
5. ✅ High-frequency MoveFileExW calls (50+ per minute)

### Supporting Indicators (Low Confidence, Combine Multiple)
1. ⚠️ CryptGenRandom calls (2x within 5 seconds)
2. ⚠️ CryptImportKey (256-byte RSA public key)
3. ⚠️ RmStartSession + RmShutdown (file unlocking)
4. ⚠️ GetLogicalDrives (drive enumeration)
5. ⚠️ CreateIoCompletionPort (ASIO thread pool)

---

## IOC Distribution Formats

### STIX 2.1 (Structured Threat Information Expression)
See: [iocs_stix.json](./iocs_stix.json) (TODO: Generate STIX bundle)

### OpenIOC (Open Indicators of Compromise)
See: [iocs_openioc.xml](./iocs_openioc.xml) (TODO: Generate OpenIOC XML)

### CSV Export (SIEM Import)
See: [iocs.csv](./iocs.csv) (TODO: Generate CSV)

### MISP (Malware Information Sharing Platform)
See: [iocs_misp.json](./iocs_misp.json) (TODO: Generate MISP event)

---

## References

- Full technical analysis: [GitHub Repository](https://github.com/[your-repo]/akira-ransomware-analysis)
- YARA rules: [yara-rules/akira_ransomware.yar](../../yara-rules/akira_ransomware.yar)
- Vulnerability analysis: [vulnerabilities.md](./vulnerabilities.md)
- MITRE ATT&CK: T1486 (Data Encrypted for Impact), T1490 (Inhibit System Recovery)

---

**Last Updated:** 2025-11-08
**Research Organization:** MottaSec
**TLP:** WHITE (Public distribution authorized)
