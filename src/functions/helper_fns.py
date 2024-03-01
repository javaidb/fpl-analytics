import math
import asyncio
import unicodedata
import difflib
import pandas as pd
import ast
import os
from collections import defaultdict
from understatapi import UnderstatClient
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import difflib

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
            return [{'gameweek': gw_info['event'], 'team': gw_info['team_h'] if gw_info['is_home'] else gw_info['team_a'], 'opponent_team': gw_info['team_a'] if gw_info['is_home'] else gw_info['team_h'], 'is_home': gw_info['is_home']} for gw_info in all_fixtures if (gw_info['event'] and (gw_info['event'] >= reference_gw+1 and gw_info['event'] <= reference_gw + games_ahead - 1))]
        compiled_player_data = {str(player_id): process_fixtures(raw_data[player_id]['fixtures']) for player_id in sorted(id_values)}
        
        #Handle blanks, which are usually not present at all
        for player_id, player_data in compiled_player_data.items():
            last_gw = max([x['id'] for x in self.api_parser.raw_data['events']])
            expected_gws = list(range(reference_gw+1, min(last_gw+1, reference_gw+games_ahead-1)))
            compiled_gws = list({x['gameweek'] for x in player_data})
            gw_conflicts = [gw for gw in expected_gws if gw not in compiled_gws]
            if len(gw_conflicts) >= 1:
                for gw in gw_conflicts:
                    compiled_player_data[player_id].append({'gameweek': gw, 'team': None, 'opponent_team': None, 'is_home': None})
                compiled_player_data[player_id] = sorted(compiled_player_data[player_id], key=lambda x: x['gameweek'])
                
        return compiled_player_data
    
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
    
    def find_best_match(self, input_string):
        best_matches = []
        max_score = 0
        dict_list = [{**{k: v for k, v in self.data_parser.master_summary[x].items() if k in ['first_name', 'second_name', 'web_name', 'pos_singular_name_short', 'team_short_name']}, 'id': x} for x in api_ops.player_ids]
        
        for d in dict_list:
            for key in ['web_name', 'second_name', 'first_name']:
                score = difflib.SequenceMatcher(None, input_string, d[key]).ratio()
                if score > max_score:
                    max_score = score
                    best_matches = [d]
                elif score == max_score:
                    best_matches.append(d)
        def remove_duplicates(dicts):
            return [dict(t) for t in {tuple(sorted(d.items())) for d in dicts}]
        best_matches = remove_duplicates(best_matches)
        
        if len(best_matches) == 1:
            return best_matches[0]["id"]
        elif len(best_matches) > 1:
            for i, match in enumerate(best_matches):
                name_str = f"{match['web_name']} [{match['team_short_name']}] ({match['first_name']} {match['second_name']})"
                print(f"{i + 1}: {name_str}")
            choice = input("Enter the number of the match you want to select (or press Enter to skip): ")
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
    def __init__(self, api_parser, data_parser):
        self.api_parser = api_parser
        self.data_parser = data_parser
        self._match_fpl_to_understat()
        self._build_team_data()
    
    def _match_fpl_to_understat(self):
        #Matching teams
        print('Matching FPL teams to UnderStat teams...')
        teams = pd.json_normalize(self.api_parser.raw_data['teams'])
        fpl_ids = teams['id'].tolist()
        fpl_names = teams['name'].tolist()
        self.fpl_nums = list(zip(fpl_ids, fpl_names))
        with UnderstatClient() as understat:
            league_szn_team_stats = understat.league(league="EPL").get_team_data(season="2023")
            understat_nums_unsorted = [(x['id'],x['title']) for x in league_szn_team_stats.values()]
            self.understat_nums = sorted(understat_nums_unsorted, key=lambda x: x[1])
        self.team_nums = list(zip(self.fpl_nums,self.understat_nums))

        #Matching players; UDID TO FPLID
        print('Matching FPL players to UnderStat players...')
        league_player_data = understat.league(league="EPL").get_player_data(season="2024")
        player_data_understat = pd.DataFrame(data=league_player_data)
        understat_player_data = player_data_understat[['id','player_name','team_title']]
        fpl_player_data = pd.DataFrame([{**{key: v[key] for key in ['first_name', 'second_name','web_name', 'team_name']}, 'id_player': k} for k, v in self.data_parser.master_summary.items()])
        column_mapping = {'id_player': 'id', 'web_name': 'player_name'}
        fpl_player_data = fpl_player_data.rename(columns=column_mapping)
        fpl_player_data['combined_name'] = fpl_player_data['first_name'] + " " + fpl_player_data['second_name']
        matched_df = pd.DataFrame(columns=['ID_understat', 'ID_FPL'])
        player_nums = []
        for _, row in understat_player_data.iterrows():
            #Understat data
            name_df1 = row['player_name']
            id_df1 = row['id']
            team_df1 = row['team_title'].split(",")[-1]
            #Fpl data
            try:
                fpl_team_name = [x[0][1] for x in self.team_nums if x[1][1] == team_df1][0]
                relevant_fpl_df = fpl_player_data.loc[fpl_player_data['name'] == fpl_team_name]
            except Exception as e:
                print(team_df1)
                print(e)
            closest_match = process.extractOne(name_df1, relevant_fpl_df['combined_name'], scorer=fuzz.ratio)
            # Assuming a minimum threshold for matching (adjust as needed)
            if closest_match[1] >= 40:
                matched_name_df2 = closest_match[0]
                matched_index_df2 = fpl_player_data[fpl_player_data['combined_name'] == matched_name_df2].index[0]
                id_df2 = fpl_player_data.at[matched_index_df2, 'id']
                matched_df = matched_df.append({'ID_understat': int(id_df1), 'ID_FPL': int(id_df2)}, ignore_index=True)
                player_nums.append(((id_df2,matched_name_df2),(id_df1,name_df1)))
            else:
                print(f'Issues with: {name_df1} {team_df1} {closest_match}')
        self.full_players_nums_df=matched_df
        self.player_nums = player_nums
        print(f'{len(self.full_players_nums_df)} / {len(understat_player_data)} players processed...')

    def _build_team_data(self):
        print('Building team stats for season so far...')
        understat = UnderstatClient()
        data_team = understat.league(league="EPL").get_team_data(season="2023")
        new_team_data = {}
        for team_id, team_data in data_team.items():
            new_team_data[team_id] = team_data.copy()
            new_history = {}
            for game in team_data['history']:
                for key, value in game.items():
                    if key not in new_history:
                        new_history[key] = []
                    new_history[key].append(value)
            new_team_data[team_id]['history'] = new_history
        self.new_team_data = new_team_data

    def grab_player_USID_from_FPLID(self, FPL_ID):
        return int([x[1][0] for x in self.player_nums if str(x[0][0]) == str(FPL_ID)][0])
        
    def grab_team_USID_from_FPLID(self, FPL_ID):
        return int([x[1][0] for x in self.team_nums if str(x[0][0]) == str(FPL_ID)][0])
        
    def grab_team_USname_from_FPLID(self, FPL_ID):
        return [x[1][1] for x in self.team_nums if str(x[0][0]) == str(FPL_ID)][0]