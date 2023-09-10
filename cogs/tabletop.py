from enum import Enum
import discord
from discord import app_commands, Interaction
from discord.ext.commands import Cog, Bot
from utils import utils, db
from typing import Dict
import random
import asyncio
import json
import sqlite3
import os

try:
    with open("configs/tabletop.json", 'r') as config_json:
        config = json.load(config_json)
except Exception as e:
    utils.log("TABLETOP", e)
    utils.log("TABLETOP", "Failed to load tabletop cog! Config not found!")
    exit(-1)

db_folder_path = "data/tabletop"
db_path = "data/tabletop/abilities.db"
if not os.path.exists(db_folder_path):
    os.makedirs(db_folder_path)

connection : sqlite3.Connection = sqlite3.connect(db_path)

db.execute_command(connection, """
    CREATE TABLE IF NOT EXISTS "ability_scores" (
        user_id INTEGER,
        str INTEGER,
        dex INTEGER,
        con INTEGER,
        int INTEGER,
        wis INTEGER,
        cha INTEGER,
        PRIMARY KEY("user_id")
    )
""")

class Ability(Enum):
    Strength = "str"
    Dexterity = "dex"
    Constitution = "con"
    Intelligence = "int"
    Wisdom = "wis"
    Charisma = "cha"

class QuipLevel(Enum):
    MAX_POS = "MAX_POS"
    HIGH_POS = "HIGH_POS"
    POS = "POS"
    MID = "MID"
    NEG = "NEG"
    HIGH_NEG = "HIGH_NEG"
    MAX_NEG = "MAX_NEG"

class DiceType(Enum):
    d4 = 4
    d6 = 6
    d8 = 8
    d10 = 10
    d12 = 12
    d20 = 20
    d100 = 100

class WithType(Enum):
    Advantage = 1
    Disadvantage = 2

