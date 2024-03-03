import os
import ast
import math
import difflib
import pandas as pd
import numpy as np

from collections import defaultdict

import asyncio

# from understatapi import UnderstatClient
# from fuzzywuzzy import fuzz
# from fuzzywuzzy import process

def calculate_mean_std_dev(data):
    mean = sum(data) / len(data)
    var = sum((l - mean) ** 2 for l in data) / len(data)
    st_dev = math.sqrt(var)

    return mean, st_dev

class GeneralHelperFns:
    def __init__(self, api_parser, data_parser):
        self.data_parser = data_parser
        self.api_parser = api_parser
        self.fdr_data = self.compile_fdr_data()
        self.unique_player_data = self.grab_all_unique_fpl_player_data()

    
    def compile_player_data(self, id_values: list):
        return {k:v for k,v in self.data_parser.master_summary.items() if k in id_values}

    def slice_player_data(self, compiled_player_data: dict, look_back: int):

        sliced_player_data = []
        for player_id, player_data in compiled_player_data.items():
            temp_dict = defaultdict(lambda: defaultdict(list))
            temp_dict['id'] = player_id
            for k,v in player_data.items():
                if isinstance(v, list):
                    if all(isinstance(item, (tuple)) for item in v):
                        v = [x[1] for x in v]
                    temp_dict[k] = v[-1*abs(look_back):]
                else:
                    temp_dict[k] = v
            sliced_player_data.append({k: v for k,v in temp_dict.items()})

        return sliced_player_data
    
    # def grab_upcoming_fixtures(self, id_values: list):
    #     raw_data = self.api_parser.full_element_summary
    #     return {player_id: gw_data for player_id in sorted(self.api_parser.player_ids) for gw_data in raw_data[player_id]['fixtures']}


    #========================== General Parsing ==========================

    def grab_player_name(self, idx):
        return self.compile_player_data([idx])[idx]['web_name']

    def grab_player_value(self, idx):
        return self.compile_player_data([idx])[idx]['value'][-1][-1]/10

    def grab_player_pos(self, idx):
        return self.compile_player_data([idx])[idx]['pos_singular_name_short']
     
    def grab_player_team(self, idx):
        return self.compile_player_data([idx])[idx]['team_short_name']
     
    def grab_player_team_id(self, idx):
        return self.compile_player_data([idx])[idx]['team']
     
    def grab_player_hist(self, idx, include_gws=False):
        return [param_val if not include_gws else (gw, param_val) for gw, param_val in self.compile_player_data([idx])[idx]['total_points']]
     
    def grab_player_returns(self, idx, include_gws=False):
        def process_binary_returns(points_tup):
            return (points_tup[0], 2) if (points_tup[1] > 9) else (points_tup[0], 1) if (points_tup[1] > 3 and points_tup[1] <= 9) else (points_tup[0], 0)
        return [process_binary_returns(param_val) if not include_gws else (gw, process_binary_returns(param_val)) for gw, param_val in self.compile_player_data([idx])[idx]['total_points']]
     
    def grab_player_minutes(self, idx, include_gws=False):
        return [param_val if not include_gws else (gw, param_val) for gw, param_val in self.compile_player_data([idx])[idx]['minutes']]
     
    def grab_player_bps(self, idx, include_gws=False):
        return [param_val if not include_gws else (gw, param_val) for gw, param_val in self.compile_player_data([idx])[idx]['bps']]
     
    # def grab_player_full90s(self, idx):
    #     name = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == idx]['fulltime']
    #     return name.values[-1]

    # def grab_player_full60s(self, idx):
    #     name = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == idx]['fullhour']
    #     return name.values[-1]

    def grab_team_id(self, team_name):
        return next(x['id'] for x in self.api_parser.raw_data['teams'] if x['name'] == team_name)

    def grab_team_name_full(self, team_id):
        return next(x['name'] for x in self.api_parser.raw_data['teams'] if x['id'] == team_id)
    
    def grab_team_name_short(self, team_id):
        return next(x['short_name'] for x in self.api_parser.raw_data['teams'] if x['id'] == team_id)

    def grab_pos_name(self, idx):
        return next((x['plural_name_short'] for x in iter(self.api_parser.raw_data['element_types']) if x['id'] == idx), None)

    def grab_upcoming_fixtures(self, id_values: list, games_ahead: int = 99, reference_gw: int = None):
        '''
        NB: We enable gw_data['event'] to handle Nonetypes as sometimes there are games that are yet to be rescheduled by the PL, so we remove it until it has been officially announced and updated in API.
        We also need to preserve gameweeks that are considered blanks, as once data is returned without including it there is no information to point to there being a blank outside of external functions.
        '''
        if reference_gw is None: reference_gw = self.api_parser.latest_gw
        raw_data = self.api_parser.full_element_summary
        def process_fixtures(all_fixtures: list):            
            return [{'gameweek': gw_info['event'], 'team': gw_info['team_h'] if gw_info['is_home'] else gw_info['team_a'], 'opponent_team': gw_info['team_a'] if gw_info['is_home'] else gw_info['team_h'], 'is_home': gw_info['is_home']} for gw_info in all_fixtures if (gw_info['event'] and (gw_info['event'] >= reference_gw+1 and gw_info['event'] <= reference_gw + games_ahead))]
        compiled_player_data = {str(player_id): process_fixtures(raw_data[player_id]['fixtures']) for player_id in sorted(id_values)}
        
        #Handle blanks, which are usually not present at all
        for player_id, player_data in compiled_player_data.items():
            last_gw = max([x['id'] for x in self.api_parser.raw_data['events']])
            expected_gws = list(range(reference_gw+1, min(last_gw+1, reference_gw+games_ahead+1)))
            compiled_gws = list({x['gameweek'] for x in player_data})
            gw_conflicts = [gw for gw in expected_gws if gw not in compiled_gws]
            if len(gw_conflicts) >= 1:
                for gw in gw_conflicts:
                    compiled_player_data[player_id].append({'gameweek': gw, 'team': None, 'opponent_team': None, 'is_home': None})
                compiled_player_data[player_id] = sorted(compiled_player_data[player_id], key=lambda x: x['gameweek'])
                
        return compiled_player_data

    def grab_all_unique_fpl_player_data(self):
        return [{**{k: v for k, v in self.data_parser.master_summary[x].items() if k in ['first_name', 'second_name', 'web_name', 'pos_singular_name_short', 'team_short_name', 'team']}, 'id': x} for x in self.api_parser.player_ids]

    def grab_bins_from_param(self, input_param):
        if input_param == 'ict_index':
            return (3.5, 5, 7.5)
        elif input_param == 'expected_goal_involvements':
            return (0.2, 0.5, 0.9)
        elif input_param == 'total_points':
            return (4, 6, 9)
        elif input_param == 'bps':
            return (14, 21, 29)
        elif input_param == 'minutes':
            return (45, 60, 89)
        elif input_param == 'value':
            return (3.8, 7.0, 13.0)
        else:
            return None

    #========================== Custom Operations ==========================
    
    def compile_fdr_data(self):
