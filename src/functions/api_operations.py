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
        self.raw_element_summary = {}
        self.config_data = self.get_config_data()
        self.latest_gw = self.get_latest_gameweek()
        self.rival_ids = self.fetch_rivals_based_on_pts()
        self.personal_fpl_raw_data = self.fetch_personal_fpl_data()
        self.fixtures = self.fetch_fixtures()
        self.blanks, self.dgws = self.look_for_blanks_and_dgws()
        self.rival_stats = self.tabulate_rival_stats(self.get_beacon_ids())

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
        return active_szn["personal_league_ids"]

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

    def fetch_personal_fpl_data(self):
        active_szn = self.config_data["fpl_id_data"]
        r = self.fetch_data_from_api(f'entry/{active_szn["personal_team_id"]}/event/{self.latest_gw}/picks/')
        if r['active_chip'] and r['active_chip'] == "freehit":
            r = self.fetch_data_from_api(f'entry/{active_szn["personal_team_id"]}/event/{self.latest_gw-1}/picks/')
        return r
    
    def fetch_fixtures(self):
        return self.fetch_data_from_api('fixtures/')
    
    def look_for_blanks_and_dgws(self):
        GWS={}
        req = self.fetch_data_from_api('fixtures/')
        for row in req:
            GW = row['event']
            if GW:
                if GW not in GWS.keys():
                    GWS[GW] = []
                GWS[GW].extend((row['team_a'],row['team_h']))
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
                    print(f"Rate limit exceeded. Retrying after {retry_after} seconds.")
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

# if __name__ == "__main__":
#     parser = FPLApiParser()
    # parser.parse_api()
