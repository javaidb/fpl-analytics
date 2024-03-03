import sys
import os
sys.path.append(os.path.abspath('..'))
from src.config import config
import requests
import json
import os
# import pandas as pd
from tqdm.notebook import tqdm_notebook
from datetime import datetime, timezone
from dateutil import parser
from understatapi import UnderstatClient
import pandas as pd
import numpy as np

import asyncio
import aiohttp

'''
TIPS:
async used for aynchronous fns which are recommended for http requests
In order to use data WITHIN this same chain that is formed from asynchronous counterparts, it is recommended
to use synchronous contexts to run compile these kinds of data. These cases we use asyncio.run()
This allows for async contexts to be used synchronously, e,g, i can now use raw_data throughout
'''

class FPLAPIParser:
    def __init__(self):
        self.base_url = config.BASE_URL
        self.raw_data = self.fetch_data_from_api('bootstrap-static/')
        self.player_ids = [x['id'] for x in self.raw_data['elements']]
        self.raw_element_summary = {}
        self.config_data = self.get_config_data()
        self.latest_gw = self.get_latest_gameweek()
        self.rival_ids = self.fetch_rivals_based_on_pts()
        self.personal_fpl_raw_data = self.fetch_personal_fpl_data()
        self.fixtures = self.fetch_fixtures()
        self.blanks, self.dgws = self.look_for_blanks_and_dgws()
        self.rival_stats = self.tabulate_rival_stats(self.get_beacon_ids())
        self.full_element_summary = asyncio.run(self.compile_master_element_summary())

    def fetch_data_from_api(self, endpoint):
        url = f'{self.base_url}{endpoint}'
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
        # async with aiohttp.ClientSession() as session:
        #     async with session.get(url) as response:
        #         data = await response.json()
        #         return data
    
    def get_config_data(self):
        config_data_path = os.path.abspath('../src/config/data.json')
        with open(config_data_path, 'r') as file:
            data = json.load(file)
            return data

    def get_latest_gameweek(self):
        gwdata = self.raw_data['events']
        now = datetime.now(timezone.utc)
        latest_gw = max(
            (int(gw['id']) for gw in gwdata if parser.parse(gw['deadline_time']) <= now),
            default=None
        )
        return latest_gw

    def get_league_ids(self):
        active_szn = self.config_data["fpl_id_data"]
        return [x["id"] for x in active_szn["personal_league_ids"]]

    def get_beacon_ids(self):
        active_szn = self.config_data["fpl_id_data"]
        return active_szn["beacon_team_ids"]

    def get_personal_fpl_id(self):
        active_szn = self.config_data["fpl_id_data"]
        return active_szn["personal_team_id"]

    def fetch_rivals_based_on_pts(self):
        rival_team_ids = []
        for league_id in self.get_league_ids():
            r = self.fetch_data_from_api('leagues-classic/' + str(league_id) + '/standings/')
            RANK_THRESH = 99
            for i in r['standings']['results']:
                if 'Javaid' in i['player_name']:
                    RANK_THRESH = i['rank']
            RIVAL_IDS = []
            for i in r['standings']['results']:
                if i['rank'] < min(RANK_THRESH,5):
                    RIVAL_IDS.append(i['entry'])
            rival_team_ids.append(RIVAL_IDS)

    def fetch_fpl_data(self, fpl_id):
        fpl_info = self.fetch_data_from_api(f"entry/{fpl_id}")
        latest_picks = self.fetch_data_from_api(f"entry/{fpl_id}/event/{self.latest_gw}/picks/")
        if latest_picks['active_chip'] and latest_picks['active_chip'] == "freehit":
            latest_picks = self.fetch_data_from_api(f"entry/{fpl_id}/event/{self.latest_gw - 1}/picks/")
        return {
            "general_info": fpl_info,
            "latest_picks": latest_picks
        }

    def fetch_player_overall_fpl_rank(self, ID):
        r = self.fetch_fpl_data(ID)
        return r["general_info"]["summary_overall_rank"]

    def fetch_player_fpl_name(self, ID):
        r = self.fetch_fpl_data(ID)["general_info"]
        first_name = r["player_first_name"]
        last_name = r["player_last_name"]
        return f"{first_name} {last_name}"

    def fetch_personal_fpl_data(self):
        fpl_id = self.get_personal_fpl_id()
        return self.fetch_fpl_data(fpl_id)
    
    def fetch_fixtures(self):
        return self.fetch_data_from_api('fixtures/')
    
    def look_for_blanks_and_dgws(self):
        GWS={}
        for fixture_data in self.fixtures:
            GW = fixture_data['event']
            if GW:
                if GW not in GWS.keys():
                    GWS[GW] = []
                GWS[GW].extend((fixture_data['team_a'],fixture_data['team_h']))
        BLANKS={}
        DGWS={}
        for gw,teams in GWS.items():
            BLANKS[gw] = [x for x in range(1,21) if x not in teams]
            DGWS[gw] = [x for x in teams if teams.count(x) > 1]
        BLANKS = {k: v for k, v in BLANKS.items() if v}
        DGWS = {k: v for k, v in DGWS.items() if v}
        return BLANKS,DGWS
    
    async def fetch_element_summaries(self, player_id: int, session = None):
        if player_id in self.raw_element_summary:
            return self.raw_element_summary[player_id]
        if session:
            headers = {'Accept': 'application/json'}
            async with session.get(f'{config.BASE_URL}/element-summary/{player_id}/', headers=headers) as resp:
                #Status code implying success
                if resp.status == 200:
                    player_data = await resp.json()
                    return player_data
                elif resp.status == 429:
                    # Rate limit exceeded, implement backoff
                    retry_after = int(resp.headers.get('Retry-After', 5))  # Default to 5 seconds
                    # print(f"Rate limit exceeded. Retrying after {retry_after} seconds.")
                    await asyncio.sleep(retry_after)
                    return await self.fetch_element_summaries(player_id, session)
                else:
                    # Handle non-200 status code
                    print(f"Error: {resp.status} - {resp.reason}")
                    return None
        else:
            player_data = self.fetch_data_from_api(f'element-summary/{player_id}/')
        self.raw_element_summary[player_id] = player_data
        return player_data
    
    async def fetch_gameweek_player_data(self, player_id, session):
        if player_id in self.raw_element_summary:
            return self.raw_element_summary[player_id]

        player_data = await self.fetch_element_summaries(player_id, session)
        return player_data
    
    async def compile_master_element_summary(self):
        full_element_summary = {}
        async def fetch_all_summaries():
            async with aiohttp.ClientSession() as session:
                tasks = [self.fetch_gameweek_player_data(player_id,session) for player_id in sorted(self.player_ids)]
                gameweek_histories = await asyncio.gather(*tasks)
            for player_num, player_id in enumerate(tqdm_notebook(sorted(self.player_ids), desc="Building element summaries")):
                try:
                    player_data = gameweek_histories[player_num]
                    full_element_summary[player_id] = player_data
                except Exception as e:
                    print(f"Error with element summary building for ID {player_id}: {e}")
        asyncio.run(fetch_all_summaries())
        return full_element_summary
    
