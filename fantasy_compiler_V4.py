"""
Created on Thu Apr 28 15:09:09 2022
@author: Javaid Baksh
"""
import requests, json
from pprint import pprint
import pandas as pd
from tqdm.notebook import tqdm_notebook
import math
from datetime import datetime, timezone
from dateutil import parser
from colorama import Fore, Back, Style
import ast
import statistics
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import difflib
import unicodedata
from prettytable import PrettyTable
import itertools
#@8vYAJc2@.U   OLD
#tjM.9QL*q*BX    OLD
#kyLp2*4mfeo&    NEW

# TEAM_IDX = 133754

import asyncio
import aiohttp
import nest_asyncio
nest_asyncio.apply()

class FPLDatabase:
    TEAM_IDX = 119615
    RIVALS_INIT = [
                   782655,#Just Quiet
                   467038#GreatestShow
                  ]
    RIVAL_TEAMS_IDS = []
    
    base_url = 'https://fantasy.premierleague.com/api/' # base url for all FPL API endpoints

    GENIUS_IDS = [
        4305040,#Fabio Borges(Clichy's Cleansheets)
#         5977880,#Magnus Carlsen(KFUM Tjuvholmen)
#         15709,#Finn Solie(Finncastle)
        14165,#Tom Stephenson(Badgers9)
        2905,#Mark Mansfield (Schmohawks)
        7632,#Ben Crellin (?????)
        157354,#Matt Corbidge (Yeezy Taught Me)
        3352,#Dan Bennett (Bend it like Bennett)
        839,#Daniel Barfield
        6312#FPL_Harry (Harry Daniels)

        ]
    
    r = requests.get(base_url+'bootstrap-static/').json()    # get data from bootstrap-static endpoint
    # pprint(r, indent=2, depth=1, compact=True) # show the top level fields
    
    players = pd.json_normalize(r['elements'])

    teams = pd.json_normalize(r['teams'])

    positions = pd.json_normalize(r['element_types'])
    
    @staticmethod
    async def fetch(session, url):
        async with session.get(url) as response:
            return await response.json()
    
    @staticmethod
    async def fetch_all(urls):
        async with aiohttp.ClientSession() as session:
            tasks = []
            for url in urls:
                tasks.append(fetch(session, url))
            return await asyncio.gather(*tasks)
    
    @classmethod
#     async def fetch_gameweek_history(self, player_id, session):
#         async with session.get(f'https://fantasy.premierleague.com/api/element-summary/{player_id}/') as resp:
#             player_data = await resp.json()
#             player_history = pd.DataFrame(player_data['history'])
#             return player_history
    async def fetch_gameweek_history(self, player_id, session):
        headers = {'Accept': 'application/json'}
        async with session.get(f'https://fantasy.premierleague.com/api/element-summary/{player_id}/', headers=headers) as resp:
            player_data = await resp.json()
            player_history = pd.DataFrame(player_data['history'])
            return player_history

    print('\n<Expedited Build>: Compiling initial dataframes from FPL API requests...') 
    async def compile_dataframes(self):
        # join team name
        self.players = self.players.merge(
            self.teams[['id', 'name']],
            left_on='team',
            right_on='id',
            suffixes=['_player', None]
        ).drop(['team', 'id'], axis=1)

        # join player positions
        self.players = self.players.merge(
            self.positions[['id', 'singular_name_short']],
            left_on='element_type',
            right_on='id'
        ).drop(['element_type', 'id'], axis=1)
        player_ids = self.players['id_player'].tolist()

        async def fetch_all_gameweek_histories(player_ids):
            async with aiohttp.ClientSession() as session:
                tasks = [self.fetch_gameweek_history(player_id, session) for player_id in player_ids]
                return await asyncio.gather(*tasks)

        # Call the function to get all the points
        points = await fetch_all_gameweek_histories(player_ids)

        self.compile_total_df(points)

    def compile_total_df(self, points):
        self.total_points_df = pd.concat(points)
#         self.total_points_df.reset_index(drop=True, inplace=True)
        # join web_name
        self.points = self.players[['id_player', 'web_name','singular_name_short']].merge(
            self.total_points_df,
            left_on='id_player',
            right_on='element'
        )

        # get top scoring players
        self.partial_summary = self.points.groupby(
            ['id_player', 'web_name']
        ).agg(
            {'total_points':'sum', 'goals_scored':'sum', 'assists':'sum','bonus':'sum'}
        ).reset_index(
        ).sort_values(
            'total_points', ascending=False
        )
        self.points.rename(columns = {'singular_name_short':'position','web_name':'player'}, inplace = True)
        self.partial_summary.rename(columns = {'singular_name_short':'position','web_name':'player'}, inplace = True)
#         total_summary = pd.merge(self.partial_summary,self.players,on=['id_player']).drop(['web_name_y','first_name','second_name'],axis=1)
        overlapping_columns = self.partial_summary.columns.intersection(self.players.columns).tolist()    
        total_summary = pd.merge(self.partial_summary,self.players,on=overlapping_columns)

        async def compile_summary():
            async with aiohttp.ClientSession() as session:
                tasks = [FPLDatabase.fetch_gameweek_history(player_id,session) for player_id in total_summary['id_player']]
                gameweek_histories = await asyncio.gather(*tasks)

                
#             def process_total_points(dfx):
#                 return dfx['total_points'].tolist()


            def process_returnhist(dfx):
                return [2 if (i > 9) else 1 if (i > 3 and i <= 9) else 0 for i in dfx['total_points']]


            def calculate_mean_std_dev(data):
                mean = sum(data) / len(data)
                var = sum((l - mean) ** 2 for l in data) / len(data)
                st_dev = math.sqrt(var)

                return mean, st_dev


            def process_fulltime_fullhour(dfx):
                fulltime = [e for e in dfx['minutes'][-6:] if e == 90]
                fullhour = [e for e in dfx['minutes'][-6:] if e >= 60]

                return len(fulltime), len(fullhour), len(dfx['minutes'][-6:])
                
            
            def calculate_last_vals(lookback,dfx):
                last_val = sum(dfx[-lookback:]) / len(dfx[-lookback:])
                return last_val
            print('\n<Expedited Build>: Scanning all players to compile master dataframe...') 
            # Replace the original for loop with a new one
            for num, idx in enumerate(tqdm_notebook(total_summary['id_player'])):
                try:
                    dfx = gameweek_histories[num]
                    existing_cols = dfx.columns.tolist()
                    for param in existing_cols[1:]:
                        p1, p2 = param, param
                        if param == 'total_points':
                            p1 = 'history'
                        elif param == 'value':
                            p1 = 'changing_value'
                        ref_list = dfx[p2].tolist()
                        converted_ref_list = []
                        for elem in ref_list:
                            try:
                                converted_ref_list.append(float(elem))
                            except:
                                converted_ref_list.append(elem)
                        total_summary.at[[num],p1] = pd.Series([converted_ref_list],index = [num])
#                     # Process total_points
#                     total_points = process_total_points(dfx)
                    # Process returnhist
                    returnhist = process_returnhist(dfx)

                    # Calculate means and standard deviations
                    mean_og, stdev_og = calculate_mean_std_dev(dfx['total_points'])
                    mean_x, stdev_x = calculate_mean_std_dev(returnhist)
                    last6_mean_x, last3_mean_x, last2_mean_x = calculate_last_vals(6,returnhist), calculate_last_vals(3,returnhist), calculate_last_vals(2,returnhist)

                    # Process fulltime and fullhour
                    fulltime_count, fullhour_count, total_minutes = process_fulltime_fullhour(dfx)
                    # Update total_summary DataFrame with calculated values
#                     total_summary.at[num, 'history'] = str(total_points)
                    total_summary.at[num,'value'] = self.points.loc[self.points['id_player'] == idx]['value'].iloc[-1] / 10
                    total_summary.at[num, 'fulltime'] = f"{fulltime_count}/{total_minutes}"
                    total_summary.at[num, 'fullhour'] = f"{fullhour_count}/{total_minutes}"
                    total_summary.at[[num], 'returnhist'] = pd.Series([returnhist],index = [num])
                    total_summary.at[num, 'mean_og'] = mean_og
                    total_summary.at[num, 'stdev_og'] = stdev_og
                    total_summary.at[num, 'mean_x'] = mean_x
                    total_summary.at[num, 'stdev_x'] = stdev_x
                    total_summary.loc[num,'last6_mean_x'] = last6_mean_x
                    total_summary.loc[num,'last3_mean_x'] = last3_mean_x
                    total_summary.loc[num,'last2_mean_x'] = last2_mean_x

                except Exception as e:
                    print(f'{num} : {e}')
                    continue
        asyncio.run(compile_summary())
        self.total_summary = total_summary.copy()
        self.total_summary.rename(columns = {'singular_name_short':'position'}, inplace = True)
        if not self.total_summary.empty:
            self.total_summary.to_csv('total_summary.csv', index=False)
            print('Exported total_summary!')
        # print(self.total_summary.columns.to_list())
        
    def __init__(self):
        self.compile_latest_gw()
        self.compile_team_info()
        self.compile_rivals()
        asyncio.run(self.compile_dataframes())
        
    def compile_latest_gw(self):
        gwdata = self.r['events']
        self.SZN_START_TIME = [x['deadline_time'] for x in gwdata][0]
        for gw in gwdata:
            gameweek = gw['id']
            date = gw['deadline_time']
            date = parser.parse(date)
            if date <= datetime.now(timezone.utc):
                self.LATEST_GW = int(gameweek)

    def compile_team_info(self):
            teamdata = self.r['teams']
            team_info = pd.DataFrame()
            list_of_dicts = []
            for data in teamdata:
                list_of_dicts.append(data)
            self.team_info = pd.DataFrame.from_records(list_of_dicts)
        
    def compile_rivals(self):
        for RIVAL in self.RIVALS_INIT:
            base_url = self.base_url + 'leagues-classic/' + str(RIVAL) + '/standings/'
            r = requests.get(base_url).json()
            RANK_THRESH = 99
            for i in r['standings']['results']:
                if 'Javaid' in i['player_name']:
                    RANK_THRESH = i['rank']
            RIVAL_IDS = []
            for i in r['standings']['results']:
                if i['rank'] < min(RANK_THRESH,5):
                    RIVAL_IDS.append(i['entry'])
            self.RIVAL_TEAMS_IDS.append(RIVAL_IDS)

# Instantiate an object of the FPLDatabase class
FPLDatabase = FPLDatabase()

class GrabFunctions:
    @classmethod
    def grab_player_name(self,idx):
        name = FPLDatabase.points.loc[FPLDatabase.points['id_player'] == idx]['player']
        return name.values[-1]

    @classmethod
    def grab_player_value(self,idx):
        name = FPLDatabase.points.loc[FPLDatabase.points['id_player'] == idx]['value'] / 10
        return name.values[-1]

    @classmethod
    def grab_player_pos(self,idx):
        name = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == idx]['position']
        return name.values[-1]

    @classmethod
    def grab_player_team(self,idx):
        name = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == idx]['name']
        return name.values[-1]

    @classmethod
    def grab_player_team_id(self,idx):
        team_name = self.grab_player_team(idx)
        name = FPLDatabase.team_info.loc[FPLDatabase.team_info['name'] == team_name]['id']
        return name.values[-1]

    @classmethod
    def grab_player_hist(self,idx):
        name = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == idx]['history']
        return name.values[-1]

    @classmethod
    def grab_player_returns(self,idx):
        name = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == idx]['returnhist']
        return name.values[-1]

    @classmethod
    def grab_player_minutes(self,idx):
        name = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == idx]['minutes']
        return name.values[-1]

    @classmethod
    def grab_player_bps(self,idx):
        name = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == idx]['bps']
        return name.values[-1]

    @classmethod
    def grab_player_full90s(self,idx):
        name = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == idx]['fulltime']
        return name.values[-1]

    @classmethod
    def grab_player_full60s(self,idx):
        name = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == idx]['fullhour']
        return name.values[-1]

    @classmethod
    def grab_team_id(self,team_name):
        idt = FPLDatabase.team_info.loc[FPLDatabase.team_info['name'] == team_name]['id'].values[0]
        return idt

    @classmethod
    def grab_team_name(self,team_id):
        idt = FPLDatabase.team_info.loc[FPLDatabase.team_info['id'] == team_id]['name'].values[0]
        return idt
    
    @classmethod
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
    
    @classmethod
    def player_fixtures(self, direction, team_id, look_size, reference_gw=None):
        if not reference_gw:
            reference_gw = FPLDatabase.LATEST_GW
        GWS={}
        baseurl = 'https://fantasy.premierleague.com/api/fixtures/'
        req = requests.get(baseurl).json()
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
            fixture = [(t[0],GrabFunctions.grab_3ltr_team_name(t[0]),'H',GrabFunctions.team_rank(t[0])) if t[1] == team_id else (t[1],GrabFunctions.grab_3ltr_team_name(t[1]),'A',GrabFunctions.team_rank(t[1])) for t in GWS[key] if team_id in (t[0], t[1])]
            fixtures.append((key,fixture))
        return fixtures
    
    @classmethod
    def init(self):
        def compile_fdr_data():
    #             ---------------> Compile FDRs from team_info---------------------------------------------
            print('\nAssigning ranks to teams...')
            init_id = 1
            fdr_data = {}
            while init_id < len(FPLDatabase.total_summary):
                if init_id in list(FPLDatabase.total_summary['id_player'].unique()):
                    null_team_id = self.grab_player_team_id(init_id)
                    base_url_x = 'https://fantasy.premierleague.com/api/element-summary/'+str(init_id)+'/'
                    elementdat = requests.get(base_url_x).json()
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
            while len(fdr_data) < 20 and init_id < len(FPLDatabase.total_summary):
                null_team_id = self.grab_player_team_id(init_id)
                base_url_x = 'https://fantasy.premierleague.com/api/element-summary/'+str(init_id)+'/'
                elementdat = requests.get(base_url_x).json()
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
        compile_fdr_data()
        
    @classmethod
    def team_rank(self,team_id):
        try:
            rank = self.fdr_data[team_id]
        except Exception as e:
            print(f'Error: {e}')
        return rank

