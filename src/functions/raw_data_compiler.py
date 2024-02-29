# from src.config import config
import pandas as pd
from tqdm.notebook import tqdm_notebook
from src.functions.helper_fns import calculate_mean_std_dev
from collections import defaultdict

import asyncio
import aiohttp
import nest_asyncio
nest_asyncio.apply()

class RawDataCompiler:
    def __init__(self, api_parser):
        self.api_parser = api_parser
        self.raw_data = api_parser.raw_data
        self.master_summary = self.build_master_summary()
        self.total_summary = None
        self.players = pd.json_normalize(self.raw_data['elements'])
        self.teams = pd.json_normalize(self.raw_data['teams'])
        self.positions = pd.json_normalize(self.raw_data['element_types'])
        self.team_info = self.get_team_info()
        self.total_summary = asyncio.run(self.compile_dataframes())
        self.effective_ownership = self.initialize_effective_ownership()
    
    def get_team_info(self):
        teamdata = self.raw_data['teams']
        list_of_dicts = [x for x in teamdata]
        return pd.DataFrame.from_records(list_of_dicts)

#======================================= BUILD MASTER SUMMARY ====================================================
    
    def grab_full_history(self):
        raw_data = self.api_parser.full_element_summary
        return [gw_data for player_id in sorted(self.api_parser.player_ids) for gw_data in raw_data[player_id]['history']]

    def build_master_summary(self):
        print("Building master summary...")
        id_values = sorted(self.api_parser.player_ids)
        elem_summaries = self.grab_full_history()
        rel_elem_summaries = [x for x in elem_summaries if x['element'] in id_values]
        rel_elem_summaries = sorted(rel_elem_summaries, key=lambda x: x['round'])

        consolidated_dict = defaultdict(lambda: defaultdict(list))
        
        #Compile from element summaries
        is_numeric = lambda s: s.replace('.', '', 1).isdigit() if isinstance(s, str) else isinstance(s, (int, float))
        for entry in rel_elem_summaries:
            player_id = entry['element']
            round_num = entry['round']
            entry_data = {k: v for k, v in entry.items() if k not in ['element', 'round']}
            for key, value in entry_data.items():
                if is_numeric(value):
                    value = round(float(value),1)
                consolidated_dict[player_id][key].append(( round_num, value ))
            consolidated_dict[player_id]['round'].append(round_num)
            
        #Add additional info from bootstrap raw data
        bootstrap_dict = self.api_parser.raw_data['elements']
        for player_id in consolidated_dict.keys():
            for raw_data_col in ['team', 'element_type', 'first_name', 'second_name', 'web_name']:
                raw_data_val = next((x[raw_data_col] for x in iter(bootstrap_dict) if x['id'] == player_id))
                consolidated_dict[player_id][raw_data_col] = raw_data_val
        
        #Add additional info from teams
        bootstrap_teams = self.api_parser.raw_data['teams']
        for player_id, player_data in consolidated_dict.items():
            team_id = player_data["team"]
            for raw_data_col in ['short_name', 'name', 'strength_overall_home', 'strength_overall_away', 'strength_attack_home', 'strength_attack_away', 'strength_defence_home', 'strength_defence_away']:
                raw_data_val = next((x[raw_data_col] for x in iter(bootstrap_teams) if x['id'] == team_id))
                consolidated_dict[player_id][f'team_{raw_data_col}'] = raw_data_val
        
        #Add additional info from positions
        bootstrap_pos = self.api_parser.raw_data['element_types']
        for player_id, player_data in consolidated_dict.items():
            pos_id = player_data["element_type"]
            for raw_data_col in ['singular_name_short']:
                raw_data_val = next((x[raw_data_col] for x in iter(bootstrap_pos) if x['id'] == pos_id))
                consolidated_dict[player_id][f'pos_{raw_data_col}'] = raw_data_val

        return {player_id: dict(data) for player_id, data in consolidated_dict.items()}