##########################################################################################################################

    def compile_rivals_team(self, team_ids: list):
        rival_ids_data = {}
        for team_id in team_ids:
            r = self.fetch_data_from_api(f'entry/{team_id}/')
            first_name = r['player_first_name']
            last_name = r['player_last_name']
            rival_ids_data[team_id] = {'name': f'{first_name} {last_name}',
                                  'points': r['summary_overall_points'],
                                  'rank': r['summary_overall_rank']}
        for rival_id in rival_ids_data.keys():
            r = self.fetch_data_from_api(f'entry/{rival_id}/event/{self.latest_gw}/picks/')
            rival_ids_data[rival_id]['team'] = [i['element'] for i in r['picks']]
        return rival_ids_data
    
    def tabulate_rival_stats(self, team_id_list: list):
        rival_id_data = self.compile_rivals_team(team_id_list)
        self.rival_id_data = rival_id_data
        list_rival_FPLteam_ids = []
        for rival_id in rival_id_data.keys():
            list_rival_FPLteam_ids.append(rival_id_data[rival_id]['team'])
        similar_ids = list(set.intersection(*map(set,list_rival_FPLteam_ids)))
        all_ids = list(set.union(*map(set,list_rival_FPLteam_ids)))
        unique_ids = list(set(all_ids).difference(similar_ids))
        id_count = {}
        for ids in list_rival_FPLteam_ids:
            for ide in ids:
                if ide not in id_count.keys():
                    id_count[ide] = 1
                else:
                    id_count[ide] += 1
        return {'unique_ids': unique_ids, 'similar_ids': similar_ids, 'id_count': id_count}

class UnderstatAPIParser:

    def __init__(self, fpl_api_parser, fpl_helper_fns):
        self.fpl_api_parser = fpl_api_parser
        self.helper_fns = fpl_helper_fns
        self.understat_to_fpl_team_data = self._match_fpl_to_understat_teams()
        self.understat_to_fpl_player_data = self._match_fpl_to_understat_players()
        self.understat_team_data = self._build_understat_team_data()
        self.understat_team_match_data = self._build_understat_team_match_data()
        # self.understat_player_shot_data_raw = self._build_understat_player_shot_data()
        # self.understat_player_shot_data_group = self._compile_understat_player_shot_data()
        # self.understat_player_match_data = self._build_understat_player_match_data()