#       #========================== Compile FDRs from team_info ==========================
        init_id = 1
        fdr_data = {}
        while init_id < len(self.api_parser.player_ids):
            if init_id in self.api_parser.player_ids:
                null_team_id = self.grab_player_team_id(init_id)
                player_element_summary = self.api_parser.full_element_summary[init_id]["fixtures"]
                try:
                    fdr_info = [[([i['team_h'],i['team_a']],i['difficulty']) for i in player_element_summary][0]]
                    fdr_simpl = [((set(x[0]) - {null_team_id}).pop(),x[1]) for x in fdr_info]
                    for pair in fdr_simpl:
                        if pair[0] not in fdr_data.keys():
                            fdr_data[pair[0]] = pair[1]
                except:
                    pass
            init_id += 10
        init_id = 1
        while len(fdr_data) < 20 and init_id < len(self.api_parser.player_ids):
            null_team_id = self.grab_player_team_id(init_id)
            player_element_summary = self.api_parser.full_element_summary[init_id]["fixtures"]
            fdr_info = [([i['team_h'],i['team_a']],i['difficulty']) for i in player_element_summary][:3]
            fdr_simpl = [((set(x[0]) - {null_team_id}).pop(),x[1]) for x in fdr_info]
            for pair in fdr_simpl:
                if pair[0] not in fdr_data.keys():
                    fdr_data[pair[0]] = pair[1] 
            init_id += 10
        if len(fdr_data) < 20:
            fdr_data = {
                1:4,2:3,3:2,4:3,5:2,6:4,7:2,8:2,9:3,10:2,11:5,12:5,13:4,14:3,15:1,16:2,17:4,18:1,19:3,20:2}
        return fdr_data

    def team_rank(self,team_id):
        try:
            rank = self.fdr_data[team_id]
        except Exception as e:
            print(f'Error: {e}')
        return rank
    
    def rem_fixtures_difficulty(self, idx: int):
        r = asyncio.run(self.api_parser.fetch_element_summaries(idx))
        difflist=[]
        for diff in r['fixtures']:
            difflist.append(diff['difficulty'])

        rec='-X-'
        if sum(i <= 3 for i in difflist[:3]) >= 2 or sum(i <= 2 for i in difflist[:4]) >= 3:
            rec = 'ST'
        if sum(i <= 2 for i in difflist[:3]) >= 2:
            rec = 'ST+'        
        if sum(i <= 2 for i in difflist[:3]) == 3:
            rec = 'ST++'
        if sum(i <= 3 for i in difflist[:5]) >= 4:
            rec = 'MT'
            if sum(i <= 2 for i in difflist[:5]) >= 4:
                rec = 'MT+'
        if sum(i <= 3 for i in difflist[:7]) >= 5:
            rec = 'LT'
            if sum(i <= 2 for i in difflist[:7]) >= 5:
                rec = 'LT+'
                if sum(i <= 2 for i in difflist[:7]) >= 6:
                    rec = 'LT++'
        if sum(i <= 3 for i in difflist[:10]) >= 8:
            rec = 'VLT'
            if sum(i <= 2 for i in difflist[:10]) >= 8:
                rec = 'VLT+'
        return (rec,difflist)
    
    def find_best_match(self, input_string, input_team_id: int = None):
        best_matches = []
        max_score = 0
        dict_list = [{**d, 'concat_name': f"{d['first_name']} {d['second_name']}"} for d in self.unique_player_data]
        if input_team_id is not None:
            dict_list = [x for x in dict_list if x["team"] == input_team_id]
        # col_names = ['web_name', 'second_name', 'first_name', 'concat_name']
        col_names = ['web_name', 'concat_name']
        for d in dict_list:
            summary = d.copy()
            for key in col_names:
                score = difflib.SequenceMatcher(None, input_string, d[key]).ratio()
                summary["score"] = score
                if score > max_score:
                    max_score = score
                    best_matches = [summary]
                elif score == max_score:
                    best_matches.append(summary)
        def remove_duplicates(dicts):
            return [dict(t) for t in {tuple(sorted(d.items())) for d in dicts}]
        best_matches = remove_duplicates(best_matches)
        
        if len(best_matches) == 1:
            return best_matches[0]["id"]
        elif len(best_matches) > 1:
            for i, match in enumerate(best_matches):
                name_str = f"{match['web_name']} [{match['team_short_name']}] ({match['first_name']} {match['second_name']})"
                print(f"{i + 1}: {name_str} ({match['score']})")
            choice = input(f"Enter the number of the match for '{input_string}' you want to select (or press Enter to skip): ")
            if choice.isdigit() and int(choice) <= len(best_matches):
                return best_matches[int(choice) - 1]["id"]
            if choice.strip() == "":
                print("Skipping selection.")
            else:
                print("Invalid choice.")
        elif len(best_matches) == 0:
            return None
    
    #========================== User Functions ==========================
    
    def get_player_points_history(self, user_id):
        user_data = self.api_parser.fetch_data_from_api(f'entry/{user_id}/history/')
        points_history = []
        for gw_data in user_data['current']:
            gameweek = gw_data['event']
            points = gw_data['total_points']
            points_history.append((gameweek, points))
        return points_history
    

    def get_rank_data(self, league_id):
        standings_data = self.api_parser.fetch_data_from_api(f'leagues-classic/{league_id}/standings/')
        last_updated_time = standings_data['last_updated_data']
        league_name = standings_data['league']['name']
        # Extract relevant information such as player ranks
        users = []
        for user in standings_data['standings']['results']:
            user_id = user['entry']
            user['entry_history'] = self.get_player_points_history(user_id)
            users.append(user)
        for user in users:
            rank_history = []
            sorted_players = sorted(users, key=lambda x: x['entry_history'][0][1], reverse=True)
            for round_num in range(1, len(user['entry_history']) + 1):
                round_scores = [(p['entry'], p['entry_history'][round_num - 1][1]) for p in sorted_players]
                round_scores.sort(key=lambda x: x[1], reverse=True)
                ranks = {player[0]: rank + 1 for rank, player in enumerate(round_scores)}
                rank_history.append((round_num, ranks[user['entry']]))
            user['rank_history'] = rank_history
        return users, last_updated_time, league_name
    
    #========================== Visualization ==========================

    def fetch_single_team_color(team_id):
        team_colors = {
            1: '#DE0202',   # Arsenal
            2: '#75AADB',   # Aston Villa
            3: '#DA291C',   # Bournemouth
            4: '#FDB913',   # Brentford
            5: '#0057B8',   # Brighton & Hove Albion
            6: '#FFD700',   #Burnley
            7: '#034694',   # Chelsea
            8: '#1B458F',   # Crystal Palace
            9: '#003399',   # Everton
            10: '#F5A646',  # Fulham
            11: '#C8102E',  # Liverpool
            12: '#0053A0',  # Luton Town
            13: '#6CABDD',  # Manchester City
            14: '#DA291C',  # Manchester United
            15: '#241F20',  # Newcastle United
            16: '#BD1E2C',  # Nottingham Forest
            17: '#D71920',  # Sheffield United
            18: '#001C58',  # Tottenham Hotspur
            19: '#7A263A',  # West Ham United
            20: '#FDB913'   # Wolverhampton Wanderers
        }
        return team_colors[team_id]
    

    #========================== Print Statements ==========================

    def team_visualizer(self, team_ids:list):
        if len(team_ids) != 15:
            print("Need 15 entries for list!")
            return
        team_dict = {}
        for idx in team_ids:
            pos = self.grab_player_pos(idx)
            if pos not in team_dict:
                team_dict[pos]=[]
            name = self.grab_player_name(idx)
            team_dict[pos].append(name)
        gkps = team_dict['GKP']
        defs = team_dict['DEF']
        mids = team_dict['MID']
        fwds = team_dict['FWD']
        print(f'\n                   {gkps[0]}   {gkps[1]}\n')
        print(f'   {defs[0]}   {defs[1]}   {defs[2]}   {defs[3]}   {defs[4]}\n')
        print(f'   {mids[0]}   {mids[1]}   {mids[2]}   {mids[3]}   {mids[4]}\n')
        print(f'               {fwds[0]}   {fwds[1]}   {fwds[2]}\n')
        return team_dict
    
    def alert_players_with_blanks_dgws(self, input_fpl_team: pd.DataFrame()):
        teams = list(input_fpl_team.team.unique())
        ids = [self.grab_team_id(x) for x in teams]
        bgws_adj = {k: v for k, v in self.blanks.items() if k > self.api_parser.latest_gw}
        dgws_adj = {k: v for k, v in self.dgws.items() if k > self.api_parser.latest_gw}
        if bgws_adj:
            print('\n------------- UPCOMING BLANKS -------------')
            for gw,teams in bgws_adj.items():
                print(f'>> Gameweek {gw}')
                matches = [self.grab_team_name(x) for x in ids if x in teams]
                players = list(input_fpl_team.loc[input_fpl_team['team'].isin(matches)]['player'])
                if len(players) > 4:
                    print(f"Suggested to remove {len(players)- 4} player(s) in anticipation of blanks:")
                [print(f' - {player}') for player in players]
        if dgws_adj:
            print('\n------------- UPCOMING DGWS -------------')
            for gw,teams in dgws_adj.items():
                print(f'>> Gameweek {gw}')
                matches = [self.grab_team_name(x) for x in ids if x in teams]
                players = list(input_fpl_team.loc[input_fpl_team['team'].isin(matches)]['player'])
                [print(f' - {player}') for player in players]
    
    def display_beacon_changes_this_gw(self):
            output_file_path = os.path.abspath("../../stats/beacon_team_history.txt")
            file = open(output_file_path, "r")
            contents = file.read()
            dictionary = ast.literal_eval(contents)
            most_recent_gw = list(dictionary.keys())[-1]
            prev_gw = list(dictionary.keys())[-2]
            change_dict = {}
            for team_id in dictionary[most_recent_gw].keys():
                name = dictionary[most_recent_gw][team_id]['name']
                t2 = dictionary[most_recent_gw][team_id]['team']
                try:
                    t1 = dictionary[prev_gw][team_id]['team']
                    pre_diff = list(set(t1) - set(t2))
                    post_diff = list(set(t2) - set(t1))
                    change_dict[team_id] = {'name':name,
                                            'out':pre_diff,
                                            'in':post_diff}
                except: pass
            file.close()
            chng = 0
            for idx in change_dict:
                name = change_dict[idx]['name']
                predifs = change_dict[idx]['out']
                postdifs = change_dict[idx]['in']
                changes = {}
                for preid in predifs:
                    pos = self.grab_player_pos(preid)
                    if pos not in changes.keys():
                        changes[pos] = {}
                    if '0' not in changes[pos].keys():
                        changes[pos]['0'] = []
                    changes[pos]['0'].append(preid)
                for postid in postdifs:
                    pos = self.grab_player_pos(postid)
                    if pos not in changes.keys():
                        changes[pos] = {}
                    if '1' not in changes[pos].keys():
                        changes[pos]['1'] = []
                    changes[pos]['1'].append(postid)
                if not predifs and not postdifs:
                    continue
                else:
                    chng = 1
                    print('\n--------------------')
                    print(f'{name}\n')
                    for pos in changes.keys():
                        a = changes[pos]['0']
                        b = changes[pos]['1']
                        for i,x in enumerate(a):
                            b4 = self.grab_player_name(x)
                            b5 = self.grab_player_name(b[i])
                            print(f'{b4} ({pos}) -> {b5} ({pos})')
            if chng == 0 :
                print('Managers have made no changes')
            return

    def display_beacon_movements_this_gw(self, ranged=None):
        if ranged and ranged != 'full':
            print('Entry must be empty or \"full\"!')
            return
        output_file_path = os.path.abspath("../../stats/beacon_team_history.txt")
        file = open(output_file_path, "r")
        contents = file.read()
        dictionary = ast.literal_eval(contents)
        recorded_gws = list(dictionary.keys())
        change_dict = {}
        if not ranged:
            gwrange = range(len(recorded_gws)-1,len(recorded_gws))
        elif ranged == 'full':
            gwrange = range(1,len(recorded_gws))
        for gw_identifier in gwrange:
            for team_id in dictionary[recorded_gws[gw_identifier]].keys():
                name = dictionary[recorded_gws[gw_identifier]][team_id]['name']
                t2 = dictionary[recorded_gws[gw_identifier]][team_id]['team']
                try:
                    t1 = dictionary[recorded_gws[gw_identifier-1]][team_id]['team']
                    pre_diff = list(set(t1) - set(t2))
                    post_diff = list(set(t2) - set(t1))
                    if team_id not in change_dict.keys():
                        change_dict[team_id] = {'name':name,
                                                'out':[],
                                                'in':[]}
                    change_dict[team_id]['out'] = change_dict[team_id]['out'] + pre_diff
                    comp1 = [x for x in change_dict[team_id]['out'] if x in change_dict[team_id]['in']]
                    change_dict[team_id]['in'] = change_dict[team_id]['in'] + post_diff
                    comp2 = [x for x in change_dict[team_id]['in'] if x in change_dict[team_id]['out']]
                    if comp1:
                        change_dict[team_id]['in'] = [x for x in change_dict[team_id]['in'] if x not in comp1]
                    if comp2:
                        change_dict[team_id]['out'] = [x for x in change_dict[team_id]['out'] if x not in comp2]
                except: pass
        tally_dict = {'OUT':{},
                        'IN':{}}
        entries = len(change_dict.keys())
        for team_id in change_dict.keys():
            outs = change_dict[team_id]['out']
            ins = change_dict[team_id]['in']
            for o in outs:
                if o not in tally_dict['OUT']:
                    tally_dict['OUT'][o] = 0
                tally_dict['OUT'][o] += 1
            for i in ins:
                if i not in tally_dict['IN']:
                    tally_dict['IN'][i] = 0
                tally_dict['IN'][i] += 1
        outlist = sorted(tally_dict['OUT'].items(), key=lambda x:x[1], reverse=True)
        inlist = sorted(tally_dict['IN'].items(), key=lambda x:x[1], reverse=True)
        print('\n---------- OUT -----------\n')
        for a,b in outlist:
            print(f'{self.grab_player_name(a)} -- {b}/{entries}')
        print('\n---------- IN -----------\n')
        for c,d in inlist:
            print(f'{self.grab_player_name(c)} -- {d}/{entries}')
        return

    def display_beacon_tallies_this_gw(self, player_ids: list):
        fplcounter = {player_id: 0 for player_id in player_ids}
        output_file_path = os.path.abspath("../../stats/beacon_team_history.txt")
        file = open(output_file_path, "r")
        contents = file.read()
        dictionary = ast.literal_eval(contents)
        recorded_gws = list(dictionary.keys())
        gw_identifier = len(recorded_gws)-1
        for team_id in dictionary[recorded_gws[gw_identifier]].keys():
            genlist = dictionary[recorded_gws[gw_identifier]][team_id]['team']
            for ids in genlist:
                if ids in fplcounter.keys():
                    fplcounter[ids] += 1
        print('\n')
        for key in fplcounter.keys():
            value = fplcounter[key]
            entries = len(dictionary[recorded_gws[gw_identifier]].keys())
            if int(value) == 0:
                tier = '\033[33m'
            elif int(value) >= 7:
                tier = '\033[36m'
            else:
                tier = ''
            print(f'{self.helper_fns.grab_player_name(key)} -- {tier}{value}\033[0m / {entries}')
        return
    
