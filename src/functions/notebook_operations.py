from prettytable import PrettyTable
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
from itertools import cycle
import numpy as np
import textwrap
from PIL import Image

class VisualizationOperations:
    
    def __init__(self, api_parser, data_parser, data_analytics, helper_fns):
        self.api_parser = api_parser
        self.data_parser = data_parser
        self.data_analytics = data_analytics
        self.helper_fns = helper_fns
        self.output_league_stats_across_gameweeks()

    #========================== Plot data ==========================


    def plot_multi_stats(self,param,dataset,values,remove_FPL15 = False):
        df = self.data_parser.total_summary.copy()
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
                    df = df.loc[~df['id_player'].isin(self.data_analytics.optimized_personal_team_df.id.to_list())]
            elif dataset == 'myteam':
                pos = values[0]
                lookback = 6
                df = df.loc[(df['id_player'].isin(self.data_analytics.optimized_personal_team_df.id.to_list())) & (df['position'] == pos)]
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
            color = self.helper_fns.fetch_single_team_color(self.helper_fns.grab_player_team_id(d['id_player']))
            team = self.helper_fns.grab_player_team(d['id_player'])
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

    def plot_individual_stats(self,player_name,paramlist):
        return

    #========================== Tabular data ==========================


    def grab_ownership_count_str(self,player_id,league_id,format_color):
        ids = self.data_parser.effective_ownership[str(league_id)]
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
    

    def calc_rgb_from_colors_n_weights(self,color1, color2, weight):
        """Interpolate between two colors with a given weight."""
        r = (1 - weight) * color1[0] + weight * color2[0]
        g = (1 - weight) * color1[1] + weight * color2[1]
        b = (1 - weight) * color1[2] + weight * color2[2]
        return (r, g, b)


    def compile_grad_color_str(self,value, min_val, med_val, max_val):
        if value < med_val:
            weight = (value - min_val) / (med_val - min_val)
            color1 = (0, 0.7, 0) # green
#             color2 = (1, 0.5, 0) # orange
            color2 = (0, 0, 1) # blue
            hex_string =  "#" + "".join("%02x" % round(c * 255) for c in self.calc_rgb_from_colors_n_weights(color1, color2, weight))
        else:
            weight = (value - med_val) / (max_val - med_val)
            color1 = (0, 0, 1) # blue