#================================================================================================================================================================
#===================================================================== MATCH FPL TO UNDERSTAT ===================================================================
#================================================================================================================================================================

    def _match_fpl_to_understat_teams(self):
        teams = self.fpl_api_parser.raw_data['teams']
        fpl_data = [{**{param_str: param_val for param_str, param_val in team.items() if param_str in ['id', 'name']}} for team in teams]

        with UnderstatClient() as understat:
            league_szn_team_stats = understat.league(league="EPL").get_team_data(season="2023")
            understat_nums_unsorted = [{"id": int(x['id']), "name": x['title']} for x in league_szn_team_stats.values()]
            understat_data = sorted(understat_nums_unsorted, key=lambda x: x["name"])

        return [{'fpl': d1, 'understat': d2} for d1, d2 in zip(fpl_data, understat_data)]
    
    def _match_fpl_to_understat_players(self):

        with UnderstatClient() as understat:
            league_player_data = understat.league(league="EPL").get_player_data(season="2023")

        matched_data = []
        team_data = self._match_fpl_to_understat_teams()
        for test_d in league_player_data:
            team_name = test_d["team_title"].split(",")[-1] #Account for cases where player switched teams in PL
            fpl_team_id = next(x["fpl"]["id"] for x in iter(team_data) if x["understat"]["name"] == team_name)
            matched_fpl_player_id = self.helper_fns.find_best_match(test_d["player_name"], fpl_team_id)
            matched_data.append({
                "fpl": {
                    "id": int(matched_fpl_player_id)
                },
                "understat": {
                    "id": int(test_d["id"]),
                    "name": test_d["player_name"],
                }
            })
        return matched_data

#================================================================================================================================================================
#================================================================ BUILD UNDERSTAT TEAM DATA =====================================================================
#================================================================================================================================================================

    def _build_understat_team_data(self):
            
        with UnderstatClient() as understat:
            fetched_team_data = understat.league(league="EPL").get_team_data(season="2023")
        compiled_team_data = {}
        for team_id, raw_team_data in tqdm_notebook(fetched_team_data.items(), desc = "Building understat team data"):
            compiled_team_data[team_id] = raw_team_data.copy()
            temp_data = {}
            for gameweek_data in raw_team_data['history']:
                for primary_param_name, primary_param_val in gameweek_data.items():
                    if isinstance(primary_param_val, dict): # For ppda where values are dicts
                        for sub_name, sub_value in primary_param_val.items():
                            temp_data.setdefault(f"{primary_param_name}_{sub_name}", []).append(sub_value)
                    else:
                        temp_data.setdefault(primary_param_name, []).append(primary_param_val)
            compiled_team_data[team_id]['history'] = temp_data
        return compiled_team_data
        
    def _build_understat_team_match_data(self):
        all_fpl_team_ids = [x['fpl']['id'] for x in self.understat_to_fpl_team_data]
        team_match_data = {}
        for fpl_team_id in tqdm_notebook(all_fpl_team_ids, desc = "Building understat team match data"):
            team_name = next(x["understat"]["name"] for x in iter(self.understat_to_fpl_team_data) if x["fpl"]["id"] == int(fpl_team_id))
            formatted_team_name = team_name.replace(" ", "_")
            with UnderstatClient() as understat:
                team_match_data[fpl_team_id] = understat.team(team=formatted_team_name).get_match_data(season="2023")
        return team_match_data
    