class UnderStatHelperFns:
    def __init__(self, understat_fetcher):
        self.api_understat_parser = understat_fetcher

    def grab_player_USID_from_FPLID(self, fpl_player_id):
        return next((x["understat"]["id"] for x in iter(self.api_understat_parser.understat_to_fpl_player_data) if x["fpl"]["id"] == fpl_player_id), None)
        
    def grab_team_USID_from_FPLID(self, fpl_player_id):
        return next((x["understat"]["id"] for x in iter(self.api_understat_parser.understat_to_fpl_team_data) if x["fpl"]["id"] == fpl_player_id), None)
        
    def grab_team_USname_from_FPLID(self, fpl_player_id):
        return next((x["understat"]["id"] for x in iter(self.api_understat_parser.understat_to_fpl_team_data) if x["fpl"]["id"] == fpl_player_id), None)

    def fetch_team_xg_against_teams_data(self, fpl_team_id):
        """
        Function returns xG of a specified team against all teams so far. Use fetch team all stats for expanded view
        """
        team_match_data = self.api_understat_parser.understat_team_match_data[fpl_team_id]
        xg_data = []
        for gw, data in enumerate(team_match_data):
            side = data['side']
            def opposite_side(side):
                if side == 'h':
                    return 'a'
                elif side == 'a':
                    return 'h'
            opposing_team = data[opposite_side(side)]
            xg_data.append({
                "gameweek": gw+1,
                "xG": data['xG'][side],
                "opponent_team_data": opposing_team
            })
        return xg_data
    
    def fetch_finite_team_param_stats(self, look_back):
        """
        Function returns all stats of all teams over a certain look back period, thus reducing to a finite value, both outputting averages and sums of all stats. 
        Usefulness is in stats like PPDA which outline how well-pressing certain teams are, which can be later be used to match up upcoming 
        teams and assess weaknesses based on general PPDA and specific PPDA.
        """
        cols_to_omit = ['h_a', 'result', 'date', 'id', 'title']
        
        compiled_team_data = []
        for _, team_data in self.api_understat_parser.understat_team_data.items():
            temp_data = {'id': team_data['id'], 'title': team_data['title']}
            for key, values in team_data['history'].items():
                if key not in cols_to_omit:
                    temp_data[f"{key}_avg"] = np.mean(values[-look_back:])
                    temp_data[f"{key}_sum"] = np.sum(values[-look_back:])
                else: continue
            compiled_team_data.append(temp_data)
        return compiled_team_data


