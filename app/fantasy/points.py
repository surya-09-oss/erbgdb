"""Fantasy points calculation engine for IPL 2026.

Implements the complete scoring system:
- Batting: runs (+1), boundary (+4 bonus), six (+7 bonus), milestones (25/50/75/100)
- Bowling: wickets (+25), LBW/bowled (+8 bonus), 3/4/5-wicket hauls, maidens
- Fielding: catches (+8), 3-catch bonus (+4), stumpings, run outs
- Strike rate & economy rate bonuses/penalties
- Playing XI bonus (+4)
- Duck penalty (-2)
"""


def calculate_batting_points(
    runs: int,
    balls: int,
    fours: int,
    sixes: int,
    is_out: bool,
    is_batter_or_wk_or_allrounder: bool = True,
) -> dict:
    """Calculate batting fantasy points from a player's innings."""
    points = 0
    breakdown: dict[str, int | float] = {}

    # +1 per run
    if runs > 0:
        breakdown["runs"] = runs
        points += runs

    # +4 bonus per boundary (four)
    if fours > 0:
        breakdown["fours_bonus"] = fours * 4
        points += fours * 4

    # +7 bonus per six
    if sixes > 0:
        breakdown["sixes_bonus"] = sixes * 7
        points += sixes * 7

    # Milestone bonuses (cumulative — each threshold adds its own bonus)
    if runs >= 25:
        breakdown["25_runs_bonus"] = 4
        points += 4
    if runs >= 50:
        breakdown["half_century_bonus"] = 8
        points += 8
    if runs >= 75:
        breakdown["75_runs_bonus"] = 12
        points += 12
    if runs >= 100:
        breakdown["century_bonus"] = 16
        points += 16

    # Duck -2 (for batters, WK, all-rounders)
    if runs == 0 and is_out and is_batter_or_wk_or_allrounder:
        breakdown["duck_penalty"] = -2
        points -= 2

    # Strike rate bonus/penalty (only if faced >= 10 balls)
    if balls >= 10:
        sr = (runs / balls) * 100
        if sr > 170:
            breakdown["strike_rate_bonus"] = 6
            points += 6
        elif sr >= 150.01:
            breakdown["strike_rate_bonus"] = 4
            points += 4
        elif sr >= 130.01:
            breakdown["strike_rate_bonus"] = 2
            points += 2
        elif 60 <= sr < 70:
            breakdown["strike_rate_penalty"] = -2
            points -= 2
        elif 50 <= sr < 60:
            breakdown["strike_rate_penalty"] = -4
            points -= 4
        elif sr < 50:
            breakdown["strike_rate_penalty"] = -6
            points -= 6

    return {"total": points, "breakdown": breakdown}


def calculate_bowling_points(
    wickets: int,
    overs: float,
    runs_conceded: int,
    maidens: int,
    lbw_bowled_count: int = 0,
) -> dict:
    """Calculate bowling fantasy points from a player's bowling spell."""
    points = 0
    breakdown: dict[str, int | float] = {}

    # +25 per wicket
    if wickets > 0:
        breakdown["wickets"] = wickets * 25
        points += wickets * 25

    # +8 bonus per LBW/Bowled dismissal
    if lbw_bowled_count > 0:
        breakdown["lbw_bowled_bonus"] = lbw_bowled_count * 8
        points += lbw_bowled_count * 8

    # Wicket haul bonuses
    if wickets >= 5:
        breakdown["five_wicket_bonus"] = 16
        points += 16
    elif wickets >= 4:
        breakdown["four_wicket_bonus"] = 8
        points += 8
    elif wickets >= 3:
        breakdown["three_wicket_bonus"] = 4
        points += 4

    # +12 per maiden over
    if maidens > 0:
        breakdown["maiden_overs"] = maidens * 12
        points += maidens * 12

    # Economy rate bonus/penalty (only if bowled >= 2 overs)
    if overs >= 2:
        economy = runs_conceded / overs if overs > 0 else 0
        if economy < 5:
            breakdown["economy_bonus"] = 6
            points += 6
        elif economy >= 5 and economy <= 5.99:
            breakdown["economy_bonus"] = 4
            points += 4
        elif economy >= 6 and economy <= 7:
            breakdown["economy_bonus"] = 2
            points += 2
        elif 9 <= economy <= 10:
            breakdown["economy_penalty"] = -2
            points -= 2
        elif 10 < economy <= 11:
            breakdown["economy_penalty"] = -4
            points -= 4
        elif economy > 11:
            breakdown["economy_penalty"] = -6
            points -= 6

    return {"total": points, "breakdown": breakdown}


def calculate_fielding_points(
    catches: int,
    stumpings: int,
    run_out_direct: int,
    run_out_assist: int,
) -> dict:
    """Calculate fielding fantasy points."""
    points = 0
    breakdown: dict[str, int | float] = {}

    # +8 per catch
    if catches > 0:
        breakdown["catches"] = catches * 8
        points += catches * 8

    # +4 bonus for 3+ catches
    if catches >= 3:
        breakdown["three_catch_bonus"] = 4
        points += 4

    # +12 per stumping
    if stumpings > 0:
        breakdown["stumpings"] = stumpings * 12
        points += stumpings * 12

    # +12 per direct run out
    if run_out_direct > 0:
        breakdown["run_out_direct"] = run_out_direct * 12
        points += run_out_direct * 12

    # +6 per run out assist
    if run_out_assist > 0:
        breakdown["run_out_assist"] = run_out_assist * 6
        points += run_out_assist * 6

    return {"total": points, "breakdown": breakdown}


def calculate_total_fantasy_points(
    batting: dict | None = None,
    bowling: dict | None = None,
    fielding: dict | None = None,
    playing_xi: bool = True,
) -> dict:
    """Combine all point categories into a total fantasy score.

    playing_xi: If True, adds +4 points for being in the Playing XI.
    """
    batting_pts = batting if batting else {"total": 0, "breakdown": {}}
    bowling_pts = bowling if bowling else {"total": 0, "breakdown": {}}
    fielding_pts = fielding if fielding else {"total": 0, "breakdown": {}}

    playing_xi_pts = 4 if playing_xi else 0
    total = batting_pts["total"] + bowling_pts["total"] + fielding_pts["total"] + playing_xi_pts

    return {
        "total_points": total,
        "playing_xi_bonus": playing_xi_pts,
        "batting_points": batting_pts["total"],
        "bowling_points": bowling_pts["total"],
        "fielding_points": fielding_pts["total"],
        "batting_breakdown": batting_pts["breakdown"],
        "bowling_breakdown": bowling_pts["breakdown"],
        "fielding_breakdown": fielding_pts["breakdown"],
    }


def parse_overs_to_float(overs_str: str) -> float:
    """Convert overs string like '3.4' to actual overs (3 + 4/6 = 3.667)."""
    try:
        if "." in str(overs_str):
            parts = str(overs_str).split(".")
            full_overs = int(parts[0])
            balls = int(parts[1]) if len(parts) > 1 else 0
            return full_overs + balls / 6.0
        return float(overs_str)
    except (ValueError, TypeError):
        return 0.0
