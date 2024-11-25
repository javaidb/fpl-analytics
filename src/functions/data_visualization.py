from prettytable import PrettyTable
import matplotlib.pyplot as plt
from itertools import cycle
import numpy as np
import textwrap
from PIL import Image
from collections import defaultdict
import statistics
from src.config import config
from src.functions.data_exporter import grab_path_relative_to_root

class NotebookDataVisualizer:
    
    def __init__(self, data_analytics):
        self.data_analytics = data_analytics

    def grab_ownership_count_str(self, player_id: int, league_name, format_color):
        compiled_ownership = next(x["summary"] for x in iter(self.data_analytics.helper_fns.league_data) if x["name"] == str(league_name))
        relevant_player_ids = compiled_ownership["players"]

        id_count = 0 if player_id not in relevant_player_ids.keys() else relevant_player_ids[player_id]
        if id_count == 0 and format_color == "sell":
            count_str = f"\033[31m{id_count}\033[0m"
        elif id_count != 0 and format_color == "buy":
            count_str = f"\033[34m{id_count}\033[0m"
        else:
            count_str = f"{id_count}"
        num_rivals = len(compiled_ownership["rivals"])
        return f"{count_str}/{num_rivals}"

#========================================================================================================================================================================================
#===================================================================== TABULAR VISUALIZATION USING ASCII ATTRIBUTES =====================================================================
#========================================================================================================================================================================================

    def grab_ascii_bins(self, bin_length, ascii_purpose, return_sequence = 'ansi', custom_color_scheme = None):
        color_map = {
            'red': {'rgb': (1, 0, 0), 'ansi': '\033[1;31m'},
            'green': {'rgb': (0, 1, 0), 'ansi': '\033[1;32m'},
            'yellow': {'rgb': (1, 1, 0), 'ansi': '\033[1;33m'},
            'blue': {'rgb': (0, 0, 1), 'ansi': '\033[1;34m'},
            'magenta': {'rgb': (1, 0, 1), 'ansi': '\033[1;35m'},
            'cyan': {'rgb': (0, 1, 1), 'ansi': '\033[1;36m'},
            'white': {'rgb': (1, 1, 1), 'ansi': '\033[1;37m'}
        }
        if custom_color_scheme is not None:
            if (ascii_purpose == 'static' and len(custom_color_scheme) == bin_length+1) or (ascii_purpose == 'gradient' and len(custom_color_scheme) == bin_length):
                return custom_color_scheme
            else:
                print(f"Lens of custom_color_scheme ({len(custom_color_scheme)}) and bin_len ({bin_length} mismatch based on '{ascii_purpose}' ascii purpose.")
        else:
            ascii_dict =  {
                'low': color_map['red'][return_sequence],
                'mid': color_map['yellow'][return_sequence],
                'good': color_map['green'][return_sequence],
                'high': color_map['blue'][return_sequence]
            }
            if ascii_purpose == 'gradient':
                bin_length -= 1
            if bin_length == 1:
                return [v for k,v in ascii_dict.items() if k in ['low', 'good']]
            elif bin_length == 2:
                return [v for k,v in ascii_dict.items() if k in ['low', 'good', 'high']]
            elif bin_length == 3:
                return [v for k,v in ascii_dict.items() if k in ['low', 'mid', 'good', 'high']]
            else:
                return None
            
            
            

    def calc_rgb_from_colors_n_weights(self, color1, color2, weight):
        """Interpolate between two colors with a given weight."""
        r = (1 - weight) * color1[0] + weight * color2[0]
        g = (1 - weight) * color1[1] + weight * color2[1]
        b = (1 - weight) * color1[2] + weight * color2[2]
        return (r, g, b)

    def grab_gradient_ascii_from_param(self, input_val, param_bins, ascii_bins):
        ordered_bins = tuple(sorted(param_bins))
        ind_lower, ind_upper = (float('-inf'), 0) if input_val < ordered_bins[0] else (len(ordered_bins) - 1, float('inf')) if input_val >= ordered_bins[-1] else next((i, i + 1) for i in range(len(ordered_bins) - 1) if ordered_bins[i] <= input_val < ordered_bins[i + 1])
        if ind_lower == -np.inf:
            weight = 0
            ind_lower, ind_upper = ind_upper,ind_upper+1
        elif ind_upper == np.inf:
            weight = 1
            ind_lower, ind_upper = ind_lower-1,ind_lower
        else:
            range_upper = param_bins[ind_upper]
            range_lower = param_bins[ind_lower]
            weight = (input_val - range_lower) / (range_upper - range_lower)
        ascii_upper = ascii_bins[ind_upper]
        ascii_lower = ascii_bins[ind_lower]
        return "#" + "".join("%02x" % round(c * 255) for c in self.calc_rgb_from_colors_n_weights(ascii_lower, ascii_upper, weight))

    def compile_gradient_color_str(self, input_vals, input_param, custom_scheme=None):
        param_bins = self.data_analytics.helper_fns.grab_bins_from_param(input_param)
        if param_bins is not None:
            ascii_bins = self.grab_ascii_bins(len(param_bins), 'gradient', 'rgb', custom_scheme)
        val_str = ""
        for val in input_vals:
            if param_bins is not None:
                color_code = self.grab_gradient_ascii_from_param(val, param_bins, ascii_bins)
                val_str += "\033[38;2;{};{};{}m{}\033[0m".format(int(color_code[1:3], 16), int(color_code[3:5], 16), int(color_code[5:], 16), val)
            else:
                color_code = ""
                val_str += f'{round(val,2)} '
        return val_str


        
    def grab_static_ascii_from_param(self, input_val, param_bins, ascii_bins):
        ordered_bins = tuple(sorted(param_bins))
        return next((color for threshold, color in zip(ordered_bins, ascii_bins) if input_val < threshold), ascii_bins[-1])

    def compile_static_color_str(self, input_vals: list, input_param: str, custom_scheme = None):
        """
        Takes a value, minimum value, and maximum value and returns a
        background-color ANSI escape code for the cell based on the value's
        position between the minimum and maximum.
        """
        param_bins = self.data_analytics.helper_fns.grab_bins_from_param(input_param)
        is_numeric = lambda s: s.replace('.', '', 1).isdigit() if isinstance(s, str) else isinstance(s, (int, float))
        if param_bins is not None:
            ascii_bins = self.grab_ascii_bins(len(param_bins), 'static', 'ansi', custom_scheme)
        val_str = ""
        for val in input_vals:
            if param_bins is not None:
                color_code = self.grab_static_ascii_from_param(val, param_bins, ascii_bins)
                val_str += color_code + str(round(float(val),2)) + ' \033[0m'
            else:
                color_code = ""
                val_str += f'{round(float(val),2)}' if is_numeric(val) else val
        return val_str

    def compile_ascii_n_spacing_for_fixtures(self, all_fixture_data):
        '''
        Input data (all_fixture_data) is full fixture data per player_id of output from grab_upcoming_fixtures() in helper_fns.
        '''
        
        def highlight_blanks_and_gameweeks_from_data(all_fixture_data):
            isolated_gws = [x['gameweek'] for x in all_fixture_data]
            return {'dgws': list({x for x in isolated_gws if isolated_gws.count(x) > 1}), 'blanks': [x['gameweek'] for x in all_fixture_data if x['opponent_team'] is None]}
        gameweek_special_cases = highlight_blanks_and_gameweeks_from_data(all_fixture_data)
        
        fdr_color_scheme = config.FDR_COLOR_SCHEMES
        dgws = list(self.data_analytics.helper_fns.special_gws["dgws"].keys())
        
        one_white_space = ' '
        no_space = ''
        printstring, space_between_fixtures = no_space, one_white_space
        mgw_count = 0
        
        for gw_data in all_fixture_data:
            #For cases where this fixture is NOT a blank
            if gw_data['gameweek'] not in gameweek_special_cases['blanks']:
                xtra = no_space
                spacing = one_white_space
                space_between_fixtures = one_white_space
                
                #For cases where this fixture IS NOT a double but there are OTHER fixtures where this gw IS a double
                if gw_data['gameweek'] in dgws and gw_data['gameweek'] not in gameweek_special_cases['dgws']:
                    spacing = one_white_space*5
                    xtra = one_white_space
                #For cases where this fixture IS a double
                elif gw_data['gameweek'] in gameweek_special_cases['dgws']:
                    mgw_count += 1
                    if mgw_count == 1: space_between_fixtures = no_space
                    
                fdr = self.data_analytics.helper_fns.team_rank(gw_data['opponent_team'])
                rgb_tuple = fdr_color_scheme[fdr]
                team = self.data_analytics.helper_fns.grab_team_name_short(gw_data['opponent_team'])
                loc = 'H' if gw_data['is_home'] else 'A'
                
                printstring += f"\x1b[48;2;{rgb_tuple[0]};{rgb_tuple[1]};{rgb_tuple[2]}m{spacing}{team} ({loc}){spacing}{xtra}\x1b[0m{space_between_fixtures}"
            else:
                #For cases where there are OTHER fixtures where this gw IS a double
                if gw_data['gameweek'] in dgws:
                    spacing = one_white_space*8
                #For normal cases
                else:
                    spacing = one_white_space*4
                printstring += f"\x1b[48;2;210;210;210m{spacing}--{spacing}\x1b[0m{space_between_fixtures}"
        return printstring

    def compile_n_format_upcoming_fixtures_for_vis(self, fixture_dict_with_ids: dict):
        '''
        Input data (fixture_dict_with_ids) is output from grab_upcoming_fixtures() in helper_fns.
        '''
        return {int(float((player_id))): self.compile_ascii_n_spacing_for_fixtures(fixture_data) for player_id, fixture_data in fixture_dict_with_ids.items()}


    def compile_ascii_team_name(self, team_name_short):
        team_colors = config.TEAM_COLOR_SCHEMES

        if team_name_short in team_colors:
            bg_rgb_tuple = team_colors[team_name_short]['bg']
            text_rgb_tuple = team_colors[team_name_short]['text']
            colored_text = f'\x1b[38;2;{text_rgb_tuple[0]};{text_rgb_tuple[1]};{text_rgb_tuple[2]}m'
            colored_bg = f'\x1b[48;2;{bg_rgb_tuple[0]};{bg_rgb_tuple[1]};{bg_rgb_tuple[2]}m'
            reset_color = '\x1b[0m'
            return f'{colored_bg}{colored_text} {team_name_short} {reset_color}'
        else:
            return team_name_short


    def compile_ascii_past_fixtures(self, input_data: list):
        fdr_color_scheme = config.FDR_COLOR_SCHEMES
        printstring = ''
        for opponent_team_id in input_data:
            opponent_fdr = self.data_analytics.helper_fns.fdr_data[opponent_team_id]
            rgb_tuple = fdr_color_scheme[opponent_fdr]
            printstring += f'\x1b[48;2;{rgb_tuple[0]};{rgb_tuple[1]};{rgb_tuple[2]}m  \x1b[0m'
        return printstring

