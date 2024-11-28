# from src.functions.helper_fns import calculate_mean_std_dev, progress_bar_update
from src.functions.helper_utils import initialize_local_data

from src.functions.raw_data_fetcher import FPLFetcher, UnderstatFetcher
# from src.functions.notebook_utils import setup_logger, log_timing

# logger = setup_logger(__name__)

from tqdm.notebook import tqdm_notebook
from understatapi import UnderstatClient
from collections import defaultdict, Counter
import datetime
# from tqdm.notebook import tqdm_notebook
import pandas as pd

import nest_asyncio
nest_asyncio.apply()

class FPLRawDataCompiler(FPLFetcher):
    def __init__(self):
        super().__init__()
        print("Building master datasets from raw data via FPL API.")
        self.master_summary = self._build_master_summary()
        # logger.info(f"Testing logger: {self.master_summary}")
        initialize_local_data(self, [
            {
                "function": self.convert_fpl_dict_to_tabular,
                "attribute_name": "master_summary_tabular",
                "file_name": f"master_summary_{self.season_year_span_id}",
                "export_path": f"cached_data/fpl/{self.season_year_span_id}",
            }
        ], update_and_export_data = True)
        # self.master_summary = self.build_master_summary()
        # self.total_summary = None
        self.players_raw = pd.json_normalize(self.raw_data['elements'])
        self.teams_raw = pd.json_normalize(self.raw_data['teams'])
        self.positions_raw = pd.json_normalize(self.raw_data['element_types'])
        self.team_info_raw = self._get_team_info()
        # self.total_summary = asyncio.run(self.compile_dataframes())
        self.league_data = self._initialize_league_data()
    
    def _get_team_info(self):
        list_of_dicts = [x for x in self.teams_raw]
        return pd.DataFrame.from_records(list_of_dicts)

