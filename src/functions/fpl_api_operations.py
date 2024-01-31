from src.config import config
import requests
import json
import os
from datetime import datetime, timezone
from dateutil import parser

class FPLApiParser:
    def __init__(self):
        self.base_url = config.BASE_URL
        self.config_data = self.get_config_data()
        self.raw_data = self.fetch_data_from_api('bootstrap-static/')
        self.rival_ids = self.fetch_rivals_based_on_pts()
        self.latest_gw = self.get_latest_gameweek()
        self.fixtures = self.fetch_fixtures()
        self.personal_fpl_raw_data = self.fetch_personal_fpl_data()
        self.compile_fdr_data()

    def fetch_data_from_api(self, endpoint):
        url = f'{self.base_url}{endpoint}'
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_config_data(self):
        cwd = os.getcwd()
        with open(f'{cwd}/src/config/data.json', 'r') as file:
            data = json.load(file)
            return data
        
    def fetch_fixtures(self):
        return self.fetch_data_from_api(f'{config.BASE_URL}/fixtures/')

    def get_latest_gameweek(self):
        gwdata = self.raw_data['events']
        now = datetime.now(timezone.utc)

        # Find the latest gameweek with a deadline in the past
        latest_gw = max(
            (int(gw['id']) for gw in gwdata if parser.parse(gw['deadline_time']) <= now),
            default=None
        )

        return latest_gw

    def get_league_ids(self):
        active_szn = self.config_data["active_season"]
        return self.config_data["season"][active_szn]["rival_league_ids"]

    def fetch_rivals_based_on_pts(self):
        rival_team_ids = []
        for league_info in self.get_league_ids():
            r = self.fetch_data_from_api('leagues-classic/' + str(league_info["id"]) + '/standings/')
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
        active_szn = self.config_data["active_season"]
        r = self.fetch_data_from_api(f'entry/{self.config_data["season"][active_szn]["personal_team_id"]}/event/{self.latest_gw}/picks/')
        if r['active_chip'] and r['active_chip'] == "freehit":
            r = self.fetch_data_from_api(f'entry/{self.config_data["season"][active_szn]["personal_team_id"]}/event/{self.latest_gw-1}/picks/')
        return r
    
    def compile_fdr_data(self):
#             ---------------> Compile FDRs from team_info---------------------------------------------
        print('\nAssigning ranks to teams...')
        init_id = 1
        fdr_data = {}
        while init_id < len(self.data_parser.total_summary):
            if init_id in list(self.data_parser.total_summary['id_player'].unique()):
                null_team_id = self.grab_player_team_id(init_id)
                elementdat = self.fetch_data_from_api(f'{config.BASE_URL}/element-summary/{init_id}/')
                try:
                    fdr_info = [[([i['team_h'],i['team_a']],i['difficulty']) for i in elementdat["fixtures"]][0]]
                    fdr_simpl = [((set(x[0]) - {null_team_id}).pop(),x[1]) for x in fdr_info]
                    # print(fdr_simpl)
                    for pair in fdr_simpl:
                        if pair[0] not in fdr_data.keys():
                            # print(pair)
                            fdr_data[pair[0]] = pair[1]
                except:
                    pass
            init_id += 10
        init_id = 1
        while len(fdr_data) < 20 and init_id < len(self.data_parser.total_summary):
            null_team_id = self.grab_player_team_id(init_id)
            elementdat = self.fetch_data_from_api(f'{config.BASE_URL}/element-summary/{init_id}/')
            fdr_info = [([i['team_h'],i['team_a']],i['difficulty']) for i in elementdat["fixtures"]][:3]
            fdr_simpl = [((set(x[0]) - {null_team_id}).pop(),x[1]) for x in fdr_info]
            # print(fdr_simpl)
            for pair in fdr_simpl:
                if pair[0] not in fdr_data.keys():
                    # print(pair)
                    fdr_data[pair[0]] = pair[1] 
            init_id += 10
        if len(fdr_data) < 20:
            fdr_data = {
                1:4,2:3,3:2,4:3,5:2,6:4,7:2,8:2,9:3,10:2,11:5,12:5,13:4,14:3,15:1,16:2,17:4,18:1,19:3,20:2}
        self.fdr_data = fdr_data

# if __name__ == "__main__":
#     parser = FPLApiParser()
    # parser.parse_api()
