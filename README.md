
# Performance Analysis for FPL (Fantasy Premier League)

This project is used a personal self-study into several areas such as data collection & wrangling, feature engineering, data analysis & modeling and visualization. At surface level, it is used as a broad view of in-form players currently in the Premier League to inform an ideal Fantasy Premier League (FPL) team to maximize performance/points output. FPL is a game which assigns points to a player based on their performance output in a given game week, and so, being able to assess performance over time either by modeling or by assessment of surface statistics is vital to maximize returns.

## Usage

In order to get started:

- Clone this repository to your local machine.
- Within src/config, make relevant changes within data_template.json AND rename data.json:
   - "beacon_team_ids" - a custom feature to include rivals you would like to measure your team against, typically those with demonstrated success.
   - "personal_team_id: - entry to include your personal FPL team ID (can be obtained through official FPL website).
   - "personal_league_ids" - used to track statistics and ranks within leagues your FPL team belongs to (or whichever is entered within "personal_team_id").
- Navigate to notebooks folder and open "visualize_metrics" within jupyter environment. Visualization and consolidation of FPL details are implemented through here.
- To execute, simply hit run all.

## Acknowledgements

 - [Fantasy Premier League](https://fantasy.premierleague.com/)
 - [Understat](https://understat.com/)

## Authors

- [@javaidb](https://www.github.com/javaidb)


## Badges

Add badges from somewhere like: [shields.io](https://shields.io/)

[![IBM License](https://img.shields.io/badge/Certificate_ML-IBM-green.svg)](https://www.credly.com/badges/6d82b78c-cade-4a4c-94cb-b7f89e142350/public_url)
