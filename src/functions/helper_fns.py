import math
import asyncio
import unicodedata
import difflib
import pandas as pd
import ast
import os
from understatapi import UnderstatClient
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

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

    #========================== General Parsing ==========================

    def grab_player_name(self,idx):
        name = self.data_parser.points.loc[self.data_parser.points['id_player'] == idx]['player']
        return name.values[-1]

    def grab_player_value(self,idx):
        name = self.data_parser.points.loc[self.data_parser.points['id_player'] == idx]['value'] / 10
        return name.values[-1]

    def grab_player_pos(self,idx):
        name = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == idx]['position']
        return name.values[-1]
     
    def grab_player_team(self,idx):
        name = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == idx]['name']
        return name.values[-1]
     
    def grab_player_team_id(self,idx):
        team_name = self.grab_player_team(idx)
        name = self.data_parser.team_info.loc[self.data_parser.team_info['name'] == team_name]['id']
        return name.values[-1]
     
    def grab_player_hist(self,idx):
        name = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == idx]['history']
        return name.values[-1]
     
    def grab_player_returns(self,idx):
        name = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == idx]['returnhist']
        return name.values[-1]
     
    def grab_player_minutes(self,idx):
        name = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == idx]['minutes']
        return name.values[-1]
     
    def grab_player_bps(self,idx):
        name = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == idx]['bps']
        return name.values[-1]
     
    def grab_player_full90s(self,idx):
        name = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == idx]['fulltime']
        return name.values[-1]

    def grab_player_full60s(self,idx):
        name = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == idx]['fullhour']
        return name.values[-1]

    def grab_team_id(self,team_name):
        idt = self.data_parser.team_info.loc[self.data_parser.team_info['name'] == team_name]['id'].values[0]
        return idt

    def grab_team_name_full(self,team_id):
        # idt = self.data_parser.team_info.loc[self.data_parser.team_info['id'] == team_id]['name'].values[0]
        return next(x['name'] for x in self.api_parser.raw_data['teams'] if x['id'] == team_id)
    
    def grab_team_name_short(self,team_id):
        return next(x['short_name'] for x in self.api_parser.raw_data['teams'] if x['id'] == team_id)

    def grab_player_fixtures(self, direction, team_id, look_size, reference_gw=None):
        if not reference_gw:
            reference_gw = self.api_parser.latest_gw
        GWS={}
        req = self.api_parser.fixtures
        for row in req:
            GW = row['event']
            if GW:
                if GW not in GWS.keys():
                    GWS[GW] = []
        #         print((row['team_a'],row['team_h']))
                GWS[GW].extend((row['team_a'],row['team_h']))
        for key in GWS:
            GWS[key] = [(GWS[key][i], GWS[key][i+1]) for i in range(0, len(GWS[key]), 2)]
        if direction == 'fwd':
            GWS = {k: v for k, v in GWS.items() if (k > reference_gw and k <= reference_gw + look_size)}
        elif direction == 'rev':
            GWS = {k: v for k, v in GWS.items() if (k >= reference_gw - look_size and k <= reference_gw)}
        fixtures = []
        for key in GWS:
            fixture = [(t[0],self.grab_team_name_short(t[0]),'H', self.team_rank(t[0])) if t[1] == team_id else (t[1], self.grab_team_name_short(t[1]),'A', self.team_rank(t[1])) for t in GWS[key] if team_id in (t[0], t[1])]
            fixtures.append((key,fixture))
        return fixtures
    
    #========================== Custom Operations ==========================
    
    def compile_fdr_data(self):
#       #========================== Compile FDRs from team_info ==========================
        init_id = 1
        fdr_data = {}
        while init_id < len(self.data_parser.total_summary):
            if init_id in list(self.data_parser.total_summary['id_player'].unique()):
                null_team_id = self.grab_player_team_id(init_id)
                elementdat = self.api_parser.fetch_data_from_api(f'element-summary/{init_id}/')
                try:
                    fdr_info = [[([i['team_h'],i['team_a']],i['difficulty']) for i in elementdat["fixtures"]][0]]
                    fdr_simpl = [((set(x[0]) - {null_team_id}).pop(),x[1]) for x in fdr_info]
                    for pair in fdr_simpl:
                        if pair[0] not in fdr_data.keys():
                            fdr_data[pair[0]] = pair[1]
                except:
                    pass
            init_id += 10
        init_id = 1
        while len(fdr_data) < 20 and init_id < len(self.data_parser.total_summary):
            null_team_id = self.grab_player_team_id(init_id)
            elementdat = self.api_parser.fetch_data_from_api(f'element-summary/{init_id}/')
            fdr_info = [([i['team_h'],i['team_a']],i['difficulty']) for i in elementdat["fixtures"]][:3]
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
    
    def loop_name_finder(self, player_name_entry):
        segments = player_name_entry.split(" ")
        name_entries_to_omit = ['van']
        preconcat_name = [seg for seg in segments if len(seg) > 2 and seg.lower() not in name_entries_to_omit and not seg[0].isupper()]
        preconcat_name = ' '.join(preconcat_name)
        all_players_from_total_summary = self.data_parser.total_summary.player.tolist()
        while preconcat_name not in all_players_from_total_summary:
            M1 = difflib.get_close_matches(player_name_entry, all_players_from_total_summary)
            split_strings = player_name_entry.split(" ")
            M2 = []
            for split_str in split_strings:
                if len(split_str) < 3:
                    continue
                for csv_name in all_players_from_total_summary:
                    csv_alt = ''.join(c for c in unicodedata.normalize('NFD', csv_name)
                                      if unicodedata.category(c) != 'Mn')
                    if split_str.lower() in csv_alt.lower():
                        M2.append(csv_name)
            preconcat_name = input(f'Couldnt find "{preconcat_name}", did you mean any of the following?\n{list(set(M1) | set(M2))}\n')
            if preconcat_name == "":
                return preconcat_name
        return preconcat_name
    
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

    def display_beacon_tallies_this_gw(player_ids: list):
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
        fpl_player_data = self.data_parser.total_summary[['id_player','first_name','second_name','web_name','name']]
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