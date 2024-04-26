import discord
from discord.ext import commands
import asyncio
from datetime import datetime
from siegeapi import Auth
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
import dataframe_image as dfi
import io
import seaborn as sns
import matplotlib as mpl
import matplotlib.pyplot as plt
from typing import List
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from discord import File


# Define the intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

custom_palette = sns.color_palette("RdYlGn")


# Helper function to calculate score
def calculate_operator_score(operator, total_rounds_played):
    # Weights (these should be adjusted based on what you consider important)
    WEIGHT_KD_RATIO = 0.2
    WEIGHT_RWL = 3
    WEIGHT_ROUNDS_PLAYED = 0.075
    WEIGHT_ACES_PCT = 0.025
    WEIGHT_CLUTCHES_PCT = 0.025
    WEIGHT_HEADSHOT_ACC = 0.01
    WEIGHT_KOST = 0.01

    # Normalize the rounds played
    normalized_rounds_played = (operator.rounds_played / total_rounds_played) * 100 if total_rounds_played > 0 else 0
    #print(normalized_rounds_played)
    # Dynamically calculate K/D ratio
    k_d_ratio = operator.kills / operator.death if operator.death > 0 else operator.kills

    # Calculate win rate
    total_rounds = operator.rounds_won + operator.rounds_lost
    rwl = operator.rounds_won / total_rounds if total_rounds > 0 else 0

    # Calculate ACE's percentage and Clutches percentage
    aces_pct = ((operator.rounds_with_an_ace/100)*operator.rounds_played) if ((operator.rounds_with_an_ace/100)*operator.rounds_played) > 0 else 0
    clutches_pct = ((operator.rounds_with_clutch/100)*operator.rounds_played) if ((operator.rounds_with_clutch/100)*operator.rounds_played) > 0 else 0
    aces_pct = round(aces_pct)
    clutches_pct = round(clutches_pct)
    KOST = operator.rounds_with_kost

    # Calculate the score
    score = (k_d_ratio * WEIGHT_KD_RATIO) + \
            (rwl * WEIGHT_RWL) + \
            (normalized_rounds_played * WEIGHT_ROUNDS_PLAYED) + \
            (aces_pct * WEIGHT_ACES_PCT) + \
            (clutches_pct * WEIGHT_CLUTCHES_PCT) + \
            ((operator.headshot_accuracy if operator.headshot_accuracy < 100 else 0) * WEIGHT_HEADSHOT_ACC if operator.rounds_played > 10 else 0.025) + \
            ((KOST if KOST < 100 else 0) * WEIGHT_KOST if operator.rounds_played > 10 else 0.025)

    # Ensure the score is out of 100
    score = min(score, 100)
    return score





# Update find_top_operators to sort by score
def find_top_operators(operators, total_rounds_played, top_n=3):
    # Assuming eligible_operators and score calculations here...
    for operator in operators:
        operator.score = calculate_operator_score(operator, total_rounds_played)
    # Sort operators by score in descending order
    sorted_operators = sorted(operators, key=lambda op: op.score, reverse=True)
    return sorted_operators[:top_n]

# Update find_worst_operators similarly, but sort in ascending order
def find_worst_operators(operators, total_rounds_played, top_n=3):
    # Assuming eligible_operators and score calculations here...
    for operator in operators:
        operator.score = calculate_operator_score(operator, total_rounds_played)
    # Sort operators by score in ascending order
    sorted_operators = sorted(operators, key=lambda op: op.score)
    return sorted_operators[:top_n]






# Bot token from Discord Developer Portal
TOKEN = 'PUT YOUR TOKEN HERE'

# Create the bot with a command prefix of '/' and the specified intents
bot = commands.Bot(command_prefix='/', intents=intents, case_insensitive=True)

# Define startDate for the data
CurrentSeasonStart = "20240312"
theCurrentSeasonStart = "20231206"
startDateAllTime = "20230606"


