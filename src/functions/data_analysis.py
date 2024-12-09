import pandas as pd
# from tqdm.notebook import tqdm_notebook
import numpy as np
import ast
import json
import os
import json

from src.functions.generated_helper_fns import FPLDataConsolidationInterpreter, UnderstatDataInterpreter

helper_fns_fpl = FPLDataConsolidationInterpreter()

class FPLDataAnalytics():
    def __init__(self):
        self.helper_fns = helper_fns_fpl
        # self.personal_team_df = self.compile_fpl_team() #df_out
        self.personal_team_data = self._compile_personal_team_data() #df_fpl
        self.replacement_players = self._compile_prospects()
        self.beacon_effective_ownership = self._generate_beacon_effective_ownership()
        # self.form_dataframes()
        # self.export_caches()
        # self.initialize_decisions()
    
    def _compile_personal_team_data(self):
        r = self.helper_fns.raw_personal_fpl_data["latest_picks"]
        fpl_team_ids = set([x["element"] for x in r["picks"]])
        return self.helper_fns.compile_player_data(fpl_team_ids)

#==================================================================================================================================
#========================================================== ELO RANKINGS ==========================================================
#==================================================================================================================================

    def _calculate_expected_score(self, player_score, average_score):
        """Calculate the expected score based on player's score and average score."""
        return player_score / average_score

    def _update_elo(self, current_rating, player_score, average_score, k_factor=30, weight=1, adjustment_factor=0):
        """Update the Elo rating based on a single round's score."""
        expected_score = self._calculate_expected_score(player_score, average_score) # Apply penalty if the score is in the "Bad" bin
        new_rating = current_rating + k_factor * (player_score - expected_score) * weight + adjustment_factor
        return new_rating

    def _bin_score(self, score):
        """Bin the score into categories."""
        if score < 4:
            return 1  # Bad
        elif 4 <= score <= 6:
            return 2  # Average
        elif 7 <= score <= 9:
            return 3  # Good
        else:
            return 4  # Excellent

    def _update_elo_with_fdr(self, current_rating, player_score, average_score, fdr, home_away, k_factor=30, weight=1, adjustment_factor=0):
        """Update the Elo rating considering Fixture Difficulty Rating (FDR) and home/away status."""
        expected_score = self._calculate_expected_score(player_score, average_score)
        
        # Determine home/away factor
        home_away_factor = 0 if home_away == 1 else 200 if home_away == 0 else 0
        
        # Calculate FDR adjustment
        fdr_adjustment = self._calculate_fdr_adjustment(fdr, home_away_factor)
        
        # Update new rating with both adjustments
        new_rating = current_rating + k_factor * (player_score - expected_score) * weight + adjustment_factor + fdr_adjustment
        return new_rating

    def _calculate_fdr_adjustment(self, fdr, home_away_factor=0, base_adjustment=20):
        """
        Calculate the adjustment factor based on Fixture Difficulty Rating (FDR).
        
        Parameters:
        - fdr: The Fixture Difficulty Rating for the upcoming fixture.
        - home_away_factor: Adjustment based on whether the match is home or away.
        - base_adjustment: The base adjustment value to apply (default is 5).
        
        Returns:
        - adjustment: The calculated adjustment factor based on FDR.
        """
        # Adjustments can be positive or negative based on FDR and home/away factor
        adjustment = base_adjustment * (fdr - 3) + home_away_factor
        return adjustment

    def _calculate_current_elo(self, scores, average_scores, fdrs, h_a, initial_rating):
        """Calculate the current Elo rating based on scores from all rounds."""
        weights = [2.5, 2.0, 1.5, 1.0, 0.8, 0.5]
        
        current_rating = initial_rating
        adjustment_factor = 0
        consecutive_bad_count = 0
        consecutive_good_count = 0
        # print(f"{scores} {average_scores}")
        for i in range(len(scores)):
            player_score = scores[i]
            weight = weights[i] if i < len(weights) else 0.5  # Default weight for older scores
            
            # Determine the bin of the current score
            current_bin = self._bin_score(player_score)
        
            # Adjust adjustment factor based on current bin
            if current_bin == 1:
                # Increment consecutive bad count and apply negative adjustment
                consecutive_bad_count += 1
                if consecutive_bad_count >= 2: consecutive_good_count = 0
                # Penalty increases with consecutive bad scores; more for recent ones
                penalty = (-1*4**consecutive_bad_count) * (1 + (len(scores) - i) / len(scores))  # More penalty for recent bad scores
                adjustment_factor += penalty
                
            elif current_bin == 2:
                # Reset consecutive bad count and increase good count
                consecutive_bad_count = 0
                consecutive_good_count += 1
                
                # Increase bonus for good performances (average)
                adjustment_factor += min(2**consecutive_good_count, 2000)  # Cap bonus to +20
                
            elif current_bin == 3:
                # Reset bad count and increase good count
                consecutive_bad_count = 0
                consecutive_good_count += 1
                
                # Increase bonus for excellent performances
                adjustment_factor += min(4**consecutive_good_count, 2000)  # Cap bonus to +30
                
            elif current_bin == 4:
                # Reset bad count and increase good count
                consecutive_bad_count = 0
                consecutive_good_count += 1
                
                # Increase bonus for excellent performances
                adjustment_factor += min(8**consecutive_good_count, 2000)  # Cap bonus to +30
                
            current_rating = self._update_elo_with_fdr(current_rating, player_score, average_scores[i], fdrs[i], h_a[i], weight=weight, adjustment_factor=adjustment_factor)
        
        return current_rating

    def score_players_on_form(self, list_of_ids: list, lookback_period: int) -> dict:
        
        full_data = self.helper_fns.compile_player_data(list_of_ids)

        player_ratings = {}
        for player_id, player_data in full_data.items():
            points = [x[1] for x in player_data['total_points']]
            fdrs = [self.helper_fns.team_rank(x[1]) for x in player_data['opponent_team']]
            h_a = [x[1] for x in player_data['was_home']]
            initial_elo = 500
            average_scores = [6]*len(points)
            # print(f"TEMP: {points} {average_scores}")
            # current_elo_after_round_4 = 0
            elo_prior_to_lookback = self._calculate_current_elo(
                points[:(len(points)-lookback_period)],
                average_scores[:(len(points)-lookback_period)],
                fdrs[:(len(points)-lookback_period)],
                h_a[:(len(points)-lookback_period)],
                initial_elo
            )
            present_elo = self._calculate_current_elo(
                points[(len(points)-lookback_period):],
                average_scores[(len(points)-lookback_period):],
                fdrs[(len(points)-lookback_period):],
                h_a[(len(points)-lookback_period):],
                initial_elo
            )
            final_elo_weighted = 0.9*present_elo + 0.1*elo_prior_to_lookback
            # print(f"{player_id} {points} {average_scores} {current_elo_after_round_4} {final_elo}")
            player_ratings[player_id] = {
                'initial_elo': round(initial_elo,2),
                'elo_prior_to_lookback': round(elo_prior_to_lookback,2),
                'present_elo': round(present_elo,2),
                'final_elo_weighted': round(final_elo_weighted,2)
            }
        return dict(sorted(player_ratings.items(), key=lambda x: x[1]['present_elo'], reverse=True))

