"""Exhaustive parity checks for cached DSC symbol decoding (no hardware)."""
import unittest

from dsc_decode import _decode_symbols, decode_symbol


class SymbolLookupTests(unittest.TestCase):
    def test_every_ten_bit_codeword_matches_original_decoder(self):
        for code in range(1 << 10):
            bits = [(code >> i) & 1 for i in range(10)]
            self.assertEqual(
                _decode_symbols(bits),
                [decode_symbol(tuple(bits))],
                f"codeword {code}",
            )

    def test_multiple_codewords_and_incomplete_trailing_bits(self):
        codes = [0, 1023, 125, 771, 12, 512]
        bits = [bit for code in codes for bit in ((code >> i) & 1 for i in range(10))]
        expected = [decode_symbol(tuple(bits[i:i + 10]))
                    for i in range(0, len(bits), 10)]
        self.assertEqual(_decode_symbols(bits), expected)
        self.assertEqual(_decode_symbols(bits + [1, 0, 1]), expected)


if __name__ == "__main__":
    unittest.main()