######################################################################################################################
    # async def fetch(session, url):
    #     async with session.get(url) as response:
    #         return await response.json()

    async def fetch_gameweek_history(self, player_id, session):
        if player_id in self.api_parser.raw_element_summary:
            player_history = self.api_parser.raw_element_summary[player_id]['history']
            return player_history

        player_data = await self.api_parser.fetch_element_summaries(player_id, session)
        player_history = player_data['history']
        return player_history

    async def compile_dataframes(self):
        self.players = self.players.merge(
            self.teams[['id', 'name']],
            left_on='team',
            right_on='id',
            suffixes=['_player', None]
        ).drop(['team', 'id'], axis=1)

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

        points = await fetch_all_gameweek_histories(player_ids)
        total_summary = self.compile_total_df(points)
        return total_summary

    def compile_total_df(self, points):
        self.total_points_df = pd.concat([pd.DataFrame(x) for x in points])
        self.points = self.players[['id_player', 'web_name','singular_name_short']].merge(
            self.total_points_df,
            left_on='id_player',
            right_on='element'
        )

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
        overlapping_columns = self.partial_summary.columns.intersection(self.players.columns).tolist()    
        total_summary = pd.merge(self.partial_summary,self.players,on=overlapping_columns)

        async def compile_summary():
            async with aiohttp.ClientSession() as session:
                tasks = [self.fetch_gameweek_history(x['id'],session) for x in self.api_parser.raw_data['elements']]
                gameweek_histories = await asyncio.gather(*tasks)

            def process_binary_returns(dfx):
                return [2 if (i > 9) else 1 if (i > 3 and i <= 9) else 0 for i in dfx['total_points']]

            def process_fulltime_fullhour(dfx):
                fulltime = [e for e in dfx['minutes'][-6:] if e == 90]
                fullhour = [e for e in dfx['minutes'][-6:] if e >= 60]
                return len(fulltime), len(fullhour), len(dfx['minutes'][-6:])
            
            def calc_rolling_avg(lookback: int, dfx: pd.DataFrame):
                return sum(dfx[-lookback:]) / len(dfx[-lookback:])

            self.master_summary_temp = []
            for num, idx in enumerate(tqdm_notebook(total_summary['id_player'], desc="Building master dataframe")):
                try:
                    player_data_history = gameweek_histories[num]
                    for player_gw_data in player_data_history:
                        self.master_summary_temp.append(player_gw_data)
                    
                    player_data_df = pd.DataFrame(data=player_data_history).copy()
                    existing_cols = player_data_df.columns.tolist()

                    for param in existing_cols[1:]:
                        p1, p2 = param, param
                        if param == 'total_points':
                            p1 = 'history'
                        elif param == 'value':
                            p1 = 'changing_value'
                        ref_list = player_data_df[p2].tolist()
                        converted_ref_list = []
                        for elem in ref_list:
                            try:
                                converted_ref_list.append(float(elem))
                            except:
                                converted_ref_list.append(elem)
                        total_summary.at[[num],p1] = pd.Series([converted_ref_list],index = [num])
                    returnhist = process_binary_returns(player_data_df)

                    mean_og, stdev_og = calculate_mean_std_dev(player_data_df['total_points'])
                    mean_x, stdev_x = calculate_mean_std_dev(returnhist)
                    last6_mean_x, last3_mean_x, last2_mean_x = calc_rolling_avg(6,returnhist), calc_rolling_avg(3,returnhist), calc_rolling_avg(2,returnhist)

                    fulltime_count, fullhour_count, total_minutes = process_fulltime_fullhour(player_data_df)
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
        total_summary.rename(columns = {'singular_name_short':'position'}, inplace = True)
        if not total_summary.empty:
            total_summary.to_csv('../../stats/total_summary.csv', index=False)
            print('Exported total_summary!')
        return total_summary
######################################################################################################################    
    
    def initialize_effective_ownership(self):    
        rival_league_ids = [x for x in self.api_parser.get_league_ids()]
        rank_thresholds = [{"name": "beacon_1k", "rank": 1000}, {"name": "beacon_10k", "rank": 10000}, {"name": "beacon_100k", "rank": 100000}]

        def rank_finder(ID):
            r = self.api_parser.fetch_data_from_api(f'entry/{ID}/event/{self.api_parser.latest_gw}/picks/')
            return r['entry_history']['overall_rank']
        grouped_user_ids_by_league={}
        for rank_thresh in rank_thresholds:
            ids_that_cross_rank = [idx for idx in self.api_parser.get_beacon_ids() if rank_finder(idx) <= rank_thresh["rank"]]
            grouped_user_ids_by_league[rank_thresh["name"]] = ids_that_cross_rank
        for rival_league_id in rival_league_ids:
            league_r = self.api_parser.fetch_data_from_api(f'leagues-classic/{rival_league_id}/standings/')
            league_players = league_r['standings']['results']
            my_rank, my_points = [(x['rank'],x['total']) for x in league_players if x['player_name'] == 'Javaid Baksh'][0]
            user_ids = [x['entry'] for x in league_players if ((x['rank'] < my_rank) or (x['total'] > my_points - 50 and x['rank'] > my_rank))]
            grouped_user_ids_by_league[str(rival_league_id)] = user_ids
        grouped_user_ids_by_league['beacon_aggregate'] = [idx for idx in self.api_parser.get_beacon_ids()]

        def dict_counter(dictx, listx, rivalx):
            for idx in listx:
                if idx not in dictx[rivalx]['players'].keys():
                    dictx[rivalx]['players'][idx] = 1
                else:
                    dictx[rivalx]['players'][idx] += 1
            return

        counter_dict = {}
        for pseudo_league_name, user_ids in grouped_user_ids_by_league.items():
            counter_dict[pseudo_league_name] = {'rivals':len(user_ids),'players':{}}
            for user_id in user_ids:
                r = self.api_parser.fetch_data_from_api(f'entry/{user_id}/event/{self.api_parser.latest_gw}/picks/')
                player_ids = [x['element'] for x in r['picks']]
                dict_counter(counter_dict, player_ids, pseudo_league_name)
            counter_dict[pseudo_league_name]['players'] = dict(sorted(counter_dict[pseudo_league_name]['players'].items(), key=lambda item: item[1], reverse=True))
        return counter_dict