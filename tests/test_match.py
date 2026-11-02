import pytest
from capricorn.match import best, score

LIB = ["Marvel Contest of Champions", "Black Myth: Wukong", "The Elder Scrolls V: Skyrim Special Edition",
       "Cyberpunk 2077", "Grand Theft Auto V", "Counter-Strike 2", "Red Dead Redemption 2", "Steam",
       "Hollow Knight", "Wuthering Waves", "Discord", "Visual Studio Code", "Opera GX Browser", "ChatGPT"]

@pytest.mark.parametrize("q,expected", [
    ("god of war", None), ("bla", None), ("the talk", None), ("champions", "Marvel Contest of Champions"),
    ("marvel contest", "Marvel Contest of Champions"), ("black myth", "Black Myth: Wukong"),
    ("wukong", "Black Myth: Wukong"), ("skyrim", "The Elder Scrolls V: Skyrim Special Edition"),
    ("cyberpunk", "Cyberpunk 2077"), ("cyberpunk 2077", "Cyberpunk 2077"), ("gta", "Grand Theft Auto V"),
    ("gta 5", "Grand Theft Auto V"), ("counter strike", "Counter-Strike 2"), ("cs2", "Counter-Strike 2"),
    ("rdr2", "Red Dead Redemption 2"), ("red dead", "Red Dead Redemption 2"), ("steam", "Steam"),
    ("hollow night", "Hollow Knight"), ("wuthering waves", "Wuthering Waves"), ("discord", "Discord"),
    ("visual studio code", "Visual Studio Code"), ("chat gpt", "ChatGPT"), ("opera gx", "Opera GX Browser"), ("chatgpt", "ChatGPT"),
    ("liked music", None), ("top 10 songs", None),
])
def test_best(q, expected):
    i = best(q, LIB)
    assert (LIB[i] if i is not None else None) == expected

def test_numbers_must_match():
    assert score("cyberpunk 2078", "Cyberpunk 2077") == 0
    assert score("red dead redemption 1", "Red Dead Redemption 2") == 0


@pytest.mark.parametrize("heard", ["black myth woo kong", "blacksmith wukong", "blackmat wukong"])
def test_misheard_game_names_still_match(heard):
    assert LIB[best(heard, LIB)] == "Black Myth: Wukong"