#========================================================== FIXTURE RANKINGS ==========================================================

    def _calculate_fixture_score(self, past_data, future_data, weights={'w1':0.7, 'w2':0.2, 'w3':0.1}, gains={'fdr':100}):
        """
        Calculate the base score based on Fixture Difficulty Rating (FDR).
        
        Parameters:
        - fdr: The Fixture Difficulty Rating for the fixture (1 to 5).
        
        Returns:
        - base_score: The calculated base score (0 to 100).
        """
        #============== PAST ==============
        ppg_data = self._calculate_ppg_stats(past_data)
        # print(f"ppg_data: {ppg_data}")
        fdr_data_past = self._calculate_fdr_stats(past_data['fdr'], past_data['h_a'])
        history_index_data = self._calculate_history_index_stats(ppg_data, fdr_data_past)
        # print(f"fdr_data_past: {fdr_data_past}")
        #============== PRESENT ==============
        fdr_data_future = self._calculate_fdr_stats(future_data['fdr'], future_data['h_a'])
        # print(f"fdr_data_future: {fdr_data_future}")
        round_score = 0
        for h_a, fdr_data in fdr_data_future.items():
            # history_index_factor = history_index_data[h_a]['base_factor']*history_index_data[h_a]['sig_fdr']
            round_score += weights['w1']*gains['fdr']*(1-(fdr_data['avg']/5)) + weights['w2']*history_index_data[h_a]['base_factor'] + weights['w3']*history_index_data[h_a]['player_factor']
        return round_score

    def _calculate_history_index_stats(self, ppg_data, fdr_data_past, gains={'k_base':100, 'k_plyr':100}):
        return {
            'h': {
                'base_factor': gains['k_base']*ppg_data['h']['team']/(ppg_data['a']['team'] + ppg_data['h']['team']) if ((ppg_data['h']['team']>0) and (ppg_data['a']['team']>0)) else 0,
                'player_factor': gains['k_plyr']*ppg_data['h']['player']/(ppg_data['a']['player'] + ppg_data['h']['player']) if ((ppg_data['h']['player']>0) and (ppg_data['a']['player']>0)) else 0,
                'sig_fdr': 1-(fdr_data_past['h']['avg']/5),
            },
            'a': {
                'base_factor': gains['k_base']*ppg_data['a']['team']/(ppg_data['a']['team'] + ppg_data['h']['team']) if ((ppg_data['h']['team']>0) and (ppg_data['a']['team']>0)) else 0,
                'player_factor': gains['k_plyr']*ppg_data['a']['player']/(ppg_data['a']['player'] + ppg_data['h']['player']) if ((ppg_data['h']['player']>0) and (ppg_data['a']['player']>0)) else 0,
                'sig_fdr': 1-(fdr_data_past['a']['avg']/5),
            }
        }

    def _calculate_fdr_stats(self, fdrs, h_a_s):
        # print(f"FDRS: {fdrs}")
        # print(f"h_a_s: {h_a_s}")
        fdr_h = [fdr for fdr, h_a in zip(fdrs, h_a_s) if h_a[-1] == 1]
        fdr_a = [fdr for fdr, h_a in zip(fdrs, h_a_s) if h_a[-1] == 0]
        return {
            'h': {
                'data': fdr_h,
                'avg': np.mean([x[-1] for x in fdr_h]),
                'sum': np.sum([x[-1] for x in fdr_h])
            },
            'a': {
                'data': fdr_a,
                'avg': np.mean([x[-1] for x in fdr_a]),
                'sum': np.sum([x[-1] for x in fdr_a])
            }
        }

    def _calculate_ppg_stats(self, matches):
        """
        Calculate the home and away performance metrics for a team.

        Parameters:
        - matches: A list of dictionaries containing match results.

        Returns:
        - home_performance: Average points per game at home.
        - away_performance: Average points per game away.
        """
        #============== TEAM ==============
        team_pts_h = 0
        team_pts_a = 0
        team_games_h = 0
        team_games_a = 0

        def tabulate_match_points(team_a_score, team_h_score, h_a):
            if (h_a == 1 and team_h_score > team_a_score) or (h_a == 0 and team_a_score > team_h_score):
                return 3
            elif team_h_score == team_a_score:
                return 1
            else:
                return 0
        
        for i in range(0, len(matches['h_a'])):
            try:
                team_match_pts = tabulate_match_points(matches['team_a_score'][i][-1], matches['team_h_score'][i][-1], matches['h_a'][i][-1])
            except:
                continue
            if matches['h_a'][i][-1] == 1:
                team_pts_h += team_match_pts
                team_games_h += 1
            elif matches['h_a'][i][-1] == 0:
                team_pts_a += team_match_pts
                team_games_a += 1

        team_ppg_h = team_pts_h / team_games_h if team_games_h > 0 else 0
        team_ppg_a = team_pts_a / team_games_a if team_games_a > 0 else 0
        
        #============== PLAYER ==============
        plyr_pts_h = 0
        plyr_pts_a = 0
        plyr_games_h = 0
        plyr_games_a = 0
        
        for i in range(0, len(matches['h_a'])):
            player_match_pts = matches['total_points'][i][-1]
            if matches['h_a'][i][-1] == 1:
                plyr_pts_h += player_match_pts
                plyr_games_h += 1
            elif matches['h_a'][i][-1] == 0:
                plyr_pts_a += player_match_pts
                plyr_games_a += 1

        plyr_ppg_h = plyr_pts_h / plyr_games_h if plyr_games_h > 0 else 0
        plyr_ppg_a = plyr_pts_a / plyr_games_a if plyr_games_a > 0 else 0
        
        return {
            'h': {
                'team': team_ppg_h,
                'player': plyr_ppg_h
            },
            'a': {
                'team': team_ppg_a,
                'player': plyr_ppg_a
            },
        }

    def score_players_on_fixtures(self, list_of_ids: list, lookback_period: int) -> dict:
        
        gameweek_data = self.helper_fns.grab_upcoming_fixtures(list_of_ids, games_ahead=lookback_period)
        full_data = {
            key: {
                'opponent_teams': [d['opponent_team'] for d in value if d['opponent_team'] is not None], 
                'fdrs': [(d['gameweek'], self.helper_fns.team_rank(d['opponent_team'])) for d in value if d['opponent_team'] is not None], 
                'is_home': [(d['gameweek'], d['is_home']) for d in value if d['is_home'] is not None]
            } for key, value in gameweek_data.items()
        }

        historical_data = self.helper_fns.compile_player_data(list_of_ids)
        
        player_ratings = {}
        for player_id, player_fixture_data in full_data.items():
        
            home_away_info = player_fixture_data['is_home']
            difficulty_ratings = player_fixture_data['fdrs']

            if not home_away_info or not difficulty_ratings:
                player_ratings[int(player_id)] = {'score': None}
            else:
                # upcoming_fixtures = [(fdr,  h_a) for fdr,  h_a in zip(difficulty_ratings, home_away_info)]
                player_future_data = {
                    'fdr': difficulty_ratings,
                    'h_a': home_away_info
                }
                
                player_historical_dict = historical_data[int(player_id)]
                player_historical_data = {
                    'h_a': player_historical_dict['was_home'],
                    'team_a_score': player_historical_dict['team_a_score'],
                    'team_h_score': player_historical_dict['team_h_score'],
                    'fdr': [(x[0], self.helper_fns.team_rank(x[1])) for x in player_historical_dict['opponent_team']],
                    'total_points': player_historical_dict['total_points'],
                }

                fixture_score = self._calculate_fixture_score(player_historical_data, player_future_data)
                # ppg_h_a = calculate_performance_metrics(player_historical_dict)
                # print(f"{fpl_data_attributes.helper_fns.grab_player_name_fpl(int(player_id))} {home_performance_metric} {away_performance_metric}")
                # average_fixture_score = calculate_adjusted_fixture_score(upcoming_fixtures, ppg_h_a)
                player_ratings[int(player_id)] = {'score': round(fixture_score, 3)}
        return dict(
                    sorted(
                        player_ratings.items(),
                        key=lambda x: (x[1]['score'] is None, x[1]['score'] if x[1]['score'] is not None else float('-inf')),
                        reverse=True
                    )
                )