#     def fetch_player_shots_against_teams(self, fpl_player_id, TEAM_AGAINST_ID):
#         player_shot_data = self.understat_player_shot_data_group[fpl_player_id]
#         df = pd.DataFrame(data=player_shot_data)
#         team_dict = {}
#         for _, row in df.iterrows():
#             season = row['season']
#             result  = row['result']
#             shot_type = row['shotType']
#             situation = row['situation']
#             if row['h_a'] == 'h':
#                 team = row['a_team']
#                 if team not in team_dict:
#                     team_dict[team] = {'h': 0, 'a': 0, 'seasons': {}}
#                 if season not in team_dict[team]['seasons']:
#                     team_dict[team]['seasons'][season] = {'h': {}, 'a': {}}
#                 if shot_type not in team_dict[team]['seasons'][season]['h'].keys():
#                     team_dict[team]['seasons'][season]['h'][shot_type] = []
#                 team_dict[team]['seasons'][season]['h'][shot_type].append((situation, result))
#                 if result == 'Goal':
#                     team_dict[team]['h'] += 1
#             elif row['h_a'] == 'a':
#                 team = row['h_team']
#                 if team not in team_dict:
#                     team_dict[team] = {'h': 0, 'a': 0, 'seasons': {}}
#                 if season not in team_dict[team]['seasons']:
#                     team_dict[team]['seasons'][season] = {'h': {}, 'a': {}}
#                 if shot_type not in team_dict[team]['seasons'][season]['a'].keys():
#                     team_dict[team]['seasons'][season]['a'][shot_type] = []
#                 team_dict[team]['seasons'][season]['a'][shot_type].append((situation, result))
#                 if result == 'Goal':
#                     team_dict[team]['a'] += 1