#             color1 = (1, 0.5, 0) # yellow
            color2 = (1, 0, 0) # red
    #         color2 = (0, 0, 1) # blue
            hex_string = "#" + "".join("%02x" % round(c * 255) for c in self.calc_rgb_from_colors_n_weights(color1, color2, weight))
    
        color = hex_string
        text = value
        colored_text = "\033[38;2;{};{};{}m{}\033[0m".format(
            int(color[1:3], 16), int(color[3:5], 16), int(color[5:], 16), text
        )
        return colored_text
    

    def compile_static_color_str(self,tuple_val, param):
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
                # color_code = '\033[1;30;2m'  # muted grey
            elif val <= mid_thr:
                color_code = '\033[1;33m'  # bold yellow
            elif val <= high_thr:
                color_code = '\033[1;32m'  # bold green
            else:
                color_code = '\033[1;34m'  # bold blue
            val_str += color_code + str(round(val,2)) + ' \033[0m'
        return avg_str + val_str
    

    def get_colored_fixtures(self,team_id, look_ahead, reference_gw=None):
        fdr_color_scheme = {
            1: (79, 121, 66),
            2: (51, 230, 153),
            3: (210, 210, 210),
            4: (255, 64, 107),
            5: (150, 27, 67)
        }

        fixturelist = self.helper_fns.grab_player_fixtures('fwd',team_id,look_ahead, reference_gw)
        dgws = list(self.api_parser.dgws.keys())
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
 

    def grab_color_from_team_str(self, team_name_short):
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


        if team_name_short in team_colors:
            bg_rgb_tuple = team_colors[team_name_short]['bg']
            text_rgb_tuple = team_colors[team_name_short]['text']
            colored_text = f'\x1b[38;2;{text_rgb_tuple[0]};{text_rgb_tuple[1]};{text_rgb_tuple[2]}m'
            colored_bg = f'\x1b[48;2;{bg_rgb_tuple[0]};{bg_rgb_tuple[1]};{bg_rgb_tuple[2]}m'
            reset_color = '\x1b[0m'
            formatted_string = f'{colored_bg}{colored_text} {team_name_short} {reset_color}'
        else:
            formatted_string = team_name_short
        return formatted_string


    def get_past_fixtures_colors(self,team_id, look_behind):
        fdr_color_scheme = {
            1: (79, 121, 66),
            2: (51, 230, 153),
            3: (210, 210, 210),
            4: (255, 64, 107),
            5: (150, 27, 67)
        }

        fixturelist = self.helper_fns.grab_player_fixtures('rev',team_id,look_behind)
        printstring = ''
        count = 0
        for gw in fixturelist:
            fixtures = gw[-1]
            if fixtures:
                for fixture in fixtures:
                    if count < look_behind:
                        count += 1
                        fdr = fixture[3]
                        rgb_tuple = fdr_color_scheme[fdr]
                        printstring += f'\x1b[48;2;{rgb_tuple[0]};{rgb_tuple[1]};{rgb_tuple[2]}m  \x1b[0m'
            else:
                continue
        return printstring


    def player_summary(self, dataset: str, values: list = None):
        if dataset == 'custom':
            players = values
            player_ids = []
            for player in players:
                if isinstance(player, str):
                    found_plyr = self.helper_fns.loop_name_finder(player)
                    if not found_plyr:
                        print(f'Empty entry, skipping player.')
                        continue
                    df = self.data_parser.total_summary.loc[self.data_parser.total_summary['player'] == str(found_plyr)]
                    player_ids.append(df.id_player.values[0])
                else:
                    player_ids.append(player)
            players = [x for x in self.data_analytics.players if x['id'] in player_ids]
            format_color = 'buy'
        elif dataset == 'FPL15':
            players = [x for x in self.data_analytics.players if x['id'] in self.data_analytics.optimized_personal_team_df['id'].to_list()]
            format_color = 'sell'
        else:
            print("'dataset' variable must be one of 'FPL15' or 'custom'")
            return
        seq_map = {'GKP':0, 'DEF':1, 'MID':2, 'FWD':3}
        sorted_players = sorted(players, key=lambda x: (seq_map[x['position']], -x['history'][0]))
        prev_position = None
    
        table_cols = ['FPL15 Player','Position','Team','Past FDRs','History','Bonus Points','ICT','xGI','Minutes','xGC','Cost','𝙹𝚀𝚁','𝙶𝚂𝙿','☆₁ₖ','☆₁₀ₖ','☆₁₀₀ₖ','☆','Upcoming Fixtures']
        tab = PrettyTable(table_cols)
        for plyr_dict in sorted_players:
            cost = plyr_dict['cost']
            name = plyr_dict['name']
            position = plyr_dict['position']
            team_id = self.helper_fns.grab_player_team_id(plyr_dict['id'])
            if prev_position:
                if prev_position != position:
                    tab.add_row(['']*len(table_cols))
            if position == 'DEF':
                tab.add_row([name,
                             position,
                             self.grab_color_from_team_str(self.helper_fns.grab_team_name_short(team_id)),
                             self.get_past_fixtures_colors(team_id,6),
                             self.compile_static_color_str(plyr_dict['history'],'history'),
                             self.compile_static_color_str(plyr_dict['bps'],'bps'),
                             self.compile_static_color_str(plyr_dict['ict'],'ict'),
                             self.compile_static_color_str(plyr_dict['xGI'],'xGI'),
                             self.compile_static_color_str(plyr_dict['minutes'],'minutes'),
                             round(plyr_dict['xGC'][0],2),
                             self.compile_grad_color_str(cost,min(cost,3.8),7,max(cost,13)),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id=782655,format_color=format_color),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id=467038,format_color=format_color),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id='beacon_1k',format_color=format_color),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id='beacon_10k',format_color=format_color),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id='beacon_100k',format_color=format_color),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id='beacon_aggregate',format_color=format_color),
                             self.get_colored_fixtures(self.helper_fns.grab_player_team_id(plyr_dict['id']),5)
                            ])
            else:
                tab.add_row([name,
                             position,
                             self.grab_color_from_team_str(self.helper_fns.grab_team_name_short(team_id)),
                             self.get_past_fixtures_colors(team_id,6),
                             self.compile_static_color_str(plyr_dict['history'],'history'),
                             self.compile_static_color_str(plyr_dict['bps'],'bps'),
                             self.compile_static_color_str(plyr_dict['ict'],'ict'),
                             self.compile_static_color_str(plyr_dict['xGI'],'xGI'),
                             self.compile_static_color_str(plyr_dict['minutes'],'minutes'),
                             '-',
                             self.compile_grad_color_str(cost,min(cost,3.8),7,max(cost,13)),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id=782655,format_color=format_color),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id=467038,format_color=format_color),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id='beacon_1k',format_color=format_color),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id='beacon_10k',format_color=format_color),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id='beacon_100k',format_color=format_color),
                             self.grab_ownership_count_str(plyr_dict['id'],league_id='beacon_aggregate',format_color=format_color),
                             self.get_colored_fixtures(self.helper_fns.grab_player_team_id(plyr_dict['id']),5)
                            ])
            prev_position = position
        print(tab)
        

    def replacement_summary(self, net_limit = True):
        net_spend_limit = round(self.api_parser.personal_fpl_raw_data['entry_history']['bank']/10, 2)
        tab = PrettyTable(['FPL15 Player','Position','FPL15 ICT','FPL15 xGI','FPL15 xGC','Replacement','Team','Past FDRs','ICT','xGI','xGC','Net Spend','Upcoming Fixtures'])
        if net_limit:
            nets = [d[-1] for inner_dict in self.my_dict.values() for d in inner_dict['replacement'] if d[-1] <= net_spend_limit]
        else:
            nets = [d[-1] for inner_dict in self.my_dict.values() for d in inner_dict['replacement']]
        for key in self.my_dict:
            FPL15_player_name = key
            comp_dict = self.my_dict[key]
            replacements = comp_dict['replacement']
            sorted_replacements = sorted(replacements, key=lambda x: x[0]['history'][0], reverse=True)
            count = 0
            for r in sorted_replacements:
                position = comp_dict['stats']['position']
                name = r[0]['name']
                team_id = self.helper_fns.grab_player_team_id(r[0]['id'])
                net = r[-1]
                if net_limit:
                    cond = (net <= net_spend_limit)
                else:
                    cond = True
                if cond:
                    if count == 0:
                        tab.add_row(['']*13)
                        FPL15_ICT = self.compile_static_color_str(comp_dict['stats']['ict'],'ict')
                        FPL15_xGI = self.compile_static_color_str(comp_dict['stats']['xGI'],'xGI')
                        if position == 'DEF':
                            FPL15_xGC = round(comp_dict['stats']['xGC'][0],2)
                        FPL15_pos = position
                    else:
                        FPL15_player_name, FPL15_pos, FPL15_ICT, FPL15_xGI, FPL15_xGC = '','','','',''
                    count += 1
                    if position == 'DEF':
                        tab.add_row([FPL15_player_name,
                                     FPL15_pos,
                                     FPL15_ICT,
                                     FPL15_xGI,
                                     FPL15_xGC,
                                     name,
                                     self.grab_color_from_team_str(self.helper_fns.grab_team_name_short(team_id)),
                                     self.get_past_fixtures_colors(team_id,6),
                                     self.compile_static_color_str(r[0]['ict'],'ict'),
                                     self.compile_static_color_str(r[0]['xGI'],'xGI'),
                                     round(r[0]['xGC'][0],2),
                                     self.compile_grad_color_str(net,min(nets),0,max(nets)),
                                     self.get_colored_fixtures(self.helper_fns.grab_player_team_id(r[0]['id']),5)])
                    else:
                        tab.add_row([FPL15_player_name,
                                     FPL15_pos,
                                     FPL15_ICT,
                                     FPL15_xGI,
                                     '-',
                                     name,
                                     self.grab_color_from_team_str(self.helper_fns.grab_team_name_short(team_id)),
                                     self.get_past_fixtures_colors(team_id,6),
                                     self.compile_static_color_str(r[0]['ict'],'ict'),
                                     self.compile_static_color_str(r[0]['xGI'],'xGI'),
                                     '-',
                                     self.compile_grad_color_str(net,min(nets),0,max(nets)),
                                     self.get_colored_fixtures(self.helper_fns.grab_player_team_id(r[0]['id']),5)])
        tab.align["Upcoming Fixtures"] = "l"
        print(tab)