GrabFunctions.init()


class FixtureMath:

    def rem_fixtures_difficulty(idx: int):
        base_url = 'https://fantasy.premierleague.com/api/'

        # get data from 'element-summary/{PID}/' endpoint for PID=4
        r = requests.get(base_url + 'element-summary/' + str(idx) + '/').json()
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
    
    def look_for_blanks_and_dgws():
        GWS={}
        baseurl = 'https://fantasy.premierleague.com/api/fixtures/'
        req = requests.get(baseurl).json()
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
    

class BestOfTheBest:
    
    def top_performers_by_mean(toplist = None,personal = None):
        '''
        Grab return history of provided list of IDs, and look back in various GW windows of either previous 6, 3 or 2 GWs.
        Count returns (0 for no return (0-3 pts), 1 for single digit return, 2 for double digit return)
        
        '''
        count_dict={}
        #First 3 statements are at start of FPL where only few seasons available
        if FPLDatabase.LATEST_GW == 1:
            LOOK_BACK_LIST = [1]
        elif FPLDatabase.LATEST_GW == 2:
            LOOK_BACK_LIST = [2]
        elif FPLDatabase.LATEST_GW < 6:
            LOOK_BACK_LIST = [3,2]
        else:
            LOOK_BACK_LIST = [6,3,2]
        base_url = 'https://fantasy.premierleague.com/api/'
        returns_nontop6={}
        for idx in toplist:
            recent_returns_bank = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == idx]['returnhist'].iloc[0]
            for look_back in LOOK_BACK_LIST:
                if look_back == 6:
                    recent_returns = recent_returns_bank[-look_back:]
                    count = recent_returns.count(1) + recent_returns.count(2)
                    thresh = 4
                    if count == 3:
                        if recent_returns.count(2) >= 1:
                            thresh = 3
                elif look_back == 3:
                    recent_returns = recent_returns_bank[-look_back:]
                    count = recent_returns.count(1) + recent_returns.count(2)
                    thresh = 3
                    if count == 2:    
                        recent_returns2 = recent_returns_bank[-4:]
                        count2 = recent_returns2.count(1) + recent_returns2.count(2)
                        if recent_returns.count(2) >= 1:
                            thresh = 2
                        elif count2 == 3:
                            thresh = 2
                elif look_back == 2:
                    recent_returns = recent_returns_bank[-look_back:]
                    count = recent_returns.count(1) + recent_returns.count(2)
                    thresh = 2
                elif look_back == 1:
                    recent_returns = recent_returns_bank[-look_back:]
                    count = recent_returns.count(1) + recent_returns.count(2)
                    thresh = 1
                else:
                    continue
                if count >= thresh:
                    if str(idx) in count_dict.keys():
                        count_dict[str(idx)] += 1
                    else:
                        count_dict[str(idx)] = 1
                elif count < thresh and personal is not None:
                    if str(idx) not in count_dict.keys():
                        count_dict[str(idx)] = 0
            recent_returns = recent_returns_bank[-10:]
            count = recent_returns.count(1) + recent_returns.count(2)
            if count >= 2:
                r = requests.get(base_url + 'element-summary/' + str(idx) + '/').json()
                teams = []
                for dictr in r['history'][-10:]:
                    opponent_team_id = dictr['opponent_team']
                    teamrank = GrabFunctions.team_rank(opponent_team_id)
                    teams.append(teamrank)
                calibrated_returns=[]
                for ind,num in enumerate(recent_returns):
                    if teams[ind] < 4 or (teams[ind] >= 4 and num > 0):
                        calibrated_returns.append(num)
                returns_nontop6[str(idx)] = calibrated_returns
                count = calibrated_returns.count(1) + calibrated_returns.count(2)
                if count/len(calibrated_returns) > 0.5:
                    if (personal is None and str(idx) not in count_dict.keys()) or (personal is not None and count_dict[str(idx)] == 0):
                        count_dict[str(idx)] = '-!-'

        df = pd.DataFrame({'id':count_dict.keys(),'count':count_dict.values()})
        df['id'] = df['id'].astype(int)
        df['count'] = df['count'].astype(str)
        df['player']='NA';df['value']='NA';df['position']='NA';df['team']='NA';df['starting_risk']='NA';df['form_top6adjusted']='NA';df['history']='NA';df['minutes']='NA';df['fulltime']='NA';df['fullhour']='NA';df['bps']='NA'
        # df = df.sort_values(by=['count'],ascending=False)
        df = df.reset_index(drop=True)
        for num,ids in enumerate( tqdm_notebook(df['id']) ):
            recent_returns = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == int(ids)]['returnhist'].iloc[0][-6:]
            count = recent_returns.count(1) + recent_returns.count(2)
            df.loc[num,'player'] = GrabFunctions.grab_player_name(int(ids))
            df.loc[num,'value'] = GrabFunctions.grab_player_value(int(ids))
            df.loc[num,'position'] = GrabFunctions.grab_player_pos(int(ids))
            df.loc[num,'team'] = GrabFunctions.grab_player_team(int(ids))
            df.loc[[num],'history'] = pd.Series([GrabFunctions.grab_player_hist(int(ids))],index=[num])
            df.loc[[num],'minutes'] = pd.Series([GrabFunctions.grab_player_minutes(int(ids))],index=[num])
            df.loc[[num],'bps'] = pd.Series([GrabFunctions.grab_player_bps(int(ids))],index=[num])
            df.loc[num,'fulltime'] = GrabFunctions.grab_player_full90s(int(ids))
            df.loc[num,'fullhour'] = GrabFunctions.grab_player_full60s(int(ids))
            if str(ids) in returns_nontop6.keys():
                df.loc[[num],'form_top6adjusted'] = pd.Series([returns_nontop6[str(ids)][-6:]],index=[num])
            if count >= 4:
                df.loc[num,'count'] = str(df['count'].iloc[num]) +  '*'
                if count >= 5:
                    df.loc[num,'count'] = str(df['count'].iloc[num]) +  '*'
        df = df.fillna(np.nan)

        return df
    
    def best_fpl_upgrades(value,fpl_df,personal=None):
        if personal is None:
#             df = FPLDatabase.total_summary[['id_player', 'player','value','name','position','history','last6_mean_x','last3_mean_x','minutes','bps']].sort_values(by=['last6_mean_x'],ascending=False).loc[FPLDatabase.total_summary['value']<=value]
            df = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['value']<=value]
            # print(df['player'])
            # print(fpl_df['player'])
            df = df[~df['player'].isin(fpl_df['player'].tolist())]
        else:
            df = fpl_df
        df2 = BestOfTheBest.top_performers_by_mean(df['id_player'].tolist(),personal)
        df2['fixture_class'] = 'NA';df2['fixtures_diff'] = 'NA';df2['consistency'] = 'NA'
        for num,id2 in enumerate( tqdm_notebook(df2['id']) ):
            # print(id2)
            classifier,fixtures = FixtureMath.rem_fixtures_difficulty(id2)
            # print(classifier,fixtures)
            df2.loc[num,'fixture_class'] = classifier
            df2.loc[[num],'fixtures_diff'] = pd.Series([fixtures],index=[num])
            returns = GrabFunctions.grab_player_returns(id2)
            returns = returns[-6:]
            df2.loc[num,'consistency'] = str(returns.count(1) + returns.count(2)) + "/" + str(len(returns))
#         df2=df2[['id','player','value','position','team','consistency','count','fixture_class','fixtures_diff','form_top6adjusted','history','minutes','fulltime','fullhour','bps']]
        # print(df2)
        return df2
    
    def versus(teamlist,df):
        relevant_df = df.loc[df['id'].isin(teamlist)]
        df1a=relevant_df.loc[(relevant_df['last6_mean_x'] > 0.66) & (relevant_df['last3_mean_x'] > 0)]
        df1b=relevant_df.loc[(relevant_df['last6_mean_x'] > 0.33) & (relevant_df['last3_mean_x'] > 0.33)]
        df1 = pd.concat([df1a,df1b],ignore_index=True)
        df1 = df1.drop_duplicates(subset=['id'])

        if FPLDatabase.LATEST_GW >= 6:
            inddrop = []
            for ind,form in enumerate(df1['form_top6adjusted']):
                if (form.count(1) + form.count(2)) / len(form) < 0.5:
                    inddrop.append(ind)
            df1 = df1.drop(inddrop)        


        # print('--------------------------------------------------------------------------')
        # print(df1)
        if len(df1) <= 1:
            filter1 = df1['id'].values.tolist()
            return filter1
        else:
            countthresh = max(df1['count'].unique())
            df2=df1.loc[(df1['count'] == countthresh)]
            # print(df2)
            if len(df2) <= 1:
                filter2 = df2['id'].values.tolist()
                return filter2
            else:
                valuelow = min(df2['value'].unique())
                df3=df2.loc[(df1['value'] <= (valuelow + 0.5))]
                # print(df3)
                filter3 = df3['id'].values.tolist()
                return filter3


class MyTeam:
    @classmethod
    def init(self):
        def compile_fpl_team():
            url = FPLDatabase.base_url + 'entry/' + str(FPLDatabase.TEAM_IDX) + '/event/' + str(FPLDatabase.LATEST_GW) + '/picks/'
            r = requests.get(url).json()
            MyTeam.bank_value = r['entry_history']['bank']/10
            if r['active_chip'] and r['active_chip'] == "freehit":
                url = FPLDatabase.base_url + 'entry/' + str(FPLDatabase.TEAM_IDX) + '/event/' + str(FPLDatabase.LATEST_GW - 1) + '/picks/'
                r = requests.get(url).json()
            r = r['picks']
            id_list = []
            for elem in r:
                id_list.append(elem['element'])

            df=pd.DataFrame({})   
            for ids in id_list:
                df2 = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == ids]
                df = pd.concat([df,df2],ignore_index=True)
            print(f"Squad value: ${sum(df['value'])}")
            self.df_out = df
            self.df_top = BestOfTheBest.top_performers_by_mean(df['id_player'].tolist())
            self.df_sum = df[['id_player', 'player','value','name','position','history','last6_mean_x','last3_mean_x','last2_mean_x','minutes','fulltime','fullhour','bps']].sort_values(by=['last6_mean_x'],ascending=False)

        def compile_fpl_analyses():
            df = BestOfTheBest.best_fpl_upgrades(99,self.df_sum,True)
            df = pd.concat([df.sort_values(by=['id'],ascending=False).reset_index(drop=True), 
                                     self.df_sum[['id_player','last6_mean_x','last3_mean_x','last2_mean_x']
                                            ].sort_values(by=['id_player'],ascending=False).reset_index(drop=True)], axis=1
                                    ).drop(['id_player'], axis=1)
            df = df[['id','player','value','position','team','last6_mean_x','last3_mean_x','last2_mean_x','consistency','count','fixture_class','fixtures_diff','form_top6adjusted','history','minutes','fulltime','fullhour','bps']]
            self.df_fpl = df
        
        compile_fpl_team()
        compile_fpl_analyses()
MyTeam.init()