def create_dataframe_from_operator_stats(operators, total_rounds_played):
    data = []
    for operator in operators:
        total_rounds = operator.rounds_played if operator.rounds_played > 0 else 1  # Avoid division by zero
        k_d_ratio = operator.kills / operator.death if operator.death > 0 else operator.kills
        rwl = operator.rounds_won / operator.rounds_lost if operator.rounds_lost > 0 else operator.rounds_won
        aces_pct = ((operator.rounds_with_an_ace/100)*operator.rounds_played) if ((operator.rounds_with_an_ace/100)*operator.rounds_played) > 0 else 0
        clutches_pct = ((operator.rounds_with_clutch/100)*operator.rounds_played) if ((operator.rounds_with_clutch/100)*operator.rounds_played) > 0 else 0
        aces_pct = round(aces_pct)
        clutches_pct = round(clutches_pct)
        headshot_acc = operator.headshot_accuracy # Convert to percentage
          # Include dynamically calculated K/D ratio
        score = calculate_operator_score(operator, total_rounds_played)
       
        data.append([operator.name, k_d_ratio, operator.rounds_played, rwl, operator.time_alive_per_match, operator.time_dead_per_match, aces_pct, clutches_pct, headshot_acc,operator.rounds_with_kost,score])
    
    df = pd.DataFrame(data, columns=[
        "Operator", "K/D Ratio", "Rounds Played", "RWL", "Time Alive", "Time Dead",
        "ACE's", "Clutches", "Headshot Acc.","KOST", "Score"
    ])
    # Sort the DataFrame by RWL in descending order
    df = df.sort_values(by="Score", ascending=False)
    
    # Adjust the index to start from 1 instead of 0
    df.index = range(1, len(df) + 1)
    
    
    return df


def style_dataframe(df):
    # Define custom colors for the gradient (from red to yellow to green)
    custom_colors = ['#F8696B', '#FFEF9C','#63BE7B']

    # Create a LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("custom_gradient", custom_colors)

    styled_df = df.style.background_gradient(
        subset=['K/D Ratio', 'Rounds Played', 'RWL', 'Time Alive', 'Time Dead', "ACE's", 'Clutches', 'Headshot Acc.', 'KOST'],
        cmap=cmap,  # Use the created colormap here
        axis=0
    ).format({
        'RWL': '{:.2f}',
        "ACE's": '{:.0f}',
        'Clutches': '{:.0f}',
        'Headshot Acc.': '{:.2f}%'
    }).set_properties(**{'text-align': 'center'})
    
    return styled_df


# The '/R6stats' command
@bot.command()
async def R6stats(ctx, username: str):
    auth = Auth("YourEmail", "YourPassword") # This should be your ubisoft email and password
    async def fetch_player_stats(playername):
        try:
            player = await auth.get_player(name=playername)
            today_date = datetime.now().strftime("%Y%m%d")
            print(today_date)
            player.set_timespan_dates(CurrentSeasonStart,today_date)
            await player.load_summaries() # Assuming this method fetches ranked profile info
            await player.load_operators()
            await player.load_maps()
            await player.load_ranked_v2()  # Assuming this method fetches ranked summary info

            # Calculate match accuracy
            TotalMatchesReal = player.ranked_profile.wins + player.ranked_profile.losses
            #Increment this for every season) SO 34 next
            try:
                matchesInSystem = player.ranked_summary[33]['Attacker'].matches_played
            except (KeyError, IndexError, TypeError):
                matchesInSystem = sum(op.matches_played for op in player.maps.ranked.attacker)
            
            print(sum(op.matches_played for op in player.operators.ranked.attacker))
            
            
            print(matchesInSystem)
            matchesInaccuracy = TotalMatchesReal - matchesInSystem

            # Send match accuracy message
            accuracy_message = f"**Match Accuracy for {playername}:**\n"
            accuracy_message += f"Total Matches Real: {TotalMatchesReal}\n"
            accuracy_message += f"Matches in System: {matchesInSystem}\n"
            accuracy_message += f"Matches Inaccuracy: {matchesInaccuracy}\n"
            await ctx.send(accuracy_message)
            await player.load_summaries()  # Load player summaries
            await player.load_operators()  # Load operator stats

            total_rounds_played_attack = sum(op.rounds_played for op in player.operators.ranked.attacker)
            total_rounds_played_defense = sum(op.rounds_played for op in player.operators.ranked.defender)
            total_rounds_played = total_rounds_played_attack + total_rounds_played_defense
            print(total_rounds_played_attack)
            attackers_df = create_dataframe_from_operator_stats(player.operators.ranked.attacker, total_rounds_played_attack)
            defenders_df = create_dataframe_from_operator_stats(player.operators.ranked.defender, total_rounds_played_defense)

        

            # Apply custom styling using the function 'style_dataframe'
            attackers_styled = style_dataframe(attackers_df)
            defenders_styled = style_dataframe(defenders_df)

            # Export the styled DataFrames to images
            dfi.export(attackers_styled, "attackers_stats.png")
            dfi.export(defenders_styled, "defenders_stats.png")

            # Now you can send the image in Discord or save it as needed
            # Example for sending in Discord
            attackers_df.to_excel("attackers_stats.xlsx", index=False)
            defenders_df.to_excel("defenders_stats.xlsx", index=False)

            await ctx.send(file=discord.File("attackers_stats.png"))
            await ctx.send(file=discord.File("defenders_stats.png"))
            await ctx.send(file=discord.File("attackers_stats.xlsx"))
            await ctx.send(file=discord.File("defenders_stats.xlsx"))

        except Exception as e:
            await ctx.send(f"Error fetching stats for {username}: {str(e)}")
        finally:
            await auth.close()

    await fetch_player_stats(username)


