"""Every example phrase in commands/README.md must parse to the documented intent."""
import pytest
from capricorn.brain import rules

CASES = [
    ("Open Discord", "_open"), ("Launch Spotify", "_open"), ("Start Notepad", "_open"),
    ("Play Skyrim", "music_play"),            # router checks installed games first
    ("Play Hollow Knight on Steam", "open_app"), ("Launch the game Elden Ring", "open_app"),
    ("Open Steam", "_open"),
    ("Play Shelter by Porter Robinson", "music_play"), ("Play some lo-fi", "music_play"),
    ("Play blinding lights on YouTube", "youtube_play"), ("Play some music", "music_play"),
    ("Play my liked music", "music_play"), ("Play the top 10 songs", "music_play"), ("Play some songs", "music_play"),
    ("Play lofi beats", "music_play"), ("Play 90s rock", "music_play"), ("Play GTA", "music_play"),
    ("Pause", "media"), ("Resume", "media"), ("Play", "media"), ("Stop the music", "media"),
    ("Next song", "media"), ("Skip", "media"), ("Previous song", "media"), ("Go back a track", "media"),
    ("Volume up", "media"), ("Louder", "media"), ("Turn it down", "media"), ("Mute", "media"),
    ("What's playing?", "now_playing"), ("What song is this?", "now_playing"),
    ("Open YouTube", "_open"), ("Open Gmail", "_open"), ("Open example.com", "open_url"),
    ("Search for RTX 5070 benchmarks", "web_answer"), ("Google best ramen near me", "web_search"),
    ("Look up the weather in Tokyo", "web_answer"),
    ("Search YouTube for Edgerunners trailer", "youtube_search"),
    ("Open my downloads", "_open"), ("Open screenshots", "_open"), ("Open projects folder", "open_folder"),
    ("Open the resume pdf", "open_file"), ("Open budget spreadsheet", "open_file"), ("Open notes.txt", "open_file"),
    ("Lock the PC", "system"), ("Lock my laptop", "system"), ("Put the PC to sleep", "system"),
    ("Shut down the computer", "system"), ("Restart", "system"),
    ("What time is it?", "time"), ("What's the date?", "time"),
    ("Minimal mode", "_ui"), ("Enable minimal mode", "_ui"), ("Go minimal", "_ui"), ("Normal mode", "_ui"),
    ("Disable minimal mode", "_ui"), ("Switch back to normal mode", "_ui"), ("Hide yourself", "_ui"),
    ("Stay hidden", "_ui"), ("Show yourself", "_ui"), ("Stay on screen", "_ui"), ("Hide", "_goodbye"),
    ("Close the game", "close_game"), ("Quit game", "close_game"), ("Kill the game", "close_game"),
    ("Close Black Myth Wukong", "close_app"), ("Stop Elden Ring", "_stop"), ("Quit Cyberpunk", "close_app"),
    ("Close Discord", "close_app"), ("Quit Spotify", "close_app"), ("Exit Steam", "close_app"),
    ("Hi", "_greeting"), ("Hello", "_greeting"), ("What's up", "_greeting"),
    ("Thanks", "_thanks"), ("Nice", "_thanks"), ("Perfect", "_thanks"),
    ("Never mind", "_goodbye"), ("Cancel", "_goodbye"), ("Bye", "_goodbye"), ("Go away", "_goodbye"),
]

@pytest.mark.parametrize("text,intent", CASES)
def test_example(text, intent):
    got = rules.parse(text)
    assert got is not None and got[0] == intent, (text, got)

def test_chat_goes_to_llm():
    for t in ["tell me a joke", "explain black holes", "what should I play tonight?"]:
        assert rules.parse(t) is None, t