class RestOfTheRoster:
    @classmethod
    def init(self):
        
        def compile_potential_analyses():
            df = BestOfTheBest.best_fpl_upgrades(99,MyTeam.df_sum)
            
            id_list = []
            for idf in df['id']:
                id_list.append(idf)
            df_temp=pd.DataFrame({})   
            for ids in id_list:
                df2 = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == ids]
                df_temp = pd.concat([df_temp,df2],ignore_index=True)
            df2 = df_temp[['id_player', 'player','value','name','position','history','last6_mean_x','last3_mean_x','last2_mean_x','minutes','fulltime','fullhour','bps']].sort_values(by=['last6_mean_x'],ascending=False)
            
            df = pd.concat([df.sort_values(by=['id'],ascending=False).reset_index(drop=True), 
                                     df2[['id_player','last6_mean_x','last3_mean_x','last2_mean_x']
                                            ].sort_values(by=['id_player'],ascending=False).reset_index(drop=True)], axis=1
                                    ).drop(['id_player'], axis=1)
            df = df[['id','player','value','position','team','last6_mean_x','last3_mean_x','last2_mean_x','consistency','count','fixture_class','fixtures_diff','form_top6adjusted','history','minutes','fulltime','fullhour','bps']]
            
            self.df_fpl_potentials = df.sort_values(by=['last6_mean_x'])

        def condense_potentials():
            df = self.df_fpl_potentials.reset_index(drop=True)

            teams = df.team.unique()
            df_by_team = {}
            for team in teams:
                ids = df['id'].loc[(df['team'] == team)].tolist()
                df_by_team[team] = ids
            positions = df.position.unique()
            df_by_pos = {}
            for position in positions:
                ids = df['id'].loc[(df['position'] == position)].tolist()
                df_by_pos[position] = ids
            indices_to_drop = []

            ###MINIMIZE to ONE-TWO positions per club
            grouped_group = {}
            for pos_key in df_by_pos:
                pos_ids = df_by_pos[pos_key]
                grouped_vals={}
                for ind_id in pos_ids:
                    for k,v in df_by_team.items():
                        if ind_id in v:
                            if k not in grouped_vals:
                                grouped_vals[k] = [ind_id]
                            else:
                                grouped_vals[k].append(ind_id)
                grouped_group[pos_key] = grouped_vals
            #################################################

            for ind,row in df.iterrows():
                cond1 = (row['count'] == '-!-' and row['fixture_class'] == '-X-')
                if FPLDatabase.LATEST_GW >= 6:
                    cond2 = (row['form_top6adjusted'].count(2) == 0 and row['form_top6adjusted'].count(1)/len(row['form_top6adjusted']) < 0.5)
                else:
                    cond2 = False
                if any([cond1,cond2]):
                    indices_to_drop.append(ind)
                locate_team_group = grouped_group[row['position']][row['team']]
                # print(f'\n{locate_team_group}')
                # if len(locate_team_group) > 1:
                ones_above_all = BestOfTheBest.versus(locate_team_group,df)
                current_id = row['id']
                # print(f'{current_id}: {ones_above_all}')
                if current_id not in ones_above_all:
                    indices_to_drop.append(ind)
            #Remove duplicates
            indices_to_drop = list(dict.fromkeys(indices_to_drop))
            df = df.drop(indices_to_drop)
            
            self.df_prime_potentials = df
            
        compile_potential_analyses()
        condense_potentials()
RestOfTheRoster.init()



class Rivalry:
        
    def compile_rivals_team(TEAM_LIST):
        RIVAL_IDS_DICT = {}
        for ID in TEAM_LIST:
            url = FPLDatabase.base_url + 'entry/' + str(ID) + '/'
            r = requests.get(url).json()
            first_name = r['player_first_name']
            last_name = r['player_last_name']
            RIVAL_IDS_DICT[ID] = {'name': str(first_name)+ " " + str(last_name),
                                  'points': r['summary_overall_points'],
                                  'rank': r['summary_overall_rank']
                                  }
        for IDR in RIVAL_IDS_DICT.keys():
            url = 'https://fantasy.premierleague.com/api/entry/' + str(IDR) + '/event/' + str(FPLDatabase.LATEST_GW) + '/picks/'
            r = requests.get(url).json()
            RIVAL_IDS_DICT[IDR]['team'] = [i['element'] for i in r['picks']]
        return RIVAL_IDS_DICT
    
    @classmethod
    def rivalry(self,TEAM_LIST):
        TEAMS_DICT = self.compile_rivals_team(TEAM_LIST)
        list_of_full15s = []
        for ID in TEAMS_DICT.keys():
            list_of_full15s.append(TEAMS_DICT[ID]['team'])
        similar_ids = list(set.intersection(*map(set,list_of_full15s)))
        all_ids = list(set.union(*map(set,list_of_full15s)))
        unique_ids = list(set(all_ids).difference(similar_ids))
        id_count = {}
        for ids in list_of_full15s:
            for ide in ids:
                if ide not in id_count.keys():
                    id_count[ide] = 1
                else:
                    id_count[ide] += 1
        return unique_ids,similar_ids,id_count
        # for idx in similar_ids:
        #     print(grab_player_name(idx))
        
    @classmethod
    def genius_summary(self):
        def genius_changes():
            file = open("genius_team_history.txt", "r")
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
            # print(change_dict)
            for idx in change_dict:
                name = change_dict[idx]['name']
                predifs = change_dict[idx]['out']
                postdifs = change_dict[idx]['in']
                changes = {}
                for preid in predifs:
                    pos = GrabFunctions.grab_player_pos(preid)
                    if pos not in changes.keys():
                        changes[pos] = {}
                    if '0' not in changes[pos].keys():
                        changes[pos]['0'] = []
                    changes[pos]['0'].append(preid)
                for postid in postdifs:
                    pos = GrabFunctions.grab_player_pos(postid)
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
                            b4 = GrabFunctions.grab_player_name(x)
                            b5 = GrabFunctions.grab_player_name(b[i])
                            print(f'{b4} ({pos}) -> {b5} ({pos})')
                    # print(f'\n{name} has made changes')
            if chng == 0 :
                print('Managers have made no changes')
            return
    
        def genius_movements(ranged=None):
            if ranged and ranged != 'full':
                print('Entry must be empty or \"full\"!')
                return
            file = open("genius_team_history.txt", "r")
            contents = file.read()
            dictionary = ast.literal_eval(contents)
            recorded_gws = list(dictionary.keys())
            change_dict = {}
            if not ranged:
                gwrange = range(len(recorded_gws)-1,len(recorded_gws))
            elif ranged == 'full':
                gwrange = range(1,len(recorded_gws))
            # print(gwrange)
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
                    # print(change_dict)
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
            # outdict = dict(outlist)
            inlist = sorted(tally_dict['IN'].items(), key=lambda x:x[1], reverse=True)
            # indict = dict(inlist)
            print('\n---------- OUT -----------\n')
            for a,b in outlist:
                print(f'{GrabFunctions.grab_player_name(a)} -- {b}/{entries}')
            print('\n---------- IN -----------\n')
            for c,d in inlist:
                print(f'{GrabFunctions.grab_player_name(c)} -- {d}/{entries}')
            return
    
        def genius_matches():
            fplids = MyTeam.df_fpl['id'].tolist()
            fplcounter = {}
            for fplid in fplids:
                fplcounter[fplid] = 0
            file = open("genius_team_history.txt", "r")
            contents = file.read()
            dictionary = ast.literal_eval(contents)
            recorded_gws = list(dictionary.keys())
            gw_identifier = len(recorded_gws)-1
            # print(gwrange)
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
                print(f'{GrabFunctions.grab_player_name(key)} -- {tier}{value}\033[0m / {entries}')
            return
    
        def genius_numbers():
            ID_COUNT = self.rivalry(FPLDatabase.GENIUS_IDS)[-1]
            ID_DICT = {}
            for i in ID_COUNT:
                pos = GrabFunctions.grab_player_pos(i)
                if pos not in ID_DICT.keys():
                    ID_DICT[pos] = []
                value = ID_COUNT[i]
                ID_DICT[pos].append((i,value))
            outlist = sorted(ID_DICT.items(), key=lambda x:x[1], reverse=True)
            self.genius_eff_own_dict = {}
            for line in outlist:
                print(f'\n-------------{line[0]}------------')
                for tup in line[1]:
                    self.genius_eff_own_dict[tup[0]] = tup[1]
                    name = GrabFunctions.grab_player_name(tup[0])
                    print(f'{name}: {tup[1]}')
            return
        operations = [
            lambda: genius_changes(),
            lambda: genius_movements(),
            lambda: genius_matches(),
            lambda: genius_numbers(),
        ]
        for operation in operations:
            try:
                operation()
            except Exception as e:
                print(f"Error encountered in 'Rivalry' operation ({operation}): {e}")
                pass
    
class PrintStatements: 
    
#     @classmethod
#     def action_summary(self):
#         def action_protocol():
#             url = FPLDatabase.base_url + 'entry/' + str(FPLDatabase.TEAM_IDX) + '/event/' + str(FPLDatabase.LATEST_GW) + '/picks/'
#             r = requests.get(url).json()
#             MyTeam.bank_value = r['entry_history']['bank']/10
#             # team_value = r['entry_history']['value']/10
#             fpldf = MyTeam.df_fpl
#             potentialdf = RestOfTheRoster.df_prime_potentials
#             fpl_bank = {'immediate':[],'recommended':[],'plan ahead':[]}
#             for i in fpldf.iterrows():
#                 fpl_player_id = i[1][0]
#                 fpl_player_name = i[1][1]
#                 fpl_player_value = i[1][2]
#                 fpl_player_pos = i[1][3]
#                 fpl_player_form = i[1]['count']
#                 fpl_player_fixtures = i[1]['fixture_class']
#                 form6_criteria = i[1]['last6_mean_x']
#                 form3_criteria = i[1]['last3_mean_x']
#                 last6mean = i[1][5]
#                 last2mean = i[1][7]
#                 if last6mean == 0 and last3mean == 0 and last2mean == 0:
#                     fpl_bank['immediate'].append((fpl_player_id,fpl_player_name,fpl_player_value,fpl_player_pos,fpl_player_form,fpl_player_fixtures,form3_criteria,form6_criteria))
#                 elif last3mean == 0 and last2mean == 0:
#                     fpl_bank['recommended'].append((fpl_player_id,fpl_player_name,fpl_player_value,fpl_player_pos,fpl_player_form,fpl_player_fixtures,form3_criteria,form6_criteria))
#                 elif fpl_player_fixtures == '-X-':
#                     fpl_bank['plan ahead'].append((fpl_player_id,fpl_player_name,fpl_player_value,fpl_player_pos,fpl_player_form,fpl_player_fixtures,form3_criteria,form6_criteria))