#================================================================================================================================================================
#================================================================ BUILD UNDERSTAT PLAYER DATA ===================================================================
#================================================================================================================================================================


    # async def fetch_player_shot_data(self, understat_client, fpl_player_id):
    #     async with aiohttp.ClientSession() as session:
    #         understat_id = next(x["understat"]["id"] for x in iter(self.understat_to_fpl_player_data) if x["fpl"]["id"] == int(fpl_player_id))
    #         player_shot_data = await understat_client.player(player=str(understat_id)).get_shot_data()
    #         return fpl_player_id, player_shot_data

    # async def fetch_all_player_shot_data(self, understat_client, player_ids):
    #     tasks = [self.fetch_player_shot_data(understat_client, player_id) for player_id in player_ids]
    #     results = {}
    #     with tqdm_notebook(total=len(player_ids)) as pbar:
    #         for completed_task in asyncio.as_completed(tasks):
    #             player_id, result = await completed_task
    #             results[player_id] = result
    #             pbar.update(1)
    #     return results

    # def _build_understat_player_shot_data(self):
    #     all_matched_fpl_player_ids = [x['fpl']['id'] for x in self.understat_to_fpl_player_data]
    #     understat_client = UnderstatClient()  # assuming you have your UnderstatClient class
    #     loop = asyncio.get_event_loop()
    #     all_player_shot_data = loop.run_until_complete(self.fetch_all_player_shot_data(understat_client, all_matched_fpl_player_ids))
    #     return all_player_shot_data
    
    def _build_understat_player_shot_data(self):

        all_matched_fpl_player_ids = [x['fpl']['id'] for x in self.understat_to_fpl_player_data]
        all_player_shot_data = {}
        for fpl_player_id in tqdm_notebook(all_matched_fpl_player_ids, desc = "Building understat player shot data"):
            with UnderstatClient() as understat:
                try:
                    understat_id = next(x["understat"]["id"] for x in iter(self.understat_to_fpl_player_data) if x["fpl"]["id"] == int(fpl_player_id))
                except: print(fpl_player_id)
                all_player_shot_data[fpl_player_id] = understat.player(player=str(understat_id)).get_shot_data()
        return all_player_shot_data

    def _compile_understat_player_shot_data(self):

        all_matched_fpl_player_ids = [x['fpl']['id'] for x in self.understat_to_fpl_player_data]
        all_player_shot_data = {}
        for fpl_player_id in all_matched_fpl_player_ids:
            player_shot_data = self.understat_player_shot_data_raw[fpl_player_id]

            season_threshold_start_str = next(x['deadline_time'] for x in iter(self.fpl_api_parser.raw_data['events']))
            def convert_dtstr_to_dt(input_str: str):
                adjusted_str = datetime.fromisoformat(input_str.replace('Z', ''))
                return datetime.strptime(adjusted_str.strftime('%Y-%m-%d'), '%Y-%m-%d')
            relevant_player_shot_data = [x for x in player_shot_data if convert_dtstr_to_dt(x['date']) >= convert_dtstr_to_dt(season_threshold_start_str)]

            df = pd.DataFrame(relevant_player_shot_data)
            grouped = df.groupby(['result', 'match_id','h_team','a_team']).size().reset_index(name='count')
            chance_summary = grouped.pivot_table(index=['match_id','h_team','a_team'], columns='result', values='count', fill_value=0)
            chance_summary.reset_index(inplace=True)
            
            hits_df = df[df["result"] == "Goal"]
            grouped = hits_df.groupby(['shotType', 'match_id','h_team','a_team']).size().reset_index(name='count')
            goal_summary = grouped.pivot_table(index=['match_id','h_team','a_team'], columns='shotType', values='count', fill_value=0)
            goal_summary.reset_index(inplace=True)

            all_player_shot_data[fpl_player_id] = pd.merge(chance_summary, goal_summary, on=['match_id','h_team','a_team'], how='outer').to_dict(orient='records')
        return all_player_shot_data
    
    def _build_understat_player_match_data(self):

        all_matched_fpl_player_ids = [x['fpl']['id'] for x in self.understat_to_fpl_player_data]
        all_player_match_data = {}
        for fpl_player_id in tqdm_notebook(all_matched_fpl_player_ids, desc = "Building understat player match data"):
            with UnderstatClient() as understat:
                understat_id = next(x["understat"]["id"] for x in iter(self.understat_to_fpl_player_data) if x["fpl"]["id"] == int(fpl_player_id))
                all_player_match_data[fpl_player_id] = understat.player(player=str(understat_id)).get_match_data()
        return all_player_match_data

#================================================================================================================================================================
#===================================================================== UNDERSTAT FUNCTIONS ======================================================================
#================================================================================================================================================================


    def fetch_team_xg_against_teams_data(self, fpl_team_id):
        """
        Function returns xG of a specified team against all teams so far. Use fetch team all stats for expanded view
        """
        team_match_data = self.understat_team_match_data[fpl_team_id]
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
        for _, team_data in self.understat_team_data.items():
            temp_data = {'id': team_data['id'], 'title': team_data['title']}
            for key, values in team_data['history'].items():
                if key not in cols_to_omit:
                    temp_data[f"{key}_avg"] = np.mean(values[-look_back:])
                    temp_data[f"{key}_sum"] = np.sum(values[-look_back:])
                else: continue
            compiled_team_data.append(temp_data)
        return compiled_team_data

# #================================================================ BUILD UNDERSTAT TEAM DATA =====================================================================


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
    