#========================================================== CONSOLIDATE RANKINGS ==========================================================

    def apply_scores_and_compile_prospects(self, list_of_ids: list, lookback_period=6):
        form_score_data = self.score_players_on_form(self.helper_fns.player_ids, lookback_period)
        fixture_score_data = self.score_players_on_fixtures(self.helper_fns.player_ids, 4)
        # team_score_data = self.score_players_on_fixtures(self.api_parser.player_ids)

        df = pd.DataFrame.from_dict({
                player_id: {
                    'elo_form_score_pres': form_score_data[player_id]['present_elo'],
                    'elo_form_score_hist': form_score_data[player_id]['elo_prior_to_lookback'],
                    'elo_form_score_net': form_score_data[player_id]['final_elo_weighted'],
                    'fixture_score': fixture_score_data[player_id]['score'],
                    'minutes_score': fixture_score_data[player_id]['score']
                } 
                for player_id in list_of_ids
            },
            orient='index').reset_index()
        
        df = df.rename(columns={'index': 'player_id'})
        return df.sort_values(by=['elo_form_score_pres'], ascending=False)
    
    def _compile_prospects(self, list_of_ids: list = None):
        if list_of_ids is None: list_of_ids = self.helper_fns.player_ids
        df = self.apply_scores_and_compile_prospects(list_of_ids)
        df['player_name'] = df['player_id'].apply(self.helper_fns.grab_player_name_fpl)
        df['player_pos'] = df['player_id'].apply(self.helper_fns.grab_player_pos)
        df['player_team'] = df['player_id'].apply(self.helper_fns.grab_player_team)
        return df
        # return df.loc[df['form_score'] > 0.5]['player_id'].to_list()

