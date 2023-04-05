from typing import List, Dict
import discord
from discord.ext.commands import Cog, Bot
import asyncio
from datetime import *
from utils import utils

poll_emojis = [
    "1️⃣",
    "2️⃣",
    "3️⃣",
    "4️⃣"
]

def format_emoji(index:int, str:str):
    return f"{poll_emojis[index]} {str}"

class Poll:
    
    def __init__(self, user:discord.User, header:str, options:List[str], end_timestamp : int):
        self._user : discord.User = user
        self._header : str = header
        self._options : List[str] = [option for option in options if len(option.split()) > 0]
        self._end_timestamp : int = end_timestamp
        self._user_votes : Dict[int,int] = {} # KVP: { user_id : int, option_index : int }
    
    def user_vote(self, user_id:int, option_index: int):
        self._user_votes[user_id] = option_index

    def is_done(self) -> bool:
        return utils.get_timestamp(utils.utcnow()) >= self._end_timestamp

    def get_message_content(self) -> str:
        if (self.is_done()):
            return f"{self._user.mention}'s poll has ended. Here are your results! (Total votes: {len(self._user_votes)})"
        return f"{self._user.mention} started a poll! Poll ends <t:{self._end_timestamp}:R>"

    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(title=self._header)
        total_votes = len(self._user_votes)

        is_done = self.is_done()

        num_votes_list = []
        num_winner_votes = 0

        if is_done:
            for i in range(len(self._options)):
                num_votes = sum(i == index for index in self._user_votes.values())
                num_votes_list.append(num_votes)
                num_winner_votes = max(num_winner_votes, num_votes)


        for i in range(len(self._options)):
            percent_str = ""

            if is_done:
                
                num_votes = num_votes_list[i]

                if total_votes > 0 and num_votes > 0:
                    percentage = round((float(num_votes) / total_votes) * 100)
                    percent_of_winner = float(num_votes) / num_winner_votes

                    for _ in range(round(percent_of_winner*30)):
                        percent_str += "\|"

                    percent_str += f"  {str(percentage)}% ({num_votes})"

                    if (num_votes == num_winner_votes):
                        percent_str = f"**{percent_str}**"
                else:
                    percent_str = "0%"

            option_str = format_emoji(i, self._options[i])

            embed.add_field(name=option_str, value=percent_str, inline=False)
        
        return embed

    def get_view(self) -> discord.ui.View:
        select = PollSelect(poll=self)
        for i in range(len(self._options)):
            select.add_option(label=self._options[i], value=f"{i}", emoji=poll_emojis[i])
        
        view = discord.ui.View(timeout=None).add_item(select)
        return view

    def print_results(self):
        print(f"Poll ended with {len(self._user_votes)} votes, results:")
        print(f"")
        for i in range(len(self._options)):
            num_votes = sum(i == index for index in self._user_votes.values())
            print(f"--({num_votes}) {self._options[i]}")
        



class PollSelect(discord.ui.Select):

    def __init__(self, poll : Poll):
        self._poll = poll
        super().__init__(placeholder="Select an option!")

    async def callback(self, interaction:discord.Interaction):
        if self._poll.is_done():
            return

        option_index = int(self.values[0])
        
        self._poll.user_vote(interaction.user.id, option_index)
        await utils.respond(interaction, f"Your vote for **{format_emoji(option_index, self.options[option_index].label)}** has been recorded!", ephemeral=True, delete_after=8)

class PollModal(discord.ui.Modal, title='Create a Poll!'):
    _headerInput = discord.ui.TextInput(label="Header", style=discord.TextStyle.paragraph, max_length=256)
    _option1Input = discord.ui.TextInput(label="Option 1", max_length=100)
    _option2Input = discord.ui.TextInput(label="Option 2", max_length=100)
    _option3Input = discord.ui.TextInput(label="Option 3", placeholder="(Optional)", required=False, max_length=100)
    _option4Input = discord.ui.TextInput(label="Option 4", placeholder="(Optional)", required=False, max_length=100)
    
    def set_exp_min(self, exp_min):
        self._exp_min : int = exp_min

    async def on_submit(self, interaction: discord.Interaction):
        options = [
            self._option1Input.value,
            self._option2Input.value,
            self._option3Input.value,
            self._option4Input.value
        ]
        
        await utils.respond(interaction, "Generating poll, standby...", ephemeral=True)

        timestamp = utils.get_timestamp(utils.utcnow() + timedelta(minutes=self._exp_min))
        poll = Poll(interaction.user, self._headerInput.value, options, timestamp)

        message : discord.Message = await interaction.channel.send(content=poll.get_message_content(), embed=poll.get_embed(), view=poll.get_view())

        original_response = await interaction.original_response()
        await original_response.delete()

        print(f"Poll created, num options: {len(poll._options)}")

        await asyncio.sleep(self._exp_min * 60)

        print(f"Poll expired, total votes: {len(poll._user_votes)}")

        channel = message.channel

        await message.delete()
        await channel.send(content=poll.get_message_content(), embed=poll.get_embed())

class PollCog(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @discord.app_commands.command(description="Brings up a popup to create a poll in the current channel.")
    @discord.app_commands.rename(exp_min="expires_after_minutes")
    @discord.app_commands.describe(exp_min="The number of minutes after the poll is created that responses will no longer be accepted")
    async def poll(self, interaction:discord.Interaction, exp_min:discord.app_commands.Range[int, 1, 180]):
        print("/poll used")
        modal = PollModal()
        modal.set_exp_min(exp_min)
        await interaction.response.send_modal(modal)


async def setup(bot : Bot):
    await bot.add_cog(PollCog(bot))