class TabletopCog(Cog):
    def __init__(self, init_bot: Bot):
        self.bot = init_bot
        

    @app_commands.command(description="Rolls a die")
    @app_commands.rename(with_type="with")
    @app_commands.describe(
        amount="Number of dice to roll",
        die_type="Type of die",
        modifier="Adjustment after rolling (accepts both positive/negative numbers)",
        with_type="Whether to roll with advantage or disadvantage"
    )
    async def roll(self, interaction: Interaction, amount: app_commands.Range[int, 1, 1000], die_type : DiceType, modifier : int = 0, with_type : WithType = None):
        await self.inner_do_roll(interaction, amount, die_type, modifier, with_type)

    @app_commands.command(description="Flips a coin")
    async def flip(self, interaction: Interaction):
        await utils.respond(interaction, f"{config['coin_emojis']['flipping']}")
        await asyncio.sleep(random.uniform(0.5, 1.5))
        side: bool = random.randint(0, 500) == 0
        emoji_str = ""
        if side:
            emoji_str = config["coin_emojis"]["side"]
        else:
            heads: bool = random.randint(0, 1) == 0
            emoji_str = config["coin_emojis"]["heads" if heads else "tails"]
        await utils.respond(interaction, f"{emoji_str}")


    @app_commands.command(description="Rolls a D&D style ability check")
    @app_commands.rename(with_type="with")
    @app_commands.describe(
        ability="The ability to check",
        with_type="Whether to roll with advantage or disadvantage"
    )
    async def roll_ability(self, interaction: Interaction, ability: Ability, with_type : WithType = None):
        modifier = db.get_single_value(connection, f"""
            SELECT
                {ability.value}
            FROM
                ability_scores
            WHERE
                user_id = ?
        """, (interaction.user.id,))
        
        if modifier is None:
            modifier = 0
        
        await self.inner_do_roll(interaction, 1, DiceType.d20, modifier, with_type, ability)


    @app_commands.command(description="Sets one of your ability modifiers")
    @app_commands.describe(
        ability="The ability to modify",
        modifier="A number between -5 to 5"
    )
    async def set_ability_modifier(self, interaction: Interaction, ability: Ability, modifier: app_commands.Range[int, -5,5]):
        self.try_add_initial_modifier(interaction.user.id)
        db.execute_command(connection, f"""
            UPDATE 
                ability_scores
            SET
                {ability.value} = ?
            WHERE
                user_id = ?
        """, (modifier, interaction.user.id))

        flavor_text : str = self.get_flavor_for_value(ability, modifier)
        await utils.respond(interaction, f"Set your **{ability.value.upper()}** modifier to **{self.format_modifier(modifier)}**.\n{flavor_text}", ephemeral=True)

    @app_commands.command(description="Allows you to set all of your ability modifiers at once")
    @app_commands.describe(
        str="Strength",
        dex="Dexterity",
        con="Constitution",
        int="Intelligence",
        wis="Wisdom",
        cha="Charisma",
    )
    async def set_ability_modifiers(self, interaction: Interaction, 
                                    str: app_commands.Range[int, -5, 5],
                                    dex: app_commands.Range[int, -5, 5],
                                    con: app_commands.Range[int, -5, 5],
                                    int: app_commands.Range[int, -5, 5],
                                    wis: app_commands.Range[int, -5, 5],
                                    cha: app_commands.Range[int, -5, 5]):
        db.execute_command(connection, """
            INSERT OR REPLACE INTO ability_scores
                (user_id, str, dex, con, int, wis, cha)
                VALUES(?,?,?,?,?,?,?)
        """, (interaction.user.id, str, dex, con, int, wis, cha))

        await utils.respond(interaction, f"Set your ability modifiers to the following:\n{self.format_ability_scores(str,dex,con,int,wis,cha)}", ephemeral=True)


    @app_commands.command(description="Displays the ability modifiers for a given member. If none is provided, it will show yours.")
    @app_commands.describe(
        member="The member's ability scores to display"
    )
    async def show_ability_modifiers(self, interaction:Interaction, member:discord.Member = None):

        if member is not None:
            if member.id == self.bot.user.id:
                await utils.respond(interaction, "The only ability modifier I have is a +5 in BOT  😎")
                return
            if member.bot:
                await utils.respond(interaction, f"**{member.display_name}'s** only ability modifier would probably be a +2 in BOT  🤖")
                return

        user_id = interaction.user.id
        display_name = interaction.user.display_name
        if (member is not None):
            user_id = member.id
            display_name = member.display_name
        
        row_data = db.get_single_row(connection, """
            SELECT
                str, dex, con, int, wis, cha
            FROM
                ability_scores
            WHERE   
                user_id = ?
            
        """, (user_id,))

        if row_data is None:
            row_data = [ 0, 0, 0, 0, 0, 0 ]

        await utils.respond(interaction, 
                      f"**{display_name}'s** Ability Modifiers:\n{self.format_ability_scores(row_data[0], row_data[1], row_data[2], row_data[3], row_data[4], row_data[5])}")

    
    def format_modifier(self, modifier:int) -> str:
        if modifier > 0:
            return f"+{modifier}"
        return f"{modifier}"

    def get_flavor_for_value(self,ability:str, modifier: int):
        flavor_texts = config["ability_flavor_text"][ability.value]
        if modifier >= 5:
            return flavor_texts["MAX_POS"]
        if modifier >= 3:
            return flavor_texts["HIGH_POS"]
        if modifier >= 1:
            return flavor_texts["POS"]
        if modifier <= -5:
            return flavor_texts["MAX_NEG"]
        if modifier <= -3:
            return flavor_texts["HIGH_NEG"]
        if modifier <= -1:
            return flavor_texts["NEG"]
        return flavor_texts["MID"]


    async def inner_do_roll(self, interaction: Interaction, amount: app_commands.Range[int, 1, 1000], die_type : DiceType, modifier : int, with_type : WithType, ability:Ability = None):
        max_value: int = die_type.value
        base_value: int = 0
        outputs: list = []

        dice_str = f"{amount}d{max_value}{self.get_modifier_str(modifier, ability)}{self.get_advantage_str(with_type)}"

        await utils.respond(interaction, f"{self.get_rolling_emoji_str(die_type)} Rolling `{dice_str}`...")
        
        for _ in range(0, amount):
            rnd_value = self.do_roll(die_type)
            if with_type != None:
                second_value = self.do_roll(die_type)
                outputs.append((rnd_value, second_value))
                if with_type == WithType.Advantage:
                    base_value += max(rnd_value, second_value)
                else:
                    base_value += min(rnd_value, second_value)
            else:
                base_value += rnd_value
                outputs.append(rnd_value)

        sleep_time = random.uniform(0.5, 1.5)
        await asyncio.sleep(sleep_time)


        total_value = base_value + modifier
        
        outputs_str = ""
        if (amount > 1 or with_type != None) and amount <= 10:
            outputs_str = f"\n`Rolls: {self.get_outputs_str(outputs)}`"

        plus_str = ""
        if modifier != 0:
            plus_str = f"({base_value}{self.get_modifier_str(modifier)})"

        prefix_str = ""
        dirty_str = ""
        if die_type == DiceType.d20 and amount == 1:
            if base_value == 1:
                prefix_str = "*Natural 1...* :pensive:\n"
            
            if base_value == 20:
                prefix_str = "**NATURAL 20**! :tada:\n"
            elif total_value == 20:
                dirty_str = "a dirty "


        await utils.respond(interaction, f"{prefix_str}{self.get_emoji_str(die_type)}`{dice_str}` ⟶ Rolled {dirty_str}**{total_value}** {plus_str} {outputs_str}")

    def try_add_initial_modifier(self, user_id: int):
        db.execute_command(connection, """
            INSERT OR IGNORE INTO ability_scores
                (user_id, str, dex, con, int, wis, cha) 
                VALUES(?,0,0,0,0,0,0)
        """, (user_id,))

    def format_ability_scores(self, str:str, dex:str, con:str, int:str, wis:str, cha:str) -> str:
        return f"STR: {self.format_modifier(str)}\nDEX: {self.format_modifier(dex)}\nCON: {self.format_modifier(con)}\nINT: {self.format_modifier(int)}\nWIS: {self.format_modifier(wis)}\nCHA: {self.format_modifier(cha)}"

    def get_emoji_str(self, die_type: DiceType):
        return config["dice_emojis"][f"{die_type.value}"]["normal"]

    def get_rolling_emoji_str(self, die_type: DiceType):
        return config["dice_emojis"][f"{die_type.value}"]["rolling"]

    def get_outputs_str(self, outputs: list):
        if len(outputs) == 1:
            return str(outputs[0])
        return str(outputs)

    def get_modifier_str(self, modifier:int, ability:Ability=None):
        ability_str = ""
        if ability is not None:
            ability_str = f"[{ability.value.upper()}]"

        if modifier == 0:
            return f"+0{ability_str}" if ability is not None else ""
        
    
        operation_str = "+" if modifier > 0 else "-"
        return f"{operation_str}{str(abs(modifier))}{ability_str}"
    

    def get_advantage_str(self, with_type: WithType):
        if with_type == WithType.Advantage:
            return "(Adv)"
        if with_type == WithType.Disadvantage:
            return "(Dis)"
        return ""

    def do_roll(self, die_type: DiceType) -> int:
        max_value : int = die_type.value
        rnd_value : int = random.randint(1, max_value)
        return rnd_value


async def setup(bot : Bot):
    await bot.add_cog(TabletopCog(bot))