#============================================  FPL EVALUATIONS  ============================================

    # def grab_top_players_by_mean(self, list_of_ids: list = None, is_for_personal_fpl_team = False) -> pd.DataFrame:
    #     '''
    #     Grab return history of provided list of IDs, and look back in various GW windows of either previous 6, 3 or 2 GWs.
    #     Count returns (0 for no return (0-3 pts), 1 for single digit return, 2 for double digit return)
        
    #     '''
    #     count_dict={}
    #     #First 3 statements are at start of FPL where only few seasons available
    #     LOOK_BACK_LIST = [1] if self.api_parser.latest_gw == 1 else [2] if self.api_parser.latest_gw  == 2 else [3,2] if self.api_parser.latest_gw  < 6 else [6,3,2]
    #     returns_nontop6={}
    #     for idx in list_of_ids:
    #         recent_returns_bank = self.helper_fns.grab_player_returns(idx)
    #         for look_back in LOOK_BACK_LIST:
    #             recent_returns = recent_returns_bank[-look_back:]
    #             count = recent_returns.count(1) + recent_returns.count(2)

    #             if look_back == 6:
    #                 thresh = 4 if count == 3 and recent_returns.count(2) >= 1 else 3
    #             elif look_back == 3:
    #                 thresh = 3 if count == 2 else 2 if recent_returns_bank[-4:].count(1) + recent_returns_bank[-4:].count(2) == 3 or recent_returns.count(2) >= 1 else 3
    #             elif look_back == 2:
    #                 thresh = 2
    #             elif look_back == 1:
    #                 thresh = 1
    #             else:
    #                 continue
    #             if count >= thresh:
    #                 count_dict[str(idx)] = count_dict.get(str(idx), 0) + 1
    #             elif count < thresh and is_for_personal_fpl_team:
    #                 count_dict[str(idx)] = count_dict.get(str(idx), 0)

    #         recent_returns = recent_returns_bank[-10:]
    #         if count >= 2:
    #             r = self.api_parser.full_element_summary(idx)
    #             teams = [self.helper_fns.fdr_data[dictr['opponent_team']] for dictr in r['history'][-10:]]
    #             calibrated_returns = [num for ind, num in enumerate(recent_returns) if teams[ind] < 4 or (teams[ind] >= 4 and num > 0)]
    #             returns_nontop6[str(idx)] = calibrated_returns

    #             if calibrated_returns.count(1) + calibrated_returns.count(2) / len(calibrated_returns) > 0.5:
    #                 count_dict[str(idx)] = '-!-'

    #     df = pd.DataFrame({'id': count_dict.keys(), 'count': count_dict.values()})
    #     df['id'] = df['id'].astype(int)
    #     df['count'] = df['count'].astype(str)
    #     df['player'] = df['value'] = df['position'] = df['team'] = df['starting_risk'] = df['form_top6adjusted'] = df['history'] = df['minutes'] = df['fulltime'] = df['fullhour'] = df['bps'] = 'NA'
    #     df = df.reset_index(drop=True)
    #     desc = "Compiling top players"
    #     if is_for_personal_fpl_team:
    #         desc += " [Personal]"
    #     else:
    #         desc += " [Otherwise]"
    #     for num, ids in enumerate(tqdm_notebook(df['id'], desc = desc)):
    #         recent_returns = self.helper_fns.grab_player_returns(idx)[-6:]
    #         count = recent_returns.count(1) + recent_returns.count(2)

    #         df.loc[num, 'player'] = self.helper_fns.grab_player_name(int(ids))
    #         df.loc[num, 'value'] = self.helper_fns.grab_player_value(int(ids))
    #         df.loc[num, 'position'] = self.helper_fns.grab_player_pos(int(ids))
    #         df.loc[num, 'team'] = self.helper_fns.grab_player_team(int(ids))
    #         df.loc[[num], 'history'] = pd.Series([self.helper_fns.grab_player_hist(int(ids))], index=[num])
    #         df.loc[[num], 'minutes'] = pd.Series([self.helper_fns.grab_player_minutes(int(ids))], index=[num])
    #         df.loc[[num], 'bps'] = pd.Series([self.helper_fns.grab_player_bps(int(ids))], index=[num])
    #         df.loc[num, 'fulltime'] = self.helper_fns.grab_player_full90s(int(ids))
    #         df.loc[num, 'fullhour'] = self.helper_fns.grab_player_full60s(int(ids))

    #         if str(ids) in returns_nontop6.keys():
    #             df.loc[[num], 'form_top6adjusted'] = pd.Series([returns_nontop6[str(ids)][-6:]], index=[num])

    #         if count >= 4:
    #             df.loc[num, 'count'] = str(df['count'].iloc[num]) + '*' + '*' if count >= 5 else ''

    #     df = df.fillna(np.nan)
    #     return df

    # def evaluate_best_fpl_upgrades(self, value_threshold: float = 99, is_for_personal_fpl_team = False) -> pd.DataFrame:
    #     if not is_for_personal_fpl_team:
    #         df = self.data_parser.total_summary.loc[self.data_parser.total_summary['value'] <= value_threshold]
    #         df = df[~df['player'].isin(self.personal_team_df['player'].tolist())]
    #     else:
    #         df = self.personal_team_df.copy()
    #     top_players = self.grab_top_players_by_mean(df['id_player'].tolist(), is_for_personal_fpl_team)
    #     top_players['fixture_class'] = 'NA';top_players['fixtures_diff'] = 'NA';top_players['consistency'] = 'NA'
    #     for num,id2 in enumerate( tqdm_notebook(top_players['id'], desc = "Evaluating prospects") ):
    #         classifier,fixtures = self.helper_fns.rem_fixtures_difficulty(id2)
    #         top_players.loc[num,'fixture_class'] = classifier
    #         top_players.loc[[num],'fixtures_diff'] = pd.Series([fixtures],index=[num])
    #         returns = self.helper_fns.grab_player_returns(id2)
    #         returns = returns[-6:]
    #         top_players.loc[num,'consistency'] = str(returns.count(1) + returns.count(2)) + "/" + str(len(returns))
    #     return top_players
    
    # def optimize_fpl_team(self):
    #     df = self.evaluate_best_fpl_upgrades(is_for_personal_fpl_team = True)
    #     df = pd.concat([df.sort_values(by=['id'],ascending=False).reset_index(drop=True), 
    #                                 self.personal_team_df[['id_player','last6_mean_x','last3_mean_x','last2_mean_x']
    #                                     ].sort_values(by=['id_player'],ascending=False).reset_index(drop=True)], axis=1
    #                             ).drop(['id_player'], axis=1)
    #     df = df[['id','player','value','position','team','last6_mean_x','last3_mean_x','last2_mean_x','consistency','count','fixture_class','fixtures_diff','form_top6adjusted','history','minutes','fulltime','fullhour','bps']]
    #     return df

    # def versus(self, list_of_player_ids: list, input_df: pd.DataFrame) -> list:
    #     relevant_df = input_df.loc[input_df['id'].isin(list_of_player_ids)]
    #     df1a=relevant_df.loc[(relevant_df['last6_mean_x'] > 0.66) & (relevant_df['last3_mean_x'] > 0)]
    #     df1b=relevant_df.loc[(relevant_df['last6_mean_x'] > 0.33) & (relevant_df['last3_mean_x'] > 0.33)]
    #     df1 = pd.concat([df1a,df1b],ignore_index=True)
    #     df1 = df1.drop_duplicates(subset=['id'])

    #     if self.api_parser.latest_gw >= 6:
    #         inddrop = []
    #         for ind,form in enumerate(df1['form_top6adjusted']):
    #             if (list(form).count(1) + list(form).count(2)) / len(list(form)) < 0.5:
    #                 inddrop.append(ind)
    #         df1 = df1.drop(inddrop)
    #     if len(df1) <= 1:
    #         filter1 = df1['id'].values.tolist()
    #         return filter1
    #     else:
    #         countthresh = max(df1['count'].unique())
    #         df2=df1.loc[(df1['count'] == countthresh)]
    #         if len(df2) <= 1:
    #             filter2 = df2['id'].values.tolist()
    #             return filter2
    #         else:
    #             valuelow = min(df2['value'].unique())
    #             df3=df2.loc[(df1['value'] <= (valuelow + 0.5))]
    #             filter3 = df3['id'].values.tolist()
    #             return filter3