# The '/R6stats' command
@bot.command()
async def R6statsLife(ctx, username: str):
    auth = Auth("YourEmail", "YourPassword") # This should be your ubisoft email and password
    async def fetch_player_stats(playername):
        try:
            player = await auth.get_player(name=playername)
            today_date = datetime.now().strftime("%Y%m%d")
            print(today_date)
           
          
            player.set_timespan_dates("20231206",today_date)
            await player.load_summaries() # Assuming this method fetches ranked profile info
            await player.load_operators()
            await player.load_ranked_v2()  # Assuming this method fetches ranked summary info

            # Calculate match accuracy
            TotalMatchesReal = player.ranked_profile.wins + player.ranked_profile.losses
            print(TotalMatchesReal)
            matchesInSystem = player.ranked_summary[33]['Attacker'].matches_played
            print(matchesInSystem)
            matchesInaccuracy = TotalMatchesReal - matchesInSystem
            print("TEST")

            # Send match accuracy message
            accuracy_message = f"**Match Accuracy for {playername}:**\n"
            accuracy_message += f"Total Matches Real: {TotalMatchesReal}\n"
            accuracy_message += f"Matches in System: {matchesInSystem}\n"
            accuracy_message += f"Matches Inaccuracy: {matchesInaccuracy}\n"
            await ctx.send(accuracy_message)
            await player.load_summaries()  # Load player summaries
            await player.load_operators()  # Load operator stats

            total_rounds_played_attack = sum(op.rounds_played for op in player.operators.ranked.attacker)
            total_rounds_played_defense = sum(op.rounds_played for op in player.operators.ranked.defender)
            total_rounds_played = total_rounds_played_attack + total_rounds_played_defense
            print(total_rounds_played_attack)
            attackers_df = create_dataframe_from_operator_stats(player.operators.ranked.attacker, total_rounds_played_attack)
            defenders_df = create_dataframe_from_operator_stats(player.operators.ranked.defender, total_rounds_played_defense)

        

            # Apply custom styling using the function 'style_dataframe'
            attackers_styled = style_dataframe(attackers_df)
            defenders_styled = style_dataframe(defenders_df)

            # Export the styled DataFrames to images
            dfi.export(attackers_styled, "attackers_stats.png")
            dfi.export(defenders_styled, "defenders_stats.png")

            # Now you can send the image in Discord or save it as needed
            # Example for sending in Discord
            attackers_df.to_excel("attackers_stats.xlsx", index=False)
            defenders_df.to_excel("defenders_stats.xlsx", index=False)

            await ctx.send(file=discord.File("attackers_stats.png"))
            await ctx.send(file=discord.File("defenders_stats.png"))
            await ctx.send(file=discord.File("attackers_stats.xlsx"))
            await ctx.send(file=discord.File("defenders_stats.xlsx"))

        except Exception as e:
            await ctx.send(f"Error fetching stats for {username}: {str(e)}")
        finally:
            await auth.close()

    await fetch_player_stats(username)



###########################################################
    