#         output_df = pd.DataFrame.from_dict(team_dict, orient='index').reset_index()
#         output_df.columns = ['Team', 'h', 'a', 'full_summary']
#         def order_season_by_year(season):
#             return {year: season[year] for year in sorted(season.keys())}
#         output_df['full_summary'] = output_df['full_summary'].apply(order_season_by_year)
#         output_df = output_df.sort_values(by=['Team']).reset_index(drop=True)
#         spreaded_stats = {}
#         for szn,data in output_df.loc[output_df['Team'] == self.und_helper_fns.grab_team_USname_from_FPLID(TEAM_AGAINST_ID)]['full_summary'].iloc[0].items():
#             spreaded_stats[szn]={}
#             for h_a, shotdata in data.items():
#                 tally = {}
#                 for foot, datalist in shotdata.items():
#                     tally[foot] = {'goals':[], 'misses':[]}
#                     for shot in datalist:
#                         if 'Goal' in shot:
#                             tally[foot]['goals'].append(shot)
#                         else:
#                             tally[foot]['misses'].append(shot)
#                 spreaded_stats[szn][h_a] = tally
#         return spreaded_stats
    
#     def fetch_player_stats_against_teams(self, FPL_ID, TEAM_AGAINST_ID):
#         player_match_data = self.understat_player_match_data[FPL_ID]
#         player_match_df = pd.DataFrame(data=player_match_data)
#         player_match_df['h_a'] = ''
#         player_team = self.und_helper_fns.grab_team_USname_from_FPLID(self.fpl_helper_fns.grab_player_team_id(FPL_ID))
#         for index, row in player_match_df.iterrows():
#             season = row['season']
#             team = player_team

