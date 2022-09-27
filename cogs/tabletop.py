from enum import Enum
from discord import app_commands, Interaction
from discord.ext.commands import Cog, Bot
from utils import utils
import random
import asyncio

class DiceType(Enum):
    d4 = 4
    d6 = 6
    d8 = 8
    d10 = 10
    d12 = 12
    d20 = 20
    d100 = 100

class Modifier(Enum):
    Normal = 0
    Advantage = 1
    Disadvantage = 2

class TabletopCog(Cog):
    def __init__(self, init_bot: Bot):
        self.bot = init_bot
        

    @app_commands.command(description="Rolls a die of a given side amount")
    async def roll(self, interaction: Interaction, amount: app_commands.Range[int, 1, 100], die_type : DiceType, plus : int = 0, modifier : Modifier = Modifier.Normal):
        max_value: int = die_type.value
        base_value: int = 0
        outputs: list = []
        await utils.respond(interaction, f"Rolling {amount}d{max_value}...")
        
        for _ in range(0, amount):
            rnd_value = self.do_roll(die_type)
            if modifier != Modifier.Normal:
                second_value = self.do_roll(die_type)
                outputs.append((rnd_value, second_value))
                if modifier == Modifier.Advantage:
                    base_value += max(rnd_value, second_value)
                else:
                    base_value += min(rnd_value, second_value)
            else:
                base_value += rnd_value
                outputs.append(rnd_value)

        sleep_time = random.uniform(0.5, 1.5)
        await asyncio.sleep(sleep_time)


        def get_outputs_str():
            if len(outputs) == 1:
                return str(outputs[0])
            return str(outputs)
        
        if die_type == DiceType.d20 and amount == 1:
            out_str = ""
            if modifier != Modifier.Normal:
                out_str = f"\n`Rolls: {get_outputs_str()}`"

            if base_value == 1:
                await utils.respond(interaction, f"*Natural 1...* :pensive: {out_str}")
                return
            elif base_value == 20:
                await utils.respond(interaction, f"**NATURAL 20**! :tada: {out_str}")
                return
        
        total_value = base_value + plus

        out_str = ""
        if (amount > 1 or modifier != Modifier.Normal) and amount < 10:
            out_str = f"\n`Rolls: {get_outputs_str()}`"

        plus_str = ""
        if plus > 0:
            plus_str = f" ({base_value}+{plus})"

        await utils.respond(interaction, f"{amount}d{max_value} ⟶ Rolled **{total_value}**{plus_str} {out_str}")

    def do_roll(self, die_type: DiceType) -> int:
        max_value : int = die_type.value
        rnd_value : int = random.randint(1, max_value)
        return rnd_value


async def setup(bot : Bot):
    await bot.add_cog(TabletopCog(bot))