#============================================================== FUNCTION CONSOLIDATORS/DATA TRANSFORMATIONS FOR ASCII TABLES ============================================================
        
    def grab_colored_param_str_for_vis(self, input_data: list, input_param: str):
        if input_param in ['value']:
            if input_param == 'value':
                return self.compile_gradient_color_str(list(input_data), input_param, [(0, 0.7, 0), (0, 0, 1), (1, 0, 0)])
            else:
                return self.compile_gradient_color_str(list(input_data), input_param)
        elif input_param in ['opponent_team']:
            return self.compile_ascii_past_fixtures(input_data)
        elif input_param in ['team_short_name']:
            return self.compile_ascii_team_name(input_data[0])
        else:
            return self.compile_static_color_str(input_data, input_param)

    def transform_data_to_str_pt(self, input_data, input_param: str):
        if isinstance(input_data, list):
            if all(isinstance(item, (int, float)) for item in input_data):
                if input_param == "value":
                    return self.grab_colored_param_str_for_vis([input_data[-1]/10], input_param)
                data_avg = round(np.mean(input_data), 2)
                data_str = self.grab_colored_param_str_for_vis(input_data, input_param)
                if input_param == "opponent_team":
                    return data_str
                else:
                    return f'{data_avg}: {data_str}'
            else:
                return None
        else:
            return self.grab_colored_param_str_for_vis(input_data if isinstance(input_data, list) else [input_data], input_param)

    def transform_player_data_for_vis_pt(self, isolated_player_data: dict):

        transformed_player_data = []
        for player_data in isolated_player_data:
            temp_dict = defaultdict(lambda: defaultdict(list))
            for k,v in player_data.items():
                temp_dict[k] = self.transform_data_to_str_pt(v, k)
            transformed_player_data.append({k: v for k,v in temp_dict.items()})

        return [{k: v for k, v in d.items() if v is not None} for d in transformed_player_data]

    def build_player_tabular_summary(self, player_ids: list, param_spread: int = 5):

        compiled_player_data = self.data_analytics.helper_fns.compile_player_data(player_ids)
        sliced_player_data = self.data_analytics.helper_fns.slice_player_data(compiled_player_data, param_spread)
        seq_map = {'GKP':0, 'DEF':1, 'MID':2, 'FWD':3}
        sliced_player_data = sorted(sliced_player_data, key=lambda x: (seq_map[x['pos_singular_name_short']], -statistics.mean(x['total_points'])))
        plot_player_data = self.transform_player_data_for_vis_pt(sliced_player_data)

        cols_of_interest = ['pos_singular_name_short', 'team_short_name', 'web_name', 'value', 'opponent_team', 'total_points', 'bps', 'ict_index', 'expected_goal_involvements', 'minutes']

        table_cols = ['Position', 'Team', 'Player', 'Cost', 'Past FDRs', 'History', 'Bonus Points', 'ICT', 'xGI', 'Minutes']
        for league_info in self.data_analytics.helper_fns.league_data:
            table_cols += [league_info["symbol"]]
        table_cols += ['Upcoming Fixtures']
        tab = PrettyTable(table_cols)
        prev_position = None
        for player_data in plot_player_data:
            position = player_data['pos_singular_name_short']
            player_id = int(float(player_data['id']))
            if prev_position:
                if prev_position != position:
                    tab.add_row(['']*len(table_cols))
            temp_tab_row = []
            for col_name in cols_of_interest:
                temp_tab_row.append(player_data[col_name])
            for league_info in self.data_analytics.helper_fns.league_data:
                temp_tab_row.append(self.grab_ownership_count_str(int(float((player_data['id']))), league_name=league_info["name"] , format_color='buy'))
            temp_tab_row.append(self.compile_n_format_upcoming_fixtures_for_vis(self.data_analytics.helper_fns.grab_upcoming_fixtures([player_id], 4))[player_id])
            tab.add_row(temp_tab_row)
            prev_position = position
        print(tab)
        return plot_player_data

    def display_tabular_summary(self):
        replacements = self.data_analytics.replacement_players
        beacon_picks = list(self.data_analytics.beacon_effective_ownership.keys())
        values = list(set(replacements).union(set(beacon_picks)))
        values = [x for x in values if x not in list(self.data_analytics.personal_team_data.keys())]
        self.build_player_tabular_summary(player_ids=values)
        return