def create_dataframe_from_map_stats(maps):
    data = []
    print(maps)
    for map_stat in maps:
        win_loss_ratio = map_stat.matches_won / float(map_stat.matches_played) if map_stat.matches_played > 0 else 0
        round_wl_ratio = map_stat.rounds_won / float(map_stat.rounds_won + map_stat.rounds_lost) if (map_stat.rounds_won + map_stat.rounds_lost) > 0 else 0
        kill_death_ratio = map_stat.kills / float(map_stat.death) if map_stat.death > 0 else map_stat.kills
        headshot_acc_percentage = (map_stat.headshots / float(map_stat.kills)) * 100 if map_stat.kills > 0 else 0
        kills_per_round = map_stat.kills / float(map_stat.rounds_played) if map_stat.rounds_played > 0 else 0
        time_alive_per_match = map_stat.time_alive_per_match  # Assuming this is already calculated
        time_dead_per_match = map_stat.time_dead_per_match  # Assuming this is already calculated

        data.append([
            map_stat.map_name, map_stat.matches_played, map_stat.rounds_played, map_stat.matches_won, map_stat.matches_lost, win_loss_ratio,
            map_stat.rounds_won, map_stat.rounds_lost, round_wl_ratio, map_stat.kills, map_stat.death, kill_death_ratio, map_stat.team_kills,
            map_stat.opening_kills, map_stat.opening_deaths, map_stat.trades, headshot_acc_percentage, kills_per_round,
            map_stat.rounds_with_a_kill, map_stat.rounds_with_multi_kill, 
            map_stat.rounds_with_kost, map_stat.rounds_survived, map_stat.rounds_with_an_ace, map_stat.rounds_with_clutch,
            time_alive_per_match, time_dead_per_match
        ])
    
    columns = [
        "Map Name", "Matches Played", "Rounds Played", "Matches Won", "Matches Lost", "MWL",
        "Rounds Won", "Rounds Lost", "RWL", "Kills", "Death", "K/D Ratio", "Team Kills",
        "Opening Kills", "Opening Deaths", "Trades", "Headshot Accuracy", "KPR",
        "Rounds with a Kill", "Multi-Kills",
        "KOST", "Rounds Survived", "ACE's", "Clutches",
        "Time Alive", "Time Dead"
    ]
    
    df = pd.DataFrame(data, columns=columns)
    df = df.sort_values(by='MWL', ascending=False)
    return df


def style_dataframe2(df):
    # Define custom colors for the gradient (from red to yellow to green)
    custom_colors = ['#F8696B', '#FFEF9C','#63BE7B']

    # Create a LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("custom_gradient", custom_colors)

    styled_df = df.style.background_gradient(
        subset=['Rounds Played', 'MWL', 'RWL', 'Time Alive', 'Time Dead', "ACE's", 'Clutches','KOST'],
        cmap=cmap,  # Use the created colormap here
        axis=0
    ).format({
        'MWL': '{:.2f}',
        'RWL': '{:.2f}',
        'MWL': '{:.2f}',
        "ACE's": '{:.0f}',
        'Clutches': '{:.0f}'
        
    }).set_properties(**{'text-align': 'center'})
    
    return styled_df

# The '/R6stats' command
@bot.command()
async def MapStats(ctx, username: str):
    auth = Auth("YourEmail", "YourPassword") # This should be your ubisoft email and password
    async def fetch_player_stats(playername):
        try:
            player = await auth.get_player(name=playername)
            today_date = datetime.now().strftime("%Y%m%d")
            print(today_date)
            player.set_timespan_dates(CurrentSeasonStart,today_date)
            await player.load_summaries() # Assuming this method fetches ranked profile info
            await player.load_operators()
            await player.load_maps()  # Assuming this method fetches ranked summary info

            

           
            await player.load_summaries()  # Load player summaries
            await player.load_operators()  # Load operator stats

            
            attackers_df = create_dataframe_from_map_stats(player.maps.ranked.attacker)
            defenders_df = create_dataframe_from_map_stats(player.maps.ranked.defender)

        

            # Apply custom styling using the function 'style_dataframe'
            attackers_styled = style_dataframe2(attackers_df)
            defenders_styled = style_dataframe2(defenders_df)

            # Export the styled DataFrames to images
            dfi.export(attackers_styled, "attackers_stats.png")
            dfi.export(defenders_styled, "defenders_stats.png")

            # Now you can send the image in Discord or save it as needed
            # Example for sending in Discord
            attackers_df.to_excel("attackers_stats.xlsx", index=False)
            defenders_df.to_excel("defenders_stats.xlsx", index=False)
            await ctx.send("ATTACKER")
            await ctx.send(file=discord.File("attackers_stats.png"))
            await ctx.send("DEFENDER")
            await ctx.send(file=discord.File("defenders_stats.png"))
            await ctx.send(file=discord.File("attackers_stats.xlsx"))
            await ctx.send(file=discord.File("defenders_stats.xlsx"))

        except Exception as e:
            await ctx.send(f"Error fetching stats for {username}: {str(e)}")
        finally:
            await auth.close()

    await fetch_player_stats(username)

###############################################################################