#             if team in row['h_team']:
#                 player_match_df.at[index, 'h_a'] = 'h'
#             elif team in row['a_team']:
#                 player_match_df.at[index, 'h_a'] = 'a'
#             else:
#                 player_match_df.at[index, 'h_a'] = 'NA'
#         team_dict = {}

#         for index, row in player_match_df.iterrows():
#             goals = int(row['goals'])
#             if goals > 0:
#                 if row['h_a'] == 'h':
#                     team = row['a_team']
#                     season = row['season']
#                     if team not in team_dict:
#                         team_dict[team] = {'h': 0, 'a': 0, 'seasons': {}}
#                     if season not in team_dict[team]['seasons']:
#                         team_dict[team]['h'] += goals
#                         team_dict[team]['a'] += 0
#                         team_dict[team]['seasons'][season] = {'h': goals, 'a': 0}
#                     else:
#                         team_dict[team]['h'] += goals
#                         team_dict[team]['seasons'][season]['h'] += goals
#                 elif row['h_a'] == 'a':
#                     team = row['h_team']
#                     season = row['season']
#                     if team not in team_dict:
#                         team_dict[team] = {'h': 0, 'a': 0, 'seasons': {}}
#                     if season not in team_dict[team]['seasons']:
#                         team_dict[team]['h'] += 0
#                         team_dict[team]['a'] += goals
#                         team_dict[team]['seasons'][season] = {'h': 0, 'a': goals}
#                     else:
#                         team_dict[team]['a'] += goals
#                         team_dict[team]['seasons'][season]['a'] += goals
#             else:
#                 if row['h_a'] == 'h':
#                     team = row['a_team']
#                 elif row['h_a'] == 'a':
#                     team = row['h_team']
#                 else:
#                     continue
#                 season = row['season']
#                 if team not in team_dict:
#                     team_dict[team] = {'h': 0, 'a': 0, 'seasons': {}}
#                 if season not in team_dict[team]['seasons']:
#                     team_dict[team]['seasons'][season] = {'h': 0, 'a': 0}