class FigureExporter():
    
    def __init__(self, fpl_data_analytics):
        self.data_analytics = fpl_data_analytics
        self._export_all_league_stat_figures()

#========================================================================================================================================================================================
#============================================================== FIGURE EXPORTS OUTLINING LEAGUE RANK/POINT SPREAD ACROSS GWS ============================================================
#========================================================================================================================================================================================

    def _export_all_league_stat_figures(self):
        for league_id in self.data_analytics.helper_fns.league_ids:
            self._export_league_stat_figures(league_id)

    def _export_league_stat_figures(self, league_id: int):
        total_player_data, last_update_time, league_name = self.data_analytics.helper_fns.get_rank_data(league_id)
        #In order to make league figure reasonable, only keep top 20 players
        total_player_data = total_player_data[:20]
        text_box_writing = f'Last update time: {last_update_time}'
        plot_settings = {
            "league_name": league_name,
            "league_id": league_id,
            "font_setting": 'Montserrat',
            "rights_text": "All rights reserved by the Premier League and its affiliates. Information usage solely for personal, non-commercial purposes abiding by terms and conditions set by the Premier League, including compliance with applicable laws and regulations regarding data usage and intellectual property rights.",
            "wrapped_text":  textwrap.fill(text_box_writing, width=30),  # Wrap the text to fit within 30 characters per line
            "rgb_setting_bg": (0.15, 0.15, 0.15),
            "rgb_setting_grid":  (0.2, 0.2, 0.2),
            "rgb_setting_font":  (1.0, 1.0, 0.95),
            "fig_size":  (20, 10),
            "color_cycle":  cycle([
                (0.12156862745098039, 0.4666666666666667, 0.7058823529411765),
                (1.0, 0.4980392156862745, 0.054901960784313725),
                (0.17254901960784313, 0.6274509803921569, 0.17254901960784313),
                (0.8392156862745098, 0.15294117647058825, 0.1568627450980392),
                (0.5803921568627451, 0.403921568627451, 0.7411764705882353),
                (0.5490196078431373, 0.33725490196078434, 0.29411764705882354),
                (0.8901960784313725, 0.4666666666666667, 0.7607843137254902),
                (0.4980392156862745, 0.4980392156862745, 0.4980392156862745),
                (0.7372549019607844, 0.7411764705882353, 0.13333333333333333),
                (0.09019607843137255, 0.7450980392156863, 0.8117647058823529),
                (0.984313725490196, 0.6862745098039216, 0.8941176470588236),
                (1.0, 0.8431372549019608, 0.7019607843137254),
                (0.7019607843137254, 0.8705882352941177, 0.4117647058823529),
                (0.9, 0.3, 0.6),
                (0.6, 0.9, 0.6),  
                (0.4, 0.4, 0.4),  
                (0.8, 0.4, 0.4)  
                ]),
        }
        
        for key in ['rank_history', 'total_points']:
            self._process_plot_functions(plt, plot_settings, total_player_data, custom_protocol=key)

    def _process_plot_functions(self, plot_obj, plot_settings: dict, input_data: list, custom_protocol=None):
        plot_obj.rcParams['font.family'] = plot_settings.get("font_setting")
        fig = plot_obj.figure(figsize=plot_settings.get("fig_size"))
        plot_obj.gca().set_facecolor(plot_settings.get("rgb_setting_bg"))
        for player_data in input_data:
            lookback = 9 if custom_protocol == "total_points" else 0
            params = [min(param, 20) if custom_protocol == "rank_history" else param for _, param in player_data[custom_protocol]][-lookback:]
            gws = [gw_num for gw_num, _ in player_data[custom_protocol]][-lookback:]
            color = next(plot_settings.get("color_cycle"))
            plot_obj.plot(gws, params, marker='', linestyle='-', color=color, linewidth=2.5, label=' '.join([word.capitalize() for word in player_data["player_name"].split()]))
        plot_obj.xlabel('Gameweek', color=plot_settings.get("rgb_setting_font"), fontsize=18, fontname=plot_settings.get("font_setting"), labelpad=20)
        
        if custom_protocol == "rank_history":
            plot_obj.ylabel('League Rank', color=plot_settings.get("rgb_setting_font"), fontsize=16, fontname=plot_settings.get("font_setting"), labelpad=20)
            plot_obj.title(f"League Rank History '23/24: {plot_settings.get('league_name')}", color=plot_settings.get("rgb_setting_font"), fontsize=22, fontname=plot_settings.get("font_setting"), pad=30)
            plot_obj.gca().invert_yaxis()
            placements = ['{}{}'.format(num, 'th' if 11 <= num <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(num % 10, 'th')) for num in range(1, len(input_data) + 1)]
            plot_obj.yticks(np.arange(1, max(params) + 1), placements, color=plot_settings.get("rgb_setting_font"), fontname=plot_settings.get("font_setting"), fontsize=13)
            plot_obj.xticks(np.arange(min(gws), max(gws) + 1), color=plot_settings.get("rgb_setting_font"), fontname=plot_settings.get("font_setting"), fontsize=13)
            figure_png_name = f'ranks_{plot_settings.get("league_id")}'
        elif custom_protocol == "total_points":
            plot_obj.ylabel('League Points', color=plot_settings.get("rgb_setting_font"), fontsize=16, fontname=plot_settings.get("font_setting"), labelpad=20)
            plot_obj.title(f"League Points History '23/24: {plot_settings.get('league_name')}", color=plot_settings.get("rgb_setting_font"), fontsize=22, fontname=plot_settings.get("font_setting"), pad=30)
            plot_obj.yticks(color=plot_settings.get("rgb_setting_font"), fontname=plot_settings.get("font_setting"), fontsize=13)
            plot_obj.xticks(np.arange(min(gws), max(gws) + 1), color=plot_settings.get("rgb_setting_font"), fontname=plot_settings.get("font_setting"), fontsize=13)
            figure_png_name = f'pts_{plot_settings.get("league_id")}'
            
        plot_obj.grid(True, linestyle='-', color=plot_settings.get("rgb_setting_grid"))
        plot_obj.gca().xaxis.set_tick_params(color=plot_settings.get("rgb_setting_grid"))
        plot_obj.gca().yaxis.set_tick_params(color=plot_settings.get("rgb_setting_grid"))
        
        plot_obj.text(1.15, -0.1, plot_settings.get("wrapped_text"), color=plot_settings.get("rgb_setting_font"), fontsize=8, fontname=plot_settings.get("font_setting"),
                transform=plot_obj.gca().transAxes, verticalalignment='bottom', horizontalalignment='right',
                bbox=dict(facecolor=plot_settings.get("rgb_setting_bg"), edgecolor=plot_settings.get("rgb_setting_bg"), alpha=0.5, boxstyle='round,pad=0.5'))
        plot_obj.text(1.03, 0.08, textwrap.fill(plot_settings.get("rights_text"), width=30), color=plot_settings.get("rgb_setting_font"), fontsize=6, fontname=plot_settings.get("font_setting"),
                transform=plot_obj.gca().transAxes, verticalalignment='bottom', horizontalalignment='left',
                bbox=dict(facecolor=plot_settings.get("rgb_setting_bg"), edgecolor=plot_settings.get("rgb_setting_bg"), alpha=0.5, boxstyle='round,pad=0.5'))
        plot_obj.text(-0.035, -0.07, 'javaidb', color=plot_settings.get("rgb_setting_font"), fontsize=8, fontname=plot_settings.get("font_setting"),
                transform=plot_obj.gca().transAxes, verticalalignment='bottom', horizontalalignment='left',
                bbox=dict(facecolor=plot_settings.get("rgb_setting_bg"), edgecolor=plot_settings.get("rgb_setting_bg"), alpha=0.5, boxstyle='round,pad=0.5'))
        
        def add_logo(path_to_logo, image_bottom_left_x, image_bottom_left_y, image_width):
            """
            Adds a logo image and text to a plot at specific positions.

            Parameters:
                path_to_logo (str): The file path to the logo image that will be added to the plot.
                image_bottom_left_x (float): The x-coordinate of the bottom-left corner of the logo image's position on the plot.
                image_bottom_left_y (float): The y-coordinate of the bottom-left corner of the logo image's position on the plot.
                image_width (float): The width of the logo image in the plot.
            """

            logo = Image.open(path_to_logo)
            image_array = np.array(logo)
            image_height = image_width * image_array.shape[0] / image_array.shape[1]

            ax_image = plot_obj.axes([image_bottom_left_x,
                                image_bottom_left_y,
                                image_width,
                                image_height])
            ax_image.imshow(image_array)
            ax_image.axis('off') # Remove axis of the image in order to improve style
        
        plot_obj.legend(loc='upper right', facecolor=plot_settings.get("rgb_setting_bg"), edgecolor=plot_settings.get("rgb_setting_bg"), labelcolor=plot_settings.get("rgb_setting_font"), fontsize = 12, bbox_to_anchor=(1.16, 1))
        plot_obj.box(False)  # Remove borders
        
        plot_obj.gca().spines['bottom'].set_color(plot_settings.get("rgb_setting_font"))
        plot_obj.gca().spines['left'].set_color(plot_settings.get("rgb_setting_font"))
        plot_obj.gca().spines['top'].set_color(plot_settings.get("rgb_setting_font"))
        plot_obj.gca().spines['right'].set_color(plot_settings.get("rgb_setting_font"))
        
        if custom_protocol == "rank_history":
            rectangle = plot_obj.Rectangle((self.data_analytics.helper_fns.latest_gw, 0.5), 0.1, 1, color='gold', alpha=0.5)
            fig.gca().add_patch(rectangle)
            rectangle = plot_obj.Rectangle((self.data_analytics.helper_fns.latest_gw, 1.5), 0.1, 1, color='silver', alpha=0.5)
            fig.gca().add_patch(rectangle)
            rectangle = plot_obj.Rectangle((self.data_analytics.helper_fns.latest_gw, 2.5), 0.1, 1, color='orange', alpha=0.5)
            fig.gca().add_patch(rectangle)
            rectangle = plot_obj.Rectangle((self.data_analytics.helper_fns.latest_gw, 3.5), 0.1, len(input_data)-4, color='green', alpha=0.2)
            fig.gca().add_patch(rectangle)
            rectangle = plot_obj.Rectangle((self.data_analytics.helper_fns.latest_gw, len(input_data)-0.5), 0.1, 1, color='red', alpha=0.5)
            fig.gca().add_patch(rectangle)
            # plot_obj.gca().add_patch(plot_obj.Rectangle((self.data_analytics.helper_fns.latest_gw + 1, 14), 0.001, 5, color = (1, 1, 0.8), alpha = 0.99, zorder = 10))

        # Add github and other credentials
        league_name = plot_settings.get("league_name")
        images_dir_relative = grab_path_relative_to_root("images/", relative=True, create_if_nonexistent=True)
        add_logo(f'{images_dir_relative}/github-mark-white.png', 0.08, 0.05, 0.02)
        add_logo(f'{images_dir_relative}/bar-graph.png', 0.89, 0.31, 0.12)
        add_logo(f'{images_dir_relative}/FPL_Fantasy_2.png', 0.88, 0.09, 0.16)
        figs_dir_relative = grab_path_relative_to_root(f"figures/{league_name}", relative=True, create_if_nonexistent=True)
        plot_obj.savefig(f'{figs_dir_relative}/league_{figure_png_name}.png', bbox_inches='tight', facecolor=plot_settings.get("rgb_setting_bg"), edgecolor=plot_settings.get("rgb_setting_bg"), transparent=True)


#========================================================================================================================================================================================
#========================================================================================================================================================================================