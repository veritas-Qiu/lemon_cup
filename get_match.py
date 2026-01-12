import requests
import json
import time
import argparse
try:
    import tomllib
except ImportError:
    import toml as tomllib

# global variables
# token need to be updated manually if it's expired    
TOKEN = "16c0b7506b59d7c8a5b94ed7245bd4111527392a"
# Milana's steam ID
STEAM_ID = "76561198130026890"
#season start date
SEASON_START_DATE = "20251222"

def get_match_ids():
    
    url = f"https://gwapi.pwesports.cn/appdatacenter/dota/match/matchResult?mySteamId={STEAM_ID}&pageSize=50&steamId={STEAM_ID}&page=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "token": TOKEN
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Check for HTTP errors
        
        # Try to parse as JSON
        try:
            data = response.json()
            
            filtered_match_ids = []
            
            # Navigate to result -> matchList
            if 'result' in data and isinstance(data['result'], dict):
                match_list = data['result'].get('matchList', [])
                
                for match in match_list:
                    level = match.get('level')
                    end_day = match.get('endDay')
                    
                    # Check conditions: level is "职业联赛" and endDay >= season start date
                    if level == "职业联赛" and end_day and end_day >= SEASON_START_DATE:
                        filtered_match_ids.append(match.get('matchId'))
                
                print(filtered_match_ids)
                return filtered_match_ids
                
            else:
                print("Unexpected JSON structure: 'result' not found or invalid format")
                # print(json.dumps(data, indent=2, ensure_ascii=False))
                return []
                
        except ValueError:
            print("Response is not JSON")
            print(response.text[:500]) # Print first 500 chars if not JSON
            return []
        
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return []

def get_match_datas(match_ids):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "token": TOKEN
    }
    
    all_matches_info = []

    for match_id in match_ids:
        url = f"https://gwapi.pwesports.cn/appdatacenter/api/v1/dota2/matches?matchId={match_id}&platform=admin"
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if 'result' in data and len(data['result']) > 0:
                # Assuming the first result is the one we want
                match_result = data['result'][0]
                if 'data' in match_result:
                    match_detail = match_result['data']
                    players = match_detail.get('players', [])
                    
                    match_players_info = []
                    for player in players:
                        match_players_info.append({
                            "account_id": player.get('account_id'),
                            "persona": player.get('persona'),
                            "hero": player.get('hero_name_zh'), # Using Chinese name as per sample
                            "win": player.get('is_win')
                        })
                    
                    all_matches_info.append({
                        "match_id": match_id,
                        "players": match_players_info
                    })
            
            # Sleep briefly to avoid rate limiting
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching match {match_id}: {e}")
        except ValueError:
            print(f"Error parsing JSON for match {match_id}")

    return all_matches_info

