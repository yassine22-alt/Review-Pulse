"""The OCR recogniser is chosen by what the page shows, not by a language setting."""

from reviewpulse.rules import readers

BOX = [[0, 0], [9, 0], [9, 9], [0, 9]]


class _Engine:
    def __init__(self, result, per_line=None):
        self.result, self.per_line, self.calls, self.cls = result, per_line, 0, []

    def __call__(self, _image, use_cls=True):
        self.calls += 1
        self.cls.append(use_cls)
        return (self.per_line if use_cls and self.per_line is not None else self.result), None


def _setup(monkeypatch, default, latin, model=True):
    d, lat = _Engine(default), _Engine(latin)
    monkeypatch.setattr(readers, "_ENGINE", d)
    monkeypatch.setattr(readers, "_LATIN_ENGINE", lat)
    monkeypatch.setattr(readers, "latin_model_path", lambda: "x.onnx" if model else None)
    return d, lat


def test_a_latin_page_is_read_again_with_the_model_that_keeps_accents(monkeypatch):
    d, lat = _setup(monkeypatch, [(BOX, "doit etre de 1,20 m", 0.98)], [(BOX, "doit être de 1,20 m", 0.99)])
    assert readers.ocr_lines(b"") == ["doit être de 1,20 m"] and (d.calls, lat.calls) == (1, 1)


def test_a_page_in_another_script_keeps_the_default_reading(monkeypatch):
    d, lat = _setup(monkeypatch, [(BOX, "卧室的使用面积不应小于9平方米", 0.99)], [(BOX, "9", 0.99)])
    assert readers.ocr_lines(b"") == ["卧室的使用面积不应小于9平方米"] and lat.calls == 0


def test_without_the_latin_model_nothing_changes(monkeypatch):
    d, lat = _setup(monkeypatch, [(BOX, "doit etre", 0.98)], [], model=False)
    assert readers.ocr_lines(b"") == ["doit etre"] and lat.calls == 0


def test_a_much_less_confident_latin_reading_is_not_kept(monkeypatch):
    _setup(monkeypatch, [(BOX, "Minimum width 900 mm", 0.98)], [(BOX, "Mlnlmum wldth 9OO mm", 0.70)])
    assert readers.ocr_lines(b"") == ["Minimum width 900 mm"]


def test_a_page_is_read_as_upright_and_the_line_classifier_is_only_a_second_try(monkeypatch):
    d, _ = _setup(monkeypatch, [(BOX, "Minimum width 900 mm", 0.98)], [], model=False)
    readers.ocr_lines(b"")
    assert d.cls == [False]                                   # a confident upright reading is final
    poor = _Engine([(BOX, "ww oo6 ypm wnwuW", 0.30)], per_line=[(BOX, "Minimum width 900 mm", 0.97)])
    monkeypatch.setattr(readers, "_ENGINE", poor)
    assert readers.ocr_lines(b"") == ["Minimum width 900 mm"] and poor.cls == [False, True]