#         def calculate_coefficient_of_variation(goals, h_a):
#             h_goals = [data['h'] for data in goals.values()]
#             a_goals = [data['a'] for data in goals.values()]
#             if len(goals) <= 1 or sum(h_goals) + sum(a_goals) == 0:
#                 return None
#             if h_a == 'total': 
#                 mean_h = statistics.mean(h_goals)
#                 mean_a = statistics.mean(a_goals)
#                 mean = (mean_h + mean_a) / 2
#                 h_standard_deviation = statistics.stdev(h_goals)
#                 a_standard_deviation = statistics.stdev(a_goals)
#                 standard_deviation = (h_standard_deviation + a_standard_deviation) / 2
#                 coefficient_of_variation = (standard_deviation / mean) * 100
#             elif h_a == 'h':
#                 if sum(h_goals) == 0:
#                     return None
#                 mean_h = statistics.mean(h_goals)
#                 h_standard_deviation = statistics.stdev(h_goals)
#                 coefficient_of_variation = (h_standard_deviation / mean_h) * 100
#             elif h_a == 'a':
#                 if sum(a_goals) == 0:
#                     return None
#                 mean_a = statistics.mean(a_goals)
#                 a_standard_deviation = statistics.stdev(a_goals)
#                 coefficient_of_variation = (a_standard_deviation / mean_a) * 100      
#             return coefficient_of_variation

