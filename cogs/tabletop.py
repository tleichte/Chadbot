from enum import Enum
from discord import app_commands, Interaction
from discord.ext.commands import Cog, Bot
from utils import utils
import random
import asyncio
import json

try:
    with open("configs/tabletop.json", 'r') as config_json:
        config = json.load(config_json)
except Exception as e:
    print(e)
    print("Failed to load tabletop cog! Config not found!")
    exit(-1)

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
        

    @app_commands.command(description="Rolls a die of a given side amount")
    @app_commands.rename(with_type="with")
    async def roll(self, interaction: Interaction, amount: app_commands.Range[int, 1, 1000], die_type : DiceType, modifier : int = 0, with_type : WithType = None):
        max_value: int = die_type.value
        base_value: int = 0
        outputs: list = []

        dice_str = f"{amount}d{max_value}{self.get_modifier_str(modifier)}{self.get_advantage_str(with_type)}"

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

    def get_emoji_str(self, die_type: DiceType):
        return config["dice_emojis"][f"{die_type.value}"]["normal"]

    def get_rolling_emoji_str(self, die_type: DiceType):
        return config["dice_emojis"][f"{die_type.value}"]["rolling"]

    def get_outputs_str(self, outputs: list):
        if len(outputs) == 1:
            return str(outputs[0])
        return str(outputs)

    def get_modifier_str(self, modifier:int):
        if (modifier != 0):
            operation_str = "+" if modifier > 0 else "-"
            return operation_str + str(abs(modifier))
        return ""

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

