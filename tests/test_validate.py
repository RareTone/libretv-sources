"""校验器回归测试，仅使用 Python 标准库。"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.validate import ROOT, ValidationError, load_json, validate_data


class SourceListTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "name": "Test sources", "version": 2,
            "sources": [{"name": "Example", "url": "https://example.com/api.php/provide/vod", "isAdult": False}],
            "liveSources": [],
        }

    def test_valid_input_is_not_modified(self):
        self.data["sources"][0]["detail"] = "https://example.com"
        self.data["liveSources"] = [{"name": "Live", "url": "http://example.org/list.m3u", "epg": "https://example.org/epg.xml.gz"}]
        original = copy.deepcopy(self.data)
        self.assertEqual(validate_data(self.data), (1, 1))
        self.assertEqual(original, self.data)

    def test_invalid_top_level(self):
        for value in ([], None, {"settings": {}}, {**self.data, "version": 2.0},
                      {**self.data, "sources": {}}, {**self.data, "liveSources": None},
                      {**self.data, "name": ""}, {**self.data, "token": "private"}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_data(value)

    def test_invalid_source_fields(self):
        for value in ({"url": "https://example.com"}, {"name": "Missing URL"},
                      {"name": "", "url": "https://example.com"}, None,
                      {"name": "Example", "url": "https://example.com", "isAdult": "false"},
                      {"name": "Example", "url": "https://example.com", "enabled": True},
                      {"name": "Example", "url": "https://example.com", "headers": {"Cookie": "private"}}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_data({**self.data, "sources": [value]})

    def test_invalid_or_sensitive_urls(self):
        for url in ("ftp://example.com/api", "/api", "https://", "https://example.com:bad/api",
                    "https://user:password@example.com/api", "https://example.com/api?token=private",
                    "https://example.com/api?api_key=private", "https://example.com/token/private",
                    "http://127.0.0.1/api", "http://192.168.1.1/api", "http://10.0.0.1/api",
                    "http://169.254.169.254/api", "http://100.64.0.1/api", "http://224.0.0.1/api",
                    "http://[::1]/api", "http://[::ffff:192.168.1.1]/api", "http://[fe80::1%eth0]/api",
                    "http://localhost/api", "http://media.local/api", "http://media/api",
                    "http://127.1/api", "http://0x7f000001/api", "http://2130706433/api",
                    "https://example.com/ api", "https://example.com/a\nb", "https://example.com\\@localhost/",
                    "https://example.com/api#token", "http://%31%32%37.0.0.1/api"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                validate_data({**self.data, "sources": [{"name": "Example", "url": url}]})

    def test_duplicate_url_normalization(self):
        for url in ("https://example.com/api.php/provide/vod", "https://EXAMPLE.com:443/api.php/provide/vod/"):
            data = copy.deepcopy(self.data)
            data["sources"].append({"name": "Another name", "url": url})
            with self.subTest(url=url), self.assertRaisesRegex(ValidationError, "duplicate URL"):
                validate_data(data)

    def test_different_queries_and_paths_are_preserved(self):
        for suffix in ("?ac=list", "?ac=detail", "/other"):
            self.data["sources"].append({"name": "Distinct", "url": self.data["sources"][0]["url"] + suffix})
        self.assertEqual(validate_data(self.data), (4, 0))

    def test_live_source_validation(self):
        for entries in ([{"name": "Live", "url": "https://example.com/list.m3u", "epg": "file:///private"}],
                        [{"name": "Live", "url": "https://example.com/list.m3u"}] * 2):
            with self.subTest(entries=entries), self.assertRaises(ValidationError):
                validate_data({**self.data, "liveSources": entries})

    def test_limits_prevent_silent_truncation(self):
        for group, limit in (("sources", 100), ("liveSources", 50)):
            entries = [{"name": str(index), "url": f"https://example.com/{index}"} for index in range(limit + 1)]
            with self.subTest(group=group), self.assertRaisesRegex(ValidationError, "limit"):
                validate_data({**self.data, group: entries})

    def test_empty_arrays_are_allowed_for_removing_all_sources(self):
        self.assertEqual(validate_data({**self.data, "sources": []}), (0, 0))

    def test_json_parser_rejects_invalid_syntax_duplicate_keys_and_nan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            for content in ('{"sources": [}', '{"name": "a", "name": "b"}', '{"value": NaN}', '{"value": Infinity}'):
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(ValidationError):
                    load_json(path)

    def test_cli_returns_nonzero_and_does_not_print_secrets(self):
        self.data["sources"][0]["url"] = "https://example.com/api?token=PRIVATE_TEST_VALUE"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.json"
            path.write_text(json.dumps(self.data), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/validate.py"), str(path)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL", result.stderr)
            self.assertNotIn("PRIVATE_TEST_VALUE", result.stderr + result.stdout)

    def test_repository_sources(self):
        for filename in ("stable.json", "all.json"):
            with self.subTest(filename=filename):
                validate_data(load_json(ROOT / "sources" / filename))


if __name__ == "__main__":
    unittest.main()
