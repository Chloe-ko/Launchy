import tomllib
import pytest
from launchy.utils import toml_dumps, _key, _val


class TestKey:
    def test_simple_alphanumeric(self):
        assert _key("foo") == "foo"

    def test_hyphen_and_underscore_allowed(self):
        assert _key("foo-bar_baz") == "foo-bar_baz"

    def test_dot_requires_quotes(self):
        assert _key("foo.bar") == '"foo.bar"'

    def test_space_requires_quotes(self):
        assert _key("foo bar") == '"foo bar"'

    def test_empty_string_requires_quotes(self):
        result = _key("")
        assert result.startswith('"')


class TestVal:
    def test_plain_string(self):
        assert _val("hello") == '"hello"'

    def test_string_with_double_quotes(self):
        assert _val('say "hi"') == '"say \\"hi\\""'

    def test_string_with_backslash(self):
        assert _val("a\\b") == '"a\\\\b"'

    def test_string_newline_escaped(self):
        assert _val("a\nb") == '"a\\nb"'

    def test_bool_true(self):
        assert _val(True) == "true"

    def test_bool_false(self):
        assert _val(False) == "false"

    def test_int(self):
        assert _val(42) == "42"

    def test_float(self):
        assert _val(3.14) == "3.14"

    def test_empty_list(self):
        assert _val([]) == "[]"

    def test_short_list_inline(self):
        result = _val(["a", "b"])
        assert result == '["a", "b"]'

    def test_list_of_ints(self):
        assert _val([1, 2, 3]) == "[1, 2, 3]"


class TestTomlDumps:
    def _roundtrip(self, data):
        text = toml_dumps(data)
        return tomllib.loads(text)

    def test_simple_scalars(self):
        data = {"key": "value", "num": 42, "flag": True}
        assert self._roundtrip(data) == data

    def test_nested_tables(self):
        data = {"general": {"countdown": 5, "proton": ""}, "env": {"FOO": "bar"}}
        assert self._roundtrip(data) == data

    def test_list_of_strings(self):
        data = {"wrappers": ["mangohud", "gamescope -W 1920"]}
        assert self._roundtrip(data) == data

    def test_empty_list_roundtrip(self):
        data = {"args": {"extra": []}}
        assert self._roundtrip(data) == data

    def test_bool_roundtrip(self):
        data = {"general": {"skip_countdown": True}}
        assert self._roundtrip(data) == data

    def test_scalars_appear_before_subtables(self):
        data = {"sub": {"x": 1}, "top": "scalar"}
        text = toml_dumps(data)
        lines = text.splitlines()
        top_idx = next(i for i, l in enumerate(lines) if l.startswith("top"))
        sub_idx = next(i for i, l in enumerate(lines) if l.startswith("[sub]"))
        assert top_idx < sub_idx

    def test_special_key_quoted(self):
        data = {"foo.bar": "v"}
        text = toml_dumps(data)
        assert '"foo.bar"' in text
        assert self._roundtrip(data) == data