# The '/R6stats' command
@bot.command()
async def PlayerStats(ctx, username: str):
    auth = Auth("YourEmail", "YourPassword") # This should be your ubisoft email and password
    async def fetch_player_stats(playername):
        try:
            player = await auth.get_player(name=playername)
            today_date = datetime.now().strftime("%Y%m%d")
            print(today_date)
            player.set_timespan_dates(CurrentSeasonStart,today_date)
            await player.load_summaries() # Assuming this method fetches ranked profile info
            await player.load_operators()
            await player.load_ranked_v2()  # Assuming this method fetches ranked summary info
            await player.load_playtime()

            await player.load_summaries() # Assuming this method fetches ranked profile info
            await player.load_operators()
            await player.load_maps()
            await player.load_ranked_v2()  # Assuming this method fetches ranked summary info

            
            #Increment this for every season) SO 34 next
            try:
                matchesInSystem = player.ranked_summary[33]['Attacker'].matches_played
            except (KeyError, IndexError, TypeError):
                matchesInSystem = sum(op.matches_played for op in player.maps.ranked.attacker)
            
            print(sum(op.matches_played for op in player.operators.ranked.attacker))

            # Calculate match accuracy
            TotalMatchesReal = player.ranked_profile.wins + player.ranked_profile.losses
           
            matchesInaccuracy = TotalMatchesReal - matchesInSystem
            print("TEST")

            # Send match accuracy message
            accuracy_message = f"**Match Accuracy for {playername}:**\n"
            accuracy_message += f"Total Matches Real: {TotalMatchesReal}\n"
            accuracy_message += f"Matches in System: {matchesInSystem}\n"
            accuracy_message += f"Matches Inaccuracy: {matchesInaccuracy}\n"
            await ctx.send(accuracy_message)
            await player.load_summaries()  # Load player summaries
            await player.load_operators()  # Load operator stats

            total_rounds_played_attack = sum(op.rounds_played for op in player.operators.ranked.attacker)
            total_rounds_played_defense = sum(op.rounds_played for op in player.operators.ranked.defender)
            # Initialize the counter
            num = 0

            # Iterate over the attackers and increment the counter based on a condition
            for op in player.operators.ranked.attacker:
                if op.name!="":  # Replace some_condition(op) with your actual condition
                    num += 1

            print(f"Number of Attacker Operators meeting the condition: {num}")

            attackKOST = sum(op.rounds_with_kost for op in player.operators.ranked.attacker)/num
            total_kills = 0
            for op in player.operators.ranked.attacker:
                print(op.kills)
                total_kills = total_kills + op.kills
            print("TOTAL KILLS")
            print(total_kills)

            # Calculate total deaths, defaulting to 0 if the attribute doesn't exist or if deaths are 0
            total_deaths = 0
            for op in player.operators.ranked.attacker:
               
                if op.death >= 0:
                    print(op.death)
                    total_deaths = total_deaths + op.death
                    print("TOTAL DEATHS")
                    print(total_deaths)
                else:
                    print(op.name)
                    print("BAD DEATH")

            # Calculate the KD ratio, handling the case where total deaths is 0 to avoid division by zero
            attackKD = total_kills / total_deaths if total_deaths > 0 else 0
            print(attackKD)

           


            num = 0

            # Iterate over the attackers and increment the counter based on a condition
            for op in player.operators.ranked.defender:
                if op.name!="":  # Replace some_condition(op) with your actual condition
                    num += 1
            defenseKOST = sum(op.rounds_with_kost for op in player.operators.ranked.defender)/num
            # Calculate total kills, defaulting to 0 if the attribute doesn't exist
            total_kills = 0
            for op in player.operators.ranked.defender:
                print(op.kills)
                total_kills = total_kills + op.kills
            print("TOTAL KILLS")
            print(total_kills)

            # Calculate total deaths, defaulting to 0 if the attribute doesn't exist or if deaths are 0
            total_deaths = 0
            for op in player.operators.ranked.defender:
               
                if op.death >= 0:
                    print(op.death)
                    total_deaths = total_deaths + op.death
                    print("TOTAL DEATHS")
                    print(total_deaths)
                else:
                    print(op.name)
                    print("BAD DEATH")

            # Calculate the KD ratio, handling the case where total deaths is 0 to avoid division by zero
            defenseKD = total_kills / total_deaths if total_deaths > 0 else 0
            print(defenseKD)


            


            total_rounds_played = total_rounds_played_attack + total_rounds_played_defense
            print(total_rounds_played_attack)
            print("AVERAGE KOST Attack / Defense")
            print(attackKOST)
            print(defenseKOST)
            defenseKOST_message = f"DefenseKOST: {defenseKOST}\n"
            attackKOST_message = f"AttackKOST: {attackKOST}\n"
            defenseKD_message = f"DefenseKD: {defenseKD}\n"
            attackKD_message = f"AttackKD: {attackKD}\n"
            playtime = player.total_time_played/60/60
            await ctx.send(f"Total Time Played: {playtime:,} Hours")
            await ctx.send(f"Level: {player.level}")
            await ctx.send(f"Rank: {player.ranked_profile.rank}")
            await ctx.send(attackKOST_message)
            await ctx.send(defenseKOST_message)
            await ctx.send(attackKD_message)
            await ctx.send(defenseKD_message)

        



        except Exception as e:
            await ctx.send(f"Error fetching stats for {username}: {str(e)}")
        finally:
            await auth.close()

    await fetch_player_stats(username)

