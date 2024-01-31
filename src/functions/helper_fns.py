import math
import requests

def calculate_mean_std_dev(data):
    mean = sum(data) / len(data)
    var = sum((l - mean) ** 2 for l in data) / len(data)
    st_dev = math.sqrt(var)

    return mean, st_dev

class DataParsing:
    def __init__(self, data_parser, api_parser):
        self.data_parser = data_parser
        self.api_parser = api_parser
     
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

    def grab_team_name(self,team_id):
        idt = self.data_parser.team_info.loc[self.data_parser.team_info['id'] == team_id]['name'].values[0]
        return idt
    
    def grab_3ltr_team_name(self,team_id):
        teams = {
                    1: 'ARS',
                    2: 'AVL',
                    3: 'BOU',
                    4: 'BRE',
                    5: 'BHA',
                    6: 'BUR',
                    7: 'CHE',
                    8: 'CRY',
                    9: 'EVE',
                    10: 'FUL',
                    11: 'LIV',
                    12: 'LUT',
                    13: 'MCI',
                    14: 'MUN',
                    15: 'NEW',
                    16: 'NFO',
                    17: 'SHE',
                    18: 'TOT',
                    19: 'WHU',
                    20: 'WOL'
                }
        return teams[team_id]
    
    def player_fixtures(self, direction, team_id, look_size, reference_gw=None):
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
            fixture = [(t[0],self.grab_3ltr_team_name(t[0]),'H', self.team_rank(t[0])) if t[1] == team_id else (t[1], self.grab_3ltr_team_name(t[1]),'A', self.team_rank(t[1])) for t in GWS[key] if team_id in (t[0], t[1])]
            fixtures.append((key,fixture))
        return fixtures
     
    def team_rank(self,team_id):
        try:
            rank = self.api_parser.fdr_data[team_id]
        except Exception as e:
            print(f'Error: {e}')
        return rank