#             fpl_bank['immediate'].sort(key=lambda i:i[3],reverse=True)
#             fpl_bank['recommended'].sort(key=lambda i:i[3],reverse=True)
#             fpl_bank['plan ahead'].sort(key=lambda i:i[3],reverse=True)
#             potentialdf = potentialdf.sort_values(by=['last6_mean_x'],ascending=False)
#             # if len(fpl_bank['immediate']) != 0:
#             prev = None
#             print(f'\n#####################FOR GAMEWEEK {FPLDatabase.LATEST_GW + 1}###################')
#             print('\033[46m x \033[0m Platinum Pick')
#             print('\033[45m x \033[0m Gold Pick')
#             print('\033[47m x \033[0m Potent Pick')
#             print('\033[42m x \033[0m Potent + Rival Pick')
#             print('\033[33m\033[42m x \033[0m Rival Pick 1')
#             print('\033[34m\033[42m x \033[0m Rival Pick 2')
#             # geniuspicks = rivalry(GENIUS_IDS)[1]
#             # potentpicks = rivalry(GENIUS_IDS)[0]
#             genius_tabulator = Rivalry.rivalry(FPLDatabase.GENIUS_IDS)[-1]
#             rivals_tabulator_1 = Rivalry.rivalry(FPLDatabase.RIVAL_TEAMS_IDS[0])[-1]
#             rivals_tabulator_2 = Rivalry.rivalry(FPLDatabase.RIVAL_TEAMS_IDS[1])[-1]
#             for key in fpl_bank.keys():
#                 print(f'\n#####################{key.upper()}###################')
#                 for info in fpl_bank[key]:
#                     # print(info)
#                     name = info[1]
#                     value_criteria = info[2]  
#                     position_criteria = info[3]
#                     form6_criteria = info[6]
#                     form3_criteria = info[7]
#                     if position_criteria != prev or not prev:
#                         print(f'\n\033[41m[{position_criteria}]\033[0m--------------------------------------')
#                     print(f'\nReplace {name} ($ {value_criteria}m) with one of the following:')
#                     prev = position_criteria
#                     count = 0
#                     for i in potentialdf.iterrows():
#                         potential_player_id = i[1][0]
#                         potential_player_name = i[1][1]
#                         potential_player_value = i[1][2]
#                         potential_player_pos = i[1][3]
#                         potential_player_form = i[1]['count']
#                         potential_player_fixtures = i[1]['fixture_class']
#                         potential_player_fixtures_diff = i[1]['fixtures_diff']
#                         potential_player_adj_hist = i[1]['form_top6adjusted']
#                         potential_player_form6 = i[1]['last6_mean_x']
#                         potential_player_form3 = i[1]['last3_mean_x']
#                         if FPLDatabase.LATEST_GW >= 6:
#                             ratio = (potential_player_adj_hist.count(1) + potential_player_adj_hist.count(2)) / len(potential_player_adj_hist)
#                         else:
#                             ratio = 1
#                         if potential_player_pos == 'GKP' and potential_player_form == '-!-' and ratio < 0.625:
#                             continue
#                         if potential_player_fixtures == '-X-' and GrabFunctions.team_rank(GrabFunctions.grab_team_id(i[1][4])) < 4 and len(potential_player_fixtures_diff) > 1:
#                             continue
#                         if '+' in potential_player_fixtures:
#                             descrip = 'Great'
#                         elif '++' in potential_player_fixtures:
#                             descrip = 'Prime'
#                         else:
#                             descrip = 'Decent'
#                         tier = ''
#                         if potential_player_id in rivals_tabulator_1.keys():
#                             if rivals_tabulator_1[potential_player_id] >= len(FPLDatabase.RIVAL_TEAMS_IDS[0]) * 0.25:
#                                 tier = '\033[33m\033[42m'
#                         elif potential_player_id in rivals_tabulator_2.keys():
#                             if rivals_tabulator_2[potential_player_id] >= len(FPLDatabase.RIVAL_TEAMS_IDS[1]) * 0.25:
#                                 tier = '\033[34m\033[42m'
#                         if potential_player_id in genius_tabulator.keys():
#                             if genius_tabulator[potential_player_id] >= len(FPLDatabase.GENIUS_IDS) - 1:
#                                 tier = '\033[46m'
#                             elif genius_tabulator[potential_player_id] >= len(FPLDatabase.GENIUS_IDS) / 2:
#                                 tier = '\033[45m'
#                             else:
#                                 tier = '\033[47m'
#                                 if potential_player_id in rivals_tabulator_1.keys():
#                                     if rivals_tabulator_1[potential_player_id] >= len(FPLDatabase.RIVAL_TEAMS_IDS[0]) * 0.25:
#                                         tier = '\033[42m'
#                                 elif potential_player_id in rivals_tabulator_2.keys():
#                                     if rivals_tabulator_2[potential_player_id] >= len(FPLDatabase.RIVAL_TEAMS_IDS[1]) * 0.25:
#                                         tier = '\033[42m'
#                         id_print = '\033[37m' + str(potential_player_id) + '\033[0m'
#                         value_print = '(\033[36m$ ' + str(potential_player_value) + 'm\033[0m) '
#                         form_print = '\033[40m' + str(potential_player_form) + '\033[0m'
#                         # print(f'{potential_player_name}: {potential_player_form6} -> {form6_criteria}  |  {potential_player_form3} -> {form3_criteria}')
#                         if potential_player_pos == position_criteria and count < 30 and((potential_player_form6>=form6_criteria and potential_player_form3>=form3_criteria)or(potential_player_form3>=form3_criteria)):
#                             if 'X' in potential_player_fixtures and len(potential_player_fixtures_diff) > 1:
#                                 print(f'>>> {id_print} {tier}{potential_player_name}\033[0m {value_print}' + Fore.RESET + Back.RESET + f' \033[32m-->\033[0m [Form Rank: {form_print}]' + '\033[33m (!)' + 'Non-ideal Fixtures\033[0m')
#                             elif 'ST' in potential_player_fixtures:
#                                 print(f'>>> {id_print} {tier}{potential_player_name}\033[0m {value_print}' + Fore.RESET + Back.RESET + f' \033[32m-->\033[0m [Form Rank: {form_print}]' + Fore.GREEN + ' (\u2713)' + Fore.RESET + f'{descrip} short-term option!')
#                             elif 'MT' in potential_player_fixtures:
#                                 print(f'>>> {id_print} {tier}{potential_player_name}\033[0m {value_print}' + Fore.RESET + Back.RESET + f' \033[32m-->\033[0m [Form Rank: {form_print}]' + Fore.GREEN + ' (\u2713\u2713)' + Fore.RESET + f'{descrip} med-term option!')
#                             elif 'LT' in potential_player_fixtures:
#                                 print(f'>>> {id_print} {tier}{potential_player_name}\033[0m {value_print}' + Fore.RESET + Back.RESET + f' \033[32m-->\033[0m [Form Rank: {form_print}]' + Fore.GREEN + ' (\u2713\u2713\u2713)' + Fore.RESET + f'{descrip} long-term option!')
#                             else:
#                                 print(f'>>> {id_print} {tier}{potential_player_name}\033[0m {value_print}' + Fore.RESET + Back.RESET + f' \033[32m-->\033[0m [Form Rank: {form_print}]')
#                             count += 1

#             print(f'\n-------> (!!!) Cannot exceed more than $ {MyTeam.bank_value}m NET')
#             return
#         action_protocol()
    
    def team_visualizer(team_ids:list):
        if len(team_ids) != 15:
            print("Need 15 entries for list!")
            return
        team_dict = {}
        for idx in team_ids:
            pos = GrabFunctions.grab_player_pos(idx)
            if pos not in team_dict:
                team_dict[pos]=[]
            name = GrabFunctions.grab_player_name(idx)
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
    
    def alert_players_with_blanks_dgws(FPL_15: pd.DataFrame()):
        teams = list(FPL_15.team.unique())
        ids = [GrabFunctions.grab_team_id(x) for x in teams]
        bgws,dgws = FixtureMath.look_for_blanks_and_dgws()
        bgws_adj = {k: v for k, v in bgws.items() if k > FPLDatabase.LATEST_GW}
        dgws_adj = {k: v for k, v in dgws.items() if k > FPLDatabase.LATEST_GW}
        if bgws_adj:
            print('\n------------- UPCOMING BLANKS -------------')
            for gw,teams in bgws_adj.items():
                print(f'>> Gameweek {gw}')
                matches = [GrabFunctions.grab_team_name(x) for x in ids if x in teams]
                players = list(FPL_15.loc[FPL_15['team'].isin(matches)]['player'])
                if len(players) > 4:
                    print(f"Suggested to remove {len(players)- 4} player(s) in anticipation of blanks:")
                [print(f' - {player}') for player in players]
        if dgws_adj:
            print('\n------------- UPCOMING DGWS -------------')
            for gw,teams in dgws_adj.items():
                print(f'>> Gameweek {gw}')
                matches = [GrabFunctions.grab_team_name(x) for x in ids if x in teams]
                players = list(FPL_15.loc[FPL_15['team'].isin(matches)]['player'])
                [print(f' - {player}') for player in players]
                

class UploadData:
    @classmethod
    def init(self):
        def upload_potentials():
            file = open("primedata_per_gw.txt", "r")
            contents = file.read()
            dictionary = ast.literal_eval(contents)
            dictionary[FPLDatabase.LATEST_GW] = []
            dictionary[FPLDatabase.LATEST_GW].append(RestOfTheRoster.df_fpl_potentials['id'].tolist())
            dictionary[FPLDatabase.LATEST_GW].append(RestOfTheRoster.df_prime_potentials['id'].tolist())
            with open("primedata_per_gw.txt", 'w') as conv_file:
                conv_file.write(json.dumps(dictionary))
            file.close()
            self.potential_dict = dictionary
            print('Uploaded primes to external file!')

        def upload_genius_teams():
            file = open("genius_team_history.txt", "r")
            contents = file.read()
            dictionary = ast.literal_eval(contents)
            dictionary[FPLDatabase.LATEST_GW] = Rivalry.compile_rivals_team(FPLDatabase.GENIUS_IDS)
            with open("genius_team_history.txt", 'w') as conv_file:
                conv_file.write(json.dumps(dictionary))
            file.close()
            self.genius_dict = dictionary
            print('Uploaded gen teams to external file!')

        def compile_returns():
            returns = []
            for i in self.potential_dict[FPLDatabase.LATEST_GW][1]:
                returns.append(GrabFunctions.grab_player_hist(i)[-1])
            larger_elements = [element for element in returns if element > 3]
            number_of_elements = len(larger_elements)
            accuracy = number_of_elements / len(returns)
            file = open("model_accuracy.txt", "r")
            contents = file.read()
            dict_acc = ast.literal_eval(contents)
            dict_acc[FPLDatabase.LATEST_GW] = {}
            dict_acc[FPLDatabase.LATEST_GW]['instant'] = accuracy*100
            with open("model_accuracy.txt", 'w') as conv_file:
                conv_file.write(json.dumps(dict_acc))
            file.close()
            print('Uploaded model accuracy to external file!')
            
        upload_potentials()
        upload_genius_teams()
        compile_returns()
UploadData.init()


class DataTransformer:
    
    @classmethod
    def init(self):
        def make_ROTR():
            ROTR_df = RestOfTheRoster.df_fpl_potentials.iloc[:, 0:8]
            ids = ROTR_df.id.tolist()
            df_tot = FPLDatabase.total_summary[FPLDatabase.total_summary['id_player'].isin(ids)]
            list_cols = df_tot.select_dtypes(include=['object']).columns.tolist()
            df_filtered = df_tot[list_cols].apply(lambda col: col[col.apply(lambda x: isinstance(x, list))])
            df_filtered = df_filtered.dropna(axis=1).reset_index(drop=True)
            df_filtered = pd.merge(ROTR_df, df_filtered, left_index=True, right_index=True, how='inner')
            self.ROTR_df = df_filtered
        def make_MT():
            MT_df = MyTeam.df_fpl.iloc[:, 0:5]
            ids = MT_df.id.tolist()
            df_tot = FPLDatabase.total_summary[FPLDatabase.total_summary['id_player'].isin(ids)]
            list_cols = df_tot.select_dtypes(include=['object']).columns.tolist()
            df_filtered = df_tot[list_cols].apply(lambda col: col[col.apply(lambda x: isinstance(x, list))])
            df_filtered = df_filtered.dropna(axis=1).reset_index(drop=True)
            df_filtered = pd.merge(MT_df, df_filtered, left_index=True, right_index=True, how='inner')
            self.MT_df = df_filtered
        def make_ALL():
            df_tot = FPLDatabase.total_summary.copy()
            df_filtered = df_tot
#             list_cols = df_tot.select_dtypes(include=['object']).columns.tolist()
#             df_filtered = df_tot[list_cols].apply(lambda col: col[col.apply(lambda x: isinstance(x, list))])
#             df_filtered = df_filtered.dropna(axis=1).reset_index(drop=True)
#             overlapping_columns = df_tot.columns.intersection(df_filtered.columns).tolist()
#             df_filtered = pd.merge(df_tot, df_filtered, on=overlapping_columns, how='outer')
            # df_filtered.rename(columns = {'singular_name_short':'position','web_name':'player'}, inplace = True)
            self.all_df = df_filtered
#             print(self.all_df.columns.to_list())
        make_ROTR()
        make_MT()
        make_ALL()    
        
    @classmethod
    def grab_tops(self,returnformat,position,sorter,num_players=None):
        if not num_players:
            num_players = 99
        grouped = self.ROTR_df.groupby('position').apply(lambda x: x.sort_values('position')).reset_index(drop=True)
        grouped_dict = {group: group_df.sort_values(by=[sorter],ascending=False).head(num_players) for group, group_df in grouped.groupby('position')}
        if returnformat == 'id':
            out = grouped_dict[position].id.tolist()
        elif returnformat == 'player':
            out = grouped_dict[position].player.tolist()
        return out
    
    @classmethod
    def grab_fpl15(self,returnformat,position):
        grouped = self.MT_df.groupby('position').apply(lambda x: x.sort_values('position')).reset_index(drop=True)
        grouped_dict = {group: group_df for group, group_df in grouped.groupby('position')}
        if returnformat == 'id':
            out = grouped_dict[position].id.tolist()
        elif returnformat == 'player':
            out = grouped_dict[position].player.tolist()
        return out
    
    @classmethod
    def sort_df(self,param: str, look_back: int, position = None):
        df = self.all_df
        paramlist = df.iloc[:, 7:].columns.tolist()
        if param not in paramlist:
            print(f'Needs to be one of {paramlist}')
            return
        if position:
            grouped = df.groupby('position').apply(lambda x: x.sort_values('position')).reset_index(drop=True)
            grouped_dict = {group: group_df for group, group_df in grouped.groupby('position')}
            df = grouped_dict[position]
        df['temp'] = df[param].apply(lambda x: sum(x[-min(len(x), look_back):]) / min(len(x), look_back))
        df_sorted = df.sort_values('temp', ascending=False)
        df_sorted.drop('temp', axis=1, inplace=True)
        return df_sorted
    
DataTransformer.init()

