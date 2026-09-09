from semantic_visual_v2_translation_eval import normalize_v2_translation_display as norm

def test_v22():
    cases = {"...":"…", "・・・・・・・・・・":"…", "…………":"…", "⋯⋯":"…", "..":"..", "・・":"・・", "‥":"・・", "ーーー":"ー", "ｰｰ":"ー", "～～～":"〜", "へヘべベぺペ":"へヘべベぺペ", "ﾍﾍﾞﾍﾟ":"ヘベペ", "ー—―−-─":"ー—―−-─", "︱":"—", "!!!":"!!"}
    for source, expected in cases.items():
        assert norm(source) == expected, (source, norm(source), expected)
        assert norm(norm(source)) == expected
    for n in range(3, 101):
        for char in (".", "．", "・", "…", "⋯"):
            assert norm(char*n) == "…"
