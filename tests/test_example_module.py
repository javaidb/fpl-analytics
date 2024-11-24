from src.functions.helper_fns import grab_player_pos

def test_position():
    assert grab_player_pos(1) in ['GKP', 'DEF', 'MID', 'FWD']

def test_subtract():
    assert subtract(2, 1) == 1
    assert subtract(1, 1) == 0
    assert subtract(-1, -1) == 0