class DataPlotter:
    
    def loop_name_finder(INPUTNAME):
        SEGMENTS = INPUTNAME.split(" ")
        NAME=[]
        for SEG in SEGMENTS:
            # print(SEG)
            if len(SEG) > 2 and SEG.lower() not in ['van'] and not SEG[0].isupper():
                SEG=SEG.title()
            # print(SEG)
            NAME.append(SEG)
        NAME = ' '.join(NAME)
        # print(NAME)
        SOURCEFILE = DataTransformer.all_df.player.tolist()
        while NAME not in SOURCEFILE:
            M1 = difflib.get_close_matches(INPUTNAME, SOURCEFILE)
            STRS = INPUTNAME.split(" ")
            M2 = []
            for STR in STRS:
                if len(STR) < 3:
                    continue
                for CSV_NAME in SOURCEFILE:
                    CSV_ALT = ''.join(c for c in unicodedata.normalize('NFD', CSV_NAME)
                                      if unicodedata.category(c) != 'Mn')
                    if STR.lower() in CSV_ALT.lower():
                        M2.append(CSV_NAME)
            NAME = input(f'Couldnt find "{NAME}", did you mean any of the following?\n{list(set(M1) | set(M2))}\n')
            if NAME == "":
                return NAME
        return NAME

    def fetch_team_color(team_id):
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

    @classmethod
    def plot_multi_stats(self,param,dataset,values,remove_FPL15 = False):
        df = DataTransformer.all_df
        if param not in df.columns:
            print(f"Incorrect 'param' format, should be one of: {list(df.columns)}")
            return
        if dataset in ['specialized','myteam']:
            if dataset == 'specialized':
                pos = values[0]
                lookback = values[1]
                num_players = values[2]
                df = df.loc[df['position'] == pos]
                if remove_FPL15:
                    df = df.loc[~df['id_player'].isin(MyTeam.df_fpl.id.to_list())]
            elif dataset == 'myteam':
                pos = values[0]
                lookback = 6
                df = df.loc[(df['id_player'].isin(MyTeam.df_fpl.id.to_list())) & (df['position'] == pos)]
                num_players = len(df)
        def average_last(lst):
            return sum(lst[-lookback:]) / lookback
        df[f"{param}_avg"] = df.apply(lambda x: average_last(x[param]), axis = 1)
        df_sorted = df.sort_values(by=f"{param}_avg", ascending=False).head(num_players)
        data = df_sorted[['id_player','player','round',param,f"{param}_avg"]]
        data = data.reset_index(drop = True)
        num_cols = min(7,len(data))
        num_rows = (len(data) + 2) // num_cols
        fig = make_subplots(rows=num_rows, cols=num_cols, subplot_titles=data['player'].tolist())
        for i, d in data.iterrows():
            row = i // num_cols + 1
            col = i % num_cols + 1
#             print(f"{row} {col}")
            color = self.fetch_team_color(GrabFunctions.grab_player_team_id(d['id_player']))
            team = GrabFunctions.grab_player_team(d['id_player'])
            fig.add_trace(go.Scatter(x=d['round'], y=d[param], name = team, mode="markers+lines", line=dict(color=color), marker=dict(color=color)), row=row, col=col)
            fig.update_xaxes(title_text='GW', row=row, col=col)
            if param == 'history':
                fig.add_hrect(y0=-1, y1=4, line_width=0, fillcolor="red", opacity=0.2, row=row, col=col)
                fig.add_hrect(y0=4, y1=6, line_width=0, fillcolor="yellow", opacity=0.2, row=row, col=col)
                fig.add_hrect(y0=6, y1=9, line_width=0, fillcolor="green", opacity=0.2, row=row, col=col)
                fig.add_hrect(y0=9, y1=max(d[param])+2, line_width=0, fillcolor="blue", opacity=0.2, row=row, col=col)
            else:
                fig.add_hline(y=d[f"{param}_avg"], line_dash='dot', line_width=2, line_color='black', row=row, col=col)
            fig.update_xaxes(nticks = 6, row=row, col=col)
            fig.update_yaxes(nticks = 6, row=row, col=col)
        fig.update_layout(height=350*(num_rows), width=350*num_cols)
        fig.update_layout(title=f'{param} vs GW',showlegend=False)
        fig.update_xaxes(title='GW')
        fig.update_yaxes(title=param)
        fig.show()
        return
    
    @classmethod
    def plot_individual_stats(self,player_name,paramlist):
        return

class DecisionMatrix:
    
    @classmethod
    def initialize_players(self):
        self.players=[]
        for num in DataTransformer.all_df.id_player.tolist():
            df = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == num]
#             print(df.columns.to_list())
            position = df['position'].iloc[0]
            history = df['history'].iloc[0]
            bps = df['bps'].iloc[0]
            ICT = df['ict_index'].iloc[0]
            xGI = df['expected_goal_involvements'].iloc[0]
            minutes = df['minutes'].iloc[0]
            xGC = df['expected_goals_conceded'].iloc[0]
            cost = df['changing_value'].iloc[0][-1]
            if position in ['DEF','GKP']:
                self.players.append({'id':num,'position':position,'name':GrabFunctions.grab_player_name(num), 'history':(np.mean(history[-6:]),history[-6:]), 'bps':(np.mean(bps[-6:]),bps[-6:]), 'ict':(np.mean(ICT[-6:]),ICT[-6:]), 'xGI':(np.mean(xGI[-6:]),xGI[-6:]), 'xGC':(np.mean(xGC[-6:]),xGC[-6:]), 'minutes':minutes[-6:], 'cost':cost/10})
            else:
                self.players.append({'id':num,'position':position,'name':GrabFunctions.grab_player_name(num), 'history':(np.mean(history[-6:]),history[-6:]), 'bps':(np.mean(bps[-6:]),bps[-6:]), 'ict':(np.mean(ICT[-6:]),ICT[-6:]), 'xGI':(np.mean(xGI[-6:]),xGI[-6:]), 'minutes':minutes[-6:], 'cost':cost/10})
       
    @classmethod
    def initialize_replacements(self):
        player_dict = {}
        for param,param_thresh in [('ict_index',7),('returnhist',1),('bps',25),('expected_goal_involvements',0.75),('history',6)]:
#             param = 'ict_index'
#             param_thresh = 5
            player_dict[param] = {}
            for look_back in [1,2,3,4,5,6]:
                df = DataTransformer.all_df
                FPL_15_players = MyTeam.df_fpl.id.tolist()
                mask = df.id_player.isin(FPL_15_players)
                df = df[~mask]
                pristine_df = df.copy()
                def last_3_values(lst):
                    return np.mean(lst[-look_back:])
                mask = df[param].apply(last_3_values) >= param_thresh
                df = df[mask]
                grouped = df.groupby('position').apply(lambda x: x.sort_values('position')).reset_index(drop=True)
                grouped_dict = {group: group_df for group, group_df in grouped.groupby('position')}
                player_dict[param][look_back] = {}
                for position in ['DEF','MID','FWD']:
                    try:
                        df = grouped_dict[position]
                        df_sorted = df.sort_values(by=param, key=lambda x: x.map(last_3_values), ascending = False)
                        player_dict[param][look_back][position] = df_sorted.id_player.tolist()
#                         # Loop through every 2,3,4 values
#                         if look_back in [2,3,4]:
#                             print(look_back)
#                             for i in range(0, len(df[param]), look_back):
#                                 if i + look_back - 1 < len(df[param]):
#                                     avg_value = np.mean(df[param][i:i+look_back])
# #                                     if avg_value >= param_thresh:
#                                     print(avg_value)
                    except:
                        pass

        unique_values = {
            'DEF': [],
            'MID': [],
            'FWD': []
        }
#         print(player_dict)
        # Iterate over the values in the inner dictionaries and update the unique_values dictionary
        for param in player_dict.keys():
            for d in player_dict[param].values():
                for k, v in d.items():
                    unique_values[k].extend(v)

        # Extract the unique values for each group
        unique_values['DEF'] = list(set(unique_values['DEF']))
        unique_values['MID'] = list(set(unique_values['MID']))
        unique_values['FWD'] = list(set(unique_values['FWD']))
        # print(unique_values)
        self.replacement_players=[]
        def passes_xGI_threshold(numbers):
            if len(numbers) >= 3:
                last_three = numbers[-3:]
                combinations = [(last_three[0], last_three[1]),
                                (last_three[0], last_three[2]),
                                (last_three[1], last_three[2])]

                for a, b in combinations:
                    average = (a + b) / 2
                    if average > 0.5:
                        return True

            return False
        for key in unique_values.keys():
        #     print(f'\n{key}\n')
            for num in unique_values[key]:
                df = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['id_player'] == num]
                history = df['history'].iloc[0]
                bps = df['bps'].iloc[0]
                ICT = df['ict_index'].iloc[0]
                xGI = df['expected_goal_involvements'].iloc[0]
                xGC = df['expected_goals_conceded'].iloc[0]
                mins = df['minutes'].iloc[0]
                cost = df['changing_value'].iloc[0][-1]
                if key == 'DEF':
        #             print(f'{GrabFunctions.grab_player_name(num)} (${cost/10})')
                    self.replacement_players.append({'id':num,'position':key,'name':GrabFunctions.grab_player_name(num), 'history':(np.mean(history[-6:]),history[-6:]), 'bps':(np.mean(bps[-6:]),bps[-6:]), 'ict':(np.mean(ICT[-6:]),ICT[-6:]), 'xGI':(np.mean(xGI[-6:]),xGI[-6:]), 'xGC':(np.mean(xGC[-6:]),xGC[-6:]), 'minutes':mins[-6:],'cost':cost/10})
                else:
                    if np.mean(xGI[-6:]) > 0.4 or passes_xGI_threshold(xGI):
        #                 print(f'{GrabFunctions.grab_player_name(num)} {xGI[-6:]} (${cost/10})')
                        self.replacement_players.append({'id':num,'position':key,'name':GrabFunctions.grab_player_name(num), 'history':(np.mean(history[-6:]),history[-6:]), 'bps':(np.mean(bps[-6:]),bps[-6:]), 'ict':(np.mean(ICT[-6:]),ICT[-6:]), 'xGI':(np.mean(xGI[-6:]),xGI[-6:]), 'minutes':mins[-6:],'cost':cost/10})
        players = [x for x in self.players if x['id'] in MyTeam.df_fpl['id'].to_list()]    
        combinations = [(dict1, dict2) for dict1, dict2 in itertools.product(players, self.replacement_players) if ((dict2['ict'][0]+1 > dict1['ict'][0]) and dict2['position'] == dict1['position'])]
        self.my_dict = {}
        for key, value in combinations:
            if key['name'] in self.my_dict:
                self.my_dict[key['name']]['replacement'].append((value,round(value['cost']-key['cost'],2)))
            else:
                self.my_dict[key['name']] = {'stats':key,'replacement':[(value,round(value['cost']-key['cost'],2))]}
        seq_map = {'GKP':0, 'DEF':1, 'MID':2, 'FWD':3}
        items = sorted(DecisionMatrix.my_dict.items(), key=lambda x: seq_map[x[1]['stats']['position']])
        self.my_dict = {k:v for k,v in items}
        
    @classmethod
    def initialize_effective_ownership(self):    
        RIVALS_INIT = [782655,#Just Quiet
                       467038,#GreatestShow
                       'genius']
        counter_dict = {}
        #Find IDs with ranks
        def rank_finder(ID):
            r = requests.get(
                            'https://fantasy.premierleague.com/api/entry/' + str(ID) + '/event/' + str(FPLDatabase.LATEST_GW) + '/picks/'
                    ).json()
            return r['entry_history']['overall_rank']
        top_1k = [idx for idx in FPLDatabase.GENIUS_IDS if rank_finder(idx) <= 1000]
        top_10k = [idx for idx in FPLDatabase.GENIUS_IDS if rank_finder(idx) <= 10000]
        top_100k = [idx for idx in FPLDatabase.GENIUS_IDS if rank_finder(idx) <= 100000]
        rank_dict={}
        for topper,namer in [(top_1k,'gen_1k'), (top_10k,'gen_10k'), (top_100k,'gen_100k')]:
#             if topper:
#                 if (namer == 'gen_10k' and len(top_10k) == len(top_1k)) or (namer == 'gen_100k' and len(top_100k) == len(top_10k)):
#                     continue
#                 else:
            RIVALS_INIT.append(namer)
            rank_dict[namer] = topper
        def dict_counter(dictx, listx, rivalx):
            for idx in listx:
                if idx not in dictx[rivalx]['players'].keys():
                    dictx[rivalx]['players'][idx] = 1
                else:
                    dictx[rivalx]['players'][idx] += 1
            return
        for RIVAL_LEAGUE in RIVALS_INIT:
            if 'gen' not in str(RIVAL_LEAGUE):
                base_url = 'https://fantasy.premierleague.com/api/' + 'leagues-classic/' + str(RIVAL_LEAGUE) + '/standings/'
                league_r = requests.get(base_url).json()
                league_players = league_r['standings']['results']
                my_rank,my_points = [(x['rank'],x['total']) for x in league_players if x['player_name'] == 'Javaid Baksh'][0]
                players_of_interest = [x['entry'] for x in league_players if ((x['rank'] < my_rank) or (x['total'] > my_points - 50 and x['rank'] > my_rank))]
            elif RIVAL_LEAGUE == 'genius':
                players_of_interest = FPLDatabase.GENIUS_IDS
