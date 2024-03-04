from src.functions.helper_fns import calculate_mean_std_dev, progress_bar_update

from collections import defaultdict, Counter
import pandas as pd
import nest_asyncio
nest_asyncio.apply()

class RawDataCompiler:
    def __init__(self, api_parser):
        self.api_parser = api_parser
        self.raw_data = api_parser.raw_data
        self.master_summary = self.build_master_summary()
        self.players = pd.json_normalize(self.raw_data['elements'])
        self.teams = pd.json_normalize(self.raw_data['teams'])
        self.positions = pd.json_normalize(self.raw_data['element_types'])
        self.team_info = self.get_team_info()
        self.league_data = self.initialize_league_data()
    
    def get_team_info(self):
        list_of_dicts = [x for x in self.teams]
        return pd.DataFrame.from_records(list_of_dicts)

#================================================================================================================================================================
#===================================================================== BUILD MASTER SUMMARY =====================================================================
#================================================================================================================================================================

    def grab_full_history(self):
        raw_data = self.api_parser.full_element_summary
        return [gw_data for player_id in sorted(self.api_parser.player_ids) for gw_data in raw_data[player_id]['history']]

    def build_master_summary(self):
        print("Building master summary ...")
        id_values = sorted(self.api_parser.player_ids)
        elem_summaries = self.grab_full_history()
        rel_elem_summaries = [x for x in elem_summaries if x['element'] in id_values]
        rel_elem_summaries = sorted(rel_elem_summaries, key=lambda x: x['round'])

        consolidated_dict = defaultdict(lambda: defaultdict(list))
        
        #Compile from element summaries
        is_numeric = lambda s: s.replace('.', '', 1).isdigit() if isinstance(s, str) else isinstance(s, (int, float))
        for num_iter, entry in enumerate(rel_elem_summaries):
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
    
    def initialize_league_data(self):
        
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
            for league_data in self.api_parser.config_data["fpl_id_data"]["personal_league_ids"]
        ]
                
        personal_user_name = self.api_parser.fetch_player_fpl_name(self.api_parser.get_personal_fpl_id())
        points_window = 50

        grouped_user_ids_by_league={}
        for league_data in pseudo_league_data:
            if league_data["custom_info"] is not None:
                ids_that_cross_rank = [idx for idx in self.api_parser.get_beacon_ids() if self.api_parser.fetch_player_overall_fpl_rank(idx) <= league_data["custom_info"]["rank"]]
                grouped_user_ids_by_league[league_data["name"]] = ids_that_cross_rank
            elif league_data["name"] == "beacon_aggregate":
                grouped_user_ids_by_league[league_data["name"]] = [idx for idx in self.api_parser.get_beacon_ids()]

        for rival_league_data in specified_league_data:
            league_r = self.api_parser.fetch_data_from_api(f'leagues-classic/{rival_league_data["id"]}/standings/')
            league_players = league_r["standings"]["results"]
            my_rank, my_points = [(x["rank"], x["total"]) for x in league_players if x["player_name"] == personal_user_name][0]
            user_ids = [x["entry"] for x in league_players if ((x["rank"] < my_rank) or (x["total"] > my_points - points_window and x["rank"] > my_rank))]
            grouped_user_ids_by_league[rival_league_data["name"]] = user_ids

        agg_league_data = pseudo_league_data + specified_league_data

        def compile_ownership(league_info):

            def fetch_latest_picks(user_id):
                r = self.api_parser.fetch_fpl_data(user_id)["latest_picks"]
                return [x["element"] for x in r["picks"]]

            user_ids = grouped_user_ids_by_league[league_info["name"]]
            league_info["summary"] = {
                "rivals": user_ids,
                "players": dict(Counter(player_id for user_id in user_ids for player_id in fetch_latest_picks(user_id)))
            }
            return league_info

        return [compile_ownership(league_info.copy()) for league_info in agg_league_data]