#============================================  COMPILING EVALUATIONS  ============================================
        
    # def compile_all_prospects(self):
    #     df = self.evaluate_best_fpl_upgrades()
    #     id_list = [x for x in df['id']]
    #     fpl_team_ids = set(id_list)
    #     df_temp = self.data_parser.total_summary[self.data_parser.total_summary['id_player'].isin(fpl_team_ids)].reset_index(drop=True)
    #     # df2 = df_temp[['id_player', 'player','value','name','position','history','last6_mean_x','last3_mean_x','last2_mean_x','minutes','fulltime','fullhour','bps']].sort_values(by=['last6_mean_x'],ascending=False)
    #     df = pd.concat([df.sort_values(by=['id'],ascending=False).reset_index(drop=True), 
    #                                 df_temp[['id_player','last6_mean_x','last3_mean_x','last2_mean_x']
    #                                     ].sort_values(by=['id_player'],ascending=False).reset_index(drop=True)], axis=1
    #                             ).drop(['id_player'], axis=1)
    #     cols_of_interest = ['id','player','value','position','team','last6_mean_x','last3_mean_x','last2_mean_x','consistency','count','fixture_class','fixtures_diff','form_top6adjusted','history','minutes','fulltime','fullhour','bps']
    #     df = df[cols_of_interest].sort_values(by=['last6_mean_x'])
    #     return df

    # def condense_prospects(self):
    #     df = self.prospects_df.copy()
    #     df = df.reset_index(drop=True)
    #     teams = df.team.unique()
    #     positions = df.position.unique()
    #     df_by_team = {team: df['id'].loc[(df['team'] == team)].tolist() for team in teams}
    #     df_by_pos = {position: df['id'].loc[(df['position'] == position)].tolist() for position in positions}
    #     indices_to_drop = []

    #     consolidated_grouping = {pos_key: {k: [ind_id for ind_id in pos_ids if ind_id in v] for k, v in df_by_team.items()} for pos_key, pos_ids in df_by_pos.items()}

    #     for ind,row in df.iterrows():
    #         cond1 = (row['count'] == '-!-' and row['fixture_class'] == '-X-')
    #         if self.api_parser.latest_gw >= 6:
    #             cond2 = (list(row['form_top6adjusted']).count(2) == 0 and list(row['form_top6adjusted']).count(1)/len(list(row['form_top6adjusted'])) < 0.5)
    #         else:
    #             cond2 = False
    #         if any([cond1,cond2]):
    #             indices_to_drop.append(ind)
    #         locate_team_group = consolidated_grouping[row['position']][row['team']]
    #         ones_above_all = self.versus(locate_team_group,df)
    #         current_id = row['id']
    #         if current_id not in ones_above_all:
    #             indices_to_drop.append(ind)
    #     indices_to_drop = list(dict.fromkeys(indices_to_drop))
    #     df = df.drop(indices_to_drop)
    #     return df

