from datetime import datetime, timezone
from dateutil import parser
import pandas as pd
import math
from tqdm.notebook import tqdm_notebook
from src.functions.helper_fns import *

import asyncio
import aiohttp
import nest_asyncio
nest_asyncio.apply()

class DataParser:
    def __init__(self, api_parser):
        self.api_parser = api_parser
        self.raw_data = api_parser.raw_data
        self.total_summary = None
        self.players = pd.json_normalize(self.raw_data['elements'])
        self.teams = pd.json_normalize(self.raw_data['teams'])
        self.positions = pd.json_normalize(self.raw_data['element_types'])
        self.team_info = self.get_team_info()
        asyncio.run(self.compile_dataframes())
    
    def get_team_info(self):
        teamdata = self.raw_data['teams']
        list_of_dicts = [x for x in teamdata]
        return pd.DataFrame.from_records(list_of_dicts)

    async def fetch(session, url):
        async with session.get(url) as response:
            return await response.json()
    
    async def fetch_all(urls):
        async with aiohttp.ClientSession() as session:
            tasks = []
            for url in urls:
                tasks.append(fetch(session, url))
            return await asyncio.gather(*tasks)
    
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
                tasks = [self.fetch_gameweek_history(player_id,session) for player_id in total_summary['id_player']]
                gameweek_histories = await asyncio.gather(*tasks)

            def process_returnhist(dfx):
                return [2 if (i > 9) else 1 if (i > 3 and i <= 9) else 0 for i in dfx['total_points']]

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

####################################################################################################################