#             print(players_of_interest)
            elif 'gen_' in RIVAL_LEAGUE:
                players_of_interest = rank_dict[RIVAL_LEAGUE]
            counter_dict[RIVAL_LEAGUE] = {'rivals':len(players_of_interest),'players':{}}
            for RIVAL_ID in players_of_interest:
                url = 'https://fantasy.premierleague.com/api/' + 'entry/' + str(RIVAL_ID) + '/event/' + str(FPLDatabase.LATEST_GW) + '/picks/'
                r = requests.get(url).json()
                player_ids = [x['element'] for x in r['picks']]
                dict_counter(counter_dict, player_ids, RIVAL_LEAGUE)
            counter_dict[RIVAL_LEAGUE]['players'] = dict(sorted(counter_dict[RIVAL_LEAGUE]['players'].items(), key=lambda item: item[1], reverse=True))
        self.eff_own_dict = counter_dict
    
    @classmethod
    def get_ownership(self,player_id,league_id,format_color):
        ids = self.eff_own_dict[league_id]
        total_rivals = ids['rivals']
        total_players = ids['players']
        if player_id not in total_players.keys():
            count = 0
        else:
            count = total_players[player_id]
        if count == 0 and format_color == 'sell':
            count_str = "\033[31m" +  str(count) + "\033[0m"
        elif count != 0 and format_color == 'buy':
            count_str = "\033[34m" +  str(count) + "\033[0m"
        else:
            count_str = str(count)
        return count_str + "/" + str(total_rivals)
    
    @classmethod
    def lerp_color(self,color1, color2, weight):
        """Interpolate between two colors with a given weight."""
        r = (1 - weight) * color1[0] + weight * color2[0]
        g = (1 - weight) * color1[1] + weight * color2[1]
        b = (1 - weight) * color1[2] + weight * color2[2]
        return (r, g, b)

    @classmethod
    def get_gradient_color(self,value, min_val, med_val, max_val):
        if value < med_val:
            weight = (value - min_val) / (med_val - min_val)
            color1 = (0, 0.7, 0) # green
#             color2 = (1, 0.5, 0) # orange
            color2 = (0, 0, 1) # blue
            hex_string =  "#" + "".join("%02x" % round(c * 255) for c in self.lerp_color(color1, color2, weight))
        else:
            weight = (value - med_val) / (max_val - med_val)
            color1 = (0, 0, 1) # blue
#             color1 = (1, 0.5, 0) # yellow
            color2 = (1, 0, 0) # red
    #         color2 = (0, 0, 1) # blue
            hex_string = "#" + "".join("%02x" % round(c * 255) for c in self.lerp_color(color1, color2, weight))
    
        color = hex_string
        text = value
        colored_text = "\033[38;2;{};{};{}m{}\033[0m".format(
            int(color[1:3], 16), int(color[3:5], 16), int(color[5:], 16), text
        )
        return colored_text
    
    @classmethod
    def get_static_color(self,tuple_val, param):
        """
        Takes a value, minimum value, and maximum value and returns a
        background-color ANSI escape code for the cell based on the value's
        position between the minimum and maximum.
        """
        if isinstance(tuple_val, tuple):
            actual_vals = tuple_val[1]
            averaged_val = round(tuple_val[0],2)
            avg_str = str(averaged_val) + ": "
        elif isinstance(tuple_val, list):
            actual_vals = tuple_val
            avg_str = ""
        if param == 'ict':
            low_thr,mid_thr,high_thr = 3.5,5,7.5
        elif param == 'xGI':
            low_thr,mid_thr,high_thr = 0.2,0.5,0.9
        elif param == 'history':
            low_thr,mid_thr,high_thr = 4,6,9
        elif param == 'bps':
            low_thr,mid_thr,high_thr = 14,21,29
        elif param == 'minutes':
            low_thr,mid_thr,high_thr = 45,60,89
        val_str = ""
        for val in actual_vals:
            if val <= low_thr:
                color_code = '\033[1;31m'  # bold red
            elif val <= mid_thr:
                color_code = '\033[1;33m'  # bold yellow
            elif val <= high_thr:
                color_code = '\033[1;32m'  # bold green
            else:
                color_code = '\033[1;34m'  # bold blue
            val_str += color_code + str(round(val,2)) + ' \033[0m'
        return avg_str + val_str
    
    @classmethod
    def get_colored_fixtures(self,team_id, look_ahead, reference_gw=None):
        fdr_color_scheme = {
            1: (79, 121, 66),
            2: (51, 230, 153),
            3: (210, 210, 210),
            4: (255, 64, 107),
            5: (150, 27, 67)
        }

        fixturelist = GrabFunctions.player_fixtures('fwd',team_id,look_ahead, reference_gw)
        bgws,dgws = FixtureMath.look_for_blanks_and_dgws()
        dgws = list(dgws.keys())
        printstring = ''
        for gw in fixturelist:
            fixtures = gw[-1]
    #         printstring += '|'
            if fixtures:
                xtra = ''
                if len(fixtures) > 1:
                    spacing = ' '
                else:
                    if gw[0] in dgws:
                        spacing = '     '
                        xtra = ' '
                    else:
                        spacing = ' '
                for fixture in fixtures:
                    team,loc,fdr = fixture[1],fixture[2],fixture[3]
                    rgb_tuple = fdr_color_scheme[fdr]
                    printstring += f'\x1b[48;2;{rgb_tuple[0]};{rgb_tuple[1]};{rgb_tuple[2]}m{spacing}{team} ({loc}){spacing}{xtra}\x1b[0m'
            else:
                if gw[0] in dgws:
                    spacing = '        '
                else:
                    spacing = '    '
                printstring += f"\x1b[48;2;210;210;210m{spacing}-{spacing}\x1b[0m"
            printstring += ' '
        return printstring
 
    @classmethod
    def get_colored_teams(self,team_3ltr):
        team_colors = {
            'ARS': {'bg': (206, 78, 95), 'text': (255, 255, 255)},
            'AVL': {'bg': (133, 60, 83), 'text': (207, 200, 99)},
            'BOU': {'bg': (206, 75, 75), 'text': (0, 0, 0)},
            'BRE': {'bg': (255, 178, 180), 'text': (0, 0, 0)},
            'BHA': {'bg': (48, 76, 143), 'text': (255, 255, 255)},
            'BUR': {'bg': (210, 210, 210), 'text': (0, 0, 0)},
            'CHE': {'bg': (59, 89, 152), 'text': (255, 255, 255)},
            'CRY': {'bg': (155, 57, 98), 'text': (255, 255, 255)},
            'EVE': {'bg': (43, 76, 116), 'text': (255, 255, 255)},
            'FUL': {'bg': (105, 105, 105), 'text': (255, 255, 255)},
            'LIV': {'bg': (100, 210, 156), 'text': (193, 53, 81)},
            'LUT': {'bg': (51, 93, 158), 'text': (246, 205, 96)},
            'MCI': {'bg': (149, 200, 210), 'text': (0, 0, 0)},
            'MUN': {'bg': (195, 68, 75), 'text': (246, 205, 96)},
            'NEW': {'bg': (105, 105, 105), 'text': (255, 255, 255)},
            'NFO': {'bg': (195, 68, 75), 'text': (255, 255, 255)},
            'SHE': {'bg': (220, 220, 220), 'text': (220, 87, 103)},
            'TOT': {'bg': (64, 92, 138), 'text': (255, 255, 255)},
            'WHU': {'bg': (146, 72, 72), 'text': (255, 255, 255)},
            'WOL': {'bg': (246, 205, 96), 'text': (0, 0, 0)}
        }


        if team_3ltr in team_colors:
            bg_rgb_tuple = team_colors[team_3ltr]['bg']
            text_rgb_tuple = team_colors[team_3ltr]['text']
            colored_text = f'\x1b[38;2;{text_rgb_tuple[0]};{text_rgb_tuple[1]};{text_rgb_tuple[2]}m'
            colored_bg = f'\x1b[48;2;{bg_rgb_tuple[0]};{bg_rgb_tuple[1]};{bg_rgb_tuple[2]}m'
            reset_color = '\x1b[0m'
            formatted_string = f'{colored_bg}{colored_text} {team_3ltr} {reset_color}'
        else:
            formatted_string = team_3ltr
        return formatted_string

    @classmethod
    def get_past_fixtures_colors(self,team_id, look_behind):
        fdr_color_scheme = {
            1: (79, 121, 66),
            2: (51, 230, 153),
            3: (210, 210, 210),
            4: (255, 64, 107),
            5: (150, 27, 67)
        }

        fixturelist = GrabFunctions.player_fixtures('rev',team_id,look_behind)
        printstring = ''
        count = 0
        for gw in fixturelist:
            fixtures = gw[-1]
    #         printstring += '|'
            if fixtures:
                for fixture in fixtures:
                    if count < look_behind:
                        count += 1
                        fdr = fixture[3]
                        rgb_tuple = fdr_color_scheme[fdr]
                        printstring += f'\x1b[48;2;{rgb_tuple[0]};{rgb_tuple[1]};{rgb_tuple[2]}m  \x1b[0m'
            else:
#                 if count < look_behind:
#                     count += 1
#                     printstring += f"\x1b[48;2;0;0;0m  \x1b[0m"
                continue
        return printstring

    @classmethod
    def player_summary(self, dataset: str, values: list = None):
        net_spend_limit = round(MyTeam.bank_value,2)
        if dataset == 'custom':
            players = values
            player_ids = []
            for player in players:
                if isinstance(player, str):
                    found_plyr = DataPlotter.loop_name_finder(player)
                    if not found_plyr:
                        print(f'Empty entry, skipping player.')
                        continue
                    df = FPLDatabase.total_summary.loc[FPLDatabase.total_summary['player'] == str(found_plyr)]
                    player_ids.append(df.id_player.values[0])
                else:
                    player_ids.append(player)
            players = [x for x in self.players if x['id'] in player_ids]
            format_color = 'buy'
        elif dataset == 'FPL15':
            players = [x for x in self.players if x['id'] in MyTeam.df_fpl['id'].to_list()]
            format_color = 'sell'
        else:
            print("'dataset' variable must be one of 'FPL15' or 'custom'")
            return
        # Define function to apply color to each cell

        seq_map = {'GKP':0, 'DEF':1, 'MID':2, 'FWD':3}
        sorted_players = sorted(players, key=lambda x: (seq_map[x['position']], -x['history'][0]))
#         costs = sorted([x['cost'] for x in sorted_players])
        prev_position = None
    
        table_cols = ['FPL15 Player','Position','Team','Past FDRs','History','Bonus Points','ICT','xGI','Minutes','xGC','Cost','𝙹𝚀𝚁','𝙶𝚂𝙿','☆₁ₖ','☆₁₀ₖ','☆₁₀₀ₖ','☆','Upcoming Fixtures']
#         gen_cols = [x for x in DecisionMatrix.eff_own_dict.keys() if 'gen_' in str(x)]
        tab = PrettyTable(table_cols)
        for plyr_dict in sorted_players:
            cost = plyr_dict['cost']
            name = plyr_dict['name']
#             history = plyr_dict['history'][0]
#             bps = plyr_dict['bps'][0]
#             ict = plyr_dict['ict'][0]
            position = plyr_dict['position']
            team_id = GrabFunctions.grab_player_team_id(plyr_dict['id'])
            if prev_position:
                if prev_position != position:
                    tab.add_row(['']*len(table_cols))
            if position == 'DEF':
                tab.add_row([name,
                             position,
                             self.get_colored_teams(GrabFunctions.grab_3ltr_team_name(team_id)),
                             self.get_past_fixtures_colors(team_id,6),
                             self.get_static_color(plyr_dict['history'],'history'),
                             self.get_static_color(plyr_dict['bps'],'bps'),
                             self.get_static_color(plyr_dict['ict'],'ict'),
                             self.get_static_color(plyr_dict['xGI'],'xGI'),
                             self.get_static_color(plyr_dict['minutes'],'minutes'),
                             round(plyr_dict['xGC'][0],2),
                             self.get_gradient_color(cost,min(cost,3.8),7,max(cost,13)),
                             self.get_ownership(plyr_dict['id'],league_id=782655,format_color=format_color),
                             self.get_ownership(plyr_dict['id'],league_id=467038,format_color=format_color),
                             self.get_ownership(plyr_dict['id'],league_id='gen_1k',format_color=format_color),
                             self.get_ownership(plyr_dict['id'],league_id='gen_10k',format_color=format_color),
                             self.get_ownership(plyr_dict['id'],league_id='gen_100k',format_color=format_color),
                             self.get_ownership(plyr_dict['id'],league_id='genius',format_color=format_color),
                             self.get_colored_fixtures(GrabFunctions.grab_player_team_id(plyr_dict['id']),5)
#                              self.get_gradient_color(cost,min(costs),statistics.median(costs),max(costs))
                            ])
            else:
                tab.add_row([name,
                             position,
                             self.get_colored_teams(GrabFunctions.grab_3ltr_team_name(team_id)),
                             self.get_past_fixtures_colors(team_id,6),
                             self.get_static_color(plyr_dict['history'],'history'),
                             self.get_static_color(plyr_dict['bps'],'bps'),
                             self.get_static_color(plyr_dict['ict'],'ict'),
                             self.get_static_color(plyr_dict['xGI'],'xGI'),
                             self.get_static_color(plyr_dict['minutes'],'minutes'),
                             '-',
                             self.get_gradient_color(cost,min(cost,3.8),7,max(cost,13)),
                             self.get_ownership(plyr_dict['id'],league_id=782655,format_color=format_color),
                             self.get_ownership(plyr_dict['id'],league_id=467038,format_color=format_color),
                             self.get_ownership(plyr_dict['id'],league_id='gen_1k',format_color=format_color),
                             self.get_ownership(plyr_dict['id'],league_id='gen_10k',format_color=format_color),
                             self.get_ownership(plyr_dict['id'],league_id='gen_100k',format_color=format_color),
                             self.get_ownership(plyr_dict['id'],league_id='genius',format_color=format_color),
                             self.get_colored_fixtures(GrabFunctions.grab_player_team_id(plyr_dict['id']),5)
                            ])
            prev_position = position
        print(tab)
        
    @classmethod
    def replacement_summary(self, net_limit = True):
        #Single replacements
        net_spend_limit = round(MyTeam.bank_value,2)
        tab = PrettyTable(['FPL15 Player','Position','FPL15 ICT','FPL15 xGI','FPL15 xGC','Replacement','Team','Past FDRs','ICT','xGI','xGC','Net Spend','Upcoming Fixtures'])
        if net_limit:
            nets = [d[-1] for inner_dict in self.my_dict.values() for d in inner_dict['replacement'] if d[-1] <= net_spend_limit]
        else:
            nets = [d[-1] for inner_dict in self.my_dict.values() for d in inner_dict['replacement']]