#============================================  QUICK-ACCESS FUNCTIONS  ============================================

    def display_tabular_summary(self):
        replacements = [x['id'] for x in self.data_analytics.replacement_players]
        beacon_picks = list(self.data_analytics.beacon_effective_ownership.keys())
        values = list(set(replacements).union(set(beacon_picks)))
        values = [x for x in values if x not in self.data_analytics.optimized_personal_team_df.id.tolist()]
        self.player_summary(dataset='custom',values=values)
        return

    def _process_plot_functions(self, plot_obj, plot_settings:dict, input_data: list, custom_protocol=None):
        plot_obj.rcParams['font.family'] = plot_settings.get("font_setting")
        fig = plot_obj.figure(figsize=plot_settings.get("fig_size"))
        plot_obj.gca().set_facecolor(plot_settings.get("rgb_setting_bg"))
        for player_data in input_data:
            if custom_protocol == "entry_history":
                lookback = 9
            elif custom_protocol == "rank_history":
                lookback = 0
            params = [param for _, param in player_data[custom_protocol]][-lookback:]
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
        elif custom_protocol == "entry_history":
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
            rectangle = plot_obj.Rectangle((self.api_parser.latest_gw, 0.5), 0.1, 1, color='gold', alpha=0.5)
            fig.gca().add_patch(rectangle)
            rectangle = plot_obj.Rectangle((self.api_parser.latest_gw, 1.5), 0.1, 1, color='silver', alpha=0.5)
            fig.gca().add_patch(rectangle)
            rectangle = plot_obj.Rectangle((self.api_parser.latest_gw, 2.5), 0.1, 1, color='orange', alpha=0.5)
            fig.gca().add_patch(rectangle)
            rectangle = plot_obj.Rectangle((self.api_parser.latest_gw, 3.5), 0.1, 13, color='green', alpha=0.2)
            fig.gca().add_patch(rectangle)
            rectangle = plot_obj.Rectangle((self.api_parser.latest_gw, 16.5), 0.1, 1, color='red', alpha=0.5)
            fig.gca().add_patch(rectangle)
            plot_obj.gca().add_patch(plot_obj.Rectangle((self.api_parser.latest_gw + 1, 14), 0.001, 5, color = (1, 1, 0.8), alpha = 0.99, zorder = 10))

        # Add github and other credentials
        add_logo('../../images/github_logo.png', 0.08, 0.05, 0.02)
        add_logo('../../images/bar-graph.png', 0.89, 0.31, 0.12)
        add_logo('../../images/FPL_Fantasy_2.png', 0.88, 0.09, 0.16)
        plot_obj.savefig(f'../../figures/league_{figure_png_name}.png', bbox_inches='tight', facecolor=plot_settings.get("rgb_setting_bg"), edgecolor=plot_settings.get("rgb_setting_bg"), transparent=True)

    def output_league_stats_across_gameweeks(self, league_id = 782655):
        total_player_data, last_update_time, league_name = self.helper_fns.get_rank_data(league_id)
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
        
        for key in ['rank_history', 'entry_history']:
            self._process_plot_functions(plt, plot_settings, total_player_data, custom_protocol=key)