#================================================================================================================================================================
#===================================================================== BUILD MASTER SUMMARY =====================================================================
#================================================================================================================================================================
    # @log_timing
    def _build_master_summary(self):
        print("Building master summary.")
        id_values = sorted(self.player_ids)
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
        bootstrap_dict = self.raw_data['elements']
        for player_id in consolidated_dict.keys():
            for raw_data_col in ['team', 'element_type', 'first_name', 'second_name', 'web_name', 'id']:
                raw_data_val = next((x[raw_data_col] for x in iter(bootstrap_dict) if x['id'] == player_id))
                consolidated_dict[player_id][raw_data_col] = raw_data_val
        
        #Add additional info from teams
        bootstrap_teams = self.raw_data['teams']
        for player_id, player_data in consolidated_dict.items():
            team_id = player_data["team"]
            for raw_data_col in ['short_name', 'name', 'strength_overall_home', 'strength_overall_away', 'strength_attack_home', 'strength_attack_away', 'strength_defence_home', 'strength_defence_away']:
                raw_data_val = next((x[raw_data_col] for x in iter(bootstrap_teams) if x['id'] == team_id))
                consolidated_dict[player_id][f'team_{raw_data_col}'] = raw_data_val
        
        #Add additional info from positions
        bootstrap_pos = self.raw_data['element_types']
        for player_id, player_data in consolidated_dict.items():
            pos_id = player_data["element_type"]
            for raw_data_col in ['singular_name_short']:
                raw_data_val = next((x[raw_data_col] for x in iter(bootstrap_pos) if x['id'] == pos_id))
                consolidated_dict[player_id][f'pos_{raw_data_col}'] = raw_data_val

        return {player_id: dict(data) for player_id, data in consolidated_dict.items()}

    def grab_full_history(self):
        raw_data = self.full_element_summary
        return [gw_data for player_id in sorted(self.player_ids) for gw_data in raw_data[player_id]['history']]

    def convert_fpl_dict_to_tabular(self):
        df_data = []
        for _, player_data in self.master_summary.items():
            org_data= {}
            key_info_to_append = []
            for col_name, col_data in player_data.items():
                if isinstance(col_data, list):
                    if all(isinstance(item, (str, int, float)) for item in col_data):
                        continue
                    if all(isinstance(item, tuple) and len(item) == 2 and all(isinstance(sub_item, (str, int, float)) for sub_item in item) for item in col_data):
                        # print(col_name)
                        for gw, param_val in col_data:
                            org_data.setdefault(gw, {}).setdefault(col_name, param_val)
                elif isinstance(col_data, (str, int, float)):
                    key_info_to_append.append((col_name, col_data))
            flattened_org_data = [{**value, 'round': key} for key, value in org_data.items()]
            df_data.extend(flattened_org_data)
            for data_per_gw in df_data:
                for append_col, append_data in key_info_to_append:
                    data_per_gw[append_col] = append_data
        return df_data

    def _initialize_league_data(self):
        
        pseudo_league_data = [
            {"name": "beacon_aggregate", "symbol": "☆", "id": None, "custom_info": None},
            {"name": "beacon_1k", "symbol": "☆₁ₖ", "id": None, "custom_info": {"rank": 1000}},
            {"name": "beacon_10k", "symbol": "☆₁₀ₖ", "id": None, "custom_info": {"rank": 10000}},
            {"name": "beacon_100k", "symbol": "☆₁₀₀ₖ", "id": None, "custom_info": {"rank": 100000}}
        ]
        specified_league_data = [
            {
                "name": str(league_data["id"]),
                "symbol": league_data["symbol"],
                "id": league_data["id"],
                "custom_info": None,
                }
            for league_data in self.config_data["fpl_id_data"]["personal_league_ids"]
        ]
                
        personal_user_name = self.fetch_player_fpl_name(self._get_personal_fpl_id())
        points_window = 50

        grouped_user_ids_by_league={}
        for league_data in pseudo_league_data:
            if league_data["custom_info"] is not None:
                ids_that_cross_rank = [idx for idx in self._get_beacon_ids() if self.fetch_player_overall_fpl_rank(idx) <= league_data["custom_info"]["rank"]]
                grouped_user_ids_by_league[league_data["name"]] = ids_that_cross_rank
            elif league_data["name"] == "beacon_aggregate":
                grouped_user_ids_by_league[league_data["name"]] = [idx for idx in self._get_beacon_ids()]

        for rival_league_data in specified_league_data:
            league_r = self.fetch_data_from_api(f'leagues-classic/{rival_league_data["id"]}/standings/')
            league_players = league_r["standings"]["results"]
            my_rank, my_points = [(x["rank"], x["total"]) for x in league_players if x["player_name"] == personal_user_name][0]
            user_ids = [x["entry"] for x in league_players if ((x["rank"] < my_rank) or (x["total"] > my_points - points_window and x["rank"] > my_rank))]
            grouped_user_ids_by_league[rival_league_data["name"]] = user_ids

        agg_league_data = pseudo_league_data + specified_league_data

        def compile_ownership(league_info):

            def fetch_latest_picks(user_id):
                r = self.fetch_fpl_data(user_id)["latest_picks"]
                return [x["element"] for x in r["picks"]]

            user_ids = grouped_user_ids_by_league[league_info["name"]]
            league_info["summary"] = {
                "rivals": user_ids,
                "players": dict(Counter(player_id for user_id in user_ids for player_id in fetch_latest_picks(user_id)))
            }
            return league_info

        return [compile_ownership(league_info.copy()) for league_info in agg_league_data]
    