@bot.command()
async def TopOps(ctx, *, usernames: str):
    auth = Auth("YourEmail", "YourPassword") # This should be your ubisoft email and password  # Use real credentials
    usernames_list = usernames.split(',')  # Split the input string into a list of usernames

    for username in usernames_list:
        username = username.strip()  # Trim whitespace
        try:
            player = await auth.get_player(name=username)
            today_date = datetime.now().strftime("%Y%m%d")
            print(today_date)
            player.set_timespan_dates(CurrentSeasonStart,today_date)
            await player.load_operators()  # Assuming this loads all operators' data

            total_rounds_played_attack = sum(op.rounds_played for op in player.operators.ranked.attacker)
            total_rounds_played_defense = sum(op.rounds_played for op in player.operators.ranked.defender)
            total_rounds_played = total_rounds_played_attack + total_rounds_played_defense
            print(total_rounds_played_attack)
            
            
            # Update function calls with total rounds played
            top_attackers = find_top_operators(player.operators.ranked.attacker, total_rounds_played_attack)
            top_defenders = find_top_operators(player.operators.ranked.defender, total_rounds_played_defense)

            # Construct and send the message with top ops information in a side-by-side format
            message = f"**Top Operators for {username}:**\n```\n"
            message += f"{'Attacker':<25}Defenders\n"
            for i in range(max(len(top_attackers), len(top_defenders))):
                attacker_name = top_attackers[i].name if i < len(top_attackers) else ""
                defender_name = top_defenders[i].name if i < len(top_defenders) else ""
                message += f"{i+1}. {attacker_name:<23}{i+1}. {defender_name}\n"
            message += "```"
            await ctx.send(message)

        except Exception as e:
            await ctx.send(f"Error fetching top operators for {username}: {str(e)}")


@bot.command()
async def WorstOps(ctx, *, usernames: str):
    auth = Auth("YourEmail", "YourPassword") # This should be your ubisoft email and password  # Use real credentials
    usernames_list = usernames.split(',')  # Split the input string into a list of usernames

    for username in usernames_list:
        username = username.strip()  # Trim whitespace
        try:
            player = await auth.get_player(name=username)
            today_date = datetime.now().strftime("%Y%m%d")
            print(today_date)
            player.set_timespan_dates(CurrentSeasonStart,today_date)
            await player.load_operators()  # Assuming this loads all operators' data

            total_rounds_played_attack = sum(op.rounds_played for op in player.operators.ranked.attacker)
            total_rounds_played_defense = sum(op.rounds_played for op in player.operators.ranked.defender)
            
            # Update function calls with total rounds played
            top_attackers = find_worst_operators(player.operators.ranked.attacker, total_rounds_played_attack)
            top_defenders = find_worst_operators(player.operators.ranked.defender, total_rounds_played_defense)
           

            # Construct and send the message with top ops information in a side-by-side format
            message = f"**Worst Operators for {username}:**\n```\n"
            message += f"{'Attacker':<25}Defenders\n"
            for i in range(max(len(top_attackers), len(top_defenders))):
                attacker_name = top_attackers[i].name if i < len(top_attackers) else ""
                defender_name = top_defenders[i].name if i < len(top_defenders) else ""
                message += f"{i+1}. {attacker_name:<23}{i+1}. {defender_name}\n"
            message += "```"
            await ctx.send(message)

        except Exception as e:
            await ctx.send(f"Error fetching top operators for {username}: {str(e)}")

