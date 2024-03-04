import pandas as pd
import numpy as np

class DataAnalytics:
    def __init__(self, api_parser, data_parser, helper_fns):
        self.api_parser = api_parser
        self.data_parser = data_parser
        self.helper_fns = helper_fns
        self.personal_team_data = self.compile_personal_team_data()
        self.replacement_players = self.compile_prospects()
        self.beacon_effective_ownership = self.generate_beacon_effective_ownership()
    
    def compile_personal_team_data(self):
        r = self.api_parser.personal_fpl_raw_data["latest_picks"]
        fpl_team_ids = set([x["element"] for x in r["picks"]])
        return self.helper_fns.compile_player_data(fpl_team_ids)

    def score_players_on_form(self, list_of_ids: list) -> dict:
        
        def convert_to_binary(points: list):
            return [2 if x > 9 else 1 if x > 3 and x <= 9 else 0 for x in points]
        
        full_data = {}
        for idx in list_of_ids:
            full_data[idx] = convert_to_binary([x for x in self.helper_fns.grab_player_hist(idx)])

        time_periods = [6, 4, 2] # Define the number of time periods to consider
        weights = [0.3, 0.3, 0.4]  # Weights for each time period

        player_mean_scores = {} # Calculate mean score for each player for each time period
        for player, categories in full_data.items():
            mean_scores = [np.mean(categories[-period:]) for period in time_periods]
            player_mean_scores[player] = mean_scores
        player_ratings = {}
        for player, mean_scores in player_mean_scores.items():
            weighted_average = np.average(mean_scores, weights=weights)
            player_ratings[player] = {'score': round(weighted_average,2)}
        return dict(sorted(player_ratings.items(), key=lambda x: x[1]['score'], reverse=True))

    def score_players_on_fixtures(self, list_of_ids: list) -> dict:
        
        gameweek_data = self.helper_fns.grab_upcoming_fixtures(list_of_ids)
        full_data = {key: {'opponent_teams': [d['opponent_team'] for d in value if d['opponent_team'] is not None], 
            'fdrs': [self.helper_fns.team_rank(d['opponent_team']) for d in value if d['opponent_team'] is not None], 
            'is_home': [d['is_home'] for d in value if d['is_home'] is not None]} for key, value in gameweek_data.items()}
        
        player_ratings = {}
        for player_id, player_fixture_data in full_data.items():
        
            home_away_info = player_fixture_data['is_home']
            difficulty_ratings = player_fixture_data['fdrs']

            # Weighing factors for the rating
            difficulty_weights = {1: 4.5, 2: 4, 3: 3, 4: 1.5, 5: 0.5}  # Higher difficulty means a tougher match
            home_weight = 1.2  # Weight for home games

            # Calculate the weighted sum of difficulty ratings based on home/away
            weighted_sum = sum(difficulty_weights[rating] * (home_weight if location == 'H' else 1)
                            for rating, location in zip(difficulty_ratings, home_away_info))
            
            # Calculate the average weighted difficulty rating
            average_weighted_difficulty = weighted_sum / len(difficulty_ratings)

            # Normalize the average weighted difficulty to get the rating in the range of 1 to 10
            min_weighted_difficulty = min(difficulty_weights.values())
            max_weighted_difficulty = max(difficulty_weights.values())
            normalized_rating = ((average_weighted_difficulty - min_weighted_difficulty)
                                / (max_weighted_difficulty - min_weighted_difficulty)) * 9 + 1

            # Ensure the rating is within the valid range of 1 to 10
            player_ratings[int(player_id)] = {'score': round(max(1, min(normalized_rating, 10)), 3)}
        return dict(sorted(player_ratings.items(), key=lambda x: x[1]['score'], reverse=True))


    def apply_scores_and_compile_prospects(self, list_of_ids: list):
        form_score_data = self.score_players_on_form(self.api_parser.player_ids)
        fixture_score_data = self.score_players_on_fixtures(self.api_parser.player_ids)

        df = pd.DataFrame.from_dict({
                player_id: {
                    'form_score': form_score_data[player_id]['score'],
                    'fixture_score': fixture_score_data[player_id]['score'],
                    'minutes_score': fixture_score_data[player_id]['score']
                } 
                for player_id in list_of_ids
            },
            orient='index').reset_index()
        
        df = df.rename(columns={'index': 'player_id'})
        return df.sort_values(by=['form_score'], ascending=False)
    
    def compile_prospects(self, list_of_ids: list = None):
        if list_of_ids is None: list_of_ids = self.api_parser.player_ids
        df = self.apply_scores_and_compile_prospects(list_of_ids)
        return df.loc[df['form_score'] > 0.5]['player_id'].to_list()

#================================================================================================================================================================
#================================================================ BUILD OWNERSHIP FROM BEACON IDS ===============================================================
#================================================================================================================================================================

    def generate_beacon_effective_ownership(self):
        id_count = self.api_parser.rival_stats['id_count']
        id_dict = {}
        for i in id_count:
            pos = self.helper_fns.grab_player_pos(i)
            id_dict.setdefault(pos, []).append((i, id_count[i]))
        outlist = sorted(id_dict.items(), key=lambda x:x[1], reverse=True)
        beacon_eff_own_dict = {}
        for line in outlist:
            for tup in line[1]:
                beacon_eff_own_dict[tup[0]] = tup[1]
        return beacon_eff_own_dict