class UnderstatRawDataCompiler(UnderstatFetcher):
    def __init__(self, fpl_helper_fns, update_and_export_data):
        self.find_best_match_fpl = fpl_helper_fns.find_best_match
        self.grab_player_name_fpl = fpl_helper_fns.grab_player_name_fpl
        self.raw_data_fpl = fpl_helper_fns.raw_data
        super().__init__(fpl_helper_fns, update_and_export_data)
        print("Mapping FPL to understat data.")
        initialize_local_data(self, [
            {
                "function": self._match_fpl_to_understat_teams,
                "attribute_name": "understat_to_fpl_team_data",
                "file_name": "understat_to_fpl_team_data",
                "export_path": f"cached_data/understat/{fpl_helper_fns.season_year_span_id}/team",
             },
            {
                "function": self._match_fpl_to_understat_players,
                "attribute_name": "understat_to_fpl_player_data",
                "file_name": "understat_to_fpl_player_data",
                "export_path": f"cached_data/understat/{fpl_helper_fns.season_year_span_id}/players",
                "update_bool_override": True,
             },
            {
                "function": self._build_understat_player_shot_data,
                "attribute_name": "understat_player_shot_data",
                "file_name": "player_shot_data",
                "export_path": f"cached_data/understat/{fpl_helper_fns.season_year_span_id}/players"
             },
            {
                "function": self._build_understat_player_match_data,
                "attribute_name": "understat_player_match_data",
                "file_name": "player_match_data",
                "export_path": f"cached_data/understat/{fpl_helper_fns.season_year_span_id}/players"
             }
        ], update_and_export_data)

#================================================================================================================================================================
#===================================================================== MATCH FPL TO UNDERSTAT ===================================================================
#================================================================================================================================================================

    def _match_fpl_to_understat_teams(self):
        teams = self.raw_data_fpl['teams']
        fpl_data = [{**{param_str: param_val for param_str, param_val in team.items() if param_str in ['id', 'name']}} for team in teams]

        understat_nums_unsorted = [{
            "id": int(x['id']), 
            "name": x['title']
        } 
        for x in self.understat_team_data_raw.values()]
        understat_data = sorted(understat_nums_unsorted, key=lambda x: x["name"])

        return [{
            "fpl": d1, 
            "understat": d2
        } 
        for d1, d2 in zip(fpl_data, understat_data)]
    
    def _match_fpl_to_understat_players(self):

        matched_data = []
        for understat_player_info in self.understat_player_data_raw:
            team_name_list = understat_player_info["team_title"].split(",") #Account for cases where player switched teams in PL
            # print(f"{team_name_list}")
            fpl_team_id_list = [next((x["fpl"]["id"] for x in iter(self.understat_to_fpl_team_data) if x["understat"]["name"] == team_name), 'null') for team_name in team_name_list]
            matched_fpl_player_id = self.find_best_match_fpl(understat_player_info["player_name"], fpl_team_id_list)
            if matched_fpl_player_id is not None:
                matched_data.append({
                    "fpl": {
                        "id": int(matched_fpl_player_id),
                        "name": self.grab_player_name_fpl(int(matched_fpl_player_id)),
                    },
                    "understat": {
                        "id": int(understat_player_info["id"]),
                        "name": understat_player_info["player_name"],
                    }
                })
        return matched_data
    
        
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
            understat_id = next(x["understat"]["id"] for x in iter(self.understat_to_fpl_player_data) if x["fpl"]["id"] == int(fpl_player_id))
            all_player_shot_data[int(fpl_player_id)] = self.understat_player_shot_data_raw.get(f"{understat_id}")
        return all_player_shot_data

    def _compile_understat_player_shot_data(self):

        all_matched_fpl_player_ids = [x['fpl']['id'] for x in self.understat_to_fpl_player_data]
        all_player_shot_data = {}
        for fpl_player_id in all_matched_fpl_player_ids:
            player_shot_data = self.understat_player_shot_data_raw[fpl_player_id]

            season_threshold_start_str = next(x['deadline_time'] for x in iter(self.raw_data_fpl['events']))
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

            all_player_shot_data[int(fpl_player_id)] = pd.merge(chance_summary, goal_summary, on=['match_id','h_team','a_team'], how='outer').to_dict(orient='records')
        return all_player_shot_data
    
    def _build_understat_player_match_data(self):

        all_matched_fpl_player_ids = [x['fpl']['id'] for x in self.understat_to_fpl_player_data]
        all_player_match_data = {}
        for fpl_player_id in tqdm_notebook(all_matched_fpl_player_ids, desc = "Building understat player match data"):
            understat_id = next(x["understat"]["id"] for x in iter(self.understat_to_fpl_player_data) if x["fpl"]["id"] == int(fpl_player_id))
            all_player_match_data[int(fpl_player_id)] = self.understat_player_match_data_raw.get(f"{understat_id}")
        return all_player_match_data