# #============================================  SUMMARIZING  ============================================
    
#     def condense_and_merge_dataframes(self, input_df: pd.DataFrame):
#         list_of_ids_from_input = input_df.id.tolist()
#         master_df_from_ids = self.data_parser.total_summary[self.data_parser.total_summary['id_player'].isin(list_of_ids_from_input)]
#         relevant_cols = master_df_from_ids.select_dtypes(include=['object']).columns.tolist()
#         dfs_with_rows_as_lists = master_df_from_ids[relevant_cols].apply(lambda col: col[col.apply(lambda x: isinstance(x, list))])
#         dfs_with_rows_as_lists = dfs_with_rows_as_lists.dropna(axis=1).reset_index(drop=True)
#         return pd.merge(input_df, dfs_with_rows_as_lists, left_index=True, right_index=True, how='inner')

#     def form_dataframes(self):
#         self.ROTR_df = self.condense_and_merge_dataframes(self.prospects_df.iloc[:, 0:8])
#         self.MT_df = self.condense_and_merge_dataframes(self.personal_team_data.iloc[:, 0:5])

# #============================================  DECISION INITIALIZATIONS  ============================================
#     def initialize_decisions(self):
#         def consolidate_all_player_data():
#             self.players=[]
#             df = self.data_parser.total_summary.copy()
#             for _, row in df.iterrows():
#                 cols_of_interest = ['id_player','position', 'history', 'bps', 'ict_index', 'expected_goal_involvements', 'minutes', 'expected_goals_conceded', 'changing_value']
#                 data = {}
#                 for col in cols_of_interest:
#                     param_val = getattr(row, col)
#                     data[col] = param_val
#                 relevant_data = {'id': data['id_player'],
#                                 'position': data['position'],
#                                 'name':self.helper_fns.grab_player_name(data['id_player']), 
#                                 'history':(np.mean(data['history'][-6:]), data['history'][-6:]), 
#                                 'bps':(np.mean(data['bps'][-6:]), data['bps'][-6:]), 
#                                 'ict':(np.mean(data['ict_index'][-6:]), data['ict_index'][-6:]), 
#                                 'xGI':(np.mean(data['expected_goal_involvements'][-6:]), data['expected_goal_involvements'][-6:]), 
#                                 'xGC':(np.mean(data['expected_goals_conceded'][-6:]), data['expected_goals_conceded'][-6:]), 
#                                 'minutes': data['minutes'][-6:], 
#                                 'cost': data['changing_value'][-1]/10}
#                 if data['position'] not in ['DEF','GKP']:
#                     relevant_data.pop('xGC')
#                 self.players.append(relevant_data)
        