@bot.command()
async def TopMaps(ctx, username: str):
    auth = Auth("YourEmail", "YourPassword") # This should be your ubisoft email and password  # Use real credentials
    try:
        player = await auth.get_player(name=username)
        today_date = datetime.now().strftime("%Y%m%d")
        print(today_date)
        player.set_timespan_dates(CurrentSeasonStart,today_date)
        await player.load_maps()  # Assuming this method populates map data for both roles

        # Combine defender and attacker map data
        combined_maps_data = {}
        for role in ['defender', 'attacker']:
            for map_stat in getattr(player.maps.ranked, role):
                if map_stat.map_name not in combined_maps_data:
                    combined_maps_data[map_stat.map_name] = {
                        'matches_won': 0,
                        'matches_lost': 0,
                        'map_name': map_stat.map_name
                    }
                combined_maps_data[map_stat.map_name]['matches_won'] += map_stat.matches_won
                combined_maps_data[map_stat.map_name]['matches_lost'] += map_stat.matches_lost

        # Convert combined data to a list and sort by win-loss ratio
        combined_maps_list = list(combined_maps_data.values())
        ranked_maps = sorted(combined_maps_list, key=lambda m: (m['matches_won'] / (m['matches_lost'] if m['matches_lost'] > 0 else 1)), reverse=True)

        message = f"**Top Ranked Maps for {username} (Combined Defender and Attacker):**\n```\n"
        for map_stat in ranked_maps:
            win_loss_ratio = map_stat['matches_won'] / (map_stat['matches_lost'] if map_stat['matches_lost'] > 0 else 1)
            message += f"{map_stat['map_name']}: W/L Ratio: {win_loss_ratio:.2f}\n"
        message += "```"
        await ctx.send(message)
    except Exception as e:
        await ctx.send(f"Error fetching top ranked maps for {username}: {str(e)}")
    finally:
        await auth.close()

@bot.command()
async def MapsToBan(ctx, *, usernames: str):
    auth = Auth("YourEmail", "YourPassword") # This should be your ubisoft email and password  # Use real credentials
    usernames_list = usernames.split(',')  # Split the input string into a list of usernames
    combined_maps_data = {}

    try:
        for username in usernames_list:
            username = username.strip()  # Trim whitespace
            try:
                player = await auth.get_player(name=username)
                today_date = datetime.now().strftime("%Y%m%d")
                print(today_date)
                player.set_timespan_dates(CurrentSeasonStart, today_date)
                await player.load_maps()  # Load map statistics for both roles

                # Aggregate map data for both defender and attacker roles
                for role in ['defender', 'attacker']:
                    for map_stat in getattr(player.maps.ranked, role):
                        map_key = map_stat.map_name
                        if map_key not in combined_maps_data:
                            combined_maps_data[map_key] = {
                                'matches_won': 0,
                                'matches_lost': 0,
                                'matches_played': 0,  # Initialize matches played
                                'map_name': map_key
                            }
                        combined_maps_data[map_key]['matches_won'] += map_stat.matches_won
                        combined_maps_data[map_key]['matches_lost'] += map_stat.matches_lost
                        combined_maps_data[map_key]['matches_played'] += map_stat.matches_played  # Aggregate matches played

            except Exception as e:
                await ctx.send(f"Error fetching maps data for {username}: {str(e)}")

        # Convert combined data to a list and sort by win-loss ratio (lowest first)
        combined_maps_list = list(combined_maps_data.values())
        ranked_maps = sorted(combined_maps_list, key=lambda m: (m['matches_won'] / (m['matches_lost'] if m['matches_lost'] > 0 else 1)))

        # Construct and send the message
        message = "**Maps to Ban (Based on Combined W/L Ratios):**\n"
        for map_stat in ranked_maps:  # Limit to worst 5 maps
            win_loss_ratio = map_stat['matches_won'] / (map_stat['matches_won'] + (map_stat['matches_lost'] if map_stat['matches_lost'] > 0 else 1))
            matches_played = map_stat['matches_played']
            message += f"{map_stat['map_name']}: {win_loss_ratio:.2f} Win/Loss, Matches Played: {matches_played}\n"
        await ctx.send(message)

    finally:
        await auth.close()







@bot.command()
async def AllPlayerStats(ctx):
    
    # Predefined list of usernames
    usernames = ["Chromius.TAMU", "Glonk..", "Glonk.MB","ThiccPie.OU","Fallen.Rqnger","Strugg1er.","Timythiccums.MB","Boomerjet123","Coolrocket.TAMU","Galahad21588","Fallen.Cortex","Dlehard.","Nobetterdough","Blade2420","Rat_Squilla","Colonizer.BU","NotLappland","Koyeetchi","Kermitt.MB","mason10_10","Strix.BBy","PincheConcha","JoeHashish.TAMU","Polar...-","lostarkwhale","catsanddog123","Asherzs","Pathos-val","Killmer.LAT","veists.","tEXAG21","Ronc.-","Solias","Jamato33","Scamped.","AkusNightmare","Wisesteyes","Elyidian","AdmiralBofa","EasterBallz--","Wh1pl4sh_117","HostMal0ne"]  # Update this with actual usernames
    
    # Placeholder for player stats
    player_stats_list = []
    
    for username in usernames:
        player_stats = await fetch_player_stats_for_excel(username)
        if player_stats:
            player_stats_list.append(player_stats)
    
    # Convert the list of dictionaries to a pandas DataFrame
    df = pd.DataFrame(player_stats_list)
    
    # Define your Excel file name
    excel_filename = "player_stats.xlsx"
    df.to_excel(excel_filename, index=False)
    
    # Send the Excel file
    await ctx.send(file=File(excel_filename))