#         prev_position,prev_FPL15_player_name = None, None
        for key in self.my_dict:
            FPL15_player_name = key
        #     print(f'Replace {key} with:')
            comp_dict = self.my_dict[key]
            replacements = comp_dict['replacement']
            sorted_replacements = sorted(replacements, key=lambda x: x[0]['history'][0], reverse=True)
            count = 0
            for r in sorted_replacements:
                #FP15 Player
                position = comp_dict['stats']['position']
#                 print(f'{position} {prev_position}')
#                 position = r[0]['position']
                #Replacements
                name = r[0]['name']
                team_id = GrabFunctions.grab_player_team_id(r[0]['id'])
                ict = r[0]['ict']
                net = r[-1]
                if net_limit:
                    cond = (net <= net_spend_limit)
                else:
                    cond = True
                if cond:
#                     print(position)
                    if count == 0:
                        tab.add_row(['']*13)
                        FPL15_ICT = self.get_static_color(comp_dict['stats']['ict'],'ict')
                        FPL15_xGI = self.get_static_color(comp_dict['stats']['xGI'],'xGI')
                        if position == 'DEF':
                            FPL15_xGC = round(comp_dict['stats']['xGC'][0],2)
                        FPL15_pos = position
                    else:
#                         if prev_FPL15_player_name == FPL15_player_name:
                        FPL15_player_name, FPL15_pos, FPL15_ICT, FPL15_xGI, FPL15_xGC = '','','','',''
#                     if prev_position:
#                         if prev_position != position:
# #                             print(f'{prev_position} {position}')
#                             tab.add_row(['']*13)
        #             print(f' - {name}  |  {round(ict,2)}  |  Net Spend: {round(net,2)} $')
                    count += 1
                    if position == 'DEF':
                        tab.add_row([FPL15_player_name,
                                     FPL15_pos,
                                     FPL15_ICT,
                                     FPL15_xGI,
                                     FPL15_xGC,
                                     name,
                                     self.get_colored_teams(GrabFunctions.grab_3ltr_team_name(team_id)),
                                     self.get_past_fixtures_colors(team_id,6),
                                     self.get_static_color(r[0]['ict'],'ict'),
                                     self.get_static_color(r[0]['xGI'],'xGI'),
                                     round(r[0]['xGC'][0],2),
                                     self.get_gradient_color(net,min(nets),0,max(nets)),
                                     self.get_colored_fixtures(GrabFunctions.grab_player_team_id(r[0]['id']),5)])
                    else:
                        tab.add_row([FPL15_player_name,
                                     FPL15_pos,
                                     FPL15_ICT,
                                     FPL15_xGI,
                                     '-',
                                     name,
                                     self.get_colored_teams(GrabFunctions.grab_3ltr_team_name(team_id)),
                                     self.get_past_fixtures_colors(team_id,6),
                                     self.get_static_color(r[0]['ict'],'ict'),
                                     self.get_static_color(r[0]['xGI'],'xGI'),
                                     '-',
                                     self.get_gradient_color(net,min(nets),0,max(nets)),
                                     self.get_colored_fixtures(GrabFunctions.grab_player_team_id(r[0]['id']),5)])
#                     if FPL15_player_name and position:
#                         prev_position,prev_FPL15_player_name = position,FPL15_player_name
        tab.align["Upcoming Fixtures"] = "l"
        print(tab)
        
DecisionMatrix.initialize_players()
DecisionMatrix.initialize_replacements()
DecisionMatrix.initialize_effective_ownership()

from understatapi import UnderstatClient
import pandas as pd
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

class UnderstatProcessing:
    def __init__(self):
        #################  MATCHING UDID to FPLID  ############################################
        #Teams=======================================================================================================================================
        print('Matching FPL teams to UnderStat teams...')
        fpl_ids = FPLDatabase.teams['id'].tolist()
        fpl_names = FPLDatabase.teams['name'].tolist()
#         self.fpl_short_names = FPLDatabase.teams['short_name'].tolist()
        self.fpl_nums = list(zip(fpl_ids,fpl_names))
        with UnderstatClient() as understat:
            league_szn_team_stats = understat.league(league="EPL").get_team_data(season="2023")
            understat_nums_unsorted = [(x['id'],x['title']) for x in league_szn_team_stats.values()]
            self.understat_nums = sorted(understat_nums_unsorted, key=lambda x: x[1])
        self.team_nums = list(zip(self.fpl_nums,self.understat_nums))
        #Players======================================================================================================================================
        print('Matching FPL players to UnderStat players...')
        league_player_data = understat.league(league="EPL").get_player_data(season="2024")
        player_data_understat = pd.DataFrame(data=league_player_data)
        # Assuming you have DataFrame 1 and DataFrame 2 with columns 'Name' and 'ID'
        df1 = player_data_understat[['id','player_name','team_title']]
        df2 = FPLDatabase.total_summary[['id_player','first_name','second_name','web_name','name']]
        # df2['player_name'] = df2['first_name'] + " " + df2['second_name'] 
        # column_mapping = {'id_player': 'id'}
        column_mapping = {'id_player': 'id', 'web_name': 'player_name'}
        df2 = df2.rename(columns=column_mapping)
        df2['combined_name'] = df2['first_name'] + " " + df2['second_name']
        # Create a new DataFrame to store the matched IDs
        matched_df = pd.DataFrame(columns=['ID_understat', 'ID_FPL'])
        # Iterate over each row in DataFrame 1
        player_nums = []
        for index, row in df1.iterrows():
            #Understat data
            name_df1 = row['player_name']
            id_df1 = row['id']
            team_df1 = row['team_title'].split(",")[-1]
            #Fpl data
            try:
                fpl_team_name = [x[0][1] for x in self.team_nums if x[1][1] == team_df1][0]
                relevant_fpl_df = df2.loc[df2['name'] == fpl_team_name]
            except Exception as e:
                print(team_df1)
                print(e)
            # Find the closest match in DataFrame 2
            closest_match = process.extractOne(name_df1, relevant_fpl_df['combined_name'], scorer=fuzz.ratio)
#             print(f'{name_df1} {team_df1} {closest_match}')
            # Assuming a minimum threshold of 80 for matching (adjust as needed)
            if closest_match[1] >= 40:
                matched_name_df2 = closest_match[0]
                matched_index_df2 = df2[df2['combined_name'] == matched_name_df2].index[0]
                id_df2 = df2.at[matched_index_df2, 'id']
                matched_df = matched_df.append({'ID_understat': int(id_df1), 'ID_FPL': int(id_df2)}, ignore_index=True)
                player_nums.append(((id_df2,matched_name_df2),(id_df1,name_df1)))
            else:
                print(f'Issues with: {name_df1} {team_df1} {closest_match}')
#         self.df1=df1
#         self.df2=df2
        self.full_players_nums_df=matched_df
        self.player_nums = player_nums
        # Print the matched DataFrame
        print(f'{len(self.full_players_nums_df)} / {len(df1)} players processed...')
        #============================================================================================================================================
        #################### BUILDING TEAM DATASETS ##############################################
        print('Building team stats for season so far...')
        understat = UnderstatClient()
        data_team = understat.league(league="EPL").get_team_data(season="2023")
        new_team_data = {}
        # Iterate over the teams in the data
        for team_id, team_data in data_team.items():
            # Copy the team's data to the new_data dictionary
            new_team_data[team_id] = team_data.copy()
            # Initialize a dictionary to hold the lists of values for the 'history' key
            new_history = {}
            # Iterate over the dictionaries in the 'history' list
            for game in team_data['history']:
                # Iterate over the keys and values in each dictionary
                for key, value in game.items():
                    # If the key is not already in the new_history dictionary, add it with an empty list as the value
                    if key not in new_history:
                        new_history[key] = []
                    # Append the value to the list for this key
                    new_history[key].append(value)
            # Replace the 'history' key in the new_data dictionary with the new_history dictionary
            new_team_data[team_id]['history'] = new_history
        self.new_team_data = new_team_data
        
    def grab_player_USID_from_FPLID(self, FPL_ID):
        return int([x[1][0] for x in self.player_nums if str(x[0][0]) == str(FPL_ID)][0])
        
    def grab_team_USID_from_FPLID(self, FPL_ID):
        return int([x[1][0] for x in self.team_nums if str(x[0][0]) == str(FPL_ID)][0])
        
    def grab_team_USname_from_FPLID(self, FPL_ID):
        return [x[1][1] for x in self.team_nums if str(x[0][0]) == str(FPL_ID)][0]
    
    #################################### TEAM FUNCTIONS ##############################################
    
    def fetch_team_xg_stats(self,FPL_ID):
        """
        Function returns xG of a specified team against all teams so far. Use fetch team all stats for expanded view
        """
        team_name = [x[1][1] for x in self.team_nums if str(x[0][0]) == str(FPL_ID)][0]
        formatted_team_name = team_name.replace(" ", "_")
        with UnderstatClient() as understat:
            team_match_data = understat.team(team=formatted_team_name).get_match_data(season="2023")
        dfdata = []
        for gw,data in enumerate(team_match_data):
            side = data['side']
            def opposite_side(side):
                if side == 'h':
                    return 'a'
                elif side == 'a':
                    return 'h'
            opposing_team = data[opposite_side(side)]['title']
            dfdata.append([gw+1,data['xG'][side],opposing_team])
        df = pd.DataFrame(data=dfdata,columns=['GW','xG','Team_Against'])
        return df
    
    def fetch_all_team_expanded_stats(self,FPL_ID):
        """
        Function returns all values for all games of this season
        """
        rows = []
        for team_id, team_data in new_team_data.items():
            row = team_data['history'].copy()  # Copy the history data
            row['id'] = team_data['id']  # Add the team id
            row['title'] = team_data['title']  # Add the team title
            rows.append(row)
        team_df = pd.DataFrame(rows)
        return team_df
    
    def fetch_all_team_finite_stats(self,look_back):
        """
        Function returns all stats of all teams over a certain look back period, thus reducing to a finite value, both outputting averages and sums of all stats. 
        Usefulness is in stats like PPDA which outline how well-pressing certain teams are, which can be later be used to match up upcoming 
        teams and assess weaknesses based on general PPDA and specific PPDA.
        """
        rows1,rows2 = [],[]
        for team_id, team_data in new_team_data.items():
            row1 = {'id': team_data['id'], 'title': team_data['title']}  # Initialize the row with the team id and title
            row2 = {'id': team_data['id'], 'title': team_data['title']}  # Initialize the row with the team id and title
            for key, values in team_data['history'].items():
                if key == 'ppda':
                    # For the 'ppda' key, create separate columns for 'att' and 'def'
                    row1['ppda_att'] = np.mean([value['att'] for value in values[-look_back:]])
                    row1['ppda_def'] = np.mean([value['def'] for value in values[-look_back:]])
                    row2['ppda_att'] = np.sum([value['att'] for value in values[-look_back:]])
                    row2['ppda_def'] = np.sum([value['def'] for value in values[-look_back:]])
                elif key == 'ppda_allowed':
                    # For the 'ppda' key, create separate columns for 'att' and 'def'
                    row1['ppda_allowed_att'] = np.mean([value['att'] for value in values[-look_back:]])
                    row1['ppda_allowed_def'] = np.mean([value['def'] for value in values[-look_back:]])
                    row2['ppda_allowed_att'] = np.sum([value['att'] for value in values[-look_back:]])
                    row2['ppda_allowed_def'] = np.sum([value['def'] for value in values[-look_back:]])
                elif key in ['h_a','result','date','id','title']:
                    continue
                else:
                    # For other keys, calculate the average of the values
                    row1[key] = np.mean(values[-look_back:])
                    row2[key] = np.sum(values[-look_back:])
            rows1.append(row1)
            rows2.append(row2)
        team_df1 = pd.DataFrame(rows1)
        team_df1 = team_df1.sort_values('npxGD', ascending=False)
        team_df2 = pd.DataFrame(rows2)
        team_df2 = team_df2.sort_values('npxGD', ascending=False)
        return team_df1,team_df2
    
    #################################### PLAYER FUNCTIONS ##############################################
    
    def fetch_player_shot_data(self, FPL_ID):
        understat = UnderstatClient()
        player_shot_data = understat.player(player=str(self.grab_player_USID_from_FPLID(FPL_ID))).get_shot_data()
        df = pd.DataFrame(data=player_shot_data)
        parsed_time = datetime.fromisoformat(FPLDatabase.SZN_START_TIME[:-1])
        formatted_string = parsed_time.strftime("%Y-%m-%d")
        date_string = formatted_string
        date_format = "%Y-%m-%d"
        df["date"] = pd.to_datetime(df["date"])
        df = df.loc[df['date']>=datetime.strptime(date_string, date_format)]
        # Group by 'round' (colY) and count 'hit' or 'miss' occurrences (colX)
        grouped = df.groupby(['result', 'match_id','h_team','a_team']).size().reset_index(name='count')
        # Pivot the grouped DataFrame to have 'hit' and 'miss' counts per round
        chance_summary = grouped.pivot_table(index=['match_id','h_team','a_team'], columns='result', values='count', fill_value=0)
        # Reset the index and rename the columns
        chance_summary.reset_index(inplace=True)
        chance_summary.columns.name = None
        # result.rename(columns={'colY': 'round', 'hit': 'number_hits', 'miss': 'number_misses'}, inplace=True)
        # Add a new column that sums the 'left_hits' and 'right_hits' columns
        # result['shots'] = result['left_hits'] + result['right_hits']
        chance_summary['Total Shots']  = chance_summary.drop(['match_id','h_team','a_team'], axis=1).sum(axis=1)
        
        # Filter DataFrame to only include rows with 'hit'
        hits_df = df[df["result"] == "Goal"]
        # Group by 'round' (colY) and count 'hit' or 'miss' occurrences (colX)
        grouped = hits_df.groupby(['shotType', 'match_id','h_team','a_team']).size().reset_index(name='count')
        # Pivot the grouped DataFrame to have 'hit' and 'miss' counts per round
        goal_summary = grouped.pivot_table(index=['match_id','h_team','a_team'], columns='shotType', values='count', fill_value=0)
        # Reset the index and rename the columns
        goal_summary.reset_index(inplace=True)
        goal_summary.columns.name = None
        return chance_summary, goal_summary
    
    def fetch_player_shots_against_teams(self, FPL_ID, TEAM_AGAINST_ID):
        understat = UnderstatClient()
        player_shot_data = understat.player(player=str(self.grab_player_USID_from_FPLID(FPL_ID))).get_shot_data()
        df = pd.DataFrame(data=player_shot_data)
        team_dict = {}
        for index, row in df.iterrows():
            season = row['season']
            result  = row['result']
            shot_type = row['shotType']
            situation = row['situation']
            if row['h_a'] == 'h':
                team = row['a_team']
                if team not in team_dict:
                    team_dict[team] = {'h': 0, 'a': 0, 'seasons': {}}
                if season not in team_dict[team]['seasons']:
                    team_dict[team]['seasons'][season] = {'h': {}, 'a': {}}
                if shot_type not in team_dict[team]['seasons'][season]['h'].keys():
                    team_dict[team]['seasons'][season]['h'][shot_type] = []
                team_dict[team]['seasons'][season]['h'][shot_type].append((situation, result))
                if result == 'Goal':
                    team_dict[team]['h'] += 1
            elif row['h_a'] == 'a':
                team = row['h_team']
                if team not in team_dict:
                    team_dict[team] = {'h': 0, 'a': 0, 'seasons': {}}
                if season not in team_dict[team]['seasons']:
                    team_dict[team]['seasons'][season] = {'h': {}, 'a': {}}
                if shot_type not in team_dict[team]['seasons'][season]['a'].keys():
                    team_dict[team]['seasons'][season]['a'][shot_type] = []
                team_dict[team]['seasons'][season]['a'][shot_type].append((situation, result))
                if result == 'Goal':
                    team_dict[team]['a'] += 1

        # Create dataframe from team dictionary
        output_df = pd.DataFrame.from_dict(team_dict, orient='index').reset_index()
        output_df.columns = ['Team', 'h', 'a', 'full_summary']
        def order_season_by_year(season):
            return {year: season[year] for year in sorted(season.keys())}
        output_df['full_summary'] = output_df['full_summary'].apply(order_season_by_year)
        output_df = output_df.sort_values(by=['Team']).reset_index(drop=True)
        #Tally up against a team
        spreaded_stats = {}
        for szn,data in output_df.loc[output_df['Team'] == self.grab_team_USname_from_FPLID(TEAM_AGAINST_ID)]['full_summary'].iloc[0].items():
