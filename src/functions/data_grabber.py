import sys
import os
sys.path.append(os.path.abspath('..'))
from src.functions.raw_data_fetcher import FPLFetcher, UnderstatFetcher
from src.functions.data_builder import RawDataCompiler
from src.functions.helper_fns import GeneralHelperFns, UnderStatHelperFns

fpl_api_fetcher = FPLFetcher()
fpl_data_compiler = RawDataCompiler(fpl_api_fetcher)
helper_fns = GeneralHelperFns(fpl_api_fetcher, fpl_data_compiler)

class DataGrabberFPL:
    def __init__(self):
        self.helper_fns = helper_fns

        self.fpl_raw_data = fpl_api_fetcher.raw_data
        self.personal_fpl_raw_data = fpl_api_fetcher.personal_fpl_raw_data
        self.rival_stats = fpl_api_fetcher.rival_stats
        self.rival_id_data = fpl_api_fetcher.rival_id_data
        self.fixtures = fpl_api_fetcher.fixtures
        self.latest_gw = fpl_api_fetcher.latest_gw
        self.season_year_span_id = fpl_api_fetcher.season_year_span_id
        self.player_ids = fpl_api_fetcher.player_ids
        self.master_summary = fpl_data_compiler.master_summary
        self.master_summary_tabular = fpl_data_compiler.master_summary_tabular
        self.league_data = fpl_data_compiler.league_data

class DataGrabberUnderstat:
    def __init__(self, update_bool = False):
        self.update_bool = update_bool
        self.attributes = UnderstatFetcher(fpl_api_fetcher, helper_fns, update_bool) 
        # self._process_understat_data(update_bool)
        self.helper_fns = UnderStatHelperFns(self.attributes)

    # def _process_understat_data(self, update_bool):
    #     if update_bool:

    #     else:
    #         data_path = grab_path_relative_to_root("cached_data/understat")