#         def process_replacements():
#             player_dict = {}
#             for param,param_thresh in [('ict_index',7),('returnhist',1),('bps',25),('expected_goal_involvements',0.75),('history',6)]:
#                 player_dict[param] = {}
#                 for look_back in [1,2,3,4,5,6]:
#                     df = self.data_parser.total_summary.copy()
#                     FPL_15_players = self.personal_team_data.id.tolist()
#                     mask = df.id_player.isin(FPL_15_players)
#                     df = df[~mask]
#                     def last_3_values(lst):
#                         return np.mean(lst[-look_back:])
#                     mask = df[param].apply(last_3_values) >= param_thresh
#                     df = df[mask]
#                     grouped = df.groupby('position').apply(lambda x: x.sort_values('position')).reset_index(drop=True)
#                     grouped_dict = {group: group_df for group, group_df in grouped.groupby('position')}
#                     player_dict[param][look_back] = {}
#                     for position in ['DEF','MID','FWD']:
#                         try:
#                             df = grouped_dict[position]
#                             df_sorted = df.sort_values(by=param, key=lambda x: x.map(last_3_values), ascending = False)
#                             player_dict[param][look_back][position] = df_sorted.id_player.tolist()
#                         except:
#                             pass

#             unique_values = {
#                 'DEF': [],
#                 'MID': [],
#                 'FWD': []
#             }
#             # Iterate over the values in the inner dictionaries and update the unique_values dictionary
#             for param in player_dict.keys():
#                 for d in player_dict[param].values():
#                     for k, v in d.items():
#                         unique_values[k].extend(v)

#             # Extract the unique values for each group
#             unique_values['DEF'] = list(set(unique_values['DEF']))
#             unique_values['MID'] = list(set(unique_values['MID']))
#             unique_values['FWD'] = list(set(unique_values['FWD']))
#             self.replacement_players=[]
#             def passes_xGI_threshold(numbers):
#                 if len(numbers) >= 3:
#                     last_three = numbers[-3:]
#                     combinations = [(last_three[0], last_three[1]),
#                                     (last_three[0], last_three[2]),
#                                     (last_three[1], last_three[2])]

#                     for a, b in combinations:
#                         average = (a + b) / 2
#                         if average > 0.5:
#                             return True

