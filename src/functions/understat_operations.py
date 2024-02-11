from understatapi import UnderstatClient
import pandas as pd
# from fuzzywuzzy import fuzz
# from fuzzywuzzy import process
import numpy as np
from datetime import datetime
import statistics
from prettytable import PrettyTable

class UnderstatProcessing:
    
    metric_thresholds = {
        'ict': (3.5, 5.0, 7.5),
        'xGI': (0.2, 0.5, 0.9),
        'history': (4.0, 6.0, 9.0),
        'bps': (14.0, 21.0, 29.0),
        'xGC': (1.5,1.0,0.5),
    }

    def __init__(self, api_parser, data_analytics, fpl_helper_fns, und_helper_fns):
        self.api_parser = api_parser
        self.data_analytics = data_analytics
        self.und_helper_fns = und_helper_fns
        self.fpl_helper_fns = fpl_helper_fns
        
    def fetch_team_xg_stats(self,FPL_ID):
        """
        Function returns xG of a specified team against all teams so far. Use fetch team all stats for expanded view
        """
        team_name = [x[1][1] for x in self.und_helper_fns.team_nums if str(x[0][0]) == str(FPL_ID)][0]
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
        for _, team_data in self.und_helper_fns.new_team_data.items():
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
        for _, team_data in self.und_helper_fns.new_team_data.items():
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
        player_shot_data = understat.player(player=str(self.und_helper_fns.grab_player_USID_from_FPLID(FPL_ID))).get_shot_data()
        df = pd.DataFrame(data=player_shot_data)
        season_start_time = [x['deadline_time'] for x in self.api_parser.raw_data['events']][0]
        parsed_time = datetime.fromisoformat(season_start_time[:-1])
        formatted_string = parsed_time.strftime("%Y-%m-%d")
        date_string = formatted_string
        date_format = "%Y-%m-%d"
        df["date"] = pd.to_datetime(df["date"])
        df = df.loc[df['date']>=datetime.strptime(date_string, date_format)]
        grouped = df.groupby(['result', 'match_id','h_team','a_team']).size().reset_index(name='count')
        chance_summary = grouped.pivot_table(index=['match_id','h_team','a_team'], columns='result', values='count', fill_value=0)
        chance_summary.reset_index(inplace=True)
        chance_summary.columns.name = None
        chance_summary['Total Shots']  = chance_summary.drop(['match_id','h_team','a_team'], axis=1).sum(axis=1)
        
        hits_df = df[df["result"] == "Goal"]
        grouped = hits_df.groupby(['shotType', 'match_id','h_team','a_team']).size().reset_index(name='count')
        goal_summary = grouped.pivot_table(index=['match_id','h_team','a_team'], columns='shotType', values='count', fill_value=0)
        goal_summary.reset_index(inplace=True)
        goal_summary.columns.name = None
        return chance_summary, goal_summary
    
    def fetch_player_shots_against_teams(self, FPL_ID, TEAM_AGAINST_ID):
        understat = UnderstatClient()
        player_shot_data = understat.player(player=str(self.und_helper_fns.grab_player_USID_from_FPLID(FPL_ID))).get_shot_data()
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

        output_df = pd.DataFrame.from_dict(team_dict, orient='index').reset_index()
        output_df.columns = ['Team', 'h', 'a', 'full_summary']
        def order_season_by_year(season):
            return {year: season[year] for year in sorted(season.keys())}
        output_df['full_summary'] = output_df['full_summary'].apply(order_season_by_year)
        output_df = output_df.sort_values(by=['Team']).reset_index(drop=True)
        spreaded_stats = {}
        for szn,data in output_df.loc[output_df['Team'] == self.und_helper_fns.grab_team_USname_from_FPLID(TEAM_AGAINST_ID)]['full_summary'].iloc[0].items():
            spreaded_stats[szn]={}
            for h_a, shotdata in data.items():
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
        player_match_data = understat.player(player=str(self.und_helper_fns.grab_player_USID_from_FPLID(FPL_ID))).get_match_data()
        player_match_df = pd.DataFrame(data=player_match_data)
        player_match_df['h_a'] = ''
        player_team = self.und_helper_fns.grab_team_USname_from_FPLID(self.fpl_helper_fns.grab_player_team_id(FPL_ID))
        for index, row in player_match_df.iterrows():
            season = row['season']
            team = player_team

            if team in row['h_team']:
                player_match_df.at[index, 'h_a'] = 'h'
            elif team in row['a_team']:
                player_match_df.at[index, 'h_a'] = 'a'
            else:
                player_match_df.at[index, 'h_a'] = 'NA'
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
        
        output_df = output_df.loc[output_df['Team'] == self.und_helper_fns.grab_team_USname_from_FPLID(TEAM_AGAINST_ID)]
        
        return output_df.to_dict()
    
    #################################### PLAYER RATINGS ASSESSMENT ##############################################
        
    def _calculate_rating(self, metric_values: list, metric_name: str, top_n_gws: int = None):
        look_back_averager = 6

        min_thr_rating, avg_thr_rating, high_thr_rating = 6.0, 7.5, 9.0

        # Get the thresholds for the given metric_name
        min_thr, avg_thr, high_thr = self.metric_thresholds.get(metric_name, (0.0, 0.0, 0.0))

        all_ratings = []
        for metric_value in metric_values[-look_back_averager:]:
            # Ensure the metric value is not below 0
            metric_value = max(metric_value, 0)

            # Calculate rating based on the metric value and the metric name
            if metric_value <= min_thr:
                rating = (metric_value / min_thr) * min_thr_rating
            elif metric_value <= avg_thr:
                rating = min_thr_rating + ((metric_value - min_thr) / (avg_thr - min_thr)) * 1.5
            elif metric_value <= high_thr:
                rating = avg_thr_rating + ((metric_value - avg_thr) / (high_thr - avg_thr)) * 1.5
            else:
                # Metric value is above high threshold, interpolate to excellent (10), capped at 10
                if metric_value <= (2 * high_thr):
                    rating = high_thr_rating + ((metric_value - high_thr) / (2 * high_thr - high_thr)) * 1.0
                else:
                    rating = 10.0

            all_ratings.append(rating)
        if top_n_gws == None:
            return np.mean(all_ratings)
        elif type(top_n_gws) == int:
            sorted_ratings = sorted(all_ratings, reverse=True)
            return np.mean(sorted_ratings[:top_n_gws])
        
    def _calculate_player_form_rating(self, player_dict: dict, top_n_gws: int = None):
        positional_metric_weightings = {
            'FWD': {'history': 0.55, 'ict': 0.1, 'xGI': 0.25, 'bps': 0.1},
            'MID': {'history': 0.55, 'ict': 0.1, 'xGI': 0.25, 'bps': 0.1},
            'DEF': {'history': 0.6, 'ict': 0.1, 'xGI': 0.1, 'xGC': 0.1, 'bps': 0.1},
            'GKP': {'history': 0.6, 'ict': 0.1, 'xGC': 0.2, 'bps': 0.1},
        }
        metric_weightings = positional_metric_weightings.get(player_dict['position'])
        metric_ratings = {}
        for param_name in [x for x in metric_weightings.keys() if x in ['history', 'ict', 'xGI', 'xGC', 'bps']]:
            rating = self._calculate_rating(player_dict[param_name][1], param_name, top_n_gws)
            metric_ratings[param_name] = rating
        total_weighting = sum(metric_weightings.values())
        normalized_weightings = {metric: weight / total_weighting for metric, weight in metric_weightings.items()}
        overall_rating = sum(metric_ratings[metric] * normalized_weightings[metric] for metric in metric_ratings)

        return overall_rating
    
    def get_player_form_rating(self, values: list, top_n_gws: int = None):
        players = [x for x in self.data_analytics.players if x['id'] in values]
        seq_map = {'GKP':0, 'DEF':1, 'MID':2, 'FWD':3}
        sorted_players = sorted(players, key=lambda x: (seq_map[x['position']], -x['history'][0]))
        rating_summary = {}
        for plyr_dict in sorted_players:
            if plyr_dict['position'] in ['MID', 'FWD','DEF']:
                overall_rating = self._calculate_player_form_rating(plyr_dict, top_n_gws)
                rating_summary[plyr_dict['id']] = overall_rating
        sorted_items = sorted(rating_summary.items(), key=lambda item: item[1], reverse=True)
        return sorted_items
    
    def calculate_team_rating(self, player_id):
        team_id_fpl = self.fpl_helper_fns.grab_player_team_id(player_id)
        team_id = self.und_helper_fns.grab_team_USID_from_FPLID(team_id_fpl)
        team_info = self.und_helper_fns.new_team_data.get(str(team_id))

        # Weighing factors for the rating
        weights = {
            'wins': 3,
            'draws': 1,
            'loses': -3,
            'xG': 2,
            'xGA': -2,
            'pts': 2,
            'npxGD': 2
        }

        # Calculate the weighted sum for each factor
        weighted_sum = sum(weights[key] * sum(team_info['history'][key]) for key in weights)

        # Normalize the weighted sum to get the rating in the range of 1 to 10
        min_weighted_sum = min(weights.values()) * sum(len(team_info['history'][key]) for key in weights)
        max_weighted_sum = max(weights.values()) * sum(len(team_info['history'][key]) for key in weights)
        normalized_rating = ((weighted_sum - min_weighted_sum) / (max_weighted_sum - min_weighted_sum)) * 9 + 1

        # Ensure the rating is within the valid range of 1 to 10
        rating = max(1, min(normalized_rating, 10))

        return rating
    
    def calculate_upcoming_FDR_rating(self, player_id):
        upcoming_fixture_list = self.fpl_helper_fns.grab_player_fixtures('fwd', self.fpl_helper_fns.grab_player_team_id(player_id),4)
        home_away_info = [x[1][0][2] for x in upcoming_fixture_list if len(x[1]) >= 1]
        difficulty_ratings = [x[1][0][3] for x in upcoming_fixture_list if len(x[1]) >= 1]
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
        rating = max(1, min(normalized_rating, 10))
        return rating

    def calculate_total_player_rating(self, PLAYER_ID,  top_n_gws = None, output_all = False):
        player_rating = self.get_player_form_rating([PLAYER_ID],top_n_gws)[0][1]
        team_rating = self.calculate_team_rating(PLAYER_ID)
        FDR_rating = self.calculate_upcoming_FDR_rating(PLAYER_ID)

        weights = [0.45,0.35,0.2]
        metric_ratings = [player_rating, team_rating, FDR_rating]

        # Calculate the weighted sum of metric ratings
        weighted_sum = sum(metric * weight for metric, weight in zip(metric_ratings, weights))

        # Normalize the weighted sum to get the overall rating
        overall_rating = weighted_sum
        if output_all:
            return metric_ratings, overall_rating
        else:
            return overall_rating
        
 #======================================== UNDERSTAT OPS ========================================

    def tabulate_ratings_table(self, rating_thresh = 5):
        positions_short = ['DEF','MID','FWD']
        values = [x['id'] for x in self.data_analytics.players if x['position'] != 'GKP' and x['position'] in positions_short]
        rating_summary = []
        for value in values:
            try:
                other_ratings, rating = self.calculate_total_player_rating(value, top_n_gws=4, output_all = True)
            except Exception as e:
                print(f'{value}: {e}')
                pass
            rating_summary.append((value, self.fpl_helper_fnshelper_fns.grab_player_name(value), rating, other_ratings))

        data = rating_summary

        min_rating = max(int(min(rating for _, _, rating, _ in data)), rating_thresh)
        max_rating = int(max(rating for _, _, rating, _ in data))
        intervals = [(i, i+1) for i in range(min_rating, max_rating + 1)]

        grouped_data = []
        for idx, name, rating, other_ratings in data:
            int_rating = int(rating)  # Convert float rating to integer
            for interval in intervals:
                if interval[0] <= int_rating < interval[1]:
                    grouped_data.append({
                        'Interval': f'{interval[0]}-{interval[1]}',
                        'FPL_ID': idx,
                        'Name': name,
                        'Total Rating': round(rating,1),
                        'Player Form': round(other_ratings[0],3),
                        'Team Form': round(other_ratings[1],3),
                        'FDR Score': round(other_ratings[2],3)
                    })
                    break

        df = pd.DataFrame(grouped_data)
        df.sort_values(['Interval', 'Total Rating'], ascending=[False, False], inplace=True)
        df = df.reset_index(drop=True)
        x = PrettyTable(df.columns.tolist())
        for row in df.itertuples(index=False):
            x.add_row(row)
        return x