async def fetch_player_stats_for_excel(username):
    try:
        auth = Auth("YourEmail", "YourPassword") # This should be your ubisoft email and password
        player = await auth.get_player(name=username)
        today_date = datetime.now().strftime("%Y%m%d")
        player.set_timespan_dates(CurrentSeasonStart, today_date)
        await player.load_operators()
        await player.load_ranked_v2()
        
        # Aggregate the data needed for the Excel file here
        # Example structure, fill in with actual logic to fetch these values
        total_rounds_played_attack = sum(op.rounds_played for op in player.operators.ranked.attacker)
        total_rounds_played_defense = sum(op.rounds_played for op in player.operators.ranked.defender)
        # Initialize the counter
        num = 0

        # Iterate over the attackers and increment the counter based on a condition
        for op in player.operators.ranked.attacker:
            if op.name!="":  # Replace some_condition(op) with your actual condition
                num += 1

        print(f"Number of Attacker Operators meeting the condition: {num}")

        attackKOST = sum(op.rounds_with_kost for op in player.operators.ranked.attacker)/num
        total_kills = 0
        for op in player.operators.ranked.attacker:
            print(op.kills)
            total_kills = total_kills + op.kills
        print("TOTAL KILLS")
        print(total_kills)

        # Calculate total deaths, defaulting to 0 if the attribute doesn't exist or if deaths are 0
        total_deaths = 0
        for op in player.operators.ranked.attacker:
            
            if op.death >= 0:
                print(op.death)
                total_deaths = total_deaths + op.death
                print("TOTAL DEATHS")
                print(total_deaths)
            else:
                print(op.name)
                print("BAD DEATH")

        # Calculate the KD ratio, handling the case where total deaths is 0 to avoid division by zero
        attackKD = total_kills / total_deaths if total_deaths > 0 else 0
        print(attackKD)

        


        num = 0

        # Iterate over the attackers and increment the counter based on a condition
        for op in player.operators.ranked.defender:
            if op.name!="":  # Replace some_condition(op) with your actual condition
                num += 1
        defenseKOST = sum(op.rounds_with_kost for op in player.operators.ranked.defender)/num
        # Calculate total kills, defaulting to 0 if the attribute doesn't exist
        total_kills = 0
        for op in player.operators.ranked.defender:
            print(op.kills)
            total_kills = total_kills + op.kills
        print("TOTAL KILLS")
        print(total_kills)

        # Calculate total deaths, defaulting to 0 if the attribute doesn't exist or if deaths are 0
        total_deaths = 0
        for op in player.operators.ranked.defender:
            
            if op.death >= 0:
                print(op.death)
                total_deaths = total_deaths + op.death
                print("TOTAL DEATHS")
                print(total_deaths)
            else:
                print(op.name)
                print("BAD DEATH")


            # Calculate the KD ratio, handling the case where total deaths is 0 to avoid division by zero
            defenseKD = total_kills / total_deaths if total_deaths > 0 else 0
            print(defenseKD)


        # Calculate the KD ratio, handling the case where total deaths is 0 to avoid division by zero
        defenseKD = total_kills / total_deaths if total_deaths > 0 else 0
        print(defenseKD)
        player_stats = {
            "Player": username,
            "Attack K/D": attackKD,
            "Defense K/D": defenseKD,
            "Attack Wins": sum(op.rounds_won for op in player.operators.ranked.attacker),
            "Attack Losses": sum(op.rounds_lost for op in player.operators.ranked.attacker),
            "Defense Wins": sum(op.rounds_won for op in player.operators.ranked.defender),
            "Defense Losses": sum(op.rounds_lost for op in player.operators.ranked.defender),
            "Attack KOST": attackKOST,
            "Defense KOST": defenseKOST,
            "Ranked Wins": player.ranked_profile.wins,
            "Ranked Losses": player.ranked_profile.losses,
        }
        return player_stats
    except Exception as e:
        print(f"Error fetching stats for {username}: {str(e)}")
        return None

# Start the bot with your Discord token
bot.run(TOKEN)