def get_user_stats():
    # Load MMR data
    try:
        with open('mmr.toml', 'rb') as f:
            mmr_data = tomllib.load(f)
    except FileNotFoundError:
        print("mmr.toml not found.")
        return

    # Load match details (assuming it's already generated or we fetch it)
    try:
        with open('match_details.json', 'r', encoding='utf-8') as f:
            match_details = json.load(f)
    except FileNotFoundError:
        print("match_details.json not found. Please run match fetching first.")
        return

    # Helper to resolve main ID
    def get_main_id(account_id):
        str_id = str(account_id)
        if str_id in mmr_data:
            if 'main_id' in mmr_data[str_id]:
                return mmr_data[str_id]['main_id']
            return int(str_id)
        return int(str_id)

    # Initialize stats
    player_stats = {} # main_id -> {score, wins, losses, total}
    hero_stats = {} # hero_name -> {wins, losses, total}
    
    # Initialize all players from mmr.toml
    for str_id, info in mmr_data.items():
        main_id = get_main_id(str_id)
        if main_id not in player_stats:
            # Try to find name for main_id
            name = info['name']
            if str(main_id) in mmr_data:
                 name = mmr_data[str(main_id)]['name']
            
            player_stats[main_id] = {
                'name': name,
                'score': 100,
                'wins': 0,
                'losses': 0,
                'total': 0
            }

    matches_processed = 0

    for match in match_details:
        players = match['players']
        
        # 1. Check for 0 MMR players
        has_zero_mmr = False
        win_mmr = 0
        loss_mmr = 0
        
        current_match_players = [] # Store (main_id, is_win)
        
        for p in players:
            acc_id = p['account_id']
            str_id = str(acc_id)
            
            if str_id not in mmr_data:
                 # Player not in TOML, treat as 0 MMR effectively
                 has_zero_mmr = True
                 break
            
            player_mmr = mmr_data[str_id]['mmr']
            if player_mmr == 0:
                has_zero_mmr = True
                break
                
            is_win = p['win']
            if is_win:
                win_mmr += player_mmr
            else:
                loss_mmr += player_mmr
            
            main_id = get_main_id(acc_id)
            current_match_players.append((main_id, is_win))

        if has_zero_mmr:
            continue
            
        # 2. Calculate score
        diff = abs(win_mmr - loss_mmr)
        match_score = 0
        if diff < 30:
            match_score = 25
        elif 30 <= diff < 50:
            match_score = 20
        else: # diff >= 50
            match_score = 15
            
        # 3. Update player stats
        for main_id, is_win in current_match_players:
            if main_id not in player_stats:
                 if str(main_id) in mmr_data:
                     name = mmr_data[str(main_id)]['name']
                 else:
                     name = f"Unknown({main_id})"
                 player_stats[main_id] = {'name': name, 'score': 100, 'wins': 0, 'losses': 0, 'total': 0}

            stats = player_stats[main_id]
            stats['total'] += 1
            if is_win:
                stats['score'] += match_score
                stats['wins'] += 1
            else:
                stats['score'] -= match_score
                stats['losses'] += 1
        
        # Update hero stats (iterate original players list again since current_match_players only has ids)
        for p in players:
             hero_name = p.get('hero', 'Unknown')
             is_win = p.get('win')
             
             if hero_name not in hero_stats:
                 hero_stats[hero_name] = {'wins': 0, 'losses': 0, 'total': 0}
             
             h_stats = hero_stats[hero_name]
             h_stats['total'] += 1
             if is_win:
                 h_stats['wins'] += 1
             else:
                 h_stats['losses'] += 1
        
        matches_processed += 1

    # 5. Output Markdown
    sorted_players = sorted(player_stats.values(), key=lambda x: x['score'], reverse=True)
    
    md_output = "## 选手榜单\n\n"
    md_output += "| 排名 | 选手 | 分数 | 胜 | 负 | 总场次 | 胜率 |\n"
    md_output += "| --- | --- | --- | --- | --- | --- | --- |\n"
    
    for i, p in enumerate(sorted_players):
        if p['total'] > 0: # Only show players who played valid matches
            win_rate = (p['wins'] / p['total'] * 100) if p['total'] > 0 else 0
            md_output += f"| {i+1} | {p['name']} | {p['score']} | {p['wins']} | {p['losses']} | {p['total']} | {win_rate:.1f}% |\n"
    
    md_output += "\n## 英雄榜单\n\n"
    md_output += "| 排名 | 英雄 | 胜 | 负 | 总场次 | 胜率 |\n"
    md_output += "| --- | --- | --- | --- | --- | --- |\n"
    
    # Sort heroes by win rate (descending) then by total games (descending)
    sorted_heroes = sorted(hero_stats.items(), key=lambda x: (x[1]['wins']/x[1]['total'] if x[1]['total']>0 else 0, x[1]['total']), reverse=True)

    for i, (hero, stats) in enumerate(sorted_heroes):
        win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
        md_output += f"| {i+1} | {hero} | {stats['wins']} | {stats['losses']} | {stats['total']} | {win_rate:.1f}% |\n"
            
    print(md_output)
    
    with open('leaderboard.md', 'w', encoding='utf-8') as f:
        f.write(md_output)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rocket Cup Stats")
    parser.add_argument('--update', action='store_true', help='Fetch and update match data')
    args = parser.parse_args()

    if args.update:
        match_ids = get_match_ids()
        if match_ids:
            match_details = get_match_datas(match_ids)
            with open('match_details.json', 'w', encoding='utf-8') as f:
                json.dump(match_details, f, indent=2, ensure_ascii=False)
    
    get_user_stats()
