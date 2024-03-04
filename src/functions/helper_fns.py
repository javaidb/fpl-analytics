import math
import difflib
import numpy as np
import sys

from collections import defaultdict

import asyncio

def calculate_mean_std_dev(data):
    mean = sum(data) / len(data)
    var = sum((l - mean) ** 2 for l in data) / len(data)
    st_dev = math.sqrt(var)

    return mean, st_dev

def progress_bar_update(i, num_iter, complete=False):
    if not complete:
        sys.stdout.write(f'\rProcessing {i+1}/4 ' + '.' * (num_iter % 4) + '   ')
    else:
        sys.stdout.write('\rProcessing... \x1b[32m\u2714\x1b[0m\n')
    sys.stdout.flush()

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
    
#================================================================================================================================================================
#=================================================================== PARAMETER GRABBING =========================================================================
#================================================================================================================================================================

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
    
#================================================================================================================================================================
#=================================================================== CUSTOM FUNCTIONS ===========================================================================
#================================================================================================================================================================
    
    def compile_fdr_data(self):
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
    
#================================================================================================================================================================
#=================================================================== USER INFO FETCHING =========================================================================
#================================================================================================================================================================
         
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
    
    
class UnderStatHelperFns:
    def __init__(self, understat_fetcher):
        self.api_understat_parser = understat_fetcher

    def grab_player_USID_from_FPLID(self, fpl_player_id):
        return next((x["understat"]["id"] for x in iter(self.api_understat_parser.understat_to_fpl_player_data) if x["fpl"]["id"] == fpl_player_id), None)
        
    def grab_team_USID_from_FPLID(self, fpl_player_id):
        return next((x["understat"]["id"] for x in iter(self.api_understat_parser.understat_to_fpl_team_data) if x["fpl"]["id"] == fpl_player_id), None)
        
    def grab_team_USname_from_FPLID(self, fpl_player_id):
        return next((x["understat"]["id"] for x in iter(self.api_understat_parser.understat_to_fpl_team_data) if x["fpl"]["id"] == fpl_player_id), None)

    def fetch_team_xg_against_teams_data(self, fpl_team_id) -> list:
        """
        Takes an inputted ID of a team from FPL API and outputs the associated team's expected goals (xG) data from understat API

        Args:
            fpl_team_id (int): FPL team ID

        Returns:
            list: List of dictionaries, where each dictionary represents each gameweek, associated xG data and the team faced
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
    
    def fetch_finite_team_param_stats(self, look_back) -> list:
        """
        Function returns all stats of all teams over a certain look back period, thus reducing to a finite value, both outputting averages and sums of all stats. 
        Usefulness is in stats like PPDA which outline how well-pressing certain teams are, which can be later be used to match up upcoming 
        teams and assess weaknesses based on general PPDA and specific PPDA.

        Args:
            look_back (int): Number of gameweeks in the past to evaluate statistics over.

        Returns:
            list: List of dictionaries, where each dictionary represents each team and the associated finite value of each parameter evaluated across the look back period.
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