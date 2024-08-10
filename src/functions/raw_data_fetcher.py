import sys
import os
sys.path.append(os.path.abspath('..'))
from src.config import config
from src.functions.data_exporter import output_data_to_json, grab_path_relative_to_root
from src.functions.helper_fns import initialize_local_data

import requests
import json
import os
import pandas as pd

from tqdm.notebook import tqdm_notebook
from datetime import datetime, timezone
from dateutil import parser

import asyncio
import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from understat import Understat
from understatapi import UnderstatClient

'''
TIPS:
async used for aynchronous fns which are recommended for http requests
In order to use data WITHIN this same chain that is formed from asynchronous counterparts, it is recommended
to use synchronous contexts to run compile these kinds of data. These cases we use asyncio.run()
This allows for async contexts to be used synchronously, e,g, i can now use raw_data throughout
'''

class FPLFetcher:
    def __init__(self):
        self.base_url = config.BASE_URL
        self.raw_data, self.season_year_span_id = self.process_raw_data()
        self.latest_gw = self.get_latest_gameweek()
        self.player_ids = self.grab_player_ids()
        self.raw_element_summary = {}
        self.config_data = self.get_config_data()
        self.rival_ids = self.fetch_rivals_based_on_pts()
        self.personal_fpl_raw_data = self.fetch_personal_fpl_data()
        self.fixtures = self.fetch_fixtures()
        # self.blanks, self.dgws = self.look_for_blanks_and_dgws()
        self.rival_stats = self.tabulate_rival_stats(self.get_beacon_ids())
        self.full_element_summary = asyncio.run(self.compile_master_element_summary())

    def process_raw_data(self):
        raw_data = self.fetch_data_from_api('bootstrap-static/')
        season_year_span_id = self.get_season_year_span(raw_data)
        raw_data_path = f"cached_data/fpl/{season_year_span_id}"
        raw_data_file_name = f"raw_data_{season_year_span_id}"
        file_path_written = grab_path_relative_to_root(raw_data_path, absolute=True, create_if_nonexistent=True)
        full_path = f'{file_path_written}/{raw_data_file_name}.json'
        output_data_to_json(raw_data, full_path)
        return raw_data, season_year_span_id

    def fetch_data_from_api(self, endpoint):
        url = f'{self.base_url}{endpoint}'
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
        # async with aiohttp.ClientSession() as session:
        #     async with session.get(url) as response:
        #         data = await response.json()
        #         return data
    
    def get_latest_gameweek(self):
        gwdata = self.raw_data['events']
        now = datetime.now(timezone.utc)
        latest_gw = max(
            (int(gw['id']) for gw in gwdata if parser.parse(gw['deadline_time']) <= now),
            default=None
        )
        return latest_gw
    
    def get_season_year_span(self, raw_data):
        datetime_strings = [x['deadline_time'] for x in raw_data['events']]
        years = [datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%SZ').year for dt_str in datetime_strings]
        start_year = years[0]
        end_year = years[-1]
        if start_year == end_year:
            return str(start_year)
        else:
            return f"{start_year}-{end_year}"
    
    def grab_player_ids(self):
        return [x['id'] for x in self.raw_data['elements']]
    
    def get_config_data(self):
        config_data_path = grab_path_relative_to_root("src/config/data.json", relative=True)
        with open(config_data_path, 'r') as file:
            data = json.load(file)
            return data

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
        personal_fpl_name = self.fetch_player_fpl_name(self.get_personal_fpl_id())
        for league_id in self.get_league_ids():
            r = self.fetch_data_from_api('leagues-classic/' + str(league_id) + '/standings/')
            rank_threshold = next((i['rank'] for i in iter(r['standings']['results']) if ['player_name'] == personal_fpl_name), None)
            if rank_threshold:
                rival_ids = []
                for i in r['standings']['results']:
                    if i['rank'] < min(rank_threshold,5):
                        rival_ids.append(i['entry'])
                rival_team_ids.append(rival_ids)
        return rival_team_ids

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

class UnderstatFetcher:

    def __init__(self, fpl_api_parser, fpl_helper_fns, update_and_export_data):
        self.fpl_api_parser = fpl_api_parser
        self.helper_fns = fpl_helper_fns
        self.understat_ops = initialize_local_data(self, [
            {
                "function": self._build_understat_team_data,
                "attribute_name": "understat_team_data",
                "file_name": "team_data",
                "export_path": f"cached_data/understat/{self.fpl_api_parser.season_year_span_id}/team",
             },
            {
                "function": self._match_fpl_to_understat_teams,
                "attribute_name": "understat_to_fpl_team_data",
                "file_name": "understat_to_fpl_team_data",
                "export_path": f"cached_data/understat/{self.fpl_api_parser.season_year_span_id}/team",
             },
            {
                "function": self._build_understat_team_shot_data,
                "attribute_name": "understat_team_shot_data",
                "file_name": "team_shot_data",
                "export_path": f"cached_data/understat/{self.fpl_api_parser.season_year_span_id}/team"
             },
            {
                "function": self._build_understat_team_match_data,
                "attribute_name": "understat_team_match_data",
                "file_name": "team_match_data",
                "export_path": f"cached_data/understat/{self.fpl_api_parser.season_year_span_id}/team"
             },
            {
                "function": self._build_understat_player_data,
                "attribute_name": "understat_player_data",
                "file_name": "player_data",
                "export_path": f"cached_data/understat/{self.fpl_api_parser.season_year_span_id}/players"
             },
            {
                "function": self._match_fpl_to_understat_players,
                "attribute_name": "understat_to_fpl_player_data",
                "file_name": "understat_to_fpl_player_data",
                "export_path": f"cached_data/understat/{self.fpl_api_parser.season_year_span_id}/players",
                "update_bool_override": True,
             },
            {
                "function": self._build_understat_player_shot_data,
                "attribute_name": "understat_player_shot_data_raw",
                "file_name": "player_shot_data",
                "export_path": f"cached_data/understat/{self.fpl_api_parser.season_year_span_id}/players"
             },
            {
                "function": self._build_understat_player_match_data,
                "attribute_name": "understat_player_match_data",
                "file_name": "player_match_data",
                "export_path": f"cached_data/understat/{self.fpl_api_parser.season_year_span_id}/players"
             }
        ], update_and_export_data)

#================================================================================================================================================================
#================================================================ BUILD UNDERSTAT TEAM DATA =====================================================================
#================================================================================================================================================================

    def _build_understat_team_data(self):
            
        async def fetch_team_data():
            async with aiohttp.ClientSession() as session:
                understat = Understat(session)
                teams = await understat.get_teams(
                    league_name='epl', 
                    season='2024'
                )
                return teams
                
        loop = asyncio.get_event_loop()
        fetched_team_data = loop.run_until_complete(fetch_team_data())

        compiled_team_data = {}
        for raw_team_data in tqdm_notebook(fetched_team_data, desc = "Fetching team data"):
            compiled_team_data[raw_team_data["id"]] = raw_team_data.copy()
            temp_data = {}
            for gameweek_data in raw_team_data['history']:
                for primary_param_name, primary_param_val in gameweek_data.items():
                    if isinstance(primary_param_val, dict): # For ppda where values are dicts
                        for sub_name, sub_value in primary_param_val.items():
                            temp_data.setdefault(f"{primary_param_name}_{sub_name}", []).append(sub_value)
                    else:
                        temp_data.setdefault(primary_param_name, []).append(primary_param_val)
            compiled_team_data[raw_team_data["id"]]['history'] = temp_data
        return compiled_team_data

    def _build_understat_team_shot_data(self):
        
        async def fetch_team_shot_data(team_data, season="2024"):
            async with aiohttp.ClientSession() as session:
                understat = Understat(session)
                player = await understat.get_team_stats(
                    team_name = team_data["name"],
                    season = season
                )
                return team_data["id"], player

        async def fetch_all_team_shot_data(all_team_data):
            tasks = [fetch_team_shot_data(team_data) for team_data in all_team_data]
            results = {}
            with tqdm_notebook(total=len(all_team_data), desc = "Fetching team shot data") as pbar:
                for completed_task in asyncio.as_completed(tasks):
                    team_id, result = await completed_task
                    results[team_id] = result
                    pbar.update(1)
            return results
        
        understat_team_identifiers = [{"id": int(x['id']), "name": x['title']} for x in self.understat_team_data.values()]
        loop = asyncio.get_event_loop()
        all_team_match_data = loop.run_until_complete(fetch_all_team_shot_data(understat_team_identifiers))
        return all_team_match_data

    def _build_understat_team_match_data(self):
        
        async def fetch_team_match_data(team_data, season="2024"):
            async with aiohttp.ClientSession() as session:
                understat = Understat(session)
                player = await understat.get_team_results(
                    team_name = team_data["name"],
                    season = season
                )
                return team_data["id"], player

        async def fetch_all_team_match_data(all_team_data):
            tasks = [fetch_team_match_data(team_data) for team_data in all_team_data]
            results = {}
            with tqdm_notebook(total=len(all_team_data), desc = "Fetching team match data") as pbar:
                for completed_task in asyncio.as_completed(tasks):
                    team_id, result = await completed_task
                    results[team_id] = result
                    pbar.update(1)
            return results
        
        understat_team_identifiers = [{"id": int(x['id']), "name": x['title']} for x in self.understat_team_data.values()]
        loop = asyncio.get_event_loop()
        all_team_match_data = loop.run_until_complete(fetch_all_team_match_data(understat_team_identifiers))
        return all_team_match_data

#================================================================================================================================================================
#===================================================================== MATCH FPL TO UNDERSTAT ===================================================================
#================================================================================================================================================================

    def _match_fpl_to_understat_teams(self):
        teams = self.fpl_api_parser.raw_data['teams']
        fpl_data = [{**{param_str: param_val for param_str, param_val in team.items() if param_str in ['id', 'name']}} for team in teams]

        understat_nums_unsorted = [{
            "id": int(x['id']), 
            "name": x['title']
        } 
        for x in self.understat_team_data.values()]
        understat_data = sorted(understat_nums_unsorted, key=lambda x: x["name"])

        return [{
            "fpl": d1, 
            "understat": d2
        } 
        for d1, d2 in zip(fpl_data, understat_data)]
    
    def _match_fpl_to_understat_players(self):

        matched_data = []
        for understat_player_info in self.understat_player_data:
            team_name_list = understat_player_info["team_title"].split(",") #Account for cases where player switched teams in PL
            fpl_team_id_list = [next(x["fpl"]["id"] for x in iter(self.understat_to_fpl_team_data) if x["understat"]["name"] == team_name) for team_name in team_name_list]
            matched_fpl_player_id = self.helper_fns.find_best_match(understat_player_info["player_name"], fpl_team_id_list)
            if matched_fpl_player_id is not None:
                matched_data.append({
                    "fpl": {
                        "id": int(matched_fpl_player_id),
                        "name": self.helper_fns.grab_player_name(int(matched_fpl_player_id)),
                    },
                    "understat": {
                        "id": int(understat_player_info["id"]),
                        "name": understat_player_info["player_name"],
                    }
                })
        return matched_data

#================================================================================================================================================================
#================================================================ BUILD UNDERSTAT PLAYER DATA ===================================================================
#================================================================================================================================================================

    def _build_understat_player_data(self):

        async def fetch_league_players():
            async with aiohttp.ClientSession() as session:
                understat = Understat(session)
                players = await understat.get_league_players(
                    league_name='epl', 
                    season='2023'
                )
                return players
                
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(fetch_league_players())

    # def _build_understat_player_shot_data(self):

    #     @retry(stop=stop_after_attempt(5), wait=wait_fixed(1), retry_error_callback=lambda x: isinstance(x, TimeoutError))
    #     async def fetch_player_shot_data(understat_player_id):
    #         try:
    #             async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
    #                 understat = Understat(session)
    #                 player_shot_data = await understat.get_player_shots(
    #                     player_id=understat_player_id,
    #                 )
    #                 return understat_player_id, player_shot_data
    #         except aiohttp.ClientError as e:
    #             print(f"Error fetching player shot data for player ID {understat_player_id}: {e}")
    #             return understat_player_id, None
        
    #     async def fetch_all_player_shot_data(player_ids):
    #         tasks = [fetch_player_shot_data(player_id) for player_id in player_ids]
    #         results = {}
    #         with tqdm_notebook(total=len(player_ids), desc = "Fetching player shot data") as pbar:
    #             for completed_task in asyncio.as_completed(tasks):
    #                 player_id, result = await completed_task
    #                 results[player_id] = result
    #                 pbar.update(1)
    #         return results

    #     all_matched_understat_player_ids = [x['understat']['id'] for x in self.understat_to_fpl_player_data]
    #     loop = asyncio.get_event_loop()
    #     all_player_shot_data = loop.run_until_complete(fetch_all_player_shot_data(all_matched_understat_player_ids))
    #     return all_player_shot_data
    
    def _build_understat_player_shot_data(self):

        # async def main():
        #     async with aiohttp.ClientSession() as session:
        #         understat = Understat(session)
        #         player = await understat.get_player_shots(
        #             player_id=8562, 
        #         )
        #         return player
        
        # loop = asyncio.get_event_loop()
        # fetched_data = loop.run_until_complete(main())

        all_matched_fpl_player_ids = [x['fpl']['id'] for x in self.understat_to_fpl_player_data]
        all_player_shot_data = {}
        for fpl_player_id in tqdm_notebook(all_matched_fpl_player_ids, desc = "Building understat player shot data"):
            with UnderstatClient() as understat:
                understat_id = next(x["understat"]["id"] for x in iter(self.understat_to_fpl_player_data) if x["fpl"]["id"] == int(fpl_player_id))
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
    
