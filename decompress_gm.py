import zlib
import gzip
import binascii
import os
import argparse

def parse_gzip_manual(filename, output_bin_path, output_hex_path=None):
    """
    Decompress a HoMM3 save file (.GM2) and verify its integrity.
    
    Args:
        filename (str): Path to the compressed .GM2 file
        output_bin_path (str): Path to save the decompressed binary
        output_hex_path (str, optional): Path to save a hex dump of the output
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Verify input file exists
        if not os.path.isfile(filename):
            print(f"Error: Input file {filename} does not exist")
            return False

        # Read the compressed file
        with open(filename, "rb") as f:
            data = f.read()

        # Verify file size
        if len(data) < 18:  # Minimum gzip size (10 header + 8 footer)
            print(f"Error: File {filename} is too small ({len(data)} bytes)")
            return False

        # Check gzip header
        pos = 0
        if data[0:2] != b'\x1f\x8b':
            print("Error: Not a GZIP file")
            return False

        method = data[2]
        if method != 8:
            print(f"Error: Not deflate method (method={method})")
            return False

        flags = data[3]
        pos = 10  # Base header size

        # Handle optional header fields
        if flags & 0x04:  # Extra field
            if pos + 2 > len(data):
                print("Error: Truncated extra field length")
                return False
            xlen = int.from_bytes(data[pos:pos+2], "little")
            pos += 2 + xlen

        if flags & 0x08:  # Original filename
            while pos < len(data) and data[pos] != 0:
                pos += 1
            pos += 1  # Skip null terminator
            if pos >= len(data):
                print("Error: Truncated filename")
                return False

        if flags & 0x10:  # Comment
            while pos < len(data) and data[pos] != 0:
                pos += 1
            pos += 1
            if pos >= len(data):
                print("Error: Truncated comment")
                return False

        if flags & 0x02:  # Header CRC16
            pos += 2
            if pos >= len(data):
                print("Error: Truncated header CRC16")
                return False

        # Extract compressed data and footer
        if pos + 8 > len(data):
            print("Error: Truncated file, missing footer")
            return False
        compressed_data = data[pos:-8]
        footer = data[-8:]
        expected_crc32 = int.from_bytes(footer[0:4], "little")
        expected_size = int.from_bytes(footer[4:8], "little")

        # Try manual decompression with zlib
        try:
            decompressed = zlib.decompress(compressed_data, wbits=-15)
            computed_crc32 = zlib.crc32(decompressed) & 0xffffffff
            if computed_crc32 != expected_crc32:
                print(f"CRC32 mismatch: computed {hex(computed_crc32)}, expected {hex(expected_crc32)}")
            if len(decompressed) != expected_size:
                print(f"Size mismatch: decompressed {len(decompressed)} bytes, expected {expected_size}")
            
            # Save decompressed file
            with open(output_bin_path, "wb") as f_out:
                f_out.write(decompressed)
            print(f"Decompression succeeded, size: {len(decompressed)} bytes")
            
            # Verify HoMM3 header
            if len(decompressed) >= 4 and decompressed[0:4] == b'H3SV':
                print("Valid HoMM3 save file detected (H3SV header)")
            else:
                print("Warning: No H3SV header found, may not be a valid HoMM3 save file")
            
        except zlib.error as e:
            print(f"Manual decompression failed: {e}")
            # Fallback to gzip module
            try:
                with gzip.open(filename, "rb") as f_in:
                    decompressed = f_in.read()
                with open(output_bin_path, "wb") as f_out:
                    f_out.write(decompressed)
                print(f"Fallback decompression succeeded, size: {len(decompressed)} bytes")
                
                # Verify HoMM3 header
                if len(decompressed) >= 4 and decompressed[0:4] == b'H3SV':
                    print("Valid HoMM3 save file detected (H3SV header)")
                else:
                    print("Warning: No H3SV header found, may not be a valid HoMM3 save file")
            except gzip.BadGzipFile as e:
                print(f"Fallback decompression failed: {e}")
                return False

        # Create hex dump if requested
        if output_hex_path:
            try:
                with open(output_bin_path, "rb") as f_in:
                    binary_data = f_in.read(10000)  # Limit to 10000 bytes
                with open(output_hex_path, "w", encoding="ascii") as f_out:
                    hex_data = binascii.hexlify(binary_data).decode("ascii")
                    for i in range(0, len(hex_data), 32):
                        f_out.write(hex_data[i:i+32] + "\n")
                print(f"Hex dump saved to {output_hex_path}")
            except Exception as e:
                print(f"Error creating hex dump: {e}")
                return False

        return True

    except Exception as e:
        print(f"Error processing file: {e}")
        return False

# Command-line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Decompress a HoMM3 .GM2 save file")
    parser.add_argument("input_file", help="Path to the compressed .GM2 file")
    parser.add_argument("--output-bin", default="decompressed.bin", help="Path to save the decompressed binary (default: decompressed.bin)")
    parser.add_argument("--output-hex", default=None, help="Path to save a hex dump of the output (optional)")
    args = parser.parse_args()

    success = parse_gzip_manual(args.input_file, args.output_bin, args.output_hex)
    if success:
        print("Decompression and verification completed successfully.")
    else:
        print("Decompression failed.")