#                 return False
#             for key in unique_values.keys():
#                 for num in unique_values[key]:
#                     df = self.data_parser.total_summary.loc[self.data_parser.total_summary['id_player'] == num]
#                     history = df['history'].iloc[0]
#                     bps = df['bps'].iloc[0]
#                     ICT = df['ict_index'].iloc[0]
#                     xGI = df['expected_goal_involvements'].iloc[0]
#                     xGC = df['expected_goals_conceded'].iloc[0]
#                     mins = df['minutes'].iloc[0]
#                     cost = df['changing_value'].iloc[0][-1]
#                     if key == 'DEF':
#                         self.replacement_players.append({'id': num,
#                                                         'position': key,
#                                                         'name': self.helper_fns.grab_player_name(num),
#                                                         'history': (np.mean(history[-6:]),history[-6:]),
#                                                         'bps': (np.mean(bps[-6:]),bps[-6:]),
#                                                         'ict': (np.mean(ICT[-6:]),ICT[-6:]),
#                                                         'xGI': (np.mean(xGI[-6:]),xGI[-6:]),
#                                                         'xGC': (np.mean(xGC[-6:]),xGC[-6:]),
#                                                         'minutes': mins[-6:],
#                                                         'cost': cost/10})
#                     else:
#                         if np.mean(xGI[-6:]) > 0.4 or passes_xGI_threshold(xGI):
#                             self.replacement_players.append({'id': num,
#                                                             'position': key,
#                                                             'name': self.helper_fns.grab_player_name(num),
#                                                             'history': (np.mean(history[-6:]),history[-6:]),
#                                                             'bps': (np.mean(bps[-6:]),bps[-6:]),
#                                                             'ict': (np.mean(ICT[-6:]),ICT[-6:]),
#                                                             'xGI': (np.mean(xGI[-6:]),xGI[-6:]),
#                                                             'minutes': mins[-6:],
#                                                             'cost': cost/10})
#             players = [x for x in self.players if x['id'] in self.personal_team_data['id'].to_list()]    
#             combinations = [(dict1, dict2) for dict1, dict2 in itertools.product(players, self.replacement_players) if ((dict2['ict'][0]+1 > dict1['ict'][0]) and dict2['position'] == dict1['position'])]
#             self.my_dict = {}
#             for key, value in combinations:
#                 if key['name'] in self.my_dict:
#                     self.my_dict[key['name']]['replacement'].append((value,round(value['cost']-key['cost'],2)))
#                 else:
#                     self.my_dict[key['name']] = {'stats': key, 'replacement': [(value,round(value['cost']-key['cost'],2))]}
#             seq_map = {'GKP': 0, 'DEF': 1, 'MID': 2, 'FWD': 3}
#             items = sorted(self.my_dict.items(), key=lambda x: seq_map[x[1]['stats']['position']])
#             self.my_dict = {k:v for k,v in items}
#         consolidate_all_player_data()
#         process_replacements()


#============================================  beacon INITIALIZATIONS  ============================================

    def _generate_beacon_effective_ownership(self):
        id_count = self.helper_fns.rival_stats['id_count']
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

#==================================================================================================================================

    def export_caches(self):
        def upload_potentials():
            output_file_path = os.path.abspath("../../stats/primedata_per_gw.json")
            stats_dir = os.path.dirname(output_file_path)
            os.makedirs(stats_dir, exist_ok=True)
            if not os.path.isfile(output_file_path):
                with open(output_file_path, 'w') as empty_file:
                    empty_file.write(json.dumps({}))
            file = open(output_file_path, "r")
            contents = file.read()
            dictionary = ast.literal_eval(contents)
            dictionary[str(self.helper_fns.latest_gw)] = self.prospects_df['id'].tolist() + self.primes_df['id'].tolist()
            with open(output_file_path, 'w') as conv_file:
                conv_file.write(json.dumps(dictionary))
            file.close()
            self.potential_dict = dictionary
            print('Uploaded primes to external file!')

        def upload_beacon_teams():
            output_file_path = os.path.abspath("../../stats/beacon_team_history.json")
            if not os.path.isfile(output_file_path):
                with open(output_file_path, 'w') as empty_file:
                    empty_file.write(json.dumps({}))
            file = open(output_file_path, "r")
            contents = file.read()
            dictionary = ast.literal_eval(contents)
            dictionary[str(self.helper_fns.latest_gw)] = self.helper_fns.rival_id_data
            with open(output_file_path, 'w') as conv_file:
                conv_file.write(json.dumps(dictionary))
            file.close()
            self.beacon_dict = dictionary
            print('Uploaded gen teams to external file!')

        def compile_returns():
            returns = []
            for i in self.potential_dict[str(self.helper_fns.latest_gw)]:
                returns.append(self.helper_fns.grab_player_hist(i)[-1])
            larger_elements = [element for element in returns if element > 3]
            number_of_elements = len(larger_elements)
            accuracy = number_of_elements / len(returns)
            output_file_path = os.path.abspath("../../stats/model_accuracy.json")
            if not os.path.isfile(output_file_path):
                with open(output_file_path, 'w') as empty_file:
                    empty_file.write(json.dumps({}))
            file = open(output_file_path, "r")
            contents = file.read()
            dict_acc = ast.literal_eval(contents)
            dict_acc[str(self.helper_fns.latest_gw)] = {'instant': accuracy*100}
            with open(output_file_path, 'w') as conv_file:
                conv_file.write(json.dumps(dict_acc))
            file.close()
            print('Uploaded model accuracy to external file!')
            
        upload_potentials()
        upload_beacon_teams()
        compile_returns()

class UnderstatDataAnalytics():
    def __init__(self, fpl_helper_fns, update_bool = False):
        self.update_bool = update_bool
        self.helper_fns = UnderstatDataInterpreter(fpl_helper_fns, update_bool)
