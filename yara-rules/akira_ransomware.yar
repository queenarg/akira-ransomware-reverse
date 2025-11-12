/*
   YARA Rules for Akira Ransomware Detection

   Organization: MottaSec
   Date: 2025-11-08
   Description: Detection rules for Akira ransomware binary and encrypted files

   References:
   - Full analysis: https://github.com/[your-repo]/akira-ransomware-analysis
*/

rule Akira_Ransomware_Binary_RSA_Key {
    meta:
        description = "Detects Akira ransomware binary by RSA public key DER structure"
        author = "MottaSec"
        date = "2025-11-08"
        severity = "critical"
        tlp = "white"
        reference = "https://github.com/[your-repo]/akira-ransomware-analysis"
        hash1 = "INSERT_SHA256_HASH_HERE"

    strings:
        // DER-encoded RSA public key header (2048-bit key, 256 bytes)
        $rsa_der_header = { 30 82 01 0a 02 82 01 01 00 }

        // RSA key location in .rdata section (typical offset)
        $rsa_key_marker = { 30 82 01 0a 02 82 01 01 00 [256-512] }

        // ChaCha20 S-box (custom 256-byte lookup table)
        // First 16 bytes of S-box
        $chacha_sbox = { 63 7C 77 7B F2 6B 6F C5 30 01 67 2B FE D7 AB 76 }

        // Blacklist strings (directory filtering)
        $blacklist_windows = "Windows" ascii wide
        $blacklist_progfiles = "Program Files" ascii wide
        $blacklist_sysvolinfo = "System Volume Information" ascii wide
        $blacklist_recyclebin = "$Recycle.Bin" ascii wide
        $blacklist_boot = "Boot" ascii wide

        // Extension blacklist strings
        $ext_exe = ".exe" ascii wide
        $ext_dll = ".dll" ascii wide
        $ext_sys = ".sys" ascii wide
        $ext_lnk = ".lnk" ascii wide
        $ext_msi = ".msi" ascii wide

        // Target file extension (encrypted files)
        $target_ext = ".akira" ascii wide

        // Ransom note filename
        $ransom_note = "akira_readme.txt" ascii wide nocase

        // Crypto API imports (used for RSA and random number generation)
        $import_crypt32 = "crypt32.dll" ascii nocase
        $import_advapi32 = "advapi32.dll" ascii nocase

        // Specific crypto functions
        $func_cryptgenrandom = "CryptGenRandom" ascii
        $func_cryptimportkey = "CryptImportKey" ascii
        $func_cryptencrypt = "CryptEncrypt" ascii

    condition:
        uint16(0) == 0x5A4D and  // PE header (MZ)
        filesize < 5MB and
        (
            // High confidence: RSA key + ChaCha20 S-box
            ($rsa_der_header and $chacha_sbox) or

            // Medium confidence: RSA key + multiple blacklist strings + crypto imports
            ($rsa_key_marker and
             3 of ($blacklist_*) and
             2 of ($import_*)) or

            // Lower confidence: Blacklist strings + extension filters + ransom note
            (5 of ($blacklist_*) and
             3 of ($ext_*) and
             ($target_ext or $ransom_note) and
             2 of ($func_*))
        )
}

rule Akira_Ransomware_Encrypted_File_Footer {
    meta:
        description = "Detects files encrypted by Akira ransomware via footer signature"
        author = "MottaSec"
        date = "2025-11-08"
        severity = "high"
        tlp = "white"
        reference = "https://github.com/[your-repo]/akira-ransomware-analysis"

    strings:
        // Footer magic signature (8 bytes, various observed variants)
        $magic1 = "AKIRA!!!" ascii
        $magic2 = "akira!!!" ascii
        $magic3 = { 41 4B 49 52 41 21 21 21 }  // AKIRA!!! in hex

    condition:
        // Check for magic signature in last 512 bytes of file
        for any of ($magic*) : (@ >= (filesize - 512) and @ < filesize)
}

rule Akira_Ransomware_Memory_Indicators {
    meta:
        description = "Detects Akira ransomware process via memory indicators"
        author = "MottaSec"
        date = "2025-11-08"
        severity = "critical"
        tlp = "white"
        reference = "https://github.com/[your-repo]/akira-ransomware-analysis"

    strings:
        // RSA public key DER structure (256 bytes total)
        $rsa_pubkey = { 30 82 01 0a 02 82 01 01 00 }

        // ChaCha20 custom S-box (256-byte table)
        $chacha_sbox_full = {
            63 7C 77 7B F2 6B 6F C5 30 01 67 2B FE D7 AB 76
            CA 82 C9 7D FA 59 47 F0 AD D4 A2 AF 9C A4 72 C0
        }

        // Task structure pattern (file path + crypto context)
        // 260-byte file path buffer followed by pointers
        $task_structure = { [260] ( 00 | 01 ) [8-16] }

        // Crypto context structure (56 bytes: state + key + nonce + counter)
        $crypto_ctx = { [64] [32] [16] [8] }

        // CRITICAL_SECTION structure (40 bytes, typical pattern)
        $critical_section = { [8] FF FF FF FF [32] }

    condition:
        // Memory-based detection
        ($rsa_pubkey and $chacha_sbox_full) or
        ($rsa_pubkey and $task_structure) or
        (2 of them)
}

rule Akira_Ransomware_Behavioral_Pattern {
    meta:
        description = "Detects Akira ransomware via behavioral patterns in strings"
        author = "MottaSec"
        date = "2025-11-08"
        severity = "medium"
        tlp = "white"
        reference = "https://github.com/[your-repo]/akira-ransomware-analysis"

    strings:
        // Shadow copy deletion command (PowerShell)
        $shadow_delete1 = "vssadmin delete shadows" ascii wide nocase
        $shadow_delete2 = "vssadmin.exe Delete Shadows /All /Quiet" ascii wide nocase

        // Common ransomware note indicators
        $ransom1 = "encrypted" ascii wide nocase
        $ransom2 = "decrypt" ascii wide nocase
        $ransom3 = "payment" ascii wide nocase
        $ransom4 = "bitcoin" ascii wide nocase
        $ransom5 = "recover your files" ascii wide nocase

        // Akira-specific strings
        $akira_ext = ".akira" ascii wide
        $akira_note = "akira_readme" ascii wide nocase

        // Drive enumeration
        $drive_enum = "GetLogicalDrives" ascii

        // File operations
        $file_find1 = "FindFirstFileW" ascii
        $file_find2 = "FindNextFileW" ascii
        $file_move = "MoveFileExW" ascii

        // Restart Manager (file unlocking)
        $restart_mgr1 = "RmStartSession" ascii
        $restart_mgr2 = "RmRegisterResources" ascii
        $restart_mgr3 = "RmShutdown" ascii

    condition:
        uint16(0) == 0x5A4D and  // PE header
        filesize < 5MB and
        (
            // Shadow copy deletion + Akira-specific indicators
            (any of ($shadow_delete*) and any of ($akira_*)) or

            // Multiple ransomware indicators + file operations
            (3 of ($ransom*) and
             2 of ($file_*) and
             $drive_enum) or

            // Restart Manager + file operations + Akira extension
            (2 of ($restart_mgr*) and
             2 of ($file_*) and
             $akira_ext)
        )
}

rule Akira_Ransomware_ChaCha20_Implementation {
    meta:
        description = "Detects Akira ransomware by custom ChaCha20 implementation"
        author = "MottaSec"
        date = "2025-11-08"
        severity = "high"
        tlp = "white"
        reference = "https://github.com/[your-repo]/akira-ransomware-analysis"

    strings:
        // ChaCha20 constant "expand 32-byte k" (in little-endian 32-bit chunks)
        $chacha_const1 = { 61 70 78 65 }  // "expa"
        $chacha_const2 = { 33 32 2D 62 }  // "nd 3"
        $chacha_const3 = { 79 74 65 20 }  // "2-by"
        $chacha_const4 = { 6B 20 65 74 }  // "te k"

        // ChaCha20 quarter-round operations (assembly patterns)
        // ADD, XOR, ROTL patterns
        $quarter_round1 = { 01 ?? 33 ?? C1 ?? 10 }  // add eax, ebx; xor ecx, eax; rol ecx, 16
        $quarter_round2 = { 01 ?? 33 ?? C1 ?? 0C }  // add eax, ebx; xor ecx, eax; rol ecx, 12

        // Custom S-box lookup pattern
        $sbox_lookup = { 8A ?? [1-4] 0F B6 ?? [1-8] }  // movzx pattern for S-box

        // Galois Field multiplication (custom addition to standard ChaCha20)
        $gf_multiply = { F6 ?? [1-4] ( 30 | 31 | 32 | 33 ) }  // mul + xor pattern

    condition:
        uint16(0) == 0x5A4D and
        filesize < 5MB and
        (
            // Standard ChaCha20 constants + custom modifications
            (all of ($chacha_const*) and ($sbox_lookup or $gf_multiply)) or

            // Quarter-round patterns + custom crypto
            (any of ($quarter_round*) and $sbox_lookup and $gf_multiply)
        )
}

/*
   Usage Instructions:

   1. Scan for Akira ransomware binaries:
      yara -r akira_ransomware.yar /path/to/scan

   2. Scan for encrypted files:
      yara -r akira_ransomware.yar /path/to/files

   3. Scan process memory (with yara process scanner):
      yara akira_ransomware.yar <PID>

   4. Integration with EDR/SIEM:
      - Import rules into your EDR platform
      - Configure real-time scanning on file write operations
      - Alert on any matches with severity "critical"

   5. False Positive Mitigation:
      - Whitelist known-good binaries by hash
      - Tune thresholds for behavioral rules
      - Combine with network/behavioral indicators

   Notes:
   - These rules are designed for detection, not prevention
   - Always verify detections manually before taking action
   - Update rules as new Akira variants are discovered
   - Combine with EDR behavioral detection for best results
*/