#             print(f'{szn}---> {data}')
            spreaded_stats[szn]={}
            for h_a, shotdata in data.items():
#                 print(h_a)
        #         print(shotdata)
                tally = {}
                for foot, datalist in shotdata.items():
                    tally[foot] = {'goals':[], 'misses':[]}
                    for shot in datalist:
                        if 'Goal' in shot:
                            tally[foot]['goals'].append(shot)
                        else:
                            tally[foot]['misses'].append(shot)
                spreaded_stats[szn][h_a] = tally
        return spreaded_stats
    
    def fetch_player_stats_against_teams(self, FPL_ID, TEAM_AGAINST_ID):
        understat = UnderstatClient()
        player_match_data = understat.player(player=str(self.grab_player_USID_from_FPLID(FPL_ID))).get_match_data()
        player_match_df = pd.DataFrame(data=player_match_data)
        player_match_df['h_a'] = ''
        player_team = self.grab_team_USname_from_FPLID(GrabFunctions.grab_player_team_id(FPL_ID))
        # Iterate over each row in df2
        for index, row in player_match_df.iterrows():
            season = row['season']
        #     team = ''

        #     # Find the corresponding team in df1 based on the season
        #     team_match = szn_df[szn_df['season'] == season]

        #     if not team_match.empty:
        #         team = team_match['team'].values[0]
            team = player_team

            # Check if the team is in 'h_team' or 'a_team' and update 'h_a' accordingly
            if team in row['h_team']:
                player_match_df.at[index, 'h_a'] = 'h'
            elif team in row['a_team']:
                player_match_df.at[index, 'h_a'] = 'a'
            else:
                player_match_df.at[index, 'h_a'] = 'NA'
#         print(player_match_df)
        team_dict = {}

        for index, row in player_match_df.iterrows():
            goals = int(row['goals'])
            if goals > 0:
                if row['h_a'] == 'h':
                    team = row['a_team']
                    season = row['season']
                    if team not in team_dict:
                        team_dict[team] = {'h': 0, 'a': 0, 'seasons': {}}
                    if season not in team_dict[team]['seasons']:
                        team_dict[team]['h'] += goals
                        team_dict[team]['a'] += 0
                        team_dict[team]['seasons'][season] = {'h': goals, 'a': 0}
                    else:
                        team_dict[team]['h'] += goals
                        team_dict[team]['seasons'][season]['h'] += goals
                elif row['h_a'] == 'a':
                    team = row['h_team']
                    season = row['season']
                    if team not in team_dict:
                        team_dict[team] = {'h': 0, 'a': 0, 'seasons': {}}
                    if season not in team_dict[team]['seasons']:
                        team_dict[team]['h'] += 0
                        team_dict[team]['a'] += goals
                        team_dict[team]['seasons'][season] = {'h': 0, 'a': goals}
                    else:
                        team_dict[team]['a'] += goals
                        team_dict[team]['seasons'][season]['a'] += goals
            else:
                if row['h_a'] == 'h':
                    team = row['a_team']
                elif row['h_a'] == 'a':
                    team = row['h_team']
                else:
                    continue
                season = row['season']
                if team not in team_dict:
                    team_dict[team] = {'h': 0, 'a': 0, 'seasons': {}}
                if season not in team_dict[team]['seasons']:
                    team_dict[team]['seasons'][season] = {'h': 0, 'a': 0}
#         print(team_dict)

        def calculate_coefficient_of_variation(goals, h_a):
            h_goals = [data['h'] for data in goals.values()]
            a_goals = [data['a'] for data in goals.values()]
            if len(goals) <= 1 or sum(h_goals) + sum(a_goals) == 0:
                return None
            if h_a == 'total': 
                mean_h = statistics.mean(h_goals)
                mean_a = statistics.mean(a_goals)
                mean = (mean_h + mean_a) / 2
                h_standard_deviation = statistics.stdev(h_goals)
                a_standard_deviation = statistics.stdev(a_goals)
                standard_deviation = (h_standard_deviation + a_standard_deviation) / 2
                coefficient_of_variation = (standard_deviation / mean) * 100
            elif h_a == 'h':
                if sum(h_goals) == 0:
                    return None
                mean_h = statistics.mean(h_goals)
                h_standard_deviation = statistics.stdev(h_goals)
                coefficient_of_variation = (h_standard_deviation / mean_h) * 100
            elif h_a == 'a':
                if sum(a_goals) == 0:
                    return None
                mean_a = statistics.mean(a_goals)
                a_standard_deviation = statistics.stdev(a_goals)
                coefficient_of_variation = (a_standard_deviation / mean_a) * 100      
            return coefficient_of_variation

        def calculate_goal_avg(goals):

            h_goals = [data['h'] for data in goals.values()]
            a_goals = [data['a'] for data in goals.values()]

            avg_goals = (sum(h_goals) + sum(a_goals)) / (2*len(goals))
            return avg_goals

        # Create dataframe from team dictionary
        output_df = pd.DataFrame.from_dict(team_dict, orient='index').reset_index()
        output_df.columns = ['Team', 'h', 'a', 'season']

        def order_season_by_year(season):
            return {year: season[year] for year in sorted(season.keys())}

        def calc_matches(szns):
            return 2*len(szns)

        output_df['season'] = output_df['season'].apply(order_season_by_year)

        output_df['Variation Coefficient (H)'] = output_df['season'].apply(calculate_coefficient_of_variation, args=('h',))
        output_df['Variation Coefficient (A)'] = output_df['season'].apply(calculate_coefficient_of_variation, args=('a',))
        output_df['Variation Coefficient (Total)'] = output_df['season'].apply(calculate_coefficient_of_variation, args=('total',))

        output_df['Avg Goals/match'] = output_df['season'].apply(calculate_goal_avg)

        output_df['Matches'] = output_df['season'].apply(calc_matches)

        output_df.sort_values(by=['Team']).reset_index(drop=True)
        output_df.sort_values(by=['Variation Coefficient (Total)'])
        
        output_df = output_df.loc[output_df['Team'] == self.grab_team_USname_from_FPLID(TEAM_AGAINST_ID)]
        
        return output_df.to_dict()
    
# Instantiate an object of the FPLDatabase class
UnderstatAnalysis = UnderstatProcessing()

# if __name__ == '__main__':
#     print('\nCompiling FPL team...')
#     df_out,df_top,df_sum=compile_fpl_team()
#     print('\nAnalyzing FPL team...')
#     df_fpl_team = compile_fpl_analyses(df_sum)
#     print('\nCompiling potential replacements...')
#     df_fpl_potentials = compile_potential_analyses(df_sum)
#     print('\nCondensing PRIME replacements...')
#     df_prime_potentials = condense_potentials(df_fpl_potentials)
#     print('\nAssigning genius teams to dataframe...')
#     genius_dict = compile_rivals_team(GENIUS_IDS)
#     print('\nDONE')
#     action_protocol(df_fpl_team,df_prime_potentials)
#     alert_players_with_blanks_dgws(df_fpl_team)
#     dictionary = upload_potentials(df_fpl_potentials,df_prime_potentials)
#     compile_returns(dictionary)
#     upload_genius_teams()
#     genius_changes()
#     genius_movements()
#     genius_matches(df_fpl_team)
#     genius_numbers()
    
     
#     # print('\nSimilar Players of ALL Genius IDs:')   
#     # for i in rivalry(GENIUS_IDS)[-1]:
#     #     name = grab_player_name(i)
#     #     print(f'{name}: {rivalry(GENIUS_IDS)[-1][i]}')
    
#     # team_visualizer(genius_dict[728021]['team'])
    
#     # print('\nSimilar Players of ALL Genius IDs:')
#     # rivalry(GENIUS_IDS)

#     # # show player #4's gameweek history
#     # out_df = get_gameweek_history(4)[
#     #     [
#     #         'round',
#     #         'total_points',
#     #         'minutes',
#     #         'goals_scored',
#     #         'assists'
#     #     ]
#     # ].head()
    
#     # # show player #1's gameweek history
#     # out2_df = get_season_history(1)[
#     #     [
#     #         'season_name',
#     #         'total_points',
#     #         'minutes',
#     #         'goals_scored',
#     #         'assists'
#     #     ]
#     # ].head(10)