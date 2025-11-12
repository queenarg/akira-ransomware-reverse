#!/usr/bin/env python3
"""
Akira Ransomware - Nonce Reuse Detection Script

This script identifies files encrypted by Akira ransomware that share the same
ChaCha20 nonce (encrypted by the same worker thread). Files with matching nonces
are vulnerable to XOR-based plaintext recovery attacks.

Organization: MottaSec
Date: 2025-11-08
License: MIT

Usage:
    python detect_nonce_reuse.py /path/to/encrypted/files
    python detect_nonce_reuse.py C:\Users\victim\Documents --output results.json
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set


class AkiraFooterAnalyzer:
    """Analyzes Akira ransomware file footers to detect nonce reuse"""

    FOOTER_SIZE = 512
    MAGIC_OFFSET = -512
    MAGIC_SIGNATURES = [b"AKIRA!!!", b"akira!!!"]
    RSA_NONCE_OFFSET = 0x108  # Offset from start of footer
    RSA_NONCE_SIZE = 256

    def __init__(self, encrypted_path: str):
        """
        Initialize analyzer with path to encrypted files

        Args:
            encrypted_path: Directory containing encrypted .akira files
        """
        self.encrypted_path = Path(encrypted_path)
        self.nonce_groups: Dict[str, List[Path]] = defaultdict(list)
        self.stats = {
            "total_files": 0,
            "akira_files": 0,
            "valid_footers": 0,
            "unique_nonces": 0,
            "exploitable_groups": 0,
            "max_group_size": 0
        }

    def is_akira_file(self, filepath: Path) -> bool:
        """Check if file has .akira extension and valid footer"""
        if not filepath.suffix.lower() == ".akira":
            return False

        try:
            with open(filepath, 'rb') as f:
                # Check file size (must be at least footer size)
                f.seek(0, 2)  # Seek to end
                size = f.tell()
                if size < self.FOOTER_SIZE:
                    return False

                # Check magic signature
                f.seek(self.MAGIC_OFFSET, 2)  # Seek to footer start
                magic = f.read(8)
                return magic in self.MAGIC_SIGNATURES

        except (IOError, OSError) as e:
            print(f"[ERROR] Cannot read {filepath}: {e}", file=sys.stderr)
            return False

    def extract_rsa_nonce(self, filepath: Path) -> bytes:
        """
        Extract RSA-encrypted nonce from footer

        Args:
            filepath: Path to encrypted .akira file

        Returns:
            256-byte RSA-encrypted nonce, or empty bytes on error
        """
        try:
            with open(filepath, 'rb') as f:
                # Seek to footer start
                f.seek(-self.FOOTER_SIZE, 2)
                footer = f.read(self.FOOTER_SIZE)

                # Extract RSA(nonce) at offset 0x108
                rsa_nonce = footer[self.RSA_NONCE_OFFSET:
                                   self.RSA_NONCE_OFFSET + self.RSA_NONCE_SIZE]

                if len(rsa_nonce) != self.RSA_NONCE_SIZE:
                    print(f"[WARN] Invalid nonce size in {filepath}: "
                          f"{len(rsa_nonce)} bytes", file=sys.stderr)
                    return b""

                return rsa_nonce

        except (IOError, OSError) as e:
            print(f"[ERROR] Cannot extract nonce from {filepath}: {e}",
                  file=sys.stderr)
            return b""

    def analyze_directory(self) -> None:
        """Scan directory and group files by RSA-encrypted nonce"""
        print(f"[*] Scanning: {self.encrypted_path}")
        print(f"[*] Looking for .akira files...")

        # Find all .akira files recursively
        akira_files = list(self.encrypted_path.rglob("*.akira"))
        self.stats["total_files"] = len(list(self.encrypted_path.rglob("*")))
        self.stats["akira_files"] = len(akira_files)

        print(f"[*] Found {self.stats['akira_files']} .akira files")
        print(f"[*] Analyzing footers...")

        # Group files by RSA-encrypted nonce
        for filepath in akira_files:
            if not self.is_akira_file(filepath):
                continue

            rsa_nonce = self.extract_rsa_nonce(filepath)
            if not rsa_nonce:
                continue

            # Use SHA256 hash of RSA(nonce) as group key
            nonce_hash = hashlib.sha256(rsa_nonce).hexdigest()
            self.nonce_groups[nonce_hash].append(filepath)
            self.stats["valid_footers"] += 1

        # Calculate statistics
        self.stats["unique_nonces"] = len(self.nonce_groups)
        self.stats["exploitable_groups"] = sum(
            1 for group in self.nonce_groups.values() if len(group) >= 2
        )
        if self.nonce_groups:
            self.stats["max_group_size"] = max(
                len(group) for group in self.nonce_groups.values()
            )

        print(f"[+] Analysis complete!")

    def print_report(self) -> None:
        """Print human-readable analysis report"""
        print("\n" + "=" * 80)
        print("AKIRA RANSOMWARE - NONCE REUSE ANALYSIS REPORT")
        print("=" * 80)

        print("\n[STATISTICS]")
        print(f"  Total files scanned:      {self.stats['total_files']:,}")
        print(f"  Encrypted files (.akira): {self.stats['akira_files']:,}")
        print(f"  Valid footers analyzed:   {self.stats['valid_footers']:,}")
        print(f"  Unique nonces found:      {self.stats['unique_nonces']:,}")
        print(f"  Exploitable groups (2+):  {self.stats['exploitable_groups']:,}")
        print(f"  Largest group size:       {self.stats['max_group_size']:,}")

        # Calculate worker thread count estimate
        unique_nonces = self.stats['unique_nonces']
        print(f"\n[WORKER THREADS]")
        print(f"  Estimated worker threads: {unique_nonces}")
        print(f"  (One nonce per worker thread)")

        # Print exploitable groups
        print(f"\n[EXPLOITABLE GROUPS - Nonce Reuse Detected]")
        if self.stats["exploitable_groups"] == 0:
            print("  None found. All files encrypted with unique nonces.")
            print("  XOR attack not possible.")
        else:
            print(f"  {self.stats['exploitable_groups']} groups vulnerable "
                  f"to XOR attack:")
            print()

            exploitable = [
                (nonce_hash, files)
                for nonce_hash, files in self.nonce_groups.items()
                if len(files) >= 2
            ]

            # Sort by group size (descending)
            exploitable.sort(key=lambda x: len(x[1]), reverse=True)

            for idx, (nonce_hash, files) in enumerate(exploitable, 1):
                print(f"  Group #{idx}: {len(files)} files "
                      f"(Nonce: {nonce_hash[:16]}...)")

                # Print first 5 files in group
                for filepath in files[:5]:
                    rel_path = filepath.relative_to(self.encrypted_path)
                    file_size = filepath.stat().st_size
                    print(f"    - {rel_path} ({file_size:,} bytes)")

                if len(files) > 5:
                    print(f"    ... and {len(files) - 5} more files")
                print()

        # Recovery recommendations
        print("[RECOVERY RECOMMENDATIONS]")
        if self.stats["exploitable_groups"] > 0:
            print("  ✅ XOR ATTACK POSSIBLE:")
            print("     1. Identify file types in each group "
                  "(DOCX, PDF, XLSX, etc.)")
            print("     2. Apply known plaintext attack using file headers:")
            print("        - PDF:  %PDF-1.")
            print("        - DOCX: PK\\x03\\x04 (ZIP header)")
            print("        - PNG:  \\x89PNG\\r\\n\\x1a\\n")
            print("     3. Use crib dragging for full plaintext recovery")
            print("     4. See: docs/findings/vulnerabilities.md for details")
            print()
            print("  ⚠️ DO NOT PAY RANSOM - Partial recovery possible!")
        else:
            print("  ❌ XOR ATTACK NOT VIABLE:")
            print("     - All files encrypted with unique nonces")
            print("     - Restore from backups if available")
            print("     - Check Volume Shadow Copies (VSS)")

        print("\n" + "=" * 80)

    def export_json(self, output_path: str) -> None:
        """Export analysis results to JSON"""
        data = {
            "metadata": {
                "scanner": "Akira Nonce Reuse Detector",
                "version": "1.0",
                "encrypted_path": str(self.encrypted_path),
                "timestamp": __import__('datetime').datetime.now().isoformat()
            },
            "statistics": self.stats,
            "nonce_groups": {
                nonce_hash: [str(f) for f in files]
                for nonce_hash, files in self.nonce_groups.items()
            },
            "exploitable_groups": {
                nonce_hash: {
                    "file_count": len(files),
                    "files": [str(f) for f in files]
                }
                for nonce_hash, files in self.nonce_groups.items()
                if len(files) >= 2
            }
        }

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"[+] Results exported to: {output_path}")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <encrypted_files_directory> [--output <json_file>]")
        print()
        print("Example:")
        print(f"  {sys.argv[0]} /path/to/encrypted/files")
        print(f"  {sys.argv[0]} C:\\Users\\victim\\Documents --output results.json")
        sys.exit(1)

    encrypted_path = sys.argv[1]
    output_path = None

    # Parse --output argument
    if len(sys.argv) >= 4 and sys.argv[2] == "--output":
        output_path = sys.argv[3]

    # Validate path
    if not os.path.isdir(encrypted_path):
        print(f"[ERROR] Directory not found: {encrypted_path}", file=sys.stderr)
        sys.exit(1)

    # Run analysis
    analyzer = AkiraFooterAnalyzer(encrypted_path)
    analyzer.analyze_directory()
    analyzer.print_report()

    # Export JSON if requested
    if output_path:
        analyzer.export_json(output_path)


if __name__ == "__main__":
    main()
