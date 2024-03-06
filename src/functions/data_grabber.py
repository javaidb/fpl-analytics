import sys
import os
sys.path.append(os.path.abspath('..'))
from src.functions.api_fetcher import FPLAPIParser, UnderstatAPIParser
from src.functions.data_builder import RawDataCompiler
from src.functions.helper_fns import GeneralHelperFns

fpl_api_fetcher = FPLAPIParser()
fpl_data_compiler = RawDataCompiler(fpl_api_fetcher)
helper_fns = GeneralHelperFns(fpl_api_fetcher, fpl_data_compiler)

class DataGrabber:
    def __init__(self):
        self.helper_fns = helper_fns

        self.personal_fpl_raw_data = fpl_api_fetcher.personal_fpl_raw_data
        self.rival_stats = fpl_api_fetcher.rival_stats
        self.rival_id_data = fpl_api_fetcher.rival_id_data
        self.fixtures = fpl_api_fetcher.fixtures
        self.latest_gw = fpl_api_fetcher.latest_gw
        self.player_ids = fpl_api_fetcher.player_ids

        self.master_summary = fpl_data_compiler.master_summary
        self.league_data = fpl_data_compiler.league_data