#         def calculate_goal_avg(goals):

#             h_goals = [data['h'] for data in goals.values()]
#             a_goals = [data['a'] for data in goals.values()]

#             avg_goals = (sum(h_goals) + sum(a_goals)) / (2*len(goals))
#             return avg_goals

#         output_df = pd.DataFrame.from_dict(team_dict, orient='index').reset_index()
#         output_df.columns = ['Team', 'h', 'a', 'season']

#         def order_season_by_year(season):
#             return {year: season[year] for year in sorted(season.keys())}

#         def calc_matches(szns):
#             return 2*len(szns)

#         output_df['season'] = output_df['season'].apply(order_season_by_year)

#         output_df['Variation Coefficient (H)'] = output_df['season'].apply(calculate_coefficient_of_variation, args=('h',))
#         output_df['Variation Coefficient (A)'] = output_df['season'].apply(calculate_coefficient_of_variation, args=('a',))
#         output_df['Variation Coefficient (Total)'] = output_df['season'].apply(calculate_coefficient_of_variation, args=('total',))

#         output_df['Avg Goals/match'] = output_df['season'].apply(calculate_goal_avg)

#         output_df['Matches'] = output_df['season'].apply(calc_matches)

#         output_df.sort_values(by=['Team']).reset_index(drop=True)
#         output_df.sort_values(by=['Variation Coefficient (Total)'])
        
#         output_df = output_df.loc[output_df['Team'] == self.und_helper_fns.grab_team_USname_from_FPLID(TEAM_AGAINST_ID)]
        
#         